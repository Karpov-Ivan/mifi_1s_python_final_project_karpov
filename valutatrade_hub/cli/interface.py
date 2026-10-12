"""Парсинг команд и отображение результатов бизнес-операций."""

import argparse
import shlex
import sys

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import CURRENCIES, get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValidationError,
    ValutaTradeError,
)
from valutatrade_hub.core.usecases import CoreService, PortfolioView, TradeResult
from valutatrade_hub.core.utils import RateQuote


class HelpRequested(Exception):
    """Справка напечатана; интерактивная сессия должна продолжиться."""


class CommandParser(argparse.ArgumentParser):
    """Парсер, который не завершает приложение при ошибках ввода."""

    def error(self, message: str) -> None:
        """Преобразовать ошибку аргументов в пользовательскую ошибку."""
        raise ValidationError(f"Ошибка аргументов: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        """После справки вернуть управление консольному циклу."""
        if status:
            raise ValidationError(message or "Некорректная команда")
        raise HelpRequested


def build_parser() -> CommandParser:
    """Описать аргументы всех пользовательских команд."""
    parser = CommandParser(prog="valutatrade", description="Валютный кошелёк")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, description in (("register", "Регистрация"), ("login", "Вход")):
        child = commands.add_parser(command, help=description)
        child.add_argument("--username", required=True)
        child.add_argument("--password", required=True)
    portfolio = commands.add_parser("show-portfolio", help="Портфель и балансы")
    portfolio.add_argument("--base")
    for command, description in (("buy", "Купить валюту"), ("sell", "Продать валюту")):
        child = commands.add_parser(command, help=description)
        child.add_argument("--currency", required=True)
        child.add_argument("--amount", required=True, type=float)
    rates = commands.add_parser("get-rate", help="Курс одной валюты к другой")
    rates.add_argument("--from", dest="from_currency", required=True)
    rates.add_argument("--to", dest="to_currency", required=True)
    commands.add_parser("help", help="Справка")
    commands.add_parser("exit", help="Завершить сессию")
    return parser


class CommandInterface:
    """Оркестрировать команды, сохраняя сессию в CoreService."""

    def __init__(self, service: CoreService | None = None) -> None:
        self.service = service or CoreService()
        self.parser = build_parser()
        self.running = True

    @staticmethod
    def _source_notice(quote: RateQuote) -> None:
        if "Stub" in quote.source:
            print("Источник: учебная заглушка, не рыночные курсы.")
        if quote.refreshed:
            print("Кэш отсутствовал или устарел; курс обновлён из заглушки.")

    @staticmethod
    def _show_portfolio(view: PortfolioView) -> None:
        print(f"Портфель пользователя '{view.username}' (база: {view.base}):")
        if not view.rows:
            print("Портфель пуст. Кошельков пока нет.")
            return
        table = PrettyTable(["Валюта", "Баланс", f"Стоимость в {view.base}"])
        for code, balance, value in view.rows:
            table.add_row([code, f"{balance:.4f}", f"{value:,.2f}"])
        print(table)
        print(f"ИТОГО: {view.total:,.2f} {view.base}")
        if any("Stub" in source for source in view.sources):
            print("Оценка использует учебную заглушку курсов.")

    def _show_trade(self, result: TradeResult, *, buying: bool) -> None:
        action = "Покупка" if buying else "Продажа"
        print(
            f"{action} выполнена: {result.amount:.4f} {result.currency} "
            f"по курсу {result.quote.rate:.2f} USD/{result.currency}"
        )
        print(get_currency(result.currency).get_display_info())
        print("Изменения в портфеле:")
        print(
            f"- {result.currency}: было {result.before:.4f} → стало {result.after:.4f}"
        )
        if result.currency != "USD":
            print(f"- USD: было {result.usd_before:.4f} → стало {result.usd_after:.4f}")
        label = "Оценочная стоимость покупки" if buying else "Оценочная выручка"
        print(f"{label}: {result.total:,.2f} USD")
        self._source_notice(result.quote)

    def execute(self, command: str | list[str]) -> bool:
        """Выполнить одну команду и сообщить, была ли она успешной."""
        try:
            try:
                tokens = shlex.split(command) if isinstance(command, str) else command
            except ValueError as exc:
                raise ValidationError(f"Не удалось разобрать команду: {exc}") from exc
            if not tokens:
                return True
            args = self.parser.parse_args(tokens)
            match args.command:
                case "register":
                    user = self.service.register(args.username, args.password)
                    print(
                        f"Пользователь '{user.username}' зарегистрирован "
                        f"(id={user.user_id}). Войдите: "
                        f"login --username '{user.username}' --password ****"
                    )
                case "login":
                    user = self.service.login(args.username, args.password)
                    print(f"Вы вошли как '{user.username}'")
                case "show-portfolio":
                    self._show_portfolio(self.service.show_portfolio(args.base))
                case "buy":
                    self._show_trade(
                        self.service.buy(args.currency, args.amount), buying=True
                    )
                case "sell":
                    self._show_trade(
                        self.service.sell(args.currency, args.amount), buying=False
                    )
                case "get-rate":
                    quote = self.service.get_rate(args.from_currency, args.to_currency)
                    origin = args.from_currency.strip().upper()
                    target = args.to_currency.strip().upper()
                    print(
                        f"Курс {origin}→{target}: {quote.rate:.8f} "
                        f"(обновлено: {quote.updated_at.isoformat()})"
                    )
                    print(f"Обратный курс {target}→{origin}: {1 / quote.rate:.8f}")
                    self._source_notice(quote)
                case "help":
                    self.parser.print_help()
                case "exit":
                    self.running = False
        except HelpRequested:
            return True
        except InsufficientFundsError as exc:
            print(exc)
            return False
        except CurrencyNotFoundError as exc:
            print(exc)
            print("Поддерживаемые валюты: " + ", ".join(sorted(CURRENCIES)))
            return False
        except ApiRequestError as exc:
            print(exc)
            print("Повторите попытку позже или проверьте подключение к сети.")
            return False
        except ValutaTradeError as exc:
            print(f"Ошибка: {exc}")
            return False
        return True

    def run(self) -> None:
        """Читать команды до exit, EOF или прерывания с клавиатуры."""
        print("ValutaTrade Hub. Справка: help. Выход: exit.")
        while self.running:
            try:
                command = input("> ")
                self.execute(command)
            except (EOFError, KeyboardInterrupt):
                print()
                break


def main() -> None:
    """Запустить интерактивный CLI или выполнить команду из аргументов."""
    try:
        interface = CommandInterface()
    except ValutaTradeError as exc:
        print(f"Ошибка: {exc}")
        raise SystemExit(1) from exc
    if len(sys.argv) > 1:
        if not interface.execute(sys.argv[1:]):
            raise SystemExit(1)
    else:
        interface.run()
