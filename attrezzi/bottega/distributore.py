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
from datetime import datetime, timedelta, timezone
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
from bottega.quota import leggi_punti, nome_variabile_punti
from bottega.ritmo import scegli_riempitivo, seleziona_gruppo_punti, valuta_ritmo
from bottega.scelta import Compito, Risultati, prossimo_gradino, scegli
from bottega.segni import comando, nota, scrivi_nota

CHIAVE_AVVISO_CI = "ci-ramo-principale"
ORE_SCADENZA_IN_CORSO = 7.0
ETICHETTA_BOZZA_PIANO = "bottega: bozza di piano"
_ETICHETTE_ESCLUSE_BOZZA: frozenset[str] = frozenset({
    "attesa utente",
    "design",
    "bottega: sospeso",
    ETICHETTA_BOZZA_PIANO,
})


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


def _info_fatto_quando(lav_numero: int, forgia: Forgia) -> tuple[str, str | None, bool]:
    """Estrae dove ha cercato, il comando Fatto quando e se esistono sotto-issue aperte."""
    sotto = forgia.sotto_issue(lav_numero)
    aperte = [s for s in sotto if s.aperta]
    if aperte:
        return f"nel compito #{aperte[0].numero}", fatto_quando(aperte[0].corpo), True
    iss = forgia.issue(lav_numero)
    return "nel corpo del lavoro", fatto_quando(iss.corpo), False


def _ricava_fatto_quando(lav_numero: int, forgia: Forgia) -> tuple[str, str | None]:
    """Estrae il comando Fatto quando dal corpo dell'issue o della prima sotto-issue aperta, con dove l'ha cercato.

    Un errore della forgia sale a chi chiama, che lo dice (B7, J4): prima diventava un «senza Fatto quando» muto.
    Il «dove» (B11) nomina il compito: un compito di correzione aggiunto a mano senza il suo «Fatto quando» fermava il
    lavoro con un messaggio che non diceva quale."""
    dove, fq, _ = _info_fatto_quando(lav_numero, forgia)
    return dove, fq


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
            # Riprova riparte da capo: tentativi, attese, motivo, gradino e modo si azzerano, il ramo resta.
            lav_riprova = board.lavoro(num_issue)
            d_riprova = nota(lav_riprova.nota) if lav_riprova else {}
            for chiave in ("tentativi", "attese", "motivo", "quote", "gradino", "modo"):
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

        # B8-3: il consigliere legge testi scritti da altri e gira come esecutore: con la rete aperta non parte.
        from bottega import giro as modulo_giro

        if modulo_giro.SENTINELLA_RETE and prefisso and not modulo_giro.rete_dell_esecutore_chiusa(prefisso):
            msg = (
                "Consulto non fatto: la rete dell'esecutore è aperta su questa macchina, o non si può verificare. "
                "Rilanciare `bottega installa macchina` sulla macchina del runner."
            )
            forgia.commenta(num_issue, msg, "distributore")
            riga = f"lavoro {num_issue}: consulto non eseguito (rete dell'esecutore aperta)"
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


def _segna_nota_esiti(board: Board, lav: Lavoro, stato_esiti: str) -> None:
    """Aggiorna la chiave esiti nella nota del giro senza cambiare lo stato Bottega del lavoro."""
    valori = nota(lav.nota)
    valori["esiti"] = stato_esiti
    board.campo(lav.numero, "Nota del giro", scrivi_nota(valori))


