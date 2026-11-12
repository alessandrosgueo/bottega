"""Comandi bottega lancia e bottega segui (Ruling B9-R6).

Solo libreria standard.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bottega.board import Board, BoardComando, BoardProject
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ForgiaGh

ESITI_LANCIO: dict[str, int] = {
    "avviato": 0,
    "manutenzione": 2,
    "occupata": 3,
    "rosso": 4,
    "assente": 1,
}


@dataclass(frozen=True)
class Giro:
    """Rappresentazione di un giro di Actions."""

    id: int
    stato: str
    conclusione: str | None
    creato: datetime
    aggiornato: datetime


def _differenza_secondi(da: datetime, a: datetime) -> float:
    """Restituisce (a - da) in secondi, gestendo differenze tra naive e aware (UTC)."""
    if da.tzinfo is None and a.tzinfo is not None:
        da = da.replace(tzinfo=UTC)
    elif da.tzinfo is not None and a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    return (a - da).total_seconds()


def esito_del_lavoro(registro: str, numero: int) -> tuple[str, str]:
    """Legge il registro del distributore e ricava l'esito per il lavoro."""
    pattern_lavoro = re.compile(rf"\b(lavoro {numero}: .*)")
    righe = registro.splitlines()

    righe_lavoro: list[str] = []
    for riga in righe:
        m = pattern_lavoro.search(riga)
        if m:
            righe_lavoro.append(m.group(1).strip())

    if righe_lavoro:
        for riga_lav in righe_lavoro:
            if "avviato" in riga_lav:
                return "avviato", riga_lav
        for riga_lav in righe_lavoro:
            if "occupata" in riga_lav:
                return "occupata", riga_lav
        return "assente", righe_lavoro[-1]

    for riga in righe:
        if "finestra di manutenzione" in riga and "nessun lavoro avviato" in riga:
            idx = riga.find("finestra di manutenzione")
            return "manutenzione", riga[idx:].strip()
        if "ramo principale" in riga and "nessun lavoro avviato" in riga:
            idx = riga.find("ramo principale")
            return "rosso", riga[idx:].strip()

    return "assente", f"nessuna riga per il lavoro {numero}"


def verdetto(
    *,
    stato: str | None,
    figli: Sequence[bool],
    giri: Sequence[Giro],
    inizio: datetime,
    adesso: datetime,
    fermo_s: float,
) -> tuple[int, str] | None:
    """Determina se il lavoro è concluso o richiede intervento."""
    # 1. stato consegnato o tutti i figli chiusi (non vuoti)
    if stato == "consegnato" or (len(figli) > 0 and not any(figli)):
        return 0, "finito"

    # 2. in attesa
    if stato == "in attesa":
        return 2, "in attesa: una domanda per chi decide"

    # 3. bloccato
    if stato == "bloccato":
        return 3, "bloccato"

    # 4. fermo
    if stato in ("pronto", "in corso"):
        nessun_incompleto = all(g.stato == "completed" for g in giri)
        if nessun_incompleto:
            if giri:
                ultimo_agg = max(g.aggiornato for g in giri)
                if _differenza_secondi(ultimo_agg, inizio) > 0:
                    riferimento = inizio
                else:
                    riferimento = ultimo_agg
            else:
                riferimento = inizio
            if _differenza_secondi(riferimento, adesso) > fermo_s:
                iso_minuto = riferimento.isoformat(timespec="minutes")
                return 4, f"fermo dal {iso_minuto}"

    return None


def giri_rossi_nuovi(
    giri: Sequence[Giro], inizio: datetime, visti: set[int]
) -> list[int]:
    """Trova i giri con conclusione failure dal momento di inizio in poi e non ancora visti."""
    rossi = [
        g
        for g in giri
        if g.conclusione == "failure"
        and _differenza_secondi(inizio, g.creato) >= 0
        and g.id not in visti
    ]
    rossi.sort(key=lambda g: (g.creato, g.id))
    return [g.id for g in rossi]


