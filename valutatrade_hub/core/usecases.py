"""Бизнес-операции приложения, независимые от консольного интерфейса."""

from dataclasses import dataclass

from valutatrade_hub.core.exceptions import (
    AuthenticationError,
    CurrencyNotFoundError,
    DataStorageError,
    InsufficientFundsError,
    ValidationError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    RateQuote,
    RateService,
    RatesView,
    validate_number,
    validate_username,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.updater import UpdateResult, create_updater


@dataclass(frozen=True)
class PortfolioView:
    """Данные для отображения портфеля без доступа CLI к хранилищу."""

    username: str
    base: str
    rows: list[tuple[str, float, float]]
    total: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class TradeResult:
    """Результат сделки с оценкой в USD и изменением целевого кошелька."""

    currency: str
    amount: float
    quote: RateQuote
    before: float
    after: float
    usd_before: float
    usd_after: float
    total: float


class CoreService:
    """Управлять пользователями, сессией, портфелями и сделками."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        # Singleton обеспечивает общие настройки и JSON-хранилище всех операций.
        self.settings = SettingsLoader()
        self.database = database or DatabaseManager()
        self.rates = RateService(self.database)
        self._current_user: User | None = None
        setup_logging()

    def _users(self) -> list[User]:
        try:
            users = [User.from_dict(row) for row in self.database.read("users")]
            if len({u.user_id for u in users}) != len(users) or len(
                {u.username for u in users}
            ) != len(users):
                raise ValueError("повторяющиеся пользователи")
            return users
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataStorageError("Некорректные данные в users.json") from exc

    def _require_user(self) -> User:
        if self._current_user is None:
            raise AuthenticationError("Сначала выполните login")
        return self._current_user

    def _portfolio(self) -> tuple[Portfolio, list[dict]]:
        user = self._require_user()
        records = self.database.read("portfolios")
        try:
            matching = [row for row in records if row["user_id"] == user.user_id]
            if len(matching) != 1:
                raise ValueError("портфель отсутствует или повторяется")
            return Portfolio.from_dict(matching[0], user), records
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataStorageError("Некорректные данные в portfolios.json") from exc

    def _save_portfolio(self, portfolio: Portfolio, records: list[dict]) -> None:
        updated = [
            portfolio.to_dict() if row["user_id"] == portfolio.user_id else row
            for row in records
        ]
        self.database.write("portfolios", updated)

    def register(self, username: str, password: str) -> User:
        """Создать пользователя и пустой портфель, не выполняя вход."""
        username = validate_username(username)
        users = self._users()
        if any(user.username == username for user in users):
            raise ValidationError(f"Имя пользователя '{username}' уже занято")
        user_id = max((user.user_id for user in users), default=0) + 1
        user = User.create(user_id, username, password)
        portfolios = self.database.read("portfolios")
        try:
            if any(row["user_id"] == user_id for row in portfolios):
                raise ValueError("идентификатор уже есть в портфелях")
        except (KeyError, TypeError, ValueError) as exc:
            raise DataStorageError("Некорректные данные в portfolios.json") from exc
        original_users = [existing.to_dict() for existing in users]
        self.database.write("users", [*original_users, user.to_dict()])
        try:
            self.database.write(
                "portfolios", [*portfolios, Portfolio(user_id, user=user).to_dict()]
            )
        except DataStorageError:
            self.database.write("users", original_users)
            raise
        return user

    def login(self, username: str, password: str) -> User:
        """Проверить пароль и установить пользователя текущей сессии."""
        self._current_user = None
        username = validate_username(username)
        user = next((u for u in self._users() if u.username == username), None)
        if user is None:
            raise AuthenticationError(f"Пользователь '{username}' не найден")
        if not user.verify_password(password):
            raise AuthenticationError("Неверный пароль")
        self._current_user = user
        return user

    def show_portfolio(self, base: str | None = None) -> PortfolioView:
        """Получить кошельки и общую стоимость в указанной валюте."""
        portfolio, _ = self._portfolio()
        base = self.settings.get("DEFAULT_BASE_CURRENCY") if base is None else base
        try:
            base = self.rates.ensure_currency(base)
        except CurrencyNotFoundError as exc:
            raise CurrencyNotFoundError(
                base, message=f"Неизвестная базовая валюта '{base}'"
            ) from exc
        rows = []
        sources = set()
        for code, wallet in sorted(portfolio.wallets.items()):
            quote = self.rates.get_rate(code, base)
            value = validate_number(wallet.balance * quote.rate, positive=False)
            rows.append((code, wallet.balance, value))
            sources.add(quote.source)
        total = validate_number(sum(row[2] for row in rows), positive=False)
        return PortfolioView(portfolio.user.username, base, rows, total, tuple(sources))

    @log_action("BUY", verbose=True)
    def buy(self, currency: str, amount: float) -> TradeResult:
        """Купить валюту за USD, автоматически создав целевой кошелёк."""
        return self._trade(currency, amount, buying=True)

    @log_action("SELL", verbose=True)
    def sell(self, currency: str, amount: float) -> TradeResult:
        """Продать валюту и начислить выручку на USD-кошелёк."""
        return self._trade(currency, amount, buying=False)

    def _trade(self, currency: str, amount: float, *, buying: bool) -> TradeResult:
        portfolio, records = self._portfolio()
        amount = validate_number(amount)
        code = self.rates.ensure_currency(currency)
        quote = self.rates.get_rate(code, "USD")
        total = validate_number(amount * quote.rate)
        wallets = portfolio.wallets
        before = wallets[code].balance if code in wallets else 0.0
        usd_before = wallets["USD"].balance if "USD" in wallets else 0.0
        if buying:
            if total > usd_before:
                raise InsufficientFundsError(usd_before, total, "USD")
            after = validate_number(before + amount, positive=False)
            usd_after = usd_before - total
        else:
            if code not in wallets:
                raise InsufficientFundsError(0.0, amount, code)
            wallet = portfolio.get_wallet(code)
            if amount > wallet.balance:
                raise InsufficientFundsError(wallet.balance, amount, code)
            after = before - amount
            usd_after = validate_number(usd_before + total, positive=False)
        # Обмен USD на USD не меняет баланс, но требует наличия суммы.
        if code == "USD":
            after = usd_after = usd_before
        else:
            if buying:
                portfolio.get_wallet("USD").withdraw(total)
                portfolio.add_currency(code).deposit(amount)
            else:
                portfolio.get_wallet(code).withdraw(amount)
                portfolio.add_currency("USD").deposit(total)
        self._save_portfolio(portfolio, records)
        return TradeResult(
            code, amount, quote, before, after, usd_before, usd_after, total
        )

    def get_rate(self, from_currency: str, to_currency: str) -> RateQuote:
        """Получить курс без требования входа пользователя."""
        return self.rates.get_rate(from_currency, to_currency)

    def update_rates(self, source: str | None = None) -> UpdateResult:
        """Обновить кэш и историю через выбранные API-клиенты."""
        return create_updater(source).run_update()

    def show_rates(
        self,
        currency: str | None = None,
        top: int | None = None,
        base: str | None = None,
    ) -> RatesView:
        """Получить отфильтрованный список курсов для консольной таблицы."""
        return self.rates.show_rates(currency, top, base)
