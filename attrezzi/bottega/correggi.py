"""Il comando bottega correggi: crea un compito di correzione e registra l'esito (B14-R2)."""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import sys

from bottega.board import Board, BoardComando, BoardProject, ErroreBoard
import bottega.brief as brief
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ErroreForgia, Forgia, ForgiaGh, repo_del_comando
import bottega.misure as misure
from bottega.segno import tocca

CAMPI_ORIGINE: dict[str, str] = {
    "piano": "Rilievi del piano",
    "brief": "Rilievi del brief",
    "esecuzione": "Rilievi dell'esecuzione",
}


class ErroreCorreggi(Exception):
    """Errore di validazione o scrittura del comando correggi."""

    def __init__(self, messaggio: str, codice: int = 1) -> None:
        super().__init__(messaggio)
        self.codice = codice


def _titolo_di_serie(numero: int, testo: str) -> str:
    prima_riga = next((r.strip() for r in testo.splitlines() if r.strip()), "")[:60]
    if prima_riga:
        return f"Correzione di #{numero}: {prima_riga}"
    return f"Correzione di #{numero}"


def _recinta_fatto_quando(comando: str) -> str:
    recinto = "~~~~" if "```" in comando else "```"
    return f"{recinto}\n{comando}\n{recinto}"


def _trova_lavoro_madre(numero: int, forgia: Forgia, board: Board) -> tuple[int, object]:
    lav_n = board.lavoro(numero)
    if lav_n is not None and lav_n.stato.strip():
        return numero, lav_n

    madre = forgia.madre_di(numero)
    if madre is None:
        raise ErroreCorreggi(
            f"#{numero} non ha uno stato della bottega né un lavoro madre",
            codice=1,
        )

    lav_m = board.lavoro(madre)
    if lav_m is None or not lav_m.stato.strip():
        raise ErroreCorreggi(
            f"il lavoro madre #{madre} di #{numero} non ha uno stato della bottega",
            codice=1,
        )
    return madre, lav_m


def correggi(
    numero: int,
    *,
    forgia: Forgia,
    board: Board,
    brief_file: Path | str | None = None,
    testo: str | None = None,
    titolo: str | None = None,
    origine: str | None = None,
    consiglio: bool = False,
) -> tuple[int, int]:
    """Crea un compito di correzione sotto il lavoro di N e scrive l'esito 'corretto' su N."""
    if (brief_file is None) == (testo is None):
        raise ErroreCorreggi("specificare --brief FILE oppure --testo TESTO (non entrambi)", codice=2)

    if origine is not None and origine not in CAMPI_ORIGINE:
        raise ErroreCorreggi(
            f"--origine deve essere una di {', '.join(CAMPI_ORIGINE)}",
            codice=2,
        )

    corpo: str
    testo_per_titolo: str
    if brief_file is not None:
        percorso = Path(brief_file)
        try:
            corpo = percorso.read_text(encoding="utf-8")
        except OSError as exc:
            motivo = exc.strerror or str(exc)
            raise ErroreCorreggi(f"{percorso}: {motivo}", codice=1) from exc
        if brief.fatto_quando(corpo) is None:
            raise ErroreCorreggi(
                f"{percorso}: manca una sezione '## Fatto quando' con blocco recintato",
                codice=2,
            )
        testo_per_titolo = corpo
    else:
        assert testo is not None
        testo_per_titolo = testo.strip()
        corpo = ""

    m, lav_m = _trova_lavoro_madre(numero, forgia, board)
    iss_m = forgia.issue(m)
    if not getattr(lav_m, "aperta", True) or not iss_m.aperta:
        raise ErroreCorreggi(f"il lavoro #{m} è chiuso", codice=1)

    if testo is not None:
        iss_n = iss_m if numero == m else forgia.issue(numero)
        fq = brief.fatto_quando(iss_n.corpo)
        if fq is None:
            raise ErroreCorreggi(
                f"#{numero} non ha una sezione 'Fatto quando'; specifica --brief FILE",
                codice=2,
            )
        corpo = f"{testo_per_titolo}\n\nCorregge: #{numero}\n\n## Fatto quando\n\n{_recinta_fatto_quando(fq)}\n"

    titolo_finale = titolo.strip() if titolo and titolo.strip() else _titolo_di_serie(numero, testo_per_titolo)

    nuovo = forgia.crea_issue(titolo_finale, corpo, madre=m)

    passi: list[tuple[str, str, Callable[[], None]]] = [
        (
            f"#{nuovo} aggiunto alla board",
            f"aggiungere #{nuovo} alla board",
            lambda: board.aggiungi(nuovo),
        ),
        (
            f"Esito del compito=corretto su #{numero}",
            f"bottega misura {numero} --esito corretto",
            lambda: board.campo(numero, "Esito del compito", "corretto"),
        ),
    ]

    if origine is not None:
        campo_origine = CAMPI_ORIGINE[origine]

        def _scrivi_origine() -> None:
            if not misure.somma(board, numero, campo_origine, 1):
                raise ErroreBoard(f"impossibile aggiornare {campo_origine} su #{numero}")

        passi.append(
            (
                f"{campo_origine} +1 su #{numero}",
                f"bottega misura {numero} --rilievi-{origine} 1",
                _scrivi_origine,
            )
        )

    if consiglio:

        def _scrivi_consiglio() -> None:
            if not misure.somma(board, numero, "Consigli accolti", 1):
                raise ErroreBoard(f"impossibile aggiornare Consigli accolti su #{numero}")

        passi.append(
            (
                f"Consigli accolti +1 su #{numero}",
                f"bottega misura {numero} --consigli-accolti 1",
                _scrivi_consiglio,
            )
        )

    passi.append(
        (
            f"Esito=correzioni su #{m}",
            f"impostare Esito=correzioni su #{m}",
            lambda: board.campo(m, "Esito", "correzioni"),
        )
    )

    fatti: list[str] = [f"issue #{nuovo} creata (madre #{m})"]
    for idx, (desc_fatto, _, azione) in enumerate(passi):
        try:
            azione()
            fatti.append(desc_fatto)
        except Exception as exc:
            mancanti = [manc for _, manc, _ in passi[idx:]]
            dettaglio = (
                f"scrittura interrotta dopo la creazione di #{nuovo} ({exc}). "
                f"Già scritto: {'; '.join(fatti)}. "
                f"Manca da completare a mano: {'; '.join(mancanti)}"
            )
            raise ErroreCorreggi(dettaglio, codice=1) from exc

    return nuovo, m


