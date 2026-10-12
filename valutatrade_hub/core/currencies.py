"""Иерархия фиатных и криптовалют и реестр поддерживаемых кодов."""

import math
import re
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError, ValidationError


def _nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} не может быть пустым")
    return value.strip()


class Currency(ABC):
    """Абстрактная валюта с именем, кодом и интерфейсом отображения."""

    def __init__(self, name: str, code: str) -> None:
        self.name = name
        self.code = code

    @property
    def name(self) -> str:
        """Человекочитаемое имя валюты."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = _nonempty(value, "Название валюты")

    @property
    def code(self) -> str:
        """Код из 2–5 букв в верхнем регистре без пробелов."""
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{2,5}", value):
            raise ValidationError(
                "Код валюты: 2–5 букв в верхнем регистре без пробелов"
            )
        self._code = value

    @abstractmethod
    def get_display_info(self) -> str:
        """Вернуть представление валюты для интерфейса и логов."""


class FiatCurrency(Currency):
    """Фиатная валюта со страной или зоной эмиссии."""

    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name, code)
        self.issuing_country = _nonempty(issuing_country, "Страна/зона эмиссии")

    def get_display_info(self) -> str:
        """Показать код, имя и страну/зону эмиссии."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и последней известной капитализацией."""

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        super().__init__(name, code)
        self.algorithm = _nonempty(algorithm, "Алгоритм")
        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or not math.isfinite(market_cap)
            or market_cap < 0
        ):
            raise ValidationError("Капитализация должна быть неотрицательным числом")
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        """Показать алгоритм и капитализацию в научной записи."""
        mantissa, exponent = f"{self.market_cap:.2e}".split("e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {mantissa}e{int(exponent)})"
        )


# Капитализация в учебном реестре задана примером, а не получена из API.
CURRENCIES: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 0.0),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of History", 0.0),
}


def get_currency(code: str) -> Currency:
    """Получить валюту по коду или выбросить CurrencyNotFoundError."""
    normalized = code.upper() if isinstance(code, str) else code
    if not isinstance(normalized, str) or normalized not in CURRENCIES:
        raise CurrencyNotFoundError(code)
    return CURRENCIES[normalized]