def _scrivi_esiti_dei_chiusi(
    lavori: Sequence[Lavoro],
    forgia: Forgia,
    board: Board,
    adesso: datetime,
) -> list[str]:
    """Scrive «Esito del compito» ai compiti lavorati dei lavori chiusi non ancora spazzati."""
    righe: list[str] = []
    per_numero = {lav.numero: lav for lav in lavori}
    candidati = sorted(
        (
            lav for lav in lavori
            if not lav.aperta and lav.stato.strip() and "esiti" not in nota(lav.nota)
        ),
        key=lambda lav: lav.numero,
        reverse=True,
    )[:10]

    adesso_norm = adesso if adesso.tzinfo is not None else adesso.replace(tzinfo=timezone.utc)

    for lav in candidati:
        try:
            chiusura = forgia.chiusura(lav.numero)
            if chiusura is None:
                continue
            motivo, quando = chiusura
            quando_norm = quando if quando.tzinfo is not None else quando.replace(tzinfo=timezone.utc)
            if (adesso_norm - quando_norm) > timedelta(days=7):
                _segna_nota_esiti(board, lav, "vecchi")
                continue

            if motivo == "completed":
                esito_nuovo = "unito com'era"
            elif motivo == "not_planned":
                esito_nuovo = "rifiutato"
            else:
                _segna_nota_esiti(board, lav, "saltati")
                continue

            sotto = forgia.sotto_issue(lav.numero)
            numeri_compiti = [s.numero for s in sotto] if sotto else [lav.numero]

            scritti = 0
            gia_scritti = 0
            for num_comp in numeri_compiti:
                comp_lav = per_numero.get(num_comp)
                if comp_lav is None or misure.numero(comp_lav, "Giri") <= 0:
                    continue
                if (comp_lav.campi.get("Esito del compito") or "").strip():
                    gia_scritti += 1
                    continue
                board.campo(num_comp, "Esito del compito", esito_nuovo)
                scritti += 1

            _segna_nota_esiti(board, lav, "scritti")
            etichetta_esito = "uniti com'erano" if esito_nuovo == "unito com'era" else "rifiutati"
            riga = f"lavoro {lav.numero}: esiti scritti ({scritti} {etichetta_esito}, {gia_scritti} già scritti)"
            righe.append(riga)
            print(riga)
        except Exception as exc:
            print(f"distributore: errore esiti lavoro {lav.numero}: {exc}", file=sys.stderr)

    return righe


def _ha_etichetta_esegue(etichette: Sequence[str]) -> bool:
    """Vero se il lavoro porta un'etichetta `esegue:` esplicita."""
    return any(et.casefold().strip().startswith("esegue:") for et in etichette)


def _escluso_da_bozza(etichette: Sequence[str]) -> bool:
    """Vero se le etichette escludono il lavoro dalla pianificazione automatica notturna."""
    for et in etichette:
        et_cf = et.strip().casefold()
        if et_cf in _ETICHETTE_ESCLUSE_BOZZA or et_cf.startswith("esegue:"):
            return True
    return False


def _conta_bozze_piano_attive(lavori: Sequence[Lavoro]) -> int:
    """Conta i lavori aperti con etichetta bozza di piano o in pianificazione attiva."""
    totale = 0
    et_bozza_cf = ETICHETTA_BOZZA_PIANO.casefold()
    for lav in lavori:
        if not lav.aperta:
            continue
        ha_et = any(et.strip().casefold() == et_bozza_cf for et in lav.etichette)
        val_nota = nota(lav.nota)
        in_pianificazione = val_nota.get("modo") == "pianifica" and lav.stato in ("in corso", "consegnato")
        if ha_et or in_pianificazione:
            totale += 1
    return totale


def _assegna_e_avvia(
    *,
    lav_numero: int,
    cand_id: str,
    configurazione: Configurazione,
    nuovi_nota: dict[str, str],
    commento: str,
    prefisso_log: str,
    adesso_fuso: datetime,
    board: Board,
    forgia: Forgia,
    botteghe_occupate: set[str],
    righe: list[str],
) -> bool:
    """Prende il lavoro sulla board, commenta il perché e avvia il workflow della bottega."""
    cand = configurazione.candidati[cand_id]
    nuovi = dict(nuovi_nota)
    nuovi["inizio"] = adesso_fuso.isoformat()
    nuovi.pop("motivo", None)
    preso = board.prendi(lav_numero, cand.nome, scrivi_nota(nuovi))  # B3-R5: il campo ha il nome
    if not preso:
        riga = f"lavoro {lav_numero}: già preso da altri"
        righe.append(riga)
        print(riga)
        return False

    botteghe_occupate.add(cand.bottega)
    forgia.commenta(lav_numero, commento, "distributore")
    file_wf = f"bottega-esecutore-{cand.bottega}.yml"
    forgia.avvia_workflow(file_wf, {"lavoro": lav_numero})
    riga = f"lavoro {lav_numero}: {prefisso_log}«{cand_id}» ({cand.bottega}), workflow {file_wf} avviato"
    righe.append(riga)
    print(riga)
    return True