def argomenti_correggi(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando bottega correggi."""
    parser.add_argument("numero", type=int, help="numero del compito o del lavoro da correggere")
    gruppo = parser.add_mutually_exclusive_group()
    gruppo.add_argument("--brief", type=Path, metavar="FILE", help="file markdown con il brief della correzione")
    gruppo.add_argument("--testo", type=str, metavar="TESTO", help="testo della correzione")
    parser.add_argument("--titolo", type=str, default=None, help="titolo del compito di correzione")
    parser.add_argument(
        "--origine",
        choices=["piano", "brief", "esecuzione"],
        default=None,
        help="origine del rilievo (piano, brief, esecuzione)",
    )
    parser.add_argument(
        "--consiglio",
        action="store_true",
        help="la correzione nasce da un consiglio accolto",
    )
    parser.add_argument(
        "--configurazione",
        type=Path,
        default=Path(PERCORSO_PREDEFINITO),
        help=f"percorso di bottega.toml (di serie: {PERCORSO_PREDEFINITO})",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="repository GitHub nel formato proprietario/repo",
    )


def comando_correggi(
    args: argparse.Namespace,
    forgia: Forgia | None = None,
    board: Board | None = None,
) -> int:
    """Chiede una correzione su un compito o lavoro e scrive l'esito 'corretto'."""
    brief_arg = getattr(args, "brief", None)
    testo_arg = getattr(args, "testo", None)
    if (brief_arg is None) == (testo_arg is None):
        print("correggi: specificare --brief FILE oppure --testo TESTO (non entrambi)", file=sys.stderr)
        return 2

    if forgia is None or board is None:
        percorso_cfg = getattr(args, "configurazione", None) or Path(PERCORSO_PREDEFINITO)
        try:
            cfg = leggi_configurazione(percorso_cfg)
        except (ErroreConfigurazione, OSError) as exc:
            motivo = exc.strerror or str(exc) if isinstance(exc, OSError) else str(exc)
            print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
            return 1

        try:
            repo = repo_del_comando(getattr(args, "repo", None), os.environ)
        except ErroreForgia as exc:
            print(f"errore: {exc}", file=sys.stderr)
            return 1

        if forgia is None:
            forgia = ForgiaGh(repo)
        if board is None:
            try:
                if cfg.progetto.adattatore:
                    board = BoardComando(shlex.split(cfg.progetto.adattatore))
                elif cfg.progetto.project is not None:
                    proprietario = forgia.proprietario()
                    board = BoardProject(proprietario=proprietario, numero=cfg.progetto.project, repo=repo)
                else:
                    print("errore: configurazione priva di progetto.project e senza adattatore", file=sys.stderr)
                    return 1
            except (ErroreForgia, ErroreBoard, OSError) as exc:
                motivo = exc.strerror or str(exc) if isinstance(exc, OSError) else str(exc)
                print(f"errore: {motivo}", file=sys.stderr)
                return 1

    try:
        nuovo, m = correggi(
            args.numero,
            forgia=forgia,
            board=board,
            brief_file=brief_arg,
            testo=testo_arg,
            titolo=getattr(args, "titolo", None),
            origine=getattr(args, "origine", None),
            consiglio=bool(getattr(args, "consiglio", False)),
        )
    except ErroreCorreggi as exc:
        print(f"correggi: {exc}", file=sys.stderr)
        return exc.codice
    except (ErroreBoard, ErroreForgia, OSError) as exc:
        motivo = exc.strerror or str(exc) if isinstance(exc, OSError) else str(exc)
        print(f"correggi: {motivo}", file=sys.stderr)
        return 1

    print(nuovo)
    print(f"poi: bottega lancia {m}")
    try:
        righe_segno = tocca(board, forgia, m, os.environ, Path.cwd(), datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - il segno non cambia mai l'esito del comando
        motivo = exc.strerror or str(exc) if isinstance(exc, OSError) else str(exc)
        righe_segno = [f"segno: {motivo}"]
    for riga in righe_segno:
        print(riga, file=sys.stderr)
    return 0
