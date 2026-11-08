"""Divisione di un piano in issue madre e sotto-issue (B3-R20)."""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bottega.brief import fatto_quando
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import Forgia, ForgiaGh
from bottega.porte import Porta, porta as porta_fabbrica
from bottega.quota import nome_variabile
from bottega.scelta import Compito, scegli


class ErroreDividi(Exception):
    """Errore durante la divisione di un piano in issue."""


def _leggi_modello_brief() -> str:
    """Legge il modello di brief dal percorso canonico o fornisce un testo minimale."""
    percorso = (
        Path(__file__).resolve().parent.parent.parent
        / "plugin"
        / "skills"
        / "bottega"
        / "modelli"
        / "brief.md"
    )
    if percorso.is_file():
        try:
            return percorso.read_text(encoding="utf-8")
        except OSError:
            pass
    return (
        "# Modello del brief\n\n"
        "Ogni compito deve contenere la sezione «## Fatto quando» con il blocco di codice eseguibile."
    )


def costruisci_prompt_consigliere(nome_piano: str) -> str:
    """Costruisce il prompt in sola lettura per il consigliere che suddivide il piano."""
    modello = _leggi_modello_brief()
    return (
        f"Sei il consigliere della bottega. Leggi il piano nel file «{nome_piano}» "
        "e proponi la divisione della tappa in una issue madre e sotto-issue per ciascun compito.\n\n"
        "Rispondi SOLO con un oggetto JSON valido (eventualmente racchiuso in un blocco ```json ... ```), "
        "senza testo prima o dopo.\n\n"
        "Formato JSON richiesto:\n"
        "{\n"
        '  "madre": {\n'
        '    "titolo": "<titolo della tappa>",\n'
        '    "corpo": "<descrizione della tappa>"\n'
        "  },\n"
        '  "compiti": [\n'
        "    {\n"
        '      "titolo": "<titolo del compito>",\n'
        '      "corpo": "<brief completo compilato secondo il modello sotto, con la sezione ## Fatto quando>"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Regole essenziali:\n"
        "1. 'madre' contiene titolo e corpo non vuoti per l'issue madre della tappa.\n"
        "2. 'compiti' contiene la lista ordinata dei compiti della tappa (almeno uno).\n"
        "3. Ogni compito ha un titolo e il corpo è un brief compilato sul modello sotto.\n"
        "4. Ogni corpo di compito DEVE avere obbligatoriamente la sezione «## Fatto quando» "
        "con un blocco recintato (```) contenente il comando di verifica.\n\n"
        "Modello di brief:\n\n"
        f"{modello}\n"
    )


def estrai_json(testo: str) -> tuple[dict[str, Any] | None, str | None]:
    """Estrae un oggetto JSON dal testo della risposta del consigliere."""
    if not testo or not testo.strip():
        return None, "risposta vuota"

    # 1. Prova estrazione da blocco di codice recintato ```json ... ```
    m = re.search(r"```(?:json)?\s*\r?\n(.*?)\r?\n```", testo, re.DOTALL | re.IGNORECASE)
    if m:
        candidato = m.group(1).strip()
        try:
            dati = json.loads(candidato)
            if isinstance(dati, dict):
                return dati, None
            return None, "il JSON estratto dal blocco di codice non è un oggetto"
        except json.JSONDecodeError:
            pass

    # 2. Prova decodifica diretta dell'intero testo
    testo_pulito = testo.strip()
    try:
        dati = json.loads(testo_pulito)
        if isinstance(dati, dict):
            return dati, None
        return None, "il JSON non è un oggetto"
    except json.JSONDecodeError:
        pass

    # 3. Prova estrazione dalla prima graffa aperta all'ultima graffa chiusa
    inizio = testo.find("{")
    fine = testo.rfind("}")
    if inizio != -1 and fine != -1 and fine > inizio:
        sotto = testo[inizio : fine + 1]
        try:
            dati = json.loads(sotto)
            if isinstance(dati, dict):
                return dati, None
            return None, "il JSON estratto non è un oggetto"
        except json.JSONDecodeError as e:
            return None, f"JSON non valido ({e})"

    return None, "nessun oggetto JSON valido trovato nella risposta"


