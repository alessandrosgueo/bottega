"""Le misure della bottega: campi, aggregazione e lettura per la scelta viva.

Definisce i campi del Project per le misure (B5-R1), la somma con gestione degli errori (B5-R3),
la lettura dei risultati storici e dei costi propri relativi per il campionamento di Thompson (B5-R8).
Solo libreria standard.
"""

from collections import defaultdict
from collections.abc import Sequence
import math
import sys

from bottega.board import Board, Lavoro
from bottega.configurazione import Configurazione
from bottega.scelta import Risultati

CAMPI: dict[str, str] = {
    "Porta": "TEXT",
    "Dove": "TEXT",
    "Durata": "NUMBER",
    "Giri": "NUMBER",
    "Consulti": "NUMBER",
    "Token esecutore": "NUMBER",
    "Token di chi decide": "NUMBER",
    "Segno": "TEXT",
    "Misure parziali": "TEXT",
    "Esito del compito": "SINGLE_SELECT",
    "Rilievi del piano": "NUMBER",
    "Rilievi del brief": "NUMBER",
    "Rilievi dell'esecuzione": "NUMBER",
    "Consigli accolti": "NUMBER",
    "Consigli respinti": "NUMBER",
}

OPZIONI_ESITO: tuple[str, ...] = ("unito com'era", "corretto", "rifiutato")


def numero(lavoro: Lavoro, nome: str) -> float:
    """Il valore del campo come float, 0.0 se vuoto o non numerico."""
    val = lavoro.campi.get(nome)
    if not val:
        return 0.0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def somma(board: Board, numero_lavoro: int, nome: str, quanto: float) -> bool:
    """Somma quanto al valore attuale del campo e scrive sulla board.

    Non solleva mai: un eventuale errore si stampa su stderr e la funzione dà False.
    """
    try:
        lav = board.lavoro(numero_lavoro)
    except Exception as e:
        print(f"misure: {nome} del #{numero_lavoro} non scritta: {e}", file=sys.stderr)
        return False

    if lav is None:
        print(f"misure: {nome} del #{numero_lavoro} non scritta: lavoro non trovato sulla board", file=sys.stderr)
        return False

    attuale = numero(lav, nome)
    nuovo = attuale + quanto
    nuovo_val: int | float = int(nuovo) if nuovo.is_integer() else nuovo

    try:
        board.campo(numero_lavoro, nome, nuovo_val)
        return True
    except Exception as e:
        print(f"misure: {nome} del #{numero_lavoro} non scritta: {e}", file=sys.stderr)
        return False


def _trova_candidato_id(esecutore: str, configurazione: Configurazione) -> str | None:
    esec_norm = esecutore.strip().lower()
    for cid, cand in configurazione.candidati.items():
        if esec_norm == cand.id.lower() or esec_norm == cand.nome.lower():
            return cand.id
    return None


def risultati(lavori: Sequence[Lavoro], configurazione: Configurazione) -> dict[tuple[str, str], Risultati]:
    """Risultati storici per (candidato_id, etichetta) e (candidato_id, '*')."""
    conteggi: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])

    for lav in lavori:
        esito = lav.campi.get("Esito del compito")
        if esito not in OPZIONI_ESITO:
            continue

        esec_testo = lav.campi.get("Esecutore") or lav.esecutore
        if not esec_testo:
            continue

        cid = _trova_candidato_id(esec_testo, configurazione)
        if cid is None:
            continue

        if esito == "unito com'era":
            idx = 0
        elif esito == "corretto":
            idx = 1
        else:
            idx = 2

        conteggi[(cid, "*")][idx] += 1
        for etichetta in set(lav.etichette):
            conteggi[(cid, etichetta)][idx] += 1

    return {
        chiave: Risultati(uniti=c[0], corretti=c[1], rifiutati=c[2])
        for chiave, c in conteggi.items()
    }


def costi_propri(lavori: Sequence[Lavoro], configurazione: Configurazione) -> dict[str, float]:
    """Costi propri relativi: media Token esecutore divisa per la media delle medie con dati.

    I candidati senza dati non compaiono nel dizionario.
    """
    token_per_candidato: dict[str, list[float]] = {}

    for lav in lavori:
        esec_testo = lav.campi.get("Esecutore") or lav.esecutore
        if not esec_testo:
            continue
        cid = _trova_candidato_id(esec_testo, configurazione)
        if cid is None:
            continue
        tok = numero(lav, "Token esecutore")
        if tok > 0:
            token_per_candidato.setdefault(cid, []).append(tok)

    if not token_per_candidato:
        return {}

    medie: dict[str, float] = {
        cid: sum(valori) / len(valori)
        for cid, valori in token_per_candidato.items()
    }

    media_delle_medie = sum(medie.values()) / len(medie)
    if media_delle_medie <= 0:
        return {cid: 1.0 for cid in medie}

    return {
        cid: media / media_delle_medie
        for cid, media in medie.items()
    }
