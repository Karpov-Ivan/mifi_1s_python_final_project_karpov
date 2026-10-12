# mifi_1s_python_final_project_karpov

**ValutaTrade Hub** — консольный валютный кошелёк: регистрация и вход,
портфель, покупка/продажа фиатных и криптовалют, курсы из внешних API.
Покупка списывает USD, продажа начисляет USD.

## Структура

```text
valutatrade_hub/
├── core/             # Модели, валюты, операции, исключения
├── infra/            # Настройки и JSON-хранилище
├── parser_service/   # API-клиенты и обновление курсов
├── cli/              # Команды и вывод
├── logging_config.py # JSON-логи и ротация
└── decorators.py     # @log_action для buy/sell
data/                # users.json, portfolios.json, rates.json, exchange_rates.json
main.py              # Точка входа
pyproject.toml       # Зависимости и настройки
uv.lock              # Версии зависимостей
Makefile             # Команды разработки
```

## Установка и запуск

Требуются `uv` и Python 3.12. Команды выполняются из корня проекта:

```bash
uv sync --locked
export EXCHANGERATE_API_KEY="<ключ ExchangeRate-API>"
uv run --locked valutatrade
```

Ключи хранятся в переменных окружения, а не в коде.

## Команды CLI

```text
register --username alice --password 1234
login --username alice --password 1234
update-rates
show-rates --top 2
show-rates --currency RUB --base EUR
show-portfolio --base USD
buy --currency BTC --amount 0.001
sell --currency BTC --amount 0.0005
get-rate --from USD --to BTC
help
exit
```

Новый портфель пуст; покупка требует USD-баланс в `data/portfolios.json`.
Просмотр портфеля, покупка и продажа доступны после `login`.

## Кэш и Parser Service

`data/rates.json` — кэш последних курсов, `data/exchange_rates.json` — история.
TTL по умолчанию — 300 секунд; устаревший курс требует `update-rates`.
Настройки Core — `[tool.valutatrade]` в `pyproject.toml`, парсера —
`valutatrade_hub/parser_service/config.py`.

Ручное обновление: `update-rates`; один источник:
`update-rates --source coingecko` или `update-rates --source exchangerate`.
Периодический запуск (интервал по умолчанию 300 секунд; остановка — Ctrl+C):

```bash
uv run --locked python -m valutatrade_hub.parser_service.scheduler
```

## Демонстрация

[Полный цикл работы приложения — asciinema](https://asciinema.org/a/WL21F10HAlkVlN8Y).
