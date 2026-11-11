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
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import shlex
import sys
import tempfile
from zoneinfo import ZoneInfo

from bottega.board import Board, BoardComando, BoardProject, ErroreBoard, Lavoro
from bottega.brief import fatto_quando
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ErroreForgia, Forgia, ForgiaGh
import bottega.misure as misure
from bottega.porte import Porta, porta as porta_fabbrica
from bottega.scelta import Compito, Risultati, scegli
from bottega.segni import comando, nota, scrivi_nota

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
    """Estrae il comando Fatto quando dal corpo dell'issue o della prima sotto-issue aperta.

    Un errore della forgia sale a chi chiama, che lo dice (B7, J4): prima diventava un «senza Fatto quando» muto."""
    sotto = forgia.sotto_issue(lav_numero)
    aperte = [s for s in sotto if s.aperta]
    if aperte:
        return fatto_quando(aperte[0].corpo)
    iss = forgia.issue(lav_numero)
    return fatto_quando(iss.corpo)


def _recinta(testo: str, limite: int = 60000) -> str:
    """Racchiude il testo in un blocco recintato più lungo di ogni sequenza di apici presente, troncato a limite."""
    testo_troncato = (testo or "")[:limite]
    apici = [len(m.group(0)) for m in re.finditer(r"`+", testo_troncato)]
    max_apici = max(apici) if apici else 0
    recinto = "`" * max(3, max_apici + 1)
    return f"{recinto}\n{testo_troncato}\n{recinto}"


