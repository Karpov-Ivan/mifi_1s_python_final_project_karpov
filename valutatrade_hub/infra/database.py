"""JSON-хранилище с атомарной заменой отдельных файлов."""

import json
import os
import tempfile
from pathlib import Path

from valutatrade_hub.core.exceptions import DataStorageError
from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Единственная точка чтения и сохранения JSON-данных приложения."""

    _instance = None

    def __new__(cls):
        # __new__ явно обеспечивает единственный экземпляр без метакласса.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self.settings = SettingsLoader()
        self._initialized = True

    def _path(self, name: str) -> Path:
        key = {
            "users": "USERS_FILE",
            "portfolios": "PORTFOLIOS_FILE",
            "rates": "RATES_FILE",
        }
        if name not in key:
            raise DataStorageError(f"Неизвестное хранилище '{name}'")
        return self.settings.get(key[name])

    def read(self, name: str) -> list | dict:
        """Прочитать файл; отсутствующий файл соответствует пустому хранилищу."""
        path = self._path(name)
        expected_type = dict if name == "rates" else list
        try:
            if not path.exists():
                return expected_type()
            result = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(result, expected_type):
                raise ValueError("неверный формат данных")
            return result
        except (OSError, ValueError) as exc:
            raise DataStorageError(f"Не удалось прочитать {path.name}: {exc}") from exc

    def write(self, name: str, data: list | dict) -> None:
        """Записать JSON через временный файл и os.replace."""
        path = self._path(name)
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except (OSError, ValueError, TypeError) as exc:
            raise DataStorageError(f"Не удалось сохранить {path.name}: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
