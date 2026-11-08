"""I segni di chi decide: inizio e fine del tempo di revisione o brief per un compito.

Registra il segno aperto nel campo `Segno` della board (B5-R4), ne calcola i token
dalle trascrizioni alla fine e aggiorna `Token di chi decide` e `Misure parziali`.
Solo libreria standard.
"""

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import sys
from zoneinfo import ZoneInfo

from bottega import configurazione
from bottega.board import Board, BoardComando, BoardProject, ErroreBoard
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ErroreForgia, ForgiaGh
from bottega import misure
from bottega.porte import Porta, porta as porta_fabbrica
from bottega.segni import nota, scrivi_nota


def porta_della_sessione(env: Mapping[str, str]) -> tuple[str, str] | None:
    """Restituisce (porta, sessione) dalle variabili d'ambiente di B5-R4, nell'ordine definito."""
    claude = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if claude:
        return "claude-code", claude

    antigravity = env.get("ANTIGRAVITY_CONVERSATION_ID", "").strip()
    if antigravity:
        return "antigravity", antigravity

    pi = env.get("PI_SESSION_FILE", "").strip()
    if pi:
        return "pi", pi

    copilot = env.get("COPILOT_AGENT_SESSION_ID", "").strip()
    if copilot:
        return "copilot-cli", copilot

    return None


def inizio(
    board: Board,
    numero: int,
    porta: str,
    sessione: str,
    adesso: datetime,
) -> str | None:
    """Apre o sostituisce il segno sul compito indicato.

    Restituisce un messaggio di avviso se un segno era già aperto, altrimenti None.
    """
    if adesso.tzinfo is None:
        adesso = adesso.replace(tzinfo=timezone.utc)

    lav = board.lavoro(numero)
    avviso = None
    if lav is not None and lav.campi.get("Segno"):
        avviso = f"avviso: segno già aperto sul #{numero}: sostituito"

    val_segno = scrivi_nota({
        "porta": porta,
        "sessione": sessione,
        "inizio": adesso.isoformat(),
    })
    board.campo(numero, "Segno", val_segno)
    return avviso


def fine(
    board: Board,
    numero: int,
    porte_e_sessioni: Sequence[tuple[Porta, str]],
    cartella: Path,
    env: Mapping[str, str],
    adesso: datetime,
) -> tuple[int | None, str]:
    """Chiude il segno sul compito indicato e ne aggiunge i token a Token di chi decide.

    Somma la sessione del segno e quelle fornite se diverse, senza mai contare due volte
    lo stesso file. Restituisce (token_aggiunti, messaggio).
    """
    lav = board.lavoro(numero)
    if lav is None:
        return None, f"lavoro #{numero} non trovato sulla board: niente numero"

    segno_testo = lav.campi.get("Segno")
    if not segno_testo:
        return None, f"nessun segno aperto sul #{numero}: niente numero"

    dati = nota(segno_testo)
    porta_segno = dati.get("porta")
    sessione_segno = dati.get("sessione")
    inizio_str = dati.get("inizio")
    if not porta_segno or not sessione_segno or not inizio_str:
        return None, f"segno malformato sul #{numero}: niente numero"

    try:
        dopo = datetime.fromisoformat(inizio_str)
    except Exception as e:
        return None, f"orario d'inizio nel segno non valido ({e}): niente numero"

    if dopo.tzinfo is None:
        dopo = dopo.replace(tzinfo=timezone.utc)
    fino = adesso
    if fino.tzinfo is None:
        fino = fino.replace(tzinfo=timezone.utc)

    try:
        p_segno = porta_fabbrica(porta_segno)
    except ValueError as e:
        return None, f"porta del segno sconosciuta ({e}): niente numero"

    tutte = [(p_segno, sessione_segno)] + list(porte_e_sessioni)

    totale_token = 0
    ha_parziale = False
    file_visti: set[Path] = set()

    for p_obj, s_id in tutte:
        try:
            tr = p_obj.trascrizione(env, cartella, sessione=s_id)
        except OSError as e:
            return None, f"errore nella ricerca della trascrizione: {e}: niente numero"

        if tr is None or not tr.is_file():
            return None, f"trascrizione non trovata per {p_obj.nome} ({s_id}): niente numero"

        tr_risolto = tr.resolve()
        if tr_risolto in file_visti:
            continue
        file_visti.add(tr_risolto)

        try:
            tok = p_obj.token(tr_risolto, dopo, fino)
        except OSError as e:
            return None, f"trascrizione non leggibile: {e}: niente numero"

        totale_token += tok.totale
        if tok.parziale:
            ha_parziale = True

    ok = misure.somma(board, numero, "Token di chi decide", totale_token)
    if not ok:
        return None, "scrittura delle misure non riuscita sulla board: niente numero"

    if ha_parziale:
        attuali = lav.campi.get("Misure parziali", "")
        voci = [v.strip() for v in attuali.split(",") if v.strip()]
        if "Token di chi decide" not in voci:
            voci.append("Token di chi decide")
            board.campo(numero, "Misure parziali", ", ".join(voci))

    board.campo(numero, "Segno", None)
    return totale_token, f"chiuso: aggiunti {totale_token} token a Token di chi decide"