def _scegli_esecutore_o_gradino(
    *,
    lav: Lavoro,
    valori_nota: Mapping[str, str],
    configurazione: Configurazione,
    risultati_storici: Mapping[tuple[str, str], Risultati],
    variabili: Mapping[str, str | None],
    adesso_fuso: datetime,
    caso: random.Random,
    costi_relativi: Mapping[str, float] | None,
) -> tuple[str | None, bool, str, int | None]:
    """Sceglie il candidato per un lavoro con `Fatto quando`, gestendo la scala sui fallimenti."""
    ha_esegue = _ha_etichetta_esegue(lav.etichette)
    gradino_raw = valori_nota.get("gradino")
    gradino = int(gradino_raw) if gradino_raw and gradino_raw.isdigit() else 0

    if gradino > 0 and not ha_esegue and configurazione.progetto.scala:
        esito = prossimo_gradino(
            configurazione.progetto.scala,
            gradino,
            configurazione,
            variabili,
            adesso_fuso,
            fuori=True,
        )
        if esito.esaurita:
            return None, False, esito.perche, None
        if esito.aspetta:
            return None, True, esito.perche, None
        return esito.candidato, False, esito.perche, esito.gradino

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
        return None, True, scelta.perche, None
    if scelta.candidato is None:
        return None, False, scelta.perche, None

    gradino_sel: int | None = None
    if (
        configurazione.progetto.scala
        and not ha_esegue
        and scelta.candidato in configurazione.progetto.scala
    ):
        gradino_sel = configurazione.progetto.scala.index(scelta.candidato)
    return scelta.candidato, False, scelta.perche, gradino_sel