def _gestisci_evento_commento(
    percorso_evento: Path | str | None,
    configurazione: Configurazione,
    forgia: Forgia,
    board: Board,
    variabili: Mapping[str, str | None],
    adesso_fuso: datetime,
    caso: random.Random,
    porte: Mapping[str, Porta] | None = None,
    prefisso: Sequence[str] = (),
    risultati: Mapping[tuple[str, str], Risultati] | None = None,
    costi_propri: Mapping[str, float] | None = None,
) -> tuple[bool, list[str]]:
    """Gestisce un eventuale comando da issue_comment nell'evento GITHUB_EVENT_PATH.

    Restituisce (procedi_con_distribuzione, righe).
    """
    if percorso_evento is None:
        env_path = os.environ.get("GITHUB_EVENT_PATH")
        if not env_path:
            return True, []
        p_ev = Path(env_path)
    else:
        p_ev = Path(percorso_evento)

    if not p_ev.is_file():
        return True, []

    try:
        evento = json.loads(p_ev.read_text(encoding="utf-8"))
    except Exception:
        return True, []

    if not isinstance(evento, dict):
        return True, []

    issue_data = evento.get("issue")
    comment_data = evento.get("comment")
    if not isinstance(issue_data, dict) or not isinstance(comment_data, dict):
        return True, []

    # C5: un evento di commento non distribuisce mai. Gira in un gruppo di concorrenza suo (un comando in coda non
    # si perde), quindi non deve prendere lavori insieme al distributore vero: `riprova` lo rilancia e basta.

    num_issue = issue_data.get("number")
    if not isinstance(num_issue, int):
        return False, []

    corpo = str(comment_data.get("body") or "")
    user_data = comment_data.get("user")
    autore = user_data.get("login", "") if isinstance(user_data, dict) else ""
    if not autore:
        return False, []

    comandanti = configurazione.progetto.comandanti or [forgia.proprietario()]
    cmd = comando(corpo, autore, comandanti)
    if cmd is None:
        return False, []

    righe: list[str] = []

    if cmd.nome == "riprova":
        in_corso = [l.numero for l in board.in_corso()]
        if num_issue in in_corso:
            msg = f"Comando /bottega riprova ignorato: il lavoro #{num_issue} è già in corso."
            forgia.commenta(num_issue, msg, "distributore")
            riga = f"lavoro {num_issue}: riprova ignorato perché già in corso"
            righe.append(riga)
            print(riga)
        else:
            # Riprova riparte da capo: tentativi, attese e motivo si azzerano, il ramo resta.
            lav_riprova = board.lavoro(num_issue)
            d_riprova = nota(lav_riprova.nota) if lav_riprova else {}
            for chiave in ("tentativi", "attese", "motivo", "quote"):
                d_riprova.pop(chiave, None)
            # C6: i comandi non sono in fila col distributore; si rilegge lo stato subito prima di scrivere.
            if lav_riprova is not None and lav_riprova.stato == "in corso":
                riga = f"lavoro {num_issue}: riprova ignorato perché già in corso"
                righe.append(riga)
                print(riga)
                return False, righe
            board.stato(num_issue, "pronto", nota=scrivi_nota(d_riprova))
            msg = f"Lavoro #{num_issue} rimesso a «pronto» su comando di @{autore}."
            forgia.commenta(num_issue, msg, "distributore")
            riga = f"lavoro {num_issue}: rimesso a pronto su comando di «{autore}»"
            righe.append(riga)
            print(riga)
        # RV13 e C5: riprova rimette pronto e rilancia il distributore, che distribuisce nel suo gruppo.
        try:
            forgia.avvia_workflow("bottega-distributore.yml", {})
        except Exception as e:
            riga = f"lavoro {num_issue}: distributore non rilanciato ({e})"
            righe.append(riga)
            print(riga)
        return False, righe

    if cmd.nome == "sospendi":
        motivo = cmd.argomento.strip() or f"sospeso su comando di @{autore}"
        lavori = board.pronti() + board.in_corso()
        lav = next((l for l in lavori if l.numero == num_issue), None)
        d_nota = nota(lav.nota) if lav else {}
        d_nota["motivo"] = motivo
        board.stato(num_issue, "in attesa", nota=scrivi_nota(d_nota))
        msg = f"Lavoro #{num_issue} sospeso su comando di @{autore}."
        if cmd.argomento.strip():
            msg += f"\n\nMotivo: {cmd.argomento.strip()}"
        forgia.commenta(num_issue, msg, "distributore")
        riga = f"lavoro {num_issue}: sospeso ({motivo})"
        righe.append(riga)
        print(riga)
        return False, righe

    if cmd.nome == "consulta":
        runner = os.environ.get("BOTTEGA_RUNNER")
        candidati_runner = {
            k: c for k, c in configurazione.candidati.items()
            if runner is not None and c.runner == runner
        }
        cfg_runner = replace(configurazione, candidati=candidati_runner)
        compito_cons = Compito(funzione="consigliare", fuori=True)
        scelta_cons = scegli(
            compito=compito_cons,
            configurazione=cfg_runner,
            risultati=risultati if risultati is not None else {},
            quote=variabili,
            adesso=adesso_fuso,
            caso=caso,
            costi_propri=costi_propri,
        )

        if scelta_cons.candidato is None:
            msg = f"Nessun consigliere disponibile sul runner per il consulto ({scelta_cons.perche})."
            forgia.commenta(num_issue, msg, "distributore")
            riga = f"lavoro {num_issue}: consulto non eseguito ({scelta_cons.perche})"
            righe.append(riga)
            print(riga)
            return False, righe

        cand = configurazione.candidati[scelta_cons.candidato]
        if porte and cand.porta in porte:
            adattatore_porta = porte[cand.porta]
        else:
            adattatore_porta = porta_fabbrica(cand.porta)

        spazio_env = os.environ.get("BOTTEGA_SPAZIO")
        kw_temp = {"dir": spazio_env} if spazio_env else {}
        # M10: un file dell'esecutore che il runner non può togliere non deve far perdere la risposta del consulto.
        lancio = None
        try:
            with tempfile.TemporaryDirectory(**kw_temp, ignore_cleanup_errors=True) as tmpdir:
                p_tmp = Path(tmpdir)
                try:
                    iss = forgia.issue(num_issue)
                    corpo_iss = iss.corpo
                    titolo_iss = iss.titolo
                except Exception:
                    corpo_iss = ""
                    titolo_iss = f"Issue #{num_issue}"

                comandanti_set = {c.strip().casefold() for c in comandanti}
                try:
                    tutti_comm = forgia.commenti(num_issue)
                    comm_cmd = [c for c in tutti_comm if c.autore.strip().casefold() in comandanti_set]
                except Exception:
                    comm_cmd = []

                testo_comm = "\n\n".join(f"### Commento di @{c.autore}:\n{c.corpo}" for c in comm_cmd)

                fascicolo_md = (
                    f"# {titolo_iss}\n\n"
                    f"## Corpo dell'issue\n{corpo_iss}\n\n"
                    f"## Commenti dei comandanti\n{testo_comm or '(nessun commento)'}\n\n"
                    f"## Domanda di consulto\n{cmd.argomento}\n"
                )
                (p_tmp / "fascicolo.md").write_text(fascicolo_md, encoding="utf-8")
                # La cartella si apre all'esecutore solo dopo che il runner vi ha scritto: prima, un link messo al posto
                # di `fascicolo.md` porterebbe la scrittura del runner fuori dal consulto.
                if spazio_env:
                    os.chmod(tmpdir, 0o2770)

                prompt = (
                    f"Sei il consigliere della bottega. Rispondi alla seguente domanda sul compito #{num_issue}.\n"
                    f"Nella cartella di lavoro è presente il fascicolo minimo (`fascicolo.md`).\n\n"
                    f"Domanda:\n{cmd.argomento}\n"
                )
                try:
                    lancio = adattatore_porta.lancia(
                        cartella=p_tmp,
                        prompt=prompt,
                        modello=cand.modello,
                        sola_lettura=True,
                        prefisso=prefisso,
                    )
                finally:
                    # M3: niente processi dell'esecutore vivi dopo il consulto; poi l'esecutore toglie ciò che ha creato,
                    # anche le sue cartelle chiuse, così la pulizia del runner non cade.
                    from bottega.giro import _uccidi_processi_esecutore, togli_come_esecutore

                    _uccidi_processi_esecutore(prefisso)
                    for voce in p_tmp.iterdir():
                        togli_come_esecutore(prefisso, voce)
        except OSError as exc:
            # Una pulizia che non riesce (un file dell'esecutore che il runner non toglie) non fa perdere la risposta.
            if lancio is None:
                raise
            print(f"consulto: pulizia non riuscita: {exc}", file=sys.stderr)

        testo_cons = lancio.testo if lancio.esito == "fatto" else f"Errore consulto ({lancio.esito}): {lancio.testo}"
        corpo_risposta = f"Risposta del consigliere ({cand.nome}):\n\n{_recinta(testo_cons)}"
        forgia.commenta(num_issue, corpo_risposta, "consigliere")
        riga = f"lavoro {num_issue}: consulto completato da «{cand.nome}»"
        righe.append(riga)
        print(riga)
        return False, righe

    return True, []


