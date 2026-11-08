"""Ingresso del comando: `python3 -m bottega [COMANDO] [ARGOMENTI]`."""

import argparse
import sys
from collections.abc import Callable

from bottega import VERSIONE

# Nome del sottocomando -> funzione che riceve gli argomenti letti e restituisce l'esito (0 = tutto bene).
COMANDI: dict[str, Callable[[argparse.Namespace], int]] = {}


class _Formattatore(argparse.HelpFormatter):
    """Mette «uso:» davanti all'uso: argparse ci mette «usage:» di serie."""

    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, prefix or "uso: ")


class _Parser(argparse.ArgumentParser):
    """Parser con l'uso in italiano e le opzioni nel gruppo «opzioni», anche nei sottocomandi."""

    def __init__(self, **kwargs):
        kwargs.setdefault("formatter_class", _Formattatore)
        kwargs["add_help"] = False
        super().__init__(**kwargs)
        self.opzioni = self.add_argument_group("opzioni")
        self.opzioni.add_argument("-h", "--help", action="help", help="mostra questo aiuto ed esci")


def costruisci_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="bottega")
    parser.opzioni.add_argument(
        "--version", action="version", version=f"bottega {VERSIONE}", help="mostra la versione ed esci"
    )
    sottocomandi = parser.add_subparsers(dest="comando", title="comandi", metavar="COMANDO", parser_class=_Parser)
    for nome in COMANDI:
        sottocomandi.add_parser(nome)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = costruisci_parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return 2
    return COMANDI[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())
