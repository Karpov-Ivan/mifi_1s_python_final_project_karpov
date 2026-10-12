"""Периодическое обновление курсов с интервалом из ParserConfig."""

import time

from valutatrade_hub.core.exceptions import ValutaTradeError
from valutatrade_hub.parser_service.updater import create_updater


def run_scheduler() -> None:
    """Обновлять курсы до прерывания пользователем; продолжать после сбоя API."""
    updater = create_updater()
    interval = updater.storage.config.UPDATE_INTERVAL
    while True:
        try:
            updater.run_update()
        except ValutaTradeError as exc:
            updater.logger.error("Периодическое обновление не выполнено: %s", exc)
        time.sleep(interval)


def main() -> None:
    """Запустить таймер через python -m valutatrade_hub.parser_service.scheduler."""
    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("Периодическое обновление остановлено.")
    except ValutaTradeError as exc:
        print(f"Ошибка: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
