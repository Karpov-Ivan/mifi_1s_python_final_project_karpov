"""Валидация, хеширование паролей и единый контракт курсов."""

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    DataStorageError,
    ValidationError,
)
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import MIN_PASSWORD_LENGTH, STUB_USD_RATES


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
    refreshed: bool = False


class RateService:
    """Читать свежие курсы из JSON, иначе использовать учебную заглушку."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.database = database or DatabaseManager()

    def _cached(self, cache: dict, pair: str, now: datetime) -> RateQuote | None:
        entry = cache.get(pair)
        if entry is None:
            return None
        try:
            rate = validate_number(entry["rate"])
            validate_number(1 / rate)
            updated_at = parse_timestamp(entry["updated_at"])
            source = entry.get("source", cache.get("source", "Cache"))
            if not isinstance(source, str) or not source:
                raise ValueError("неверный источник курса")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataStorageError(f"Некорректная запись курса {pair}") from exc
        age = (now - updated_at).total_seconds()
        if 0 <= age < self.database.settings.get("RATES_TTL_SECONDS"):
            return RateQuote(rate, updated_at, source)
        return None

    def ensure_currency(self, code: str) -> str:
        """Проверить валюту через фабрику get_currency()."""
        return validate_currency(code)

    def get_rate(self, from_currency: str, to_currency: str) -> RateQuote:
        """Вернуть прямой, обратный или кросс-курс с учётом TTL."""
        origin = self.ensure_currency(from_currency)
        target = self.ensure_currency(to_currency)
        cache = self.database.read("rates")
        now = datetime.now(UTC)
        if origin == target:
            return RateQuote(1.0, now, "Identity")
        direct = self._cached(cache, f"{origin}_{target}", now)
        if direct:
            return direct
        inverse = self._cached(cache, f"{target}_{origin}", now)
        if inverse:
            return RateQuote(
                validate_number(1 / inverse.rate), inverse.updated_at, inverse.source
            )
        quotes = []
        pending = {}
        for code in (origin, target):
            if code == "USD":
                quotes.append(RateQuote(1.0, now, "Identity"))
                continue
            quote = self._cached(cache, f"{code}_USD", now)
            if quote is None:
                reverse = self._cached(cache, f"USD_{code}", now)
                if reverse:
                    quote = RateQuote(
                        validate_number(1 / reverse.rate),
                        reverse.updated_at,
                        reverse.source,
                    )
            if quote is None:
                try:
                    stub_rate = validate_number(STUB_USD_RATES[code])
                except (KeyError, ValidationError) as exc:
                    raise ApiRequestError(
                        f"Курс {origin}→{target} недоступен в заглушке"
                    ) from exc
                quote = RateQuote(stub_rate, now, "Stub", refreshed=True)
                pending[f"{code}_USD"] = {
                    "rate": quote.rate,
                    "updated_at": now.isoformat(),
                    "source": "Stub",
                }
            quotes.append(quote)
        refreshed = bool(pending)
        if refreshed:
            cache.update(pending)
            sources = [
                entry.get("source", cache.get("source", "Cache"))
                for pair, entry in cache.items()
                if re.fullmatch(r"[A-Z]+_[A-Z]+", pair) and isinstance(entry, dict)
            ]
            cache["source"] = (
                "Stub" if all(source == "Stub" for source in sources) else "Mixed"
            )
            cache["last_refresh"] = now.isoformat()
            self.database.write("rates", cache)
        sources = {q.source for q in quotes if q.source != "Identity"}
        return RateQuote(
            validate_number(quotes[0].rate / quotes[1].rate),
            min(q.updated_at for q in quotes),
            "/".join(sorted(sources)),
            refreshed,
        )
