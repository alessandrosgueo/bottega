"""Il distributore: sceglie i compiti pronti dalla board e avvia l'esecutore della bottega.

Un solo distributore gira alla volta:
1. Non esegue durante finestre di manutenzione.
2. Si ferma con un avviso se la CI del ramo principale è rossa.
3. Reimposta a «pronto» i lavori «in corso» da più di 7 ore.
4. Considera occupata ogni bottega che ha già un lavoro in corso.
5. Per ogni lavoro pronto (etichetta «bottega: fuori», «esegue: ...», o «liberi» di notte, con «Fatto quando»):
   - Invoca la scelta viva.
   - Se aspetta, incrementa le attese (solo con un precedente) e passa al seguente.
   - Se il candidato richiesto non esiste o vi è conflitto, blocca il lavoro.
   - Se la bottega è occupata, passa al seguente.
   - Altrimenti prende il lavoro, commenta il perché col segno «distributore» e avvia il workflow dell'esecutore.
Solo libreria standard.
"""

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import random
import sys
from zoneinfo import ZoneInfo

from bottega.board import Board, BoardComando, BoardProject, Lavoro
from bottega.brief import fatto_quando
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import Forgia, ForgiaGh
from bottega.scelta import Compito, scegli
from bottega.segni import nota, scrivi_nota

CHIAVE_AVVISO_CI = "ci-ramo-principale"
ORE_SCADENZA_IN_CORSO = 7.0


def _dentro_finestra(adesso: datetime, finestra: str, fuso_str: str) -> bool:
    """Verifica se l'istante adesso ricade nella finestra HH:MM-HH:MM rispetto al fuso indicato."""
    try:
        fuso = ZoneInfo(fuso_str)
    except Exception:
        fuso = ZoneInfo("UTC")

    adesso_fuso = adesso.astimezone(fuso) if adesso.tzinfo else adesso.replace(tzinfo=fuso)
    minuti_correnti = adesso_fuso.hour * 60 + adesso_fuso.minute

    try:
        ini_str, fin_str = finestra.split("-")
        h1, m1 = map(int, ini_str.split(":"))
        h2, m2 = map(int, fin_str.split(":"))
    except ValueError:
        return False

    t1 = h1 * 60 + m1
    t2 = h2 * 60 + m2

    if t1 < t2:
        return t1 <= minuti_correnti < t2
    # Finestra che attraversa la mezzanotte (es. 23:30-01:00)
    return minuti_correnti >= t1 or minuti_correnti < t2


def _in_manutenzione(adesso: datetime, finestre: Sequence[str], fuso_str: str) -> str | None:
    """Restituisce la prima finestra di manutenzione attiva nell'istante indicato, o None."""
    for f in finestre:
        if _dentro_finestra(adesso, f, fuso_str):
            return f
    return None


def _trova_bottega(esecutore: str | None, configurazione: Configurazione) -> str | None:
    """Ricava l'identificativo della bottega associata a un esecutore (id candidato, nome o id bottega)."""
    if not esecutore:
        return None
    if esecutore in configurazione.candidati:
        return configurazione.candidati[esecutore].bottega
    for c in configurazione.candidati.values():
        if c.nome.casefold() == esecutore.casefold():
            return c.bottega
    if esecutore in configurazione.botteghe:
        return esecutore
    return None


def _elegibile_per_etichette(etichette: Sequence[str], liberi: Sequence[str], notte: bool) -> bool:
    """Verifica se il lavoro ha le etichette necessarie per essere preso in considerazione."""
    for et in etichette:
        et_cf = et.casefold().strip()
        if et_cf == "bottega: fuori" or et_cf.startswith("esegue:"):
            return True
        if notte:
            for lib in liberi:
                if et_cf == lib.casefold().strip():
                    return True
    return False


def _ricava_fatto_quando(lav_numero: int, forgia: Forgia) -> str | None:
    """Estrae il comando Fatto quando dal corpo dell'issue o della prima sotto-issue aperta."""
    try:
        sotto = forgia.sotto_issue(lav_numero)
        aperte = [s for s in sotto if s.aperta]
        if aperte:
            return fatto_quando(aperte[0].corpo)
        iss = forgia.issue(lav_numero)
        return fatto_quando(iss.corpo)
    except Exception:
        return None


