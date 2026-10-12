"""API-клиенты с единым форматом курсов и безопасными сообщениями об ошибках."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from time import perf_counter

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_number
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Общий контракт клиента: пары валют и положительные числовые курсы."""

    source: str
    name: str

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig()
        self.updated_at: datetime | None = None
        self.meta: dict[str, dict] = {}

    def _request(self, url: str, **kwargs) -> tuple[dict, dict]:
        start = perf_counter()
        try:
            response = requests.get(url, timeout=self.config.REQUEST_TIMEOUT, **kwargs)
        except requests.exceptions.Timeout:
            raise ApiRequestError(f"{self.source}: превышено время ожидания") from None
        except requests.exceptions.RequestException:
            # Текст requests может содержать URL с ключом, поэтому его не выводим.
            raise ApiRequestError(f"{self.source}: сетевая ошибка") from None
        if response.status_code != 200:
            reason = {
                401: "неверный API-ключ",
                403: "доступ запрещён; проверьте API-ключ",
                429: "лимит запросов превышен; повторите позже",
            }.get(response.status_code, f"HTTP {response.status_code}")
            raise ApiRequestError(f"{self.source}: {reason}")
        try:
            data = response.json()
        except ValueError:
            raise ApiRequestError(f"{self.source}: некорректный JSON") from None
        if not isinstance(data, dict):
            raise ApiRequestError(f"{self.source}: неверный формат ответа")
        metadata = {
            "request_ms": round((perf_counter() - start) * 1000),
            "status_code": response.status_code,
        }
        if response.headers.get("ETag"):
            metadata["etag"] = response.headers["ETag"]
        return data, metadata

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получить курсы в формате {'BTC_USD': 59337.21, ...}."""


class CoinGeckoClient(BaseApiClient):
    """Запросить цены криптовалют по CoinGecko ID."""

    source = "CoinGecko"
    name = "coingecko"

    def fetch_rates(self) -> dict[str, float]:
        """Получить криптовалютные пары и метаданные измерений."""
        try:
            ids = {
                code: self.config.CRYPTO_ID_MAP[code]
                for code in self.config.CRYPTO_CURRENCIES
            }
        except KeyError:
            raise ApiRequestError("CoinGecko: отсутствует ID криптовалюты") from None
        base = self.config.BASE_FIAT_CURRENCY
        headers = {}
        if self.config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = self.config.COINGECKO_API_KEY
        data, metadata = self._request(
            self.config.COINGECKO_URL,
            params={
                "ids": ",".join(ids.values()),
                "vs_currencies": base.lower(),
                "include_last_updated_at": "true",
            },
            headers=headers,
        )
        rates = {}
        meta = {}
        try:
            for code, coin_id in ids.items():
                entry = data[coin_id]
                pair = f"{code}_{base}"
                rates[pair] = validate_number(entry[base.lower()])
                validate_number(1 / rates[pair])
                meta[pair] = metadata | {"raw_id": coin_id}
                if entry.get("last_updated_at") is not None:
                    meta[pair]["provider_updated_at"] = datetime.fromtimestamp(
                        validate_number(entry["last_updated_at"]), UTC
                    ).isoformat()
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise ApiRequestError("CoinGecko: неверные данные курсов") from None
        # TTL кэша отсчитывается от успешного получения; дата провайдера — в meta.
        self.updated_at = datetime.now(UTC)
        self.meta = meta
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Получить фиатные курсы и инвертировать пары к базовой валюте."""

    source = "ExchangeRate-API"
    name = "exchangerate"

    def fetch_rates(self) -> dict[str, float]:
        """Вернуть EUR_USD и другие пары вместо исходных USD_EUR."""
        if not self.config.EXCHANGERATE_API_KEY:
            raise ApiRequestError("Задайте переменную окружения EXCHANGERATE_API_KEY")
        base = self.config.BASE_FIAT_CURRENCY
        url = (
            f"{self.config.EXCHANGERATE_API_URL}/"
            f"{self.config.EXCHANGERATE_API_KEY}/latest/{base}"
        )
        data, metadata = self._request(url)
        if data.get("result") != "success":
            error_type = data.get("error-type")
            if not isinstance(error_type, str):
                error_type = ""
            reason = {
                "invalid-key": "неверный API-ключ",
                "inactive-account": "аккаунт не подтверждён",
                "quota-reached": "лимит запросов превышен",
                "unsupported-code": "базовая валюта не поддерживается",
            }.get(error_type, "API вернул ошибку")
            raise ApiRequestError(f"ExchangeRate-API: {reason}")
        rates = {}
        try:
            if data["base_code"] != base:
                raise ValueError("неверная базовая валюта")
            conversions = data["conversion_rates"]
            codes = set(self.config.FIAT_CURRENCIES)
            if base != "USD":
                codes.add("USD")
            for code in sorted(codes - {base}):
                rates[f"{code}_{base}"] = validate_number(
                    1 / validate_number(conversions[code])
                )
        except (KeyError, TypeError, ValueError):
            raise ApiRequestError("ExchangeRate-API: неверные данные курсов") from None
        self.updated_at = datetime.now(UTC)
        if data.get("time_last_update_utc"):
            metadata["provider_updated_at"] = data["time_last_update_utc"]
        self.meta = {pair: metadata.copy() for pair in rates}
        return rates
