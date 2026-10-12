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

    def __init__(self, code: str, *, message: str | None = None) -> None:
        super().__init__(message or f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Курс недоступен в кэше и источнике курсов."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class DataStorageError(ValutaTradeError):
    """Ошибка чтения или записи JSON-хранилища."""