def distribuisci(
    *,
    configurazione: Configurazione,
    forgia: Forgia,
    board: Board,
    variabili: Mapping[str, str | None],
    adesso: datetime,
    caso: random.Random,
    notte: bool = False,
) -> list[str]:
    """Esegue un giro di distribuzione dei lavori secondo la regola B3-R16."""
    righe: list[str] = []

    # 1. Finestra di manutenzione
    f_manutenzione = _in_manutenzione(adesso, configurazione.progetto.manutenzione, configurazione.progetto.fuso)
    if f_manutenzione is not None:
        riga = f"finestra di manutenzione «{f_manutenzione}»: nessun lavoro avviato"
        print(riga)
        return [riga]

    # 2. Ramo principale rosso
    ramo = forgia.ramo_principale()
    stato_ci = forgia.stato_ci(ramo)
    titolo_avviso = f"Avviso della bottega: ramo principale «{ramo}»"
    if stato_ci == "rosso":
        motivo_avviso = f"La CI del ramo «{ramo}» è rossa; nessun lavoro nuovo finché non torna verde."
        forgia.avviso(CHIAVE_AVVISO_CI, titolo_avviso, motivo_avviso)
        riga = f"ramo principale «{ramo}» rosso: nessun lavoro avviato"
        print(riga)
        return [riga]
    if stato_ci == "verde":
        forgia.avviso(CHIAVE_AVVISO_CI, titolo_avviso, None)

    try:
        fuso_cfg = ZoneInfo(configurazione.progetto.fuso)
    except Exception:
        fuso_cfg = ZoneInfo("UTC")
    adesso_fuso = adesso.astimezone(fuso_cfg) if adesso.tzinfo else adesso.replace(tzinfo=fuso_cfg)

    # 3. Lavori in corso: verifica scadenza (> 7 ore) e botteghe occupate
    lavori_in_corso = board.in_corso()
    botteghe_occupate: set[str] = set()

    for lav in lavori_in_corso:
        valori = nota(lav.nota)
        inizio_str = valori.get("inizio")
        scaduto = False
        if inizio_str:
            try:
                inizio_dt = datetime.fromisoformat(inizio_str)
                if inizio_dt.tzinfo is None:
                    inizio_dt = inizio_dt.replace(tzinfo=adesso_fuso.tzinfo)
                if (adesso_fuso - inizio_dt).total_seconds() > ORE_SCADENZA_IN_CORSO * 3600:
                    scaduto = True
            except Exception:
                pass

        if scaduto:
            board.stato(lav.numero, "pronto")
            riga = f"lavoro {lav.numero}: in corso da oltre 7 ore, reimpostato a pronto"
            righe.append(riga)
            print(riga)
        else:
            bottega = _trova_bottega(lav.esecutore, configurazione)
            if bottega:
                botteghe_occupate.add(bottega)

    # 4. Lavori pronti
    lavori_pronti = board.pronti()
    for lav in lavori_pronti:
        if not _elegibile_per_etichette(lav.etichette, configurazione.progetto.liberi, notte):
            continue

        fq = _ricava_fatto_quando(lav.numero, forgia)
        if fq is None:
            continue

        valori_nota = nota(lav.nota)
        precedente = valori_nota.get("precedente")
        attese_raw = valori_nota.get("attese")
        attese = int(attese_raw) if attese_raw and attese_raw.isdigit() else 0

        # Il distributore lancia solo lavoro fuori: anche con la sola etichetta «esegue:» serve un candidato col runner.
        compito = Compito(
            funzione="eseguire",
            fuori=True,
            etichette=frozenset(lav.etichette),
            precedente=precedente,
            giri_in_attesa=attese,
        )

        scelta = scegli(
            compito=compito,
            configurazione=configurazione,
            risultati={},
            quote=variabili,
            adesso=adesso_fuso,
            caso=caso,
        )

        if scelta.aspetta:
            if precedente is not None:
                nuovi = dict(valori_nota)
                nuovi["attese"] = str(attese + 1)
                board.campo(lav.numero, "Nota del giro", scrivi_nota(nuovi))
            riga = f"lavoro {lav.numero}: in attesa ({scelta.perche})"
            righe.append(riga)
            print(riga)
            continue

        if scelta.candidato is None:
            nuovi = dict(valori_nota)
            nuovi["motivo"] = scelta.perche
            board.stato(lav.numero, "bloccato", nota=scrivi_nota(nuovi))
            forgia.commenta(lav.numero, scelta.perche, "distributore")
            riga = f"lavoro {lav.numero}: bloccato ({scelta.perche})"
            righe.append(riga)
            print(riga)
            continue

        cand = configurazione.candidati[scelta.candidato]
        bottega = cand.bottega
        if bottega in botteghe_occupate:
            riga = f"lavoro {lav.numero}: bottega «{bottega}» occupata, salto"
            righe.append(riga)
            print(riga)
            continue

        nuovi = dict(valori_nota)
        nuovi["inizio"] = adesso_fuso.isoformat()
        nuovi.pop("motivo", None)
        preso = board.prendi(lav.numero, cand.nome, scrivi_nota(nuovi))  # B3-R5: il campo ha il nome
        if not preso:
            riga = f"lavoro {lav.numero}: già preso da altri"
            righe.append(riga)
            print(riga)
            continue

        botteghe_occupate.add(bottega)
        forgia.commenta(lav.numero, scelta.perche, "distributore")
        file_wf = f"bottega-esecutore-{bottega}.yml"
        forgia.avvia_workflow(file_wf, {"lavoro": lav.numero})
        riga = f"lavoro {lav.numero}: assegnato a «{scelta.candidato}» ({bottega}), workflow {file_wf} avviato"
        righe.append(riga)
        print(riga)

    return righe


def argomenti_distribuisci(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando distribuisci."""
    parser.add_argument(
        "--notte",
        action="store_true",
        help="modalità notte: considera anche le etichette dei lavori liberi",
    )
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="PERCORSO",
        help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
    )


def comando_distribuisci(args: argparse.Namespace) -> int:
    """Distribuisce i lavori pronti della board: esce 0 se eseguito, 1 con errore."""
    percorso_cfg = Path(args.file)
    try:
        cfg = leggi_configurazione(percorso_cfg)
    except (ErroreConfigurazione, OSError) as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
        return 1

    variabili_raw = os.environ.get("BOTTEGA_VARIABILI", "{}")
    try:
        variabili = json.loads(variabili_raw)
        if not isinstance(variabili, dict):
            variabili = {}
    except Exception:
        variabili = {}

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    forgia = ForgiaGh(repo)
    if cfg.progetto.adattatore:
        board = BoardComando([cfg.progetto.adattatore])
    else:
        if cfg.progetto.project is None:
            print("errore: configurazione priva di progetto.project e senza adattatore", file=sys.stderr)
            return 1
        proprietario = forgia.proprietario()
        board = BoardProject(proprietario=proprietario, numero=cfg.progetto.project, repo=repo)

    try:
        fuso = ZoneInfo(cfg.progetto.fuso)
    except Exception:
        fuso = ZoneInfo("UTC")
    adesso = datetime.now(fuso)
    caso = random.Random()

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=caso,
        notte=args.notte,
    )
    return 0