def valida_divisione(dati: Any) -> list[str]:
    """Verifica che il piano suddiviso rispetti tutti i requisiti di forma e contenuto."""
    errori: list[str] = []
    if not isinstance(dati, dict):
        return ["il JSON deve essere un oggetto con 'madre' e 'compiti'"]

    madre = dati.get("madre")
    if madre is None:
        errori.append("manca l'oggetto 'madre'")
    elif not isinstance(madre, dict):
        errori.append("il campo 'madre' deve essere un oggetto")
    else:
        titolo = madre.get("titolo")
        if not isinstance(titolo, str) or not titolo.strip():
            errori.append("la madre deve avere un titolo non vuoto")
        corpo = madre.get("corpo")
        if corpo is None or not isinstance(corpo, str):
            errori.append("la madre deve avere un corpo")

    compiti = dati.get("compiti")
    if compiti is None:
        errori.append("manca la lista 'compiti'")
    elif not isinstance(compiti, list):
        errori.append("il campo 'compiti' deve essere una lista")
    elif len(compiti) == 0:
        errori.append("la lista 'compiti' deve contenere almeno un compito")
    else:
        for i, c in enumerate(compiti, start=1):
            if not isinstance(c, dict):
                errori.append(f"compito {i}: deve essere un oggetto")
                continue
            c_titolo = c.get("titolo")
            if not isinstance(c_titolo, str) or not c_titolo.strip():
                errori.append(f"compito {i}: titolo mancante o vuoto")
            c_corpo = c.get("corpo")
            if c_corpo is None or not isinstance(c_corpo, str):
                errori.append(f"compito {i}: corpo mancante o non valido")
            else:
                fq = fatto_quando(c_corpo)
                if not fq:
                    errori.append(f"compito {i}: manca la sezione «## Fatto quando» o il blocco di codice eseguibile")

    return errori


def crea_forgia(repo: str | None = None) -> Forgia:
    """Costruisce l'adattatore della forgia GitHub (gh) per il repository indicato o rilevato."""
    repo_effettivo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo_effettivo:
        try:
            proc = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                repo_effettivo = proc.stdout.strip()
        except Exception:
            pass
    if not repo_effettivo:
        repo_effettivo = ""
    return ForgiaGh(repo_effettivo)


def ottieni_porta(nome: str, eseguibile: str | None = None) -> Porta:
    """Restituisce l'adattatore della porta richiesta."""
    return porta_fabbrica(nome, eseguibile=eseguibile)


