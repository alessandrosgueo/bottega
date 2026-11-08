"""I conti delle misure della bottega (B5-R9).

Aggrega per candidato e per Dove (fuori, sessione) le misure dei compiti registrate nel Project:
compiti, giri medi, durata media, token esecutore medi, token di chi decide medi (solo compiti col numero;
quanti senza), esiti per tipo, rilievi per origine, consigli.
Mostra in fondo la spia (costo decisore fuori vs sessione).
Solo libreria standard.
"""

import argparse
from collections import defaultdict
from collections.abc import Sequence
import json
import math
import os
from pathlib import Path
import shlex
import sys
from typing import Any

import bottega.misure as misure
from bottega.board import Board, BoardComando, BoardProject, Lavoro
from bottega.configurazione import PERCORSO_PREDEFINITO, ErroreConfigurazione, leggi_configurazione
from bottega.forgia import ForgiaGh
from bottega.misure import CAMPI, OPZIONI_ESITO, numero


def _ha_misura(lav: Lavoro) -> bool:
    """Vero se il lavoro possiede almeno un valore per i campi di misura del Project."""
    return any(lav.campi.get(k, "").strip() != "" for k in CAMPI)


def _statistiche_gruppo(lavori: Sequence[Lavoro]) -> dict[str, Any]:
    """Calcola le statistiche aggregate per un insieme di compiti misurati."""
    n = len(lavori)
    if n == 0:
        return {
            "compiti": 0,
            "giri_medi": None,
            "durata_media": None,
            "token_esecutore_medi": None,
            "token_decisore_medi": None,
            "senza_numero": 0,
            "esiti": {k: 0 for k in OPZIONI_ESITO},
            "rilievi": {"piano": 0, "brief": 0, "esecuzione": 0},
            "consigli": {"accolti": 0, "respinti": 0},
        }

    somma_giri = sum(numero(l, "Giri") for l in lavori)
    somma_durata = sum(numero(l, "Durata") for l in lavori)
    somma_tok_esec = sum(numero(l, "Token esecutore") for l in lavori)

    # Token di chi decide: media sui soli compiti col numero; quanti senza
    con_numero = 0
    somma_tok_dec = 0.0
    for l in lavori:
        val = l.campi.get("Token di chi decide")
        if val is not None and val.strip() != "":
            try:
                f = float(val)
                if not (math.isnan(f) or math.isinf(f)):
                    somma_tok_dec += f
                    con_numero += 1
            except (ValueError, TypeError):
                pass

    senza_numero = n - con_numero
    token_decisore_medi = (somma_tok_dec / con_numero) if con_numero > 0 else None

    # Esiti
    esiti: dict[str, int] = {k: 0 for k in OPZIONI_ESITO}
    for l in lavori:
        esito = l.campi.get("Esito del compito")
        if esito in esiti:
            esiti[esito] += 1

    # Rilievi
    rilievi = {
        "piano": int(sum(numero(l, "Rilievi del piano") for l in lavori)),
        "brief": int(sum(numero(l, "Rilievi del brief") for l in lavori)),
        "esecuzione": int(sum(numero(l, "Rilievi dell'esecuzione") for l in lavori)),
    }

    # Consigli
    consigli = {
        "accolti": int(sum(numero(l, "Consigli accolti") for l in lavori)),
        "respinti": int(sum(numero(l, "Consigli respinti") for l in lavori)),
    }

    return {
        "compiti": n,
        "giri_medi": somma_giri / n,
        "durata_media": somma_durata / n,
        "token_esecutore_medi": somma_tok_esec / n,
        "token_decisore_medi": token_decisore_medi,
        "senza_numero": senza_numero,
        "esiti": esiti,
        "rilievi": rilievi,
        "consigli": consigli,
    }


def conti(lavori: Sequence[Lavoro]) -> dict[str, Any]:
    """Aggrega le misure dei compiti della board: per_candidato, per_dove e spia."""
    lavori_misurati = [l for l in lavori if _ha_misura(l)]

    per_candidato: dict[str, list[Lavoro]] = defaultdict(list)
    for l in lavori_misurati:
        if misure.PIU_ESECUTORI in [v.strip() for v in (l.campi.get("Misure parziali") or "").split(",")]:
            continue
        esec = l.campi.get("Esecutore") or l.esecutore
        if esec and esec.strip():
            per_candidato[esec.strip()].append(l)

    stats_candidati = {
        nome: _statistiche_gruppo(lavs)
        for nome, lavs in sorted(per_candidato.items())
    }

    fuori_lavs = [l for l in lavori_misurati if l.campi.get("Dove", "").strip().lower() == "fuori"]
    sessione_lavs = [l for l in lavori_misurati if l.campi.get("Dove", "").strip().lower() == "sessione"]

    stats_dove = {
        "fuori": _statistiche_gruppo(fuori_lavs),
        "sessione": _statistiche_gruppo(sessione_lavs),
    }

    spia = {
        "fuori": stats_dove["fuori"]["token_decisore_medi"],
        "sessione": stats_dove["sessione"]["token_decisore_medi"],
    }

    return {
        "per_candidato": stats_candidati,
        "per_dove": stats_dove,
        "spia": spia,
    }


