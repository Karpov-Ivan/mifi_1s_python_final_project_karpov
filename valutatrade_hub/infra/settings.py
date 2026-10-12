"""Централизованная конфигурация приложения."""

import os
import tomllib
from pathlib import Path
from typing import Any

from valutatrade_hub.core.exceptions import DataStorageError

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


class SettingsLoader:
    """Единственный загрузчик секции [tool.valutatrade] из pyproject.toml."""

    _instance = None

    def __new__(cls):
        # __new__ проще метакласса: здесь нужен Singleton только одного класса.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        root = Path.cwd()
        config_path = root / "pyproject.toml"
        try:
            config = (
                tomllib.loads(config_path.read_text(encoding="utf-8"))
                .get("tool", {})
                .get("valutatrade", {})
                if config_path.exists()
                else {}
            )
            values = {
                "DATA_DIR": "data",
                "USERS_FILE": "users.json",
                "PORTFOLIOS_FILE": "portfolios.json",
                "RATES_FILE": "rates.json",
                "RATES_TTL_SECONDS": DEFAULT_RATES_TTL,
                "DEFAULT_BASE_CURRENCY": "USD",
                "LOG_FILE": "logs/actions.log",
                "LOG_FORMAT": "json",
                "LOG_LEVEL": "INFO",
                "LOG_MAX_BYTES": 1048576,
                "LOG_BACKUP_COUNT": 3,
            }
            values.update(config)
            values["DATA_DIR"] = Path(
                os.environ.get("VALUTATRADE_DATA_DIR", values["DATA_DIR"])
            )
            if not values["DATA_DIR"].is_absolute():
                values["DATA_DIR"] = root / values["DATA_DIR"]
            for key in ("USERS_FILE", "PORTFOLIOS_FILE", "RATES_FILE"):
                path = Path(values[key])
                values[key] = path if path.is_absolute() else values["DATA_DIR"] / path
            log_path = Path(values["LOG_FILE"])
            values["LOG_FILE"] = log_path if log_path.is_absolute() else root / log_path
            for key in ("RATES_TTL_SECONDS", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT"):
                value = values[key]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError(f"{key} должен быть положительным целым числом")
            if values["LOG_FORMAT"] != "json":
                raise ValueError("Поддерживаемый LOG_FORMAT: json")
            if values["LOG_LEVEL"] not in ("INFO", "DEBUG"):
                raise ValueError("Поддерживаемые LOG_LEVEL: INFO, DEBUG")
            self._values = values
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise DataStorageError(f"Не удалось загрузить конфигурацию: {exc}") from exc
        self._initialized = True

    def get(self, key: str, default: Any = None) -> Any:
        """Вернуть значение конфигурации или переданное значение по умолчанию."""
        return self._values.get(key, default)
