"""История измерений и последний срез курсов с атомарной записью JSON."""

from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import DataStorageError
from valutatrade_hub.core.utils import (
    parse_timestamp,
    validate_currency,
    validate_number,
)
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    """Сохранять измерения без повторных ID и обновлять только более свежие пары."""

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig()
        self.database = DatabaseManager()

    def save(self, records: list[dict]) -> tuple[int, str]:
        """Вернуть число обновлённых пар и время успешного обновления кэша."""
        normalized = []
        try:
            for record in records:
                origin = validate_currency(record["from_currency"])
                target = validate_currency(record["to_currency"])
                rate = validate_number(record["rate"])
                validate_number(1 / rate)
                timestamp = (
                    parse_timestamp(record["timestamp"])
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                if not isinstance(record["source"], str) or not record["source"]:
                    raise ValueError("неверный источник")
                if not isinstance(record.get("meta", {}), dict):
                    raise ValueError("неверные метаданные")
                normalized.append(
                    record
                    | {
                        "id": f"{origin}_{target}_{timestamp}",
                        "from_currency": origin,
                        "to_currency": target,
                        "rate": rate,
                        "timestamp": timestamp,
                    }
                )
            history = self.database.read_file(self.config.HISTORY_FILE_PATH, list)
            ids = {record["id"] for record in history}
            cache = self.database.read_file(self.config.RATES_FILE_PATH, dict)
            pairs = cache.get("pairs", {})
            if not isinstance(pairs, dict):
                raise ValueError("неверный формат pairs")
            # Проверка существующего среза до любой записи в историю или кэш.
            for pair, entry in pairs.items():
                origin, target = pair.split("_")
                validate_currency(origin)
                validate_currency(target)
                validate_number(entry["rate"])
                parse_timestamp(entry["updated_at"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DataStorageError(
                "Некорректные данные истории или кэша курсов"
            ) from exc
        updated = set()
        added = 0
        for record in normalized:
            if record["id"] not in ids:
                history.append(record)
                ids.add(record["id"])
                added += 1
            pair = f"{record['from_currency']}_{record['to_currency']}"
            current = pairs.get(pair)
            if current is None or parse_timestamp(
                record["timestamp"]
            ) > parse_timestamp(current["updated_at"]):
                pairs[pair] = {
                    "rate": record["rate"],
                    "updated_at": record["timestamp"],
                    "source": record["source"],
                }
                updated.add(pair)
        refreshed = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        if added:
            self.database.write_file(self.config.HISTORY_FILE_PATH, history)
        self.database.write_file(
            self.config.RATES_FILE_PATH, {"pairs": pairs, "last_refresh": refreshed}
        )
        return len(updated), refreshed
