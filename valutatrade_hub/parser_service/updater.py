"""Опрос источников, объединение результатов и сохранение курсов."""

from dataclasses import dataclass
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    DataStorageError,
    ValidationError,
)
from valutatrade_hub.core.utils import validate_currency, validate_number
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage


@dataclass(frozen=True)
class UpdateResult:
    """Обновлённые пары, время сохранения, результаты источников и ошибки."""

    updated: int
    last_refresh: str
    fetched: dict[str, int]
    errors: dict[str, str]


class RatesUpdater:
    """Продолжать обновление из доступных источников при частичном сбое."""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage) -> None:
        self.clients = clients
        self.storage = storage
        self.logger = setup_logging("parser")

    def run_update(self) -> UpdateResult:
        """Последовательно опросить клиентов и атомарно сохранить корректные данные."""
        self.logger.info("Начало обновления курсов")
        records = []
        errors = {}
        fetched = {}
        for client in self.clients:
            self.logger.info("Получение данных из %s", client.source)
            try:
                rates = client.fetch_rates()
                timestamp = (
                    (client.updated_at or datetime.now(UTC))
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                measurements = []
                for pair, rate in rates.items():
                    origin, target = pair.split("_")
                    origin = validate_currency(origin)
                    target = validate_currency(target)
                    rate = validate_number(rate)
                    validate_number(1 / rate)
                    measurements.append(
                        {
                            "from_currency": origin,
                            "to_currency": target,
                            "rate": rate,
                            "timestamp": timestamp,
                            "source": client.source,
                            "meta": client.meta.get(pair, {}),
                        }
                    )
                if not measurements:
                    raise ApiRequestError(f"{client.source}: нет курсов в ответе")
            except (
                ApiRequestError,
                CurrencyNotFoundError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                message = (
                    str(exc)
                    .removeprefix("Ошибка при обращении к внешнему API: ")
                    .removeprefix(f"{client.source}: ")
                    if isinstance(exc, ApiRequestError)
                    else (f"{client.source}: неверный формат данных")
                )
                errors[client.source] = message
                self.logger.error("Ошибка источника %s: %s", client.source, message)
                continue
            records.extend(measurements)
            fetched[client.source] = len(measurements)
            self.logger.info(
                "%s: получено курсов — %d", client.source, len(measurements)
            )
        if not records:
            self.logger.error("Обновление не выполнено: все источники недоступны")
            raise ApiRequestError(
                "; ".join(f"{source}: {message}" for source, message in errors.items())
                or "нет источников курсов"
            )
        try:
            updated, refreshed = self.storage.save(records)
        except DataStorageError as exc:
            self.logger.error("Не удалось сохранить курсы: %s", exc)
            raise
        self.logger.info(
            "Обновление завершено: %d пар, ошибок источников — %d", updated, len(errors)
        )
        return UpdateResult(updated, refreshed, fetched, errors)


def create_updater(source: str | None = None) -> RatesUpdater:
    """Создать парсер всех источников или одного выбранного источника."""
    config = ParserConfig()
    factories = {"coingecko": CoinGeckoClient, "exchangerate": ExchangeRateApiClient}
    if source is not None and source not in factories:
        raise ValidationError("Источник должен быть coingecko или exchangerate")
    clients = [
        factory(config)
        for name, factory in factories.items()
        if source is None or name == source
    ]
    return RatesUpdater(clients, RatesStorage(config))
