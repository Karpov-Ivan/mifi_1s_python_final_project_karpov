"""Централизованная конфигурация приложения."""

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RATES_TTL = 300
MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 16
STUB_USD_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "RUB": 0.01016,
    "ETH": 3720.0,
}


@dataclass(frozen=True)
class Settings:
    """Пути и TTL; каталог данных можно переопределить через окружение."""

    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("VALUTATRADE_DATA_DIR", Path.cwd() / "data")
        )
    )
    rates_ttl: int = DEFAULT_RATES_TTL
