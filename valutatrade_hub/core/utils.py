"""Валидация, хеширование паролей и единый контракт курсов."""

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    DataStorageError,
    ValidationError,
)
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import MIN_PASSWORD_LENGTH


def validate_username(username: str) -> str:
    """Проверить непустое имя и убрать пробелы по краям."""
    if not isinstance(username, str) or not username.strip():
        raise ValidationError("Имя пользователя не может быть пустым")
    return username.strip()


def validate_password(password: str) -> str:
    """Проверить минимальную длину пароля."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError("Пароль должен быть не короче 4 символов")
    return password


def hash_password(password: str, salt: str) -> str:
    """Получить SHA-256 от пароля и индивидуальной соли."""
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def validate_currency(currency_code: str) -> str:
    """Получить нормализованный код поддерживаемой валюты из реестра."""
    return get_currency(currency_code).code


def validate_number(value: float, *, positive: bool = True) -> float:
    """Проверить конечное число, исключая bool, NaN и бесконечность."""
    message = (
        "'amount' должен быть положительным числом"
        if positive
        else "Баланс должен быть неотрицательным числом"
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(message)
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValidationError(message) from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValidationError(message)
    return result


def parse_timestamp(value: str) -> datetime:
    """Прочитать ISO-дату; даты без часового пояса считать UTC."""
    result = datetime.fromisoformat(value)
    return (
        result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    )


@dataclass(frozen=True)
class RateQuote:
    """Курс, время самого старого компонента и происхождение значения."""

    rate: float
    updated_at: datetime
    source: str


@dataclass(frozen=True)
class RatesView:
    """Отфильтрованные курсы и признак свежести каждой строки."""

    rows: list[tuple[str, RateQuote, bool]]
    last_refresh: str | None


class RateService:
    """Читать курсы из локального кэша; обновление выполняет Parser Service."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.database = database or DatabaseManager()

    def read_cache(self) -> dict:
        """Прочитать снимок pairs + last_refresh и проверить структуру."""
        cache = self.database.read("rates")
        if not cache:
            return {"pairs": {}, "last_refresh": None}
        if not isinstance(cache.get("pairs"), dict):
            raise DataStorageError("Некорректный формат pairs в rates.json")
        if cache.get("last_refresh") is not None:
            try:
                parse_timestamp(cache["last_refresh"])
            except (TypeError, ValueError) as exc:
                raise DataStorageError(
                    "Некорректный last_refresh в rates.json"
                ) from exc
        return cache

    def is_fresh(self, quote: RateQuote) -> bool:
        """Проверить возраст записи по TTL из SettingsLoader."""
        age = (datetime.now(UTC) - quote.updated_at).total_seconds()
        return 0 <= age < self.database.settings.get("RATES_TTL_SECONDS")

    def _cached(self, pairs: dict, pair: str, allow_stale: bool) -> RateQuote | None:
        entry = pairs.get(pair)
        if entry is None:
            return None
        try:
            rate = validate_number(entry["rate"])
            validate_number(1 / rate)
            updated_at = parse_timestamp(entry["updated_at"])
            source = entry["source"]
            if not isinstance(source, str) or not source:
                raise ValueError("неверный источник курса")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataStorageError(f"Некорректная запись курса {pair}") from exc
        quote = RateQuote(rate, updated_at, source)
        return quote if allow_stale or self.is_fresh(quote) else None

    def ensure_currency(self, code: str) -> str:
        """Проверить валюту через фабрику get_currency()."""
        return validate_currency(code)

    def _leg(
        self, pairs: dict, origin: str, target: str, allow_stale: bool
    ) -> RateQuote | None:
        if origin == target:
            return RateQuote(1.0, datetime.now(UTC), "Identity")
        direct = self._cached(pairs, f"{origin}_{target}", allow_stale)
        if direct:
            return direct
        inverse = self._cached(pairs, f"{target}_{origin}", allow_stale)
        if inverse:
            return RateQuote(1 / inverse.rate, inverse.updated_at, inverse.source)
        return None

    def _quote(
        self, pairs: dict, origin: str, target: str, *, allow_stale: bool = False
    ) -> RateQuote:
        direct = self._leg(pairs, origin, target, allow_stale)
        if direct:
            return direct
        bridges = set()
        for pair in pairs:
            try:
                first, second = pair.split("_")
                bridges.update((first, second))
            except (ValueError, AttributeError) as exc:
                raise DataStorageError("Некорректная пара в rates.json") from exc
        for bridge in sorted(bridges - {origin, target}, key=lambda c: (c != "USD", c)):
            first = self._leg(pairs, origin, bridge, allow_stale)
            second = self._leg(pairs, bridge, target, allow_stale)
            if first and second:
                return RateQuote(
                    validate_number(first.rate * second.rate),
                    min(first.updated_at, second.updated_at),
                    "/".join(sorted({first.source, second.source})),
                )
        raise ApiRequestError(
            f"Курс {origin}→{target} отсутствует или устарел. Выполните 'update-rates'."
        )

    def get_rate(self, from_currency: str, to_currency: str) -> RateQuote:
        """Вернуть свежий прямой, обратный или кросс-курс без сетевых запросов."""
        origin = self.ensure_currency(from_currency)
        target = self.ensure_currency(to_currency)
        return self._quote(self.read_cache()["pairs"], origin, target)

    def show_rates(
        self,
        currency: str | None = None,
        top: int | None = None,
        base: str | None = None,
    ) -> RatesView:
        """Отфильтровать кэш; устаревшие записи показывать с явной отметкой."""
        if top is not None and (
            isinstance(top, bool) or not isinstance(top, int) or top <= 0
        ):
            raise ValidationError("'top' должен быть положительным целым числом")
        cache = self.read_cache()
        pairs = cache["pairs"]
        if not pairs:
            raise ValidationError(
                "Локальный кеш курсов пуст. Выполните 'update-rates', "
                "чтобы загрузить данные."
            )
        if currency is not None:
            try:
                currency = self.ensure_currency(currency)
            except CurrencyNotFoundError as exc:
                raise CurrencyNotFoundError(
                    currency, message=f"Курс для '{currency}' не найден в кеше."
                ) from exc
        if top is not None and base is None:
            base = self.database.settings.get("DEFAULT_BASE_CURRENCY")
        if base is not None:
            base = self.ensure_currency(base)
        rows = {}
        for pair in sorted(pairs):
            try:
                origin, target = pair.split("_")
            except (ValueError, AttributeError) as exc:
                raise DataStorageError(f"Некорректная пара '{pair}'") from exc
            self.ensure_currency(origin)
            self.ensure_currency(target)
            if currency is not None and currency not in (origin, target):
                continue
            if top is not None and not isinstance(get_currency(origin), CryptoCurrency):
                continue
            quote = self._cached(pairs, pair, allow_stale=True)
            if base is not None:
                converted = self._quote(pairs, origin, base, allow_stale=True)
                quote = RateQuote(
                    converted.rate,
                    min(quote.updated_at, converted.updated_at),
                    converted.source,
                )
                pair = f"{origin}_{base}"
            rows[pair] = (pair, quote, self.is_fresh(quote))
        result = list(rows.values())
        if not result:
            raise ValidationError(
                f"Курс для '{currency}' не найден в кеше."
                if currency
                else "В кеше нет курсов, соответствующих фильтрам."
            )
        if top is not None:
            # Сравниваем цены в одной базе, даже если в кэше несколько источников.
            ranking_base = base or self.database.settings.get("DEFAULT_BASE_CURRENCY")
            result.sort(
                key=lambda row: (
                    self._quote(
                        pairs, row[0].split("_")[0], ranking_base, allow_stale=True
                    ).rate
                ),
                reverse=True,
            )
            result = result[:top]
        return RatesView(result, cache.get("last_refresh"))