def argomenti_segno(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il sottocomando segno."""
    sottoparsers = parser.add_subparsers(dest="azione", metavar="AZIONE", required=True)

    for az in ("inizio", "fine"):
        sub = sottoparsers.add_parser(az, help=f"segno {az}")
        sub.add_argument("numero", type=int, help="numero del compito")
        sub.add_argument("--porta", choices=configurazione.PORTE, help="porta della sessione")
        sub.add_argument("--sessione", help="identificativo o percorso della sessione")
        sub.add_argument(
            "--configurazione",
            default=PERCORSO_PREDEFINITO,
            metavar="PERCORSO",
            help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
        )


def comando_segno(args: argparse.Namespace, board: Board | None = None) -> int:
    """Esegue il sottocomando segno (inizio o fine)."""
    azione = getattr(args, "azione", None)
    numero = getattr(args, "numero", None)
    if azione not in ("inizio", "fine") or numero is None or not isinstance(numero, int):
        print("errore: azione o numero del compito mancante o non valido", file=sys.stderr)
        return 2

    porta_arg = getattr(args, "porta", None)
    if porta_arg and porta_arg not in configurazione.PORTE:
        print(f"errore: porta sconosciuta: {porta_arg}", file=sys.stderr)
        return 2

    cartella = Path.cwd()
    env = os.environ

    if board is None:
        percorso_cfg = Path(getattr(args, "configurazione", PERCORSO_PREDEFINITO))
        try:
            cfg = leggi_configurazione(percorso_cfg)
        except (ErroreConfigurazione, OSError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
            return 1

        repo = os.environ.get("GITHUB_REPOSITORY", "")
        forgia = ForgiaGh(repo)
        try:
            if cfg.progetto.adattatore:
                board = BoardComando(shlex.split(cfg.progetto.adattatore))
            else:
                if cfg.progetto.project is None:
                    print("errore: configurazione priva di progetto.project e senza adattatore", file=sys.stderr)
                    return 1
                proprietario = forgia.proprietario()
                board = BoardProject(proprietario=proprietario, numero=cfg.progetto.project, repo=repo)
            fuso = ZoneInfo(cfg.progetto.fuso)
        except (ErroreBoard, ErroreForgia, FileNotFoundError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {motivo}", file=sys.stderr)
            return 1
        except Exception:
            fuso = ZoneInfo("UTC")
        adesso = datetime.now(fuso)
    else:
        adesso = datetime.now(timezone.utc)

    sessione_arg = getattr(args, "sessione", None)

    if azione == "inizio":
        if porta_arg:
            p_nome = porta_arg
            if sessione_arg:
                s_id = sessione_arg
            else:
                env_pair = porta_della_sessione(env)
                if env_pair and env_pair[0] == p_nome:
                    s_id = env_pair[1]
                else:
                    p_obj = porta_fabbrica(p_nome)
                    tr = p_obj.trascrizione(env, cartella, sessione=None)
                    if tr is None:
                        print(f"errore: trascrizione per {p_nome} non trovata: niente numero", file=sys.stderr)
                        return 1
                    if p_nome == "pi":
                        s_id = str(tr)
                    elif p_nome == "copilot-cli":
                        s_id = tr.parent.name
                    elif p_nome == "antigravity":
                        s_id = tr.parent.parent.parent.name
                    else:
                        s_id = tr.stem
        else:
            env_pair = porta_della_sessione(env)
            if env_pair:
                p_nome, s_id = env_pair
                if sessione_arg:
                    s_id = sessione_arg
            else:
                candidati = []
                for nome_cand in configurazione.PORTE:
                    p_obj = porta_fabbrica(nome_cand)
                    tr = p_obj.trascrizione(env, cartella, sessione=None)
                    if tr and tr.is_file():
                        candidati.append((tr.stat().st_mtime, nome_cand, tr))
                if not candidati:
                    print("errore: porta o sessione non rilevata dall'ambiente: niente numero", file=sys.stderr)
                    return 1
                candidati.sort(key=lambda x: x[0], reverse=True)
                _, p_nome, tr = candidati[0]
                if sessione_arg:
                    s_id = sessione_arg
                elif p_nome == "pi":
                    s_id = str(tr)
                elif p_nome == "copilot-cli":
                    s_id = tr.parent.name
                elif p_nome == "antigravity":
                    s_id = tr.parent.parent.parent.name
                else:
                    s_id = tr.stem

        avviso = inizio(board, numero, p_nome, s_id, adesso)
        if avviso:
            print(avviso, file=sys.stderr)
        return 0

    if azione == "fine":
        porte_e_sessioni: list[tuple[Porta, str]] = []
        if porta_arg:
            p_nome = porta_arg
            s_id = sessione_arg
            if not s_id:
                env_pair = porta_della_sessione(env)
                if env_pair and env_pair[0] == p_nome:
                    s_id = env_pair[1]
                else:
                    p_obj = porta_fabbrica(p_nome)
                    tr = p_obj.trascrizione(env, cartella, sessione=None)
                    if tr:
                        if p_nome == "pi":
                            s_id = str(tr)
                        elif p_nome == "copilot-cli":
                            s_id = tr.parent.name
                        elif p_nome == "antigravity":
                            s_id = tr.parent.parent.parent.name
                        else:
                            s_id = tr.stem
            if s_id:
                porte_e_sessioni.append((porta_fabbrica(p_nome), s_id))
        else:
            env_pair = porta_della_sessione(env)
            if env_pair:
                p_nome, s_id = env_pair
                if sessione_arg:
                    s_id = sessione_arg
                porte_e_sessioni.append((porta_fabbrica(p_nome), s_id))

        aggiunti, msg = fine(board, numero, porte_e_sessioni, cartella, env, adesso)
        if aggiunti is None:
            print(f"errore: {msg}", file=sys.stderr)
            return 1
        print(f"segno: {msg}")
        return 0

    return 2
