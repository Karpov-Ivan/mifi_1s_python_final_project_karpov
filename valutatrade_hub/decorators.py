"""Логирование доменных операций без изменения их результата."""

import inspect
import logging
import math
from functools import wraps


def log_action(action: str, *, verbose: bool = False):
    """Записать результат операции и пробросить её исключение после записи."""

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            service = arguments.get("self")
            user = getattr(service, "_current_user", None)
            amount = arguments.get("amount")
            if not isinstance(amount, (str, int, float, type(None))) or (
                isinstance(amount, float) and not math.isfinite(amount)
            ):
                amount = str(amount)
            currency = arguments.get("currency")
            data = {
                "action": action,
                "username": user.username if user else None,
                "user_id": user.user_id if user else None,
                "currency_code": currency
                if isinstance(currency, str)
                else str(currency),
                "amount": amount,
                "rate": None,
                "base": "USD",
            }
            logger = logging.getLogger("valutatrade.actions")
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                data.update(
                    result="ERROR",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                logger.info("%s", action, extra={"action_data": data})
                raise
            data.update(
                currency_code=result.currency,
                amount=result.amount,
                rate=result.quote.rate,
                result="OK",
            )
            if verbose:
                data["wallet_before"] = result.before
                data["wallet_after"] = result.after
                data["usd_before"] = result.usd_before
                data["usd_after"] = result.usd_after
            logger.info("%s", action, extra={"action_data": data})
            return result

        return wrapped

    return decorate