def _distribuisci_riempitivi(
    *,
    lavori_pronti: Sequence[Lavoro],
    presi_nel_giro: set[int],
    configurazione: Configurazione,
    forgia: Forgia,
    board: Board,
    variabili: Mapping[str, str | None],
    adesso_fuso: datetime,
    caso: random.Random,
    risultati_storici: Mapping[tuple[str, str], Risultati],
    costi_relativi: Mapping[str, float] | None,
    botteghe_occupate: set[str],
    comandanti_cf: set[str],
    cache_autore_valido: dict[int, bool],
    cache_ha_fq: dict[int, bool],
    righe: list[str],
) -> None:
    """Avvia eventuali riempitivi per le botteghe libere con quota settimanale indietro."""
    if not configurazione.progetto.aree_non_delicate:
        return

    def _autore_valido(num: int) -> bool:
        if num in cache_autore_valido:
            return cache_autore_valido[num]
        try:
            iss = forgia.issue(num)
            autore = iss.autore.strip().casefold() if iss.autore else ""
            valido = autore in comandanti_cf
        except Exception:
            valido = False
        cache_autore_valido[num] = valido
        return valido

    def _ha_fq(num: int) -> bool:
        if num in cache_ha_fq:
            return cache_ha_fq[num]
        try:
            _, fq, _ = _info_fatto_quando(num, forgia)
            presente = fq is not None
        except Exception:
            presente = False
        cache_ha_fq[num] = presente
        return presente

    for b_id in configurazione.botteghe:
        if b_id in botteghe_occupate:
            continue
        val_punti = variabili.get(nome_variabile_punti(b_id))
        if not val_punti:
            continue
        _, punti = leggi_punti(val_punti)
        punto = seleziona_gruppo_punti(punti, configurazione, b_id)
        if punto is None:
            continue

        esito_ritmo = valuta_ritmo(
            punto,
            adesso_fuso,
            soglia_ritardo=configurazione.ritmo.ritardo,
            riserva_5h=configurazione.ritmo.riserva_5h,
            riserva_settimana=configurazione.ritmo.riserva_settimana,
        )
        if not esito_ritmo.lancia:
            riga = f"bottega «{b_id}»: nessun riempitivo ({esito_ritmo.motivo})"
            righe.append(riga)
            print(riga)
            continue

        disponibili = [lav for lav in lavori_pronti if lav.numero not in presi_nel_giro]
        scelto = scegli_riempitivo(
            disponibili,
            aree_non_delicate=configurazione.progetto.aree_non_delicate,
            ha_fatto_quando=_ha_fq,
            autore_valido=_autore_valido,
        )
        if scelto is None:
            riga = f"bottega «{b_id}»: {esito_ritmo.motivo}, nessun riempitivo pronto"
            righe.append(riga)
            print(riga)
            continue

        lav_riemp, fascia = scelto
        nuovi = dict(nota(lav_riemp.nota))
        cand_id: str | None = None
        gradino_riemp: int | None = None
        perche_cand = ""

        if configurazione.progetto.scala:
            gradino_raw = nuovi.get("gradino", "0")
            try:
                indice = int(gradino_raw)
            except ValueError:
                indice = 0
            if indice < 0:
                indice = 0
            esito_pg = prossimo_gradino(
                configurazione.progetto.scala,
                indice,
                configurazione,
                variabili,
                adesso_fuso,
                fuori=True,
            )
            if esito_pg.esaurita:
                nuovi["motivo"] = esito_pg.perche
                board.stato(lav_riemp.numero, "bloccato", nota=scrivi_nota(nuovi))
                forgia.commenta(lav_riemp.numero, esito_pg.perche, "distributore")
                riga = f"lavoro {lav_riemp.numero}: scala esaurita, a chi decide"
                righe.append(riga)
                print(riga)
                continue
            if (
                esito_pg.aspetta
                or esito_pg.candidato is None
                or configurazione.candidati[esito_pg.candidato].bottega != b_id
            ):
                if esito_pg.aspetta:
                    riga = f"lavoro {lav_riemp.numero}: in attesa ({esito_pg.perche})"
                    righe.append(riga)
                    print(riga)
                continue
            cand_id = esito_pg.candidato
            gradino_riemp = esito_pg.gradino
            perche_cand = esito_pg.perche
        else:
            cand_bottega = {k: c for k, c in configurazione.candidati.items() if c.bottega == b_id}
            cfg_b = replace(configurazione, candidati=cand_bottega)
            scelta_b = scegli(
                compito=Compito(funzione="eseguire", fuori=True, etichette=frozenset(lav_riemp.etichette)),
                configurazione=cfg_b,
                risultati=risultati_storici,
                quote=variabili,
                adesso=adesso_fuso,
                caso=caso,
                costi_propri=costi_relativi,
            )
            if scelta_b.candidato is None:
                continue
            cand_id = scelta_b.candidato
            perche_cand = scelta_b.perche

        nuovi.pop("modo", None)
        nuovi["riempitivo"] = "1"
        if gradino_riemp is not None:
            nuovi["gradino"] = str(gradino_riemp)
        commento = f"riempitivo [fascia {fascia}] ({esito_ritmo.motivo}): {perche_cand}"
        if _assegna_e_avvia(
            lav_numero=lav_riemp.numero,
            cand_id=cand_id,
            configurazione=configurazione,
            nuovi_nota=nuovi,
            commento=commento,
            prefisso_log=f"riempitivo [fascia {fascia}] assegnato a ",
            adesso_fuso=adesso_fuso,
            board=board,
            forgia=forgia,
            botteghe_occupate=botteghe_occupate,
            righe=righe,
        ):
            presi_nel_giro.add(lav_riemp.numero)


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
        lavori_elenco: list[Lavoro] | None = board.elenco()
        risultati_storici = misure.risultati(lavori_elenco, configurazione)
        costi_relativi = misure.costi_propri(lavori_elenco, configurazione)
    except Exception as exc:
        print(f"distributore: errore lettura elenco board: {exc}", file=sys.stderr)
        lavori_elenco = None
        risultati_storici = {}
        costi_relativi = None

    if lavori_elenco is not None:
        righe.extend(_scrivi_esiti_dei_chiusi(lavori_elenco, forgia, board, adesso_fuso))

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
    presi_nel_giro: set[int] = set()
    cache_autore_valido: dict[int, bool] = {}
    cache_ha_fq: dict[int, bool] = {}
    comandanti_cf = {c.strip().casefold() for c in configurazione.progetto.comandanti} | {
        forgia.proprietario().strip().casefold()
    }
    ha_pianificatore_fuori = (
        notte
        and configurazione.progetto.bozze_piano > 0
        and any(
            "pianificare" in c.funzioni and bool(c.runner) and not c.su_richiesta
            for c in configurazione.candidati.values()
        )
    )
    elenco_tetto = lavori_elenco if lavori_elenco is not None else (lavori_in_corso + lavori_pronti)
    bozze_attive = _conta_bozze_piano_attive(elenco_tetto) if ha_pianificatore_fuori else 0
    avviso_tetto_stampato = False

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
        elegibile_ordinario = ha_comando_esplicito or ha_liberi
        # B15-R8: anche le bozze di piano notturne partono solo da un lavoro con «bottega: fuori» o un'etichetta di
        # `liberi`: la bottega non prende issue che nessuno le ha affidato.
        if not elegibile_ordinario:
            continue

        # RV14 e C5: solo issue il cui autore è un comandante (o il proprietario), con o senza etichetta: il corpo
        # (brief e «Fatto quando») lo può cambiare il suo autore anche dopo l'etichetta.
        # B7 (J4): ogni lavoro con l'etichetta che si salta lo dice, col motivo.
        try:
            iss = forgia.issue(lav.numero)
            autore = iss.autore.strip().casefold() if iss.autore else ""
            autore_ok = autore in comandanti_cf
            cache_autore_valido[lav.numero] = autore_ok
            dove_fq, fq, ha_sotto_aperte = (
                _info_fatto_quando(lav.numero, forgia) if autore_ok else ("", None, False)
            )
            if autore_ok:
                cache_ha_fq[lav.numero] = fq is not None
        except Exception as e:
            if elegibile_ordinario:
                riga = f"lavoro {lav.numero}: la forgia non risponde ({e}), salto"
                righe.append(riga)
                print(riga)
            continue

        if not autore_ok:
            if elegibile_ordinario:
                riga = f"lavoro {lav.numero}: l'autore non è fra i comandanti, salto"
                righe.append(riga)
                print(riga)
            continue

        if not elegibile_ordinario and fq is not None:
            continue

        valori_nota = nota(lav.nota)
        precedente = valori_nota.get("precedente")
        attese_raw = valori_nota.get("attese")
        attese = int(attese_raw) if attese_raw and attese_raw.isdigit() else 0

        if fq is None:
            if not ha_pianificatore_fuori or ha_sotto_aperte or _escluso_da_bozza(lav.etichette):
                if elegibile_ordinario:
                    riga = (
                        f"lavoro {lav.numero}: senza «Fatto quando» {dove_fq} "
                        "(serve la sezione «## Fatto quando» con il comando in un blocco recintato), salto"
                    )
                    righe.append(riga)
                    print(riga)
                continue

            if bozze_attive >= configurazione.progetto.bozze_piano:
                if not avviso_tetto_stampato:
                    riga = (
                        f"bozze di piano al tetto ({bozze_attive}/{configurazione.progetto.bozze_piano}): "
                        "nessuna nuova pianificazione"
                    )
                    righe.append(riga)
                    print(riga)
                    avviso_tetto_stampato = True
                continue

            scelta_plan = scegli(
                compito=Compito(
                    funzione="pianificare",
                    fuori=True,
                    etichette=frozenset(lav.etichette),
                ),
                configurazione=configurazione,
                risultati=risultati_storici,
                quote=variabili,
                adesso=adesso_fuso,
                caso=caso,
                costi_propri=costi_relativi,
            )
            if scelta_plan.aspetta:
                riga = f"lavoro {lav.numero}: in attesa ({scelta_plan.perche})"
                righe.append(riga)
                print(riga)
                continue
            if scelta_plan.candidato is None:
                riga = f"lavoro {lav.numero}: nessuna pianificazione ({scelta_plan.perche}), salto"
                righe.append(riga)
                print(riga)
                continue

            cand_plan = configurazione.candidati[scelta_plan.candidato]
            if cand_plan.bottega in botteghe_occupate:
                riga = f"lavoro {lav.numero}: bottega «{cand_plan.bottega}» occupata, salto"
                righe.append(riga)
                print(riga)
                continue

            nuovi_plan = dict(valori_nota)
            nuovi_plan["modo"] = "pianifica"
            if _assegna_e_avvia(
                lav_numero=lav.numero,
                cand_id=scelta_plan.candidato,
                configurazione=configurazione,
                nuovi_nota=nuovi_plan,
                commento=scelta_plan.perche,
                prefisso_log="assegnato a ",
                adesso_fuso=adesso_fuso,
                board=board,
                forgia=forgia,
                botteghe_occupate=botteghe_occupate,
                righe=righe,
            ):
                bozze_attive += 1
                presi_nel_giro.add(lav.numero)
            continue

        cand_id, aspetta, perche, gradino_sel = _scegli_esecutore_o_gradino(
            lav=lav,
            valori_nota=valori_nota,
            configurazione=configurazione,
            risultati_storici=risultati_storici,
            variabili=variabili,
            adesso_fuso=adesso_fuso,
            caso=caso,
            costi_relativi=costi_relativi,
        )

        if aspetta:
            if precedente is not None:
                nuovi = dict(valori_nota)
                nuovi["attese"] = str(attese + 1)
                board.campo(lav.numero, "Nota del giro", scrivi_nota(nuovi))
            riga = f"lavoro {lav.numero}: in attesa ({perche})"
            righe.append(riga)
            print(riga)
            continue

        if cand_id is None:
            nuovi = dict(valori_nota)
            nuovi["motivo"] = perche
            board.stato(lav.numero, "bloccato", nota=scrivi_nota(nuovi))
            forgia.commenta(lav.numero, perche, "distributore")
            riga = f"lavoro {lav.numero}: bloccato ({perche})"
            righe.append(riga)
            print(riga)
            continue

        cand = configurazione.candidati[cand_id]
        if cand.bottega in botteghe_occupate:
            riga = f"lavoro {lav.numero}: bottega «{cand.bottega}» occupata, salto"
            righe.append(riga)
            print(riga)
            continue

        nuovi = dict(valori_nota)
        nuovi.pop("modo", None)
        if gradino_sel is not None:
            nuovi["gradino"] = str(gradino_sel)
        if _assegna_e_avvia(
            lav_numero=lav.numero,
            cand_id=cand_id,
            configurazione=configurazione,
            nuovi_nota=nuovi,
            commento=perche,
            prefisso_log="assegnato a ",
            adesso_fuso=adesso_fuso,
            board=board,
            forgia=forgia,
            botteghe_occupate=botteghe_occupate,
            righe=righe,
        ):
            presi_nel_giro.add(lav.numero)

    # 5. Riempitivi del ritmo (giorno e notte)
    _distribuisci_riempitivi(
        lavori_pronti=lavori_pronti,
        presi_nel_giro=presi_nel_giro,
        configurazione=configurazione,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso_fuso=adesso_fuso,
        caso=caso,
        risultati_storici=risultati_storici,
        costi_relativi=costi_relativi,
        botteghe_occupate=botteghe_occupate,
        comandanti_cf=comandanti_cf,
        cache_autore_valido=cache_autore_valido,
        cache_ha_fq=cache_ha_fq,
        righe=righe,
    )

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
