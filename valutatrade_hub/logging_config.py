"""JSON-формат логов действий и ротация по размеру файла."""

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from valutatrade_hub.core.exceptions import DataStorageError
from valutatrade_hub.infra.settings import SettingsLoader


class JsonFormatter(logging.Formatter):
    """Одна операция — одна JSON-строка с ISO-датой и уровнем."""

    def format(self, record: logging.LogRecord) -> str:
        """Сериализовать обязательные поля и контекст операции."""
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            **record.action_data,
        }
        return json.dumps(data, ensure_ascii=False, default=str, allow_nan=False)


def setup_logging() -> logging.Logger:
    """Настроить единственный обработчик логов действий приложения."""
    settings = SettingsLoader()
    logger = logging.getLogger("valutatrade.actions")
    if not logger.handlers:
        path = settings.get("LOG_FILE")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path,
                maxBytes=settings.get("LOG_MAX_BYTES"),
                backupCount=settings.get("LOG_BACKUP_COUNT"),
                encoding="utf-8",
            )
        except OSError as exc:
            raise DataStorageError(f"Не удалось открыть файл логов: {exc}") from exc
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(settings.get("LOG_LEVEL"))
    logger.propagate = False
    return logger
