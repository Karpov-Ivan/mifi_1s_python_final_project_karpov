"""Модели пользователя, валютного кошелька и портфеля."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValidationError,
)
from valutatrade_hub.core.utils import (
    RateService,
    hash_password,
    parse_timestamp,
    validate_currency,
    validate_number,
    validate_password,
    validate_username,
)
from valutatrade_hub.infra.settings import SALT_BYTES


class User:
    """Пользователь с индивидуальной солью и хешем пароля."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValidationError(
                "Идентификатор пользователя должен быть положительным"
            )
        if not isinstance(hashed_password, str) or len(hashed_password) != 64:
            raise ValidationError("Некорректный SHA-256 хеш пароля")
        try:
            int(hashed_password, 16)
        except ValueError as exc:
            raise ValidationError("Некорректный SHA-256 хеш пароля") from exc
        if not isinstance(salt, str) or not salt:
            raise ValidationError("Соль пароля не может быть пустой")
        if not isinstance(registration_date, datetime):
            raise ValidationError("Некорректная дата регистрации")
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> User:
        """Создать пользователя, сохраняя только соль и хеш пароля."""
        password = validate_password(password)
        salt = secrets.token_hex(SALT_BYTES)
        return cls(
            user_id, username, hash_password(password, salt), salt, datetime.now(UTC)
        )

    @property
    def user_id(self) -> int:
        """Неизменяемый идентификатор пользователя."""
        return self._user_id

    @property
    def username(self) -> str:
        """Имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        self._username = validate_username(value)

    @property
    def hashed_password(self) -> str:
        """Хеш для сериализации; изменяется через change_password."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Индивидуальная соль для сериализации."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Дата регистрации пользователя."""
        return self._registration_date

    def get_user_info(self) -> dict:
        """Вернуть информацию без пароля, его хеша и соли."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Изменить пароль с проверкой длины и генерацией новой соли."""
        new_password = validate_password(new_password)
        self._salt = secrets.token_hex(SALT_BYTES)
        self._hashed_password = hash_password(new_password, self.salt)

    def verify_password(self, password: str) -> bool:
        """Сравнить хеш введённого пароля с сохранённым хешем."""
        return isinstance(password, str) and hmac.compare_digest(
            hash_password(password, self.salt), self.hashed_password
        )

    def to_dict(self) -> dict:
        """Подготовить запись пользователя для users.json."""
        return self.get_user_info() | {
            "hashed_password": self.hashed_password,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        """Восстановить пользователя из JSON-записи."""
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            parse_timestamp(data["registration_date"]),
        )


class Wallet:
    """Кошелёк одной валюты с неотрицательным конечным балансом."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        self._currency_code = validate_currency(currency_code)
        self.balance = balance

    @property
    def currency_code(self) -> str:
        """Неизменяемый код валюты кошелька."""
        return self._currency_code

    @property
    def balance(self) -> float:
        """Текущий баланс кошелька."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        self._balance = validate_number(value, positive=False)

    def deposit(self, amount: float) -> None:
        """Пополнить кошелёк положительной конечной суммой."""
        self.balance += validate_number(amount)

    def withdraw(self, amount: float) -> None:
        """Снять сумму, не превышающую текущий баланс."""
        amount = validate_number(amount)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance -= amount

    def get_balance_info(self) -> str:
        """Вернуть код валюты и баланс для отображения."""
        return f"{self.currency_code}: {self.balance:.4f}"

    def to_dict(self) -> dict:
        """Подготовить кошелёк для JSON-портфеля."""
        return {"currency_code": self.currency_code, "balance": self.balance}


class Portfolio:
    """Кошельки одного пользователя с уникальными кодами валют."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        *,
        user: User,
    ) -> None:
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or user_id != user.user_id
        ):
            raise ValidationError(
                "Портфель должен принадлежать указанному пользователю"
            )
        self._user_id = user_id
        self._user = user
        self._wallets: dict[str, Wallet] = {}
        for code, wallet in (wallets or {}).items():
            code = validate_currency(code)
            if not isinstance(wallet, Wallet) or wallet.currency_code != code:
                raise ValidationError("Код кошелька не совпадает с ключом портфеля")
            if code in self._wallets:
                raise ValidationError(f"Кошелёк '{code}' уже существует")
            self._wallets[code] = wallet

    @property
    def user_id(self) -> int:
        """Идентификатор владельца портфеля."""
        return self._user_id

    @property
    def user(self) -> User:
        """Владелец портфеля без возможности перезаписи."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Вернуть копию словаря, сохраняя объекты кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Создать кошелёк или вернуть существующий без обнуления баланса."""
        code = validate_currency(currency_code)
        if code not in self._wallets:
            self._wallets[code] = Wallet(code)
        return self._wallets[code]

    def get_wallet(self, currency_code: str) -> Wallet:
        """Получить кошелёк или сообщить о его отсутствии."""
        code = validate_currency(currency_code)
        if code not in self._wallets:
            raise CurrencyNotFoundError(
                f"У вас нет кошелька '{code}'. Добавьте валюту: "
                "она создаётся автоматически при первой покупке."
            )
        return self._wallets[code]

    def get_total_value(
        self, base_currency: str = "USD", *, rate_service: RateService | None = None
    ) -> float:
        """Конвертировать все кошельки в базовую валюту через единый сервис."""
        rates = rate_service or RateService()
        base = rates.ensure_currency(base_currency)
        total = sum(
            wallet.balance * rates.get_rate(code, base).rate
            for code, wallet in self._wallets.items()
            if wallet.balance
        )
        return validate_number(total, positive=False)

    def to_dict(self) -> dict:
        """Подготовить запись для portfolios.json."""
        return {
            "user_id": self.user_id,
            "wallets": {
                code: wallet.to_dict() for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, user: User) -> Portfolio:
        """Прочитать кошельки с кодом валюты в ключе или в записи."""
        wallets = {
            code: Wallet(entry.get("currency_code", code), entry["balance"])
            for code, entry in data["wallets"].items()
        }
        return cls(data["user_id"], wallets, user=user)
