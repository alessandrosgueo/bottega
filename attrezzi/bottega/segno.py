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
from bottega.board import Board, BoardComando, BoardProject, ErroreBoard, Lavoro
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ErroreForgia, Forgia, ForgiaGh
from bottega import misure
from bottega.porte import Porta, porta as porta_fabbrica
from bottega.segni import nota, scrivi_nota


def _messaggio_errore(exc: BaseException) -> str:
    return exc.strerror or str(exc) if isinstance(exc, OSError) else str(exc)


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
        # Solo il nome del file: il percorso contiene la casa e la cartella di chi decide.
        return "pi", Path(pi).name

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

    # Una lettura sola: l'elenco serve anche all'avviso dei segni doppi; senza elenco, il solo lavoro.
    try:
        tutti = board.elenco()
        lav = next((x for x in tutti if x.numero == numero), None)
    except Exception:  # noqa: BLE001 - l'avviso dei segni doppi è un di più
        tutti = []
        lav = board.lavoro(numero)
    avviso = None
    if lav is not None and lav.campi.get("Segno"):
        avviso = f"avviso: segno già aperto sul #{numero}: sostituito"
    altri = [
        altro.numero
        for altro in tutti
        if altro.numero != numero and nota(altro.campi.get("Segno", "")).get("sessione") == sessione
    ]
    if altri:
        elenco_altri = ", ".join(f"#{n}" for n in altri)
        avviso = (avviso + "; " if avviso else "avviso: ") + (
            f"la stessa sessione ha un segno aperto anche su {elenco_altri}: i token si conteranno su tutti e due"
        )

    val_segno = scrivi_nota({
        "porta": porta,
        "sessione": sessione,
        "inizio": adesso.isoformat(),
    })
    board.campo(numero, "Segno", val_segno)
    return avviso


def _aggiungi_misura_parziale(board: Board, numero: int, attuali: str | None = None) -> None:
    if attuali is None:
        lav = board.lavoro(numero)
        if lav is None:
            return
        attuali = lav.campi.get("Misure parziali", "")
    voci = [v.strip() for v in attuali.split(",") if v.strip()]
    if "Token di chi decide" not in voci:
        voci.append("Token di chi decide")
        board.campo(numero, "Misure parziali", ", ".join(voci))


