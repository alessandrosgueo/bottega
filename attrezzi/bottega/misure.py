"""Le misure della bottega: campi, aggregazione e lettura per la scelta viva.

Definisce i campi del Project per le misure (B5-R1), la somma con gestione degli errori (B5-R3),
la lettura dei risultati storici e dei costi propri relativi per il campionamento di Thompson (B5-R8).
Solo libreria standard.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math
import sys

from bottega.board import Board, Lavoro
from bottega.configurazione import Configurazione
from bottega.porte import somma_pesata
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
    "Misurato da": "TEXT",
    "Esito del compito": "SINGLE_SELECT",
    "Rilievi del piano": "NUMBER",
    "Rilievi del brief": "NUMBER",
    "Rilievi dell'esecuzione": "NUMBER",
    "Consigli accolti": "NUMBER",
    "Consigli respinti": "NUMBER",
}

OPZIONI_ESITO: tuple[str, ...] = ("unito com'era", "corretto", "rifiutato")

# La voce di `Misure parziali` di un compito eseguito da più candidati: non entra in risultati e costi.
PIU_ESECUTORI = "più esecutori"

# L'intestazione del commento che il giro scrive sul lavoro madre quando una misura non entra sulla board (B10-R1):
# `bottega segui` la cerca fra i commenti per avvisare.
INTESTAZIONE_MISURE_PERSE = "Misure non scritte sulla board"


def _di_piu_esecutori(lavoro: Lavoro) -> bool:
    voci = [v.strip() for v in (lavoro.campi.get("Misure parziali") or "").split(",")]
    return PIU_ESECUTORI in voci


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
        if _di_piu_esecutori(lav):
            continue
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
        if _di_piu_esecutori(lav):
            continue
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


# Le chiavi dei contatori di ogni porta (l'uscita del lancio) e quella della lettura dalla cache, che pesa un decimo.
_CHIAVI_CONTATORI: dict[str, tuple[tuple[str, ...], str]] = {
    "claude-code": (
        ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"),
        "cache_read_input_tokens",
    ),
    "antigravity": (("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens"), "cache_read_tokens"),
    "pi": (("input", "output", "cacheRead", "cacheWrite"), "cacheRead"),
    "copilot-cli": (("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"), "cacheReadTokens"),
}


def token_dei_contatori(porta: str, contatori: Mapping[str, int]) -> int:
    """I token pesati dei contatori dell'uscita di una porta (B5-R5 e R6): una lettura dalla cache vale un decimo.

    Si sommano le parti, non il totale della porta (che conterebbe le letture dalla cache per intero); solo se le parti
    mancano si prende il totale. Un contatore che non è un intero vale 0.
    """
    puliti = {k: v for k, v in contatori.items() if isinstance(v, int) and not isinstance(v, bool)}
    chiavi, cache_letta = _CHIAVI_CONTATORI.get(porta, ((), ""))
    if any(k in puliti for k in chiavi):
        return somma_pesata(puliti, chiavi, cache_letta=cache_letta) or 0
    for totale in ("total_tokens", "totalTokens"):
        if totale in puliti:
            return puliti[totale]
    return 0