def argomenti_lancia(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando bottega lancia."""
    parser.add_argument("numero", type=int, help="numero del lavoro da lanciare")
    parser.add_argument(
        "--repo", type=str, default=None, help="repository GitHub (proprietario/repo)"
    )
    parser.add_argument(
        "--attesa",
        type=int,
        default=180,
        help="secondi di attesa per veder nascere il giro (di serie: 180)",
    )
    parser.add_argument(
        "--tetto",
        type=int,
        default=900,
        help="secondi di tetto per la fine del giro (di serie: 900)",
    )


def esecutore_gh(comando: Sequence[str], ambiente: Mapping[str, str] | None = None) -> tuple[int, str]:
    """Lancia un comando e dà (codice, stdout) se riesce, (codice, stderr + stdout) se no.

    Solo lo stdout di un comando riuscito: `gh` scrive avvisi su stderr (una versione nuova, un'API deprecata), e uniti
    allo stdout romperebbero il JSON. Niente avviso di aggiornamento, tetto di 600 secondi, stdin nullo.
    """
    env = {**os.environ, "GH_NO_UPDATE_NOTIFIER": "1", **(ambiente or {})}
    try:
        res = subprocess.run(
            list(comando), env=env, timeout=600, stdin=subprocess.DEVNULL, capture_output=True, text=True
        )
    except subprocess.TimeoutExpired:
        return 124, f"{comando[:3]}: nessuna risposta in 600 secondi"
    except OSError as exc:
        return 127, str(exc)
    if res.returncode == 0:
        return 0, res.stdout or ""
    return res.returncode, (res.stderr or "") + (res.stdout or "")


def _esegui_chiamata(esegui_fn: Callable[..., tuple[int, str]], cmd: Sequence[str]) -> tuple[int, str]:
    return esegui_fn(list(cmd), None)


def comando_lancia(
    args: argparse.Namespace,
    esegui: Callable[[Sequence[str], Mapping[str, str] | None], tuple[int, str]]
    | None = None,
    dormi: Callable[[float], None] = time.sleep,
    adesso: Callable[[], datetime] | None = None,
) -> int:
    """Lancia un lavoro verificando che il giro del distributore sia partito."""
    esegui_fn = esegui or esecutore_gh
    adesso_fn = adesso or (lambda: datetime.now(UTC))
    repo_arg = getattr(args, "repo", None)
    repo_args = ["--repo", repo_arg] if repo_arg else []
    numero = args.numero
    attesa = getattr(args, "attesa", 180)
    tetto = getattr(args, "tetto", 900)

    inizio = adesso_fn()
    soglia_creazione = inizio - timedelta(seconds=60)

    # 1. Verifica etichette
    codice, uscita = _esegui_chiamata(
        esegui_fn, ["gh", "issue", "view", str(numero), "--json", "labels", *repo_args]
    )
    if codice != 0:
        motivo = uscita.strip() if uscita.strip() else f"codice {codice}"
        print(f"lancio non verificato: {motivo}", file=sys.stderr)
        return 1

    try:
        dati_issue = json.loads(uscita)
        etichette = [
            e.get("name") for e in dati_issue.get("labels", []) if isinstance(e, dict)
        ]
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"lancio non verificato: {exc}", file=sys.stderr)
        return 1

    if "bottega: fuori" in etichette:
        cmd_avvio = ["gh", "workflow", "run", "bottega-distributore.yml", *repo_args]
    else:
        cmd_avvio = [
            "gh",
            "issue",
            "edit",
            str(numero),
            "--add-label",
            "bottega: fuori",
            *repo_args,
        ]

    codice, uscita = _esegui_chiamata(esegui_fn, cmd_avvio)
    if codice != 0:
        motivo = uscita.strip() if uscita.strip() else f"codice {codice}"
        print(f"lancio non verificato: {motivo}", file=sys.stderr)
        return 1

    # 2. Attesa comparsa giro distributore ed esame dei registri
    letti: set[int] = set()
    giri_visti: set[int] = set()
    ultima_riga = f"nessuna riga per il lavoro {numero}"

    while True:
        cmd_list = [
            "gh",
            "run",
            "list",
            "--workflow",
            "bottega-distributore.yml",
            "--limit",
            "10",
            "--json",
            "databaseId,createdAt",
            *repo_args,
        ]
        codice, uscita = _esegui_chiamata(esegui_fn, cmd_list)
        if codice != 0:
            motivo = uscita.strip() if uscita.strip() else f"codice {codice}"
            print(f"lancio non verificato: {motivo}", file=sys.stderr)
            return 1

        try:
            elenco = json.loads(uscita)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"lancio non verificato: {exc}", file=sys.stderr)
            return 1

        nuovi: list[tuple[int, datetime]] = []
        if isinstance(elenco, list):
            for item in elenco:
                if isinstance(item, dict) and "databaseId" in item and "createdAt" in item:
                    try:
                        creato = datetime.fromisoformat(item["createdAt"])
                        id_giro = int(item["databaseId"])
                    except (ValueError, TypeError):
                        continue
                    if _differenza_secondi(soglia_creazione, creato) >= 0:
                        giri_visti.add(id_giro)
                        if id_giro not in letti:
                            nuovi.append((id_giro, creato))

        nuovi.sort(key=lambda t: (t[1], t[0]))

        for id_giro, _ in nuovi:
            letti.add(id_giro)
            inizio_giro = adesso_fn()
            giro_annullato = False
            while True:
                cmd_status = [
                    "gh",
                    "run",
                    "view",
                    str(id_giro),
                    "--json",
                    "status,conclusion",
                    *repo_args,
                ]
                codice, uscita = _esegui_chiamata(esegui_fn, cmd_status)
                if codice != 0:
                    motivo = uscita.strip() if uscita.strip() else f"codice {codice}"
                    print(f"lancio non verificato: {motivo}", file=sys.stderr)
                    return 1

                try:
                    info = json.loads(uscita)
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    print(f"lancio non verificato: {exc}", file=sys.stderr)
                    return 1

                if info.get("status") == "completed":
                    if info.get("conclusion") == "cancelled":
                        giro_annullato = True
                    break

                if _differenza_secondi(inizio_giro, adesso_fn()) >= tetto:
                    print(
                        f"lancio non verificato: giro {id_giro} non completato entro {tetto} s",
                        file=sys.stderr,
                    )
                    return 1

                dormi(10)

            if giro_annullato:
                continue

            cmd_log = ["gh", "run", "view", str(id_giro), "--log", *repo_args]
            codice, log_uscita = _esegui_chiamata(esegui_fn, cmd_log)
            if codice != 0:
                motivo = log_uscita.strip() if log_uscita.strip() else f"codice {codice}"
                print(f"lancio non verificato: {motivo}", file=sys.stderr)
                return 1

            esito, riga = esito_del_lavoro(log_uscita, numero)
            ultima_riga = riga
            if esito != "assente":
                print(f"giro {id_giro}: {riga}")
                return ESITI_LANCIO[esito]

        if not nuovi:
            if _differenza_secondi(inizio, adesso_fn()) >= attesa:
                break
            dormi(10)

    if not giri_visti:
        print(f"nessun giro del distributore entro {attesa} s", file=sys.stderr)
        return 1

    print(ultima_riga, file=sys.stderr)
    return 1


def argomenti_segui(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando bottega segui."""
    parser.add_argument("numero", type=int, help="numero del lavoro da seguire")
    parser.add_argument(
        "--repo", type=str, default=None, help="repository GitHub (proprietario/repo)"
    )
    parser.add_argument(
        "--intervallo",
        type=int,
        default=300,
        help="secondi fra un controllo e l'altro (di serie: 300)",
    )
    parser.add_argument(
        "--fermo",
        type=float,
        default=1200.0,
        help="secondi senza giri attivi prima di segnalare il fermo (di serie: 1200)",
    )
    parser.add_argument(
        "--tetto",
        type=float,
        default=18000.0,
        help="secondi massimi prima dello scadere del tempo (di serie: 18000)",
    )
    parser.add_argument(
        "--configurazione",
        type=Path,
        default=Path(PERCORSO_PREDEFINITO),
        help=f"percorso di bottega.toml (di serie: {PERCORSO_PREDEFINITO})",
    )


def comando_segui(
    args: argparse.Namespace,
    esegui: Callable[[Sequence[str], Mapping[str, str] | None], tuple[int, str]]
    | None = None,
    dormi: Callable[[float], None] = time.sleep,
    adesso: Callable[[], datetime] | None = None,
    board: Board | None = None,
) -> int:
    """Segue l'avanzamento di un lavoro finché non si conclude o si blocca."""
    esegui_fn = esegui or esecutore_gh
    adesso_fn = adesso or (lambda: datetime.now(UTC))

    if board is None:
        percorso_cfg = getattr(args, "configurazione", None) or Path(
            PERCORSO_PREDEFINITO
        )
        try:
            cfg = leggi_configurazione(percorso_cfg)
        except (ErroreConfigurazione, OSError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
            return 1

        repo = getattr(args, "repo", None) or os.environ.get("GITHUB_REPOSITORY", "")
        forgia = ForgiaGh(repo)
        if cfg.progetto.adattatore:
            board = BoardComando(shlex.split(cfg.progetto.adattatore))
        elif cfg.progetto.project is not None:
            proprietario = forgia.proprietario()
            board = BoardProject(
                proprietario=proprietario, numero=cfg.progetto.project, repo=repo
            )
        else:
            print(
                "errore: configurazione priva di progetto.project e senza adattatore",
                file=sys.stderr,
            )
            return 1

    numero = args.numero
    intervallo = getattr(args, "intervallo", 300)
    fermo = getattr(args, "fermo", 1200.0)
    tetto = getattr(args, "tetto", 18000.0)
    repo_arg = getattr(args, "repo", None)
    repo_args = ["--repo", repo_arg] if repo_arg else []

    inizio = adesso_fn()
    visti: set[int] = set()

    while True:
        ora = adesso_fn()
        if _differenza_secondi(inizio, ora) >= tetto:
            print("tempo scaduto")
            return 6

        # 1. Stato del lavoro dalla board
        stato: str | None = None
        try:
            lav = board.lavoro(numero)
            if lav is not None:
                stato = lav.stato
        except Exception as exc:  # noqa: BLE001
            print(f"avviso: board #{numero}: {exc}", file=sys.stderr)

        # 2. Sotto-issue da gh api
        if repo_arg:
            percorso_api = f"repos/{repo_arg}/issues/{numero}/sub_issues"
        else:
            percorso_api = f"repos/{{owner}}/{{repo}}/issues/{numero}/sub_issues"

        figli: list[bool] = []
        codice_sub, uscita_sub = _esegui_chiamata(
            esegui_fn, ["gh", "api", percorso_api]
        )
        if codice_sub != 0:
            motivo = (
                uscita_sub.strip() if uscita_sub.strip() else f"codice {codice_sub}"
            )
            print(f"avviso: {motivo}", file=sys.stderr)
        else:
            try:
                dati_sub = json.loads(uscita_sub)
                if isinstance(dati_sub, list):
                    figli = [
                        s.get("state") == "open"
                        for s in dati_sub
                        if isinstance(s, dict)
                    ]
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                print(f"avviso: sub_issues #{numero}: {exc}", file=sys.stderr)

        # 3. Giri Actions da gh workflow list e gh run list
        giri: list[Giro] = []
        cmd_wf = [
            "gh",
            "workflow",
            "list",
            "--all",
            "--json",
            "name,path",
            *repo_args,
        ]
        codice_wf, uscita_wf = _esegui_chiamata(esegui_fn, cmd_wf)
        if codice_wf != 0:
            motivo = (
                uscita_wf.strip() if uscita_wf.strip() else f"codice {codice_wf}"
            )
            print(f"avviso: {motivo}", file=sys.stderr)
        else:
            try:
                dati_wf = json.loads(uscita_wf)
                percorsi_wf: list[str] = []
                if isinstance(dati_wf, list):
                    for item in dati_wf:
                        if isinstance(item, dict):
                            nome_wf = item.get("name") or ""
                            if nome_wf.startswith("bottega-esecutore") and "path" in item:
                                percorsi_wf.append(str(item["path"]))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                print(f"avviso: workflow list: {exc}", file=sys.stderr)
                percorsi_wf = []

            for path_wf in percorsi_wf:
                cmd_run = [
                    "gh",
                    "run",
                    "list",
                    "--workflow",
                    path_wf,
                    "--limit",
                    "10",
                    "--json",
                    "databaseId,status,conclusion,createdAt,updatedAt",
                    *repo_args,
                ]
                codice_run, uscita_run = _esegui_chiamata(esegui_fn, cmd_run)
                if codice_run != 0:
                    motivo = (
                        uscita_run.strip()
                        if uscita_run.strip()
                        else f"codice {codice_run}"
                    )
                    print(f"avviso: {motivo}", file=sys.stderr)
                else:
                    try:
                        dati_run = json.loads(uscita_run)
                        if isinstance(dati_run, list):
                            for item in dati_run:
                                if isinstance(item, dict):
                                    giri.append(
                                        Giro(
                                            id=int(item["databaseId"]),
                                            stato=str(item.get("status", "")),
                                            conclusione=item.get("conclusion"),
                                            creato=datetime.fromisoformat(
                                                item["createdAt"]
                                            ),
                                            aggiornato=datetime.fromisoformat(
                                                item["updatedAt"]
                                            ),
                                        )
                                    )
                    except (json.JSONDecodeError, KeyError, ValueError) as exc:
                        print(f"avviso: run list: {exc}", file=sys.stderr)

        # 4. Giri rossi nuovi
        rossi_nuovi = giri_rossi_nuovi(giri, inizio, visti)
        for r_id in rossi_nuovi:
            visti.add(r_id)
            print(f"avviso: giro {r_id} finito male")

        # 5. Stampa riga breve del passo
        aperti = sum(1 for f in figli if f)
        tutti = len(figli)
        ora_str = ora.strftime("%H:%M")
        print(f"{ora_str} stato {stato} figli {aperti}/{tutti}")

        # 6. Verdetto
        esito_v = verdetto(
            stato=stato,
            figli=figli,
            giri=giri,
            inizio=inizio,
            adesso=ora,
            fermo_s=fermo,
        )
        if esito_v is not None:
            codice_res, testo_res = esito_v
            print(testo_res)
            return codice_res

        dormi(intervallo)