def _fine_con_stato(
    board: Board,
    numero: int,
    porte_e_sessioni: Sequence[tuple[Porta, str]],
    cartella: Path,
    env: Mapping[str, str],
    adesso: datetime,
    fino: datetime | None = None,
    compiti: Sequence[int] = (),
) -> tuple[int | None, str, str]:
    """Chiude il segno sul compito indicato e ne aggiunge i token a Token di chi decide.

    Restituisce (token_aggiunti, messaggio, stato) dove stato è 'ok', 'chiuso_vuoto' o 'errore'.
    """
    lav = board.lavoro(numero)
    if lav is None:
        return None, f"lavoro #{numero} non trovato sulla board: niente numero", "errore"

    segno_testo = lav.campi.get("Segno")
    if not segno_testo:
        return None, f"nessun segno aperto sul #{numero}: niente numero", "errore"

    dati = nota(segno_testo)
    porta_segno = dati.get("porta")
    sessione_segno = dati.get("sessione")
    inizio_str = dati.get("inizio")
    if not porta_segno or not sessione_segno or not inizio_str:
        return None, f"segno malformato sul #{numero}: niente numero", "errore"

    try:
        dopo = datetime.fromisoformat(inizio_str)
    except Exception as e:
        return None, f"orario d'inizio nel segno non valido ({e}): niente numero", "errore"

    if dopo.tzinfo is None:
        dopo = dopo.replace(tzinfo=timezone.utc)
    fino_passato = fino is not None
    fino_eff = fino if fino is not None else adesso
    if fino_eff.tzinfo is None:
        fino_eff = fino_eff.replace(tzinfo=timezone.utc)

    try:
        p_segno = porta_fabbrica(porta_segno)
    except ValueError as e:
        return None, f"porta del segno sconosciuta ({e}): niente numero", "errore"

    tutte = [(p_segno, sessione_segno)] + list(porte_e_sessioni)

    totale_token = 0
    totale_messaggi = 0
    ha_parziale = False
    file_visti: set[Path] = set()
    messaggi_visti: set[str] = set()

    for p_obj, s_id in tutte:
        try:
            tr = p_obj.trascrizione(env, cartella, sessione=s_id)
        except OSError as e:
            return None, f"errore nella ricerca della trascrizione: {e}: niente numero", "errore"

        if tr is None or not tr.is_file():
            return None, f"trascrizione non trovata per {p_obj.nome} ({s_id}): niente numero", "errore"

        tr_risolto = tr.resolve()
        if tr_risolto in file_visti:
            continue
        file_visti.add(tr_risolto)

        try:
            tok = p_obj.token(tr_risolto, dopo, fino_eff, visti=messaggi_visti)
        except OSError as e:
            return None, f"trascrizione non leggibile: {e}: niente numero", "errore"

        totale_token += tok.totale
        totale_messaggi += tok.messaggi
        if tok.parziale:
            ha_parziale = True

    if totale_messaggi == 0:
        if not fino_passato:
            # Nessun messaggio nell'intervallo: il segno resta aperto per riprovare con --sessione.
            return (
                None,
                "nessun messaggio fra l'inizio e adesso nella trascrizione: niente numero (segno ancora aperto)",
                "errore",
            )
        try:
            board.campo(numero, "Segno", None)
        except Exception as e:  # noqa: BLE001 - un guasto qui lascia tutto com'era
            return None, f"segno non chiuso ({e}): niente numero, riprova", "errore"
        return (
            None,
            "nessun messaggio fra l'inizio e la chiusura nella trascrizione: segno chiuso senza numero",
            "chiuso_vuoto",
        )

    # Prima si chiude il segno: se poi la somma non riesce il numero si perde, ma non si conta mai due volte.
    try:
        board.campo(numero, "Segno", None)
    except Exception as e:  # noqa: BLE001 - un guasto qui lascia tutto com'era
        return None, f"segno non chiuso ({e}): niente numero, riprova", "errore"

    compiti_lista = list(compiti)
    if not compiti_lista:
        ok = misure.somma(board, numero, "Token di chi decide", totale_token)
        if not ok:
            return (
                None,
                f"segno chiuso ma la somma di {totale_token} token non è riuscita sulla board: per scriverli a mano "
                f"`bottega misura {numero} --token-decisore {totale_token}`",
                "errore",
            )
        if ha_parziale:
            try:
                _aggiungi_misura_parziale(board, numero, lav.campi.get("Misure parziali", ""))
            except Exception as e:  # noqa: BLE001 - il numero è già scritto
                return (
                    totale_token,
                    f"chiuso: aggiunti {totale_token} token, ma «Misure parziali» non è stato aggiornato ({e})",
                    "ok",
                )
        return totale_token, f"chiuso: aggiunti {totale_token} token a Token di chi decide", "ok"

    base, resto = divmod(totale_token, len(compiti_lista))
    falliti: list[tuple[int, int]] = []
    parziali_falliti: list[int] = []
    for idx, comp_num in enumerate(compiti_lista):
        quota = base + (1 if idx < resto else 0)
        if not misure.somma(board, comp_num, "Token di chi decide", quota):
            falliti.append((comp_num, quota))
        elif ha_parziale:
            try:
                _aggiungi_misura_parziale(board, comp_num)
            except Exception:  # noqa: BLE001 - il numero è già scritto
                parziali_falliti.append(comp_num)

    if falliti:
        comandi = ", ".join(f"`bottega misura {c} --token-decisore {q}`" for c, q in falliti)
        return (
            None,
            f"segno chiuso ma la somma non è riuscita su tutti i compiti: per scriverli a mano {comandi}",
            "errore",
        )
    if parziali_falliti:
        elenco_p = ", ".join(f"#{c}" for c in parziali_falliti)
        return (
            totale_token,
            f"chiuso: aggiunti {totale_token} token su {len(compiti_lista)} compiti, "
            f"ma «Misure parziali» non è stato aggiornato su {elenco_p}",
            "ok",
        )
    return (
        totale_token,
        f"chiuso: aggiunti {totale_token} token a Token di chi decide su {len(compiti_lista)} compiti",
        "ok",
    )


def fine(
    board: Board,
    numero: int,
    porte_e_sessioni: Sequence[tuple[Porta, str]],
    cartella: Path,
    env: Mapping[str, str],
    adesso: datetime,
    fino: datetime | None = None,
    compiti: Sequence[int] = (),
) -> tuple[int | None, str]:
    """Chiude il segno sul compito indicato e ne aggiunge i token a Token di chi decide.

    Somma la sessione del segno e quelle fornite se diverse, senza mai contare due volte
    lo stesso file. Se `compiti` non è vuoto divide in parti uguali (resto al primo).
    Restituisce (token_aggiunti, messaggio).
    """
    aggiunti, msg, _ = _fine_con_stato(
        board,
        numero,
        porte_e_sessioni,
        cartella,
        env,
        adesso,
        fino=fino,
        compiti=compiti,
    )
    return aggiunti, msg


