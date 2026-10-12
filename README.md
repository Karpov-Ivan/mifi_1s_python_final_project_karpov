# mifi_1s_python_final_project_karpov

**ValutaTrade Hub** — итоговый проект по Python: консольное приложение,
имитирующее работу валютного кошелька. Поддерживает регистрацию, вход,
портфели, покупку/продажу валют и просмотр курсов.

Для запуска нужны `uv` и Python 3.12. Из корня проекта выполните:

```bash
uv sync --locked
uv run --locked valutatrade
```

В открывшейся сессии:

```text
register --username alice --password 1234
login --username alice --password 1234
show-portfolio
get-rate --from USD --to BTC
buy --currency BTC --amount 0.01
sell --currency BTC --amount 0.005
exit
```

Новый портфель пуст: для покупки нужен баланс USD в `data/portfolios.json`.
Покупка списывает USD, продажа начисляет USD. Курсы пока учебные;
кэш хранится в `data/rates.json` и обновляется из заглушки через 5 минут.
Все команды: `help`.
