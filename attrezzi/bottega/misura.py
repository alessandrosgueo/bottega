"""Il comando bottega misura: scrive le misure e l'esito di un compito sulla board (B5-R7).

Solo libreria standard.
"""

import argparse
import os
from pathlib import Path
import shlex
import sys

from bottega.board import Board, BoardComando, BoardProject
from bottega.configurazione import (
    PORTE,
    PERCORSO_PREDEFINITO,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ForgiaGh
import bottega.misure as misure

OPZIONI_MISURA: tuple[str, ...] = (
    "esito",
    "porta",
    "dove",
    "durata",
    "giri",
    "token_esecutore",
    "token_decisore",
    "rilievi_piano",
    "rilievi_brief",
    "rilievi_esecuzione",
    "consigli_accolti",
    "consigli_respinti",
)

MAPPA_ESITO: dict[str, str] = {
    "unito": "unito com'era",
    "corretto": "corretto",
    "rifiutato": "rifiutato",
}


def argomenti_misura(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando bottega misura."""
    parser.add_argument("numero", type=int, help="numero del compito")
    parser.add_argument(
        "--esito",
        choices=["unito", "corretto", "rifiutato"],
        help="esito della revisione (unito, corretto, rifiutato)",
    )
    parser.add_argument(
        "--rilievi-piano",
        type=int,
        help="numero di rilievi sul piano",
    )
    parser.add_argument(
        "--rilievi-brief",
        type=int,
        help="numero di rilievi sul brief",
    )
    parser.add_argument(
        "--rilievi-esecuzione",
        type=int,
        help="numero di rilievi sull'esecuzione",
    )
    parser.add_argument(
        "--consigli-accolti",
        type=int,
        help="numero di consigli accolti",
    )
    parser.add_argument(
        "--consigli-respinti",
        type=int,
        help="numero di consigli respinti",
    )
    parser.add_argument(
        "--porta",
        type=str,
        help="porta utilizzata",
    )
    parser.add_argument(
        "--dove",
        type=str,
        help="dove è stato svolto il lavoro (sessione o fuori)",
    )
    parser.add_argument(
        "--durata",
        type=int,
        help="durata in secondi",
    )
    parser.add_argument(
        "--giri",
        type=int,
        help="numero di giri",
    )
    parser.add_argument(
        "--token-esecutore",
        type=int,
        help="token spesi dall'esecutore",
    )
    parser.add_argument(
        "--token-decisore",
        type=int,
        help="token di chi decide (per un numero che `segno fine` ha letto ma non ha potuto scrivere)",
    )
    parser.add_argument(
        "--configurazione",
        type=Path,
        default=Path(PERCORSO_PREDEFINITO),
        help=f"percorso di bottega.toml (di serie: {PERCORSO_PREDEFINITO})",
    )


def comando_misura(args: argparse.Namespace, board: Board | None = None) -> int:
    """Scrive le misure di un compito sulla board."""
    if not any(getattr(args, opt, None) is not None for opt in OPZIONI_MISURA):
        print("misura: nessuna opzione specificata", file=sys.stderr)
        return 2

    dove = getattr(args, "dove", None)
    if dove is not None and dove not in ("sessione", "fuori"):
        print("misura: --dove deve essere 'sessione' o 'fuori'", file=sys.stderr)
        return 2

    for opt in OPZIONI_MISURA:
        val = getattr(args, opt, None)
        if isinstance(val, int) and not isinstance(val, bool) and val < 0:
            print(f"misura: --{opt.replace('_', '-')} non può essere negativo", file=sys.stderr)
            return 2

    porta_arg = getattr(args, "porta", None)
    if porta_arg is not None and porta_arg not in PORTE:
        print(f"misura: --porta deve essere una di {', '.join(PORTE)}", file=sys.stderr)
        return 2

    esito = getattr(args, "esito", None)
    if esito is not None and esito not in MAPPA_ESITO:
        print("misura: --esito deve essere 'unito', 'corretto' o 'rifiutato'", file=sys.stderr)
        return 2

    if board is None:
        percorso_cfg = getattr(args, "configurazione", None) or Path(PERCORSO_PREDEFINITO)
        try:
            cfg = leggi_configurazione(percorso_cfg)
        except (ErroreConfigurazione, OSError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
            return 1

        repo = os.environ.get("GITHUB_REPOSITORY", "")
        forgia = ForgiaGh(repo)
        if cfg.progetto.adattatore:
            board = BoardComando(shlex.split(cfg.progetto.adattatore))
        elif cfg.progetto.project is not None:
            proprietario = forgia.proprietario()
            board = BoardProject(proprietario=proprietario, numero=cfg.progetto.project, repo=repo)
        else:
            print("errore: configurazione priva di progetto.project e senza adattatore", file=sys.stderr)
            return 1

    numero = args.numero
    successo = True

    if esito is not None:
        valore_esito = MAPPA_ESITO[esito]
        try:
            board.campo(numero, "Esito del compito", valore_esito)
        except Exception as exc:
            print(f"misura: errore scrittura Esito del compito per #{numero}: {exc}", file=sys.stderr)
            successo = False

    porta = getattr(args, "porta", None)
    if porta is not None:
        try:
            board.campo(numero, "Porta", porta)
        except Exception as exc:
            print(f"misura: errore scrittura Porta per #{numero}: {exc}", file=sys.stderr)
            successo = False

    if dove is not None:
        try:
            board.campo(numero, "Dove", dove)
        except Exception as exc:
            print(f"misura: errore scrittura Dove per #{numero}: {exc}", file=sys.stderr)
            successo = False

    campi_numerici: tuple[tuple[str, str], ...] = (
        ("durata", "Durata"),
        ("giri", "Giri"),
        ("token_esecutore", "Token esecutore"),
        ("token_decisore", "Token di chi decide"),
        ("rilievi_piano", "Rilievi del piano"),
        ("rilievi_brief", "Rilievi del brief"),
        ("rilievi_esecuzione", "Rilievi dell'esecuzione"),
        ("consigli_accolti", "Consigli accolti"),
        ("consigli_respinti", "Consigli respinti"),
    )

    for attr, nome_campo in campi_numerici:
        val = getattr(args, attr, None)
        if val is not None:
            if not misure.somma(board, numero, nome_campo, val):
                successo = False

    return 0 if successo else 1
