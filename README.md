# mifi_1s_python_final_project_karpov

**ValutaTrade Hub** — итоговый проект по Python: консольное приложение,
имитирующее работу валютного кошелька. Поддерживает регистрацию, вход,
портфели, покупку/продажу валют и просмотр курсов.

Для запуска нужны `uv` и Python 3.12. Из корня проекта выполните:

```bash
uv sync --locked
export EXCHANGERATE_API_KEY="<ваш_ключ>"
uv run --locked valutatrade
```

В открывшейся сессии:

```text
register --username alice --password 1234
login --username alice --password 1234
update-rates
show-rates --top 2
show-portfolio
get-rate --from USD --to BTC
buy --currency BTC --amount 0.01
sell --currency BTC --amount 0.005
exit
```

Новый портфель пуст: для покупки нужен баланс USD в `data/portfolios.json`.
Покупка списывает USD, продажа начисляет USD. Курсы берутся из API;
кэш — `data/rates.json`, история — `data/exchange_rates.json`.
TTL кэша — 5 минут; устаревшие курсы обновляются командой `update-rates`.
Все команды: `help`.

Настройки — секция `[tool.valutatrade]` в `pyproject.toml`.
Логи сделок — `logs/actions.log` в формате JSON с ротацией по размеру.
Логи парсера — `logs/parser.log`.

Команда `update-rates --source exchangerate` обновляет только фиатные курсы;
`show-rates` поддерживает `--currency`, `--top` и `--base`.
Периодическое обновление (интервал задаётся в `parser_service/config.py`):

```bash
uv run --locked python -m valutatrade_hub.parser_service.scheduler
```