def dividi(
    piano: Path | str | None = None,
    *,
    dal_json: Path | str | None = None,
    forgia: Forgia | None = None,
    configurazione: Configurazione | None = None,
    percorso_configurazione: Path | str | None = None,
    porta: Porta | None = None,
    adesso: datetime | None = None,
    caso: random.Random | None = None,
) -> list[int]:
    """Divide un piano in issue madre e sotto-issue, creandole nella forgia senza bottega: fuori."""
    if dal_json is not None:
        p_json = Path(dal_json)
        if not p_json.exists():
            raise ErroreDividi(f"file JSON non trovato: {p_json}")
        try:
            with p_json.open("rb") as f:
                dati = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ErroreDividi(f"impossibile leggere il JSON da {p_json}: {e}")
    else:
        if piano is None:
            raise ErroreDividi("specificare il file del piano (--piano) o il file JSON (--dal-json)")
        p_piano = Path(piano)
        if not p_piano.exists():
            raise ErroreDividi(f"file del piano non trovato: {p_piano}")

        cfg = configurazione
        if cfg is None:
            percorso_cfg = Path(percorso_configurazione or PERCORSO_PREDEFINITO)
            if not percorso_cfg.exists():
                raise ErroreDividi(f"file di configurazione non trovato: {percorso_cfg}")
            try:
                cfg = leggi_configurazione(percorso_cfg)
            except ErroreConfigurazione as e:
                raise ErroreDividi(f"configurazione non valida in {percorso_cfg}: {e}")

        compito = Compito(funzione="consigliare", fuori=False)

        quote_map: dict[str, str | None] = {}
        for b_id in cfg.botteghe:
            var_quota = nome_variabile(b_id)
            val = forgia.variabile(var_quota) if forgia is not None else None
            if val is None:
                val = os.environ.get(var_quota)
            quote_map[b_id] = val

        istante = adesso
        if istante is None:
            try:
                fuso = ZoneInfo(cfg.progetto.fuso)
            except Exception:
                fuso = ZoneInfo("UTC")
            istante = datetime.now(fuso)

        generatore = caso if caso is not None else random.Random()
        esito_scelta = scegli(compito, cfg, {}, quote_map, istante, generatore)
        if esito_scelta.candidato is None:
            raise ErroreDividi(f"nessun consigliere disponibile: {esito_scelta.perche}")

        cand = cfg.candidati[esito_scelta.candidato]
        adattatore_porta = porta or ottieni_porta(cand.porta)

        cartella = p_piano.resolve().parent
        prompt = costruisci_prompt_consigliere(p_piano.name)
        lancio = adattatore_porta.lancia(
            cartella=cartella,
            prompt=prompt,
            modello=cand.modello,
            sola_lettura=True,
        )
        if lancio.esito != "fatto":
            raise ErroreDividi(f"il consigliere ha fallito ({lancio.esito}): {lancio.testo}")

        dati_estratti, errore_estrazione = estrai_json(lancio.testo)
        if errore_estrazione is not None:
            raise ErroreDividi(f"risposta del consigliere non è JSON valido: {errore_estrazione}")
        dati = dati_estratti

    # Validazione preventiva completa: niente si crea se una parte non va
    errori = valida_divisione(dati)
    if errori:
        raise ErroreDividi(f"divisione non valida: {'; '.join(errori)}")

    f_effettiva = forgia or crea_forgia()

    # Creazione della madre prima
    madre_titolo = dati["madre"]["titolo"].strip()
    madre_corpo = dati["madre"]["corpo"]
    num_madre = f_effettiva.crea_issue(titolo=madre_titolo, corpo=madre_corpo, madre=None)

    numeri_creati = [num_madre]
    for c in dati["compiti"]:
        c_titolo = c["titolo"].strip()
        c_corpo = c["corpo"]
        num_c = f_effettiva.crea_issue(titolo=c_titolo, corpo=c_corpo, madre=num_madre)
        numeri_creati.append(num_c)

    return numeri_creati


def argomenti_dividi(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti della riga di comando per il sottocomando `dividi`."""
    parser.add_argument("--piano", metavar="FILE", help="il file del piano da dividere")
    parser.add_argument(
        "--dal-json",
        metavar="FILE",
        help="legge la divisione da un file JSON senza consultare il consigliere",
    )
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="PERCORSO",
        help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
    )
    parser.add_argument(
        "--repo",
        default=None,
        metavar="REPO",
        help="repository GitHub nel formato proprietario/repo",
    )


def comando_dividi(args: argparse.Namespace) -> int:
    """Divide un piano in issue madre e sotto-issue coi brief tramite un consigliere o da JSON."""
    if not args.piano and not args.dal_json:
        print("errore: specificare --piano FILE oppure --dal-json FILE", file=sys.stderr)
        return 2

    if args.piano and not args.dal_json:
        if not Path(args.piano).exists():
            print(f"errore: file del piano non trovato: {args.piano}", file=sys.stderr)
            return 1

    forgia = crea_forgia(args.repo)
    try:
        numeri = dividi(
            piano=args.piano,
            dal_json=args.dal_json,
            forgia=forgia,
            percorso_configurazione=args.file,
        )
    except ErroreDividi as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1

    for num in numeri:
        print(num)
    return 0