def _fmt(val: float | int | None) -> str:
    """Formatta un valore numerico per il resoconto; None diventa un trattino em-dash."""
    if val is None:
        return "—"
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.1f}"
    return str(val)


def _formatta_gruppo(titolo: str, s: dict[str, Any]) -> list[str]:
    return [
        f"{titolo}:",
        f"  compiti: {s['compiti']}",
        f"  giri medi: {_fmt(s['giri_medi'])}",
        f"  durata media: {_fmt(s['durata_media'])}",
        f"  token esecutore medi: {_fmt(s['token_esecutore_medi'])}",
        f"  token di chi decide medi: {_fmt(s['token_decisore_medi'])} (senza numero: {s['senza_numero']})",
        (
            f"  esiti: uniti com'erano {s['esiti'].get('unito com\'era', 0)}, "
            f"corretti {s['esiti'].get('corretto', 0)}, "
            f"rifiutati {s['esiti'].get('rifiutato', 0)}"
        ),
        (
            f"  rilievi: piano {s['rilievi'].get('piano', 0)}, "
            f"brief {s['rilievi'].get('brief', 0)}, "
            f"esecuzione {s['rilievi'].get('esecuzione', 0)}"
        ),
        f"  consigli: accolti {s['consigli'].get('accolti', 0)}, respinti {s['consigli'].get('respinti', 0)}",
    ]


def testo_conti(d: dict[str, Any]) -> str:
    """Scrive le statistiche dei conti in formato testuale leggibile, usando — per None."""
    righe: list[str] = []
    if d.get("per_candidato"):
        righe.append("Per candidato:")
        for nome, stats in d["per_candidato"].items():
            righe.extend(_formatta_gruppo(f"  {nome}", stats))
    if d.get("per_dove"):
        righe.append("Per dove:")
        for dove in ("fuori", "sessione"):
            if dove in d["per_dove"]:
                righe.extend(_formatta_gruppo(f"  {dove}", d["per_dove"][dove]))
    if "spia" in d:
        spia = d["spia"]
        righe.append("Spia (token decisore medi per compito):")
        righe.append(f"  fuori: {_fmt(spia.get('fuori'))}")
        righe.append(f"  sessione: {_fmt(spia.get('sessione'))}")
    return "\n".join(righe) + "\n"


testo_conti.__test__ = False


def argomenti_conti(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando conti."""
    parser.add_argument(
        "--json",
        action="store_true",
        help="stampa i conti in formato JSON",
    )
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="PERCORSO",
        help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
    )
    parser.add_argument(
        "--repo",
        default="",
        metavar="REPO",
        help="il repo di GitHub (predefinito: da GITHUB_REPOSITORY)",
    )


def comando_conti(args: argparse.Namespace, board: Board | None = None) -> int:
    """Legge i conti delle misure dalla board: esce 0 se eseguito, 1 con errore."""
    if board is None:
        percorso_cfg = Path(args.file)
        try:
            cfg = leggi_configurazione(percorso_cfg)
        except (ErroreConfigurazione, OSError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
            return 1

        repo = getattr(args, "repo", None) or os.environ.get("GITHUB_REPOSITORY", "")
        forgia = ForgiaGh(repo)
        try:
            if cfg.progetto.adattatore:
                board = BoardComando(shlex.split(cfg.progetto.adattatore))
            elif cfg.progetto.project is not None:
                proprietario = forgia.proprietario()
                board = BoardProject(proprietario=proprietario, numero=cfg.progetto.project, repo=repo)
            else:
                print("errore: configurazione priva di progetto.project e senza adattatore", file=sys.stderr)
                return 1
        except Exception as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {motivo}", file=sys.stderr)
            return 1

    try:
        lavori = board.elenco()
    except Exception as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        print(f"errore: {motivo}", file=sys.stderr)
        return 1

    d = conti(lavori)
    if getattr(args, "json", False):
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        print(testo_conti(d), end="")
    return 0
