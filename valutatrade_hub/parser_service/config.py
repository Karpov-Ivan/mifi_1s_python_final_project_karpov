"""Настройки источников курсов, запросов и периодического обновления."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ValidationError
from valutatrade_hub.infra.settings import SettingsLoader


@dataclass
class ParserConfig:
    """Хранить параметры парсера; загружать API-ключи только из окружения."""

    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY", ""), repr=False
    )
    COINGECKO_API_KEY: str = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY", ""), repr=False
    )
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"
    BASE_FIAT_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    )
    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL: int = 300
    RATES_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().get("RATES_FILE")
    )
    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().get("HISTORY_FILE")
    )

    def __post_init__(self) -> None:
        self.RATES_FILE_PATH = Path(self.RATES_FILE_PATH)
        self.HISTORY_FILE_PATH = Path(self.HISTORY_FILE_PATH)
        self.BASE_FIAT_CURRENCY = get_currency(self.BASE_FIAT_CURRENCY).code
        for code in (*self.FIAT_CURRENCIES, *self.CRYPTO_CURRENCIES):
            get_currency(code)
        for value in (self.REQUEST_TIMEOUT, self.UPDATE_INTERVAL):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValidationError("Таймаут и интервал должны быть положительными")
