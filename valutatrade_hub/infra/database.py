"""JSON-хранилище с атомарной заменой отдельных файлов."""

import json
import os
import tempfile
from pathlib import Path

from valutatrade_hub.core.exceptions import DataStorageError
from valutatrade_hub.infra.settings import Settings


class DatabaseManager:
    """Читать и сохранять пользователей, портфели и курсы."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def read(self, name: str) -> list | dict:
        """Прочитать файл; отсутствующий файл соответствует пустому хранилищу."""
        path = self.settings.data_dir / f"{name}.json"
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
        path = self.settings.data_dir / f"{name}.json"
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