def distribuisci(
    *,
    configurazione: Configurazione,
    forgia: Forgia,
    board: Board,
    variabili: Mapping[str, str | None],
    adesso: datetime,
    caso: random.Random,
    notte: bool = False,
    percorso_evento: Path | str | None = None,
    porte: Mapping[str, Porta] | None = None,
    prefisso: Sequence[str] = (),
) -> list[str]:
    """Esegue un giro di distribuzione dei lavori secondo la regola B3-R16."""
    righe: list[str] = []

    try:
        fuso_cfg = ZoneInfo(configurazione.progetto.fuso)
    except Exception:
        fuso_cfg = ZoneInfo("UTC")
    adesso_fuso = adesso.astimezone(fuso_cfg) if adesso.tzinfo else adesso.replace(tzinfo=fuso_cfg)

    try:
        lavori_elenco = board.elenco()
        risultati_storici = misure.risultati(lavori_elenco, configurazione)
        costi_relativi = misure.costi_propri(lavori_elenco, configurazione)
    except Exception as exc:
        print(f"distributore: errore lettura elenco board: {exc}", file=sys.stderr)
        risultati_storici = {}
        costi_relativi = None

    # RV13: gestione comandi da issue_comment nell'evento GITHUB_EVENT_PATH
    procedi, righe_ev = _gestisci_evento_commento(
        percorso_evento=percorso_evento,
        configurazione=configurazione,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso_fuso=adesso_fuso,
        caso=caso,
        porte=porte,
        prefisso=prefisso,
        risultati=risultati_storici,
        costi_propri=costi_relativi,
    )
    righe.extend(righe_ev)
    if not procedi:
        return righe

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
            # C5: un giro appeso conta un tentativo; al terzo il lavoro si blocca invece di ripartire per sempre.
            tentativi = int(valori.get("tentativi", 0) or 0) + 1
            valori["tentativi"] = str(tentativi)
            valori["motivo"] = "in corso da oltre 7 ore"
            stato_scaduto = "bloccato" if tentativi >= 3 else "pronto"
            board.stato(lav.numero, stato_scaduto, nota=scrivi_nota(valori))
            riga = f"lavoro {lav.numero}: in corso da oltre 7 ore, reimpostato a {stato_scaduto}"
            righe.append(riga)
            print(riga)
        else:
            bottega = _trova_bottega(lav.esecutore, configurazione)
            if bottega:
                botteghe_occupate.add(bottega)

    # 4. Lavori pronti
    lavori_pronti = board.pronti()
    for lav in lavori_pronti:
        ha_comando_esplicito = any(
            et.casefold().strip() == "bottega: fuori" or et.casefold().strip().startswith("esegue:")
            for et in lav.etichette
        )
        ha_liberi = (
            notte
            and any(
                any(et.casefold().strip() == lib.casefold().strip() for lib in configurazione.progetto.liberi)
                for et in lav.etichette
            )
        )
        if not (ha_comando_esplicito or ha_liberi):
            continue

        # RV14 e C5: solo issue il cui autore è un comandante (o il proprietario), con o senza etichetta: il corpo
        # (brief e «Fatto quando») lo può cambiare il suo autore anche dopo l'etichetta.
        comandanti_cf = {c.strip().casefold() for c in configurazione.progetto.comandanti} | {
            forgia.proprietario().strip().casefold()
        }
        # B7 (J4): ogni lavoro con l'etichetta che si salta lo dice, col motivo.
        try:
            iss = forgia.issue(lav.numero)
            autore = iss.autore.strip().casefold() if iss.autore else ""
            fq = _ricava_fatto_quando(lav.numero, forgia) if autore in comandanti_cf else None
        except Exception as e:
            riga = f"lavoro {lav.numero}: la forgia non risponde ({e}), salto"
            righe.append(riga)
            print(riga)
            continue
        if autore not in comandanti_cf:
            riga = f"lavoro {lav.numero}: l'autore non è fra i comandanti, salto"
            righe.append(riga)
            print(riga)
            continue
        if fq is None:
            riga = f"lavoro {lav.numero}: senza «Fatto quando», salto"
            righe.append(riga)
            print(riga)
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
            risultati=risultati_storici,
            quote=variabili,
            adesso=adesso_fuso,
            caso=caso,
            costi_propri=costi_relativi,
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
    try:
        if cfg.progetto.adattatore:
            board = BoardComando(shlex.split(cfg.progetto.adattatore))
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
            # Il consigliere di `/bottega consulta` legge testi scritti da altri: gira come l'esecutore.
            prefisso=tuple(shlex.split(os.environ.get("BOTTEGA_PREFISSO_ESECUTORE", ""))),
        )
        return 0
    except (ErroreBoard, ErroreForgia, FileNotFoundError) as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        print(f"errore: {motivo}", file=sys.stderr)
        return 1