def chiudi_segni_dei_chiusi(
    board: Board,
    forgia: Forgia,
    env: Mapping[str, str],
    cartella: Path,
    adesso: datetime,
    tutti: Sequence[Lavoro] | None = None,
) -> list[str]:
    """Chiude i segni rimasti aperti su lavori chiusi all'ora della chiusura (B14-R5).

    `tutti` è l'elenco già letto da chi chiama: ogni lettura dell'elenco può costare secondi, e se ne fa una sola.
    """
    righe: list[str] = []
    if tutti is None:
        try:
            tutti = board.elenco()
        except Exception as exc:  # noqa: BLE001 - non solleva mai
            return [f"segno: {_messaggio_errore(exc)}"]

    for lav in tutti:
        if lav.aperta or not lav.campi.get("Segno"):
            continue
        try:
            chiusura = forgia.chiusura(lav.numero)
            if chiusura is None:
                continue
            _, ora_chiusura = chiusura
            compiti = [iss.numero for iss in forgia.sotto_issue(lav.numero)]
            _, msg, stato = _fine_con_stato(
                board,
                lav.numero,
                (),
                cartella,
                env,
                adesso,
                fino=ora_chiusura,
                compiti=compiti,
            )
            if stato == "errore":
                righe.append(f"segno: #{lav.numero}: {msg}")
        except Exception as exc:  # noqa: BLE001 - un lavoro rotto non blocca gli altri
            righe.append(f"segno: #{lav.numero}: {_messaggio_errore(exc)}")
    return righe


def tocca(
    board: Board,
    forgia: Forgia,
    numero: int,
    env: Mapping[str, str],
    cartella: Path,
    adesso: datetime,
) -> list[str]:
    """Aggiorna il segno della sessione corrente sul lavoro indicato (B14-R4).

    Non fa nulla se non c'è una sessione riconosciuta in `env`. Non solleva mai:
    restituisce eventuali errori/avvisi da stampare su stderr. Legge l'elenco una volta sola.
    """
    sess = porta_della_sessione(env)
    if sess is None:
        return []
    porta_nome, sessione_id = sess

    try:
        tutti = board.elenco()
    except Exception as exc:  # noqa: BLE001 - non solleva mai
        return [f"segno: {_messaggio_errore(exc)}"]

    righe = chiudi_segni_dei_chiusi(board, forgia, env, cartella, adesso, tutti=tutti)

    chiusura_fallita_su: int | None = None
    for lav in tutti:
        if not lav.aperta or lav.numero == numero:
            continue
        segno_val = lav.campi.get("Segno", "")
        if not segno_val or nota(segno_val).get("sessione") != sessione_id:
            continue
        try:
            compiti = [iss.numero for iss in forgia.sotto_issue(lav.numero)]
            p_corrente = porta_fabbrica(porta_nome)
            # `fino` passato: una finestra senza messaggi (due lavori toccati di fila) si chiude senza numero. Restando
            # aperta, i messaggi di dopo si conterebbero su tutti e due i lavori.
            _, msg, stato = _fine_con_stato(
                board,
                lav.numero,
                [(p_corrente, sessione_id)],
                cartella,
                env,
                adesso,
                fino=adesso,
                compiti=compiti,
            )
            if stato == "errore":
                righe.append(f"segno: #{lav.numero}: {msg}")
                if chiusura_fallita_su is None:
                    chiusura_fallita_su = lav.numero
        except Exception as exc:  # noqa: BLE001 - non solleva mai
            righe.append(f"segno: #{lav.numero}: {_messaggio_errore(exc)}")
            if chiusura_fallita_su is None:
                chiusura_fallita_su = lav.numero

    lav_num = next((x for x in tutti if x.numero == numero), None)
    # Un segno già aperto resta com'è (anche di un'altra sessione); su un lavoro chiuso non se ne apre uno nuovo.
    if lav_num is not None and (lav_num.campi.get("Segno") or not lav_num.aperta):
        return righe

    if chiusura_fallita_su is not None:
        righe.append(f"segno: #{numero}: non aperto, il segno su #{chiusura_fallita_su} è ancora aperto")
        return righe

    try:
        if adesso.tzinfo is None:
            adesso = adesso.replace(tzinfo=timezone.utc)
        board.campo(
            numero,
            "Segno",
            scrivi_nota({"porta": porta_nome, "sessione": sessione_id, "inizio": adesso.isoformat()}),
        )
    except Exception as exc:  # noqa: BLE001 - non solleva mai
        righe.append(f"segno: #{numero}: {_messaggio_errore(exc)}")

    return righe


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
                        s_id = tr.name
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
                    s_id = tr.name
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
                            s_id = tr.name
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
