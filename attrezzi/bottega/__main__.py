"""Ingresso del comando: `python3 -m bottega [COMANDO] [ARGOMENTI]`."""

import argparse
import sys
from collections.abc import Callable

from bottega import VERSIONE
from bottega.casi import argomenti_casi, comando_casi
from bottega.configurazione import argomenti_configurazione, comando_configurazione
from bottega.distributore import argomenti_distribuisci, comando_distribuisci
from bottega.dividi import argomenti_dividi, comando_dividi
from bottega.pubblico import argomenti_controlla_pubblico, controlla_pubblico
from bottega.scelta import argomenti_scegli, comando_scegli

# Nome del sottocomando -> funzione che riceve gli argomenti letti e restituisce l'esito (0 = tutto bene).
COMANDI: dict[str, Callable[[argparse.Namespace], int]] = {
    "controlla-pubblico": controlla_pubblico,
    "casi": comando_casi,
    "configurazione": comando_configurazione,
    "scegli": comando_scegli,
    "distribuisci": comando_distribuisci,
    "dividi": comando_dividi,
}
# Nome del sottocomando -> funzione che aggiunge i suoi argomenti al sottoparser (solo i comandi che ne hanno).
ARGOMENTI: dict[str, Callable[[argparse.ArgumentParser], None]] = {
    "controlla-pubblico": argomenti_controlla_pubblico,
    "casi": argomenti_casi,
    "configurazione": argomenti_configurazione,
    "scegli": argomenti_scegli,
    "distribuisci": argomenti_distribuisci,
    "dividi": argomenti_dividi,
}


class _Formattatore(argparse.HelpFormatter):
    """Mette «uso:» davanti all'uso: argparse ci mette «usage:» di serie."""

    def add_usage(self, usage, actions, groups, prefix=None):
        # Il prefisso vuoto serve ad add_subparsers per ricavare il nome del comando: non va riempito.
        super().add_usage(usage, actions, groups, "uso: " if prefix is None else prefix)


class _Parser(argparse.ArgumentParser):
    """Parser con l'uso in italiano e le opzioni nel gruppo «opzioni», anche nei sottocomandi."""

    def __init__(self, **kwargs):
        kwargs.setdefault("formatter_class", _Formattatore)
        kwargs["add_help"] = False
        super().__init__(**kwargs)
        self.opzioni = self.add_argument_group("opzioni")
        self.opzioni.add_argument("-h", "--help", action="help", help="mostra questo aiuto ed esci")

    def add_argument(self, *args, **kwargs):
        """Le opzioni, anche quelle dei sottocomandi, finiscono nel gruppo «opzioni»; i posizionali restano fuori."""
        if args and not args[0].startswith("-"):
            return super().add_argument(*args, **kwargs)
        return self.opzioni.add_argument(*args, **kwargs)


def _prima_riga(funzione: Callable) -> str:
    """Prima riga della docstring del comando: è la scritta che l'elenco dei comandi mostra."""
    righe = (funzione.__doc__ or "").strip().splitlines()
    return righe[0].strip() if righe else ""


def costruisci_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="bottega")
    parser.opzioni.add_argument(
        "--version", action="version", version=f"bottega {VERSIONE}", help="mostra la versione ed esci"
    )
    sottocomandi = parser.add_subparsers(dest="comando", title="comandi", metavar="COMANDO", parser_class=_Parser)
    for nome, funzione in COMANDI.items():
        sottoparser = sottocomandi.add_parser(nome, help=_prima_riga(funzione))
        if nome in ARGOMENTI:
            ARGOMENTI[nome](sottoparser)
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
