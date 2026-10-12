"""Ошибки, которые консольный интерфейс показывает пользователю."""


class ValutaTradeError(Exception):
    """Базовая ошибка приложения."""


class ValidationError(ValutaTradeError, ValueError):
    """Некорректные входные данные."""


class AuthenticationError(ValutaTradeError):
    """Не удалось войти или операция требует входа."""


class InsufficientFundsError(ValutaTradeError):
    """На кошельке недостаточно средств для операции."""

    def __init__(self, available: float, required: float, currency: str) -> None:
        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {currency}, "
            f"требуется {required:.4f} {currency}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """Неизвестная валюта или отсутствующий кошелёк."""


class ApiRequestError(ValutaTradeError):
    """Курс недоступен в кэше и источнике курсов."""


class DataStorageError(ValutaTradeError):
    """Ошибка чтения или записи JSON-хранилища."""
