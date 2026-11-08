"""Segni nei commenti, ruoli dei partecipanti, comandi e nota del giro."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

RUOLI: tuple[str, ...] = ("distributore", "esecutore", "consigliere", "revisore", "avviso")

_SEGNO_GENERICO = re.compile(r"<!--\s*bottega:[a-z]+\s*-->")
_SEGNO_RUOLO = re.compile(r"<!--\s*bottega:\s*([a-z]+)\s*-->")
_COMANDI_VALIDI = frozenset({"riprova", "consulta", "sospendi"})


@dataclass(frozen=True)
class Comando:
    """Un comando inviato alla bottega attraverso un commento su GitHub."""

    nome: str
    argomento: str = ""


def segna(testo: str, ruolo: str) -> str:
    """Appone il segno del ruolo alla prima riga del testo."""
    if ruolo not in RUOLI:
        raise ValueError(f"Ruolo non valido: {ruolo!r}; ammessi: {', '.join(RUOLI)}")
    segno = f"<!-- bottega:{ruolo} -->"
    if testo:
        return f"{segno}\n{testo}"
    return segno


def ruolo(testo: str) -> str | None:
    """Il ruolo estratto dal segno nel testo; None se manca o se il ruolo non è fra quelli ammessi."""
    for m in _SEGNO_RUOLO.finditer(testo):
        r = m.group(1)
        if r in RUOLI:
            return r
    return None


def comando(corpo: str, autore: str, comandanti: Sequence[str]) -> Comando | None:
    """Estrae il comando dal corpo di un commento se l'autore è fra i comandanti e non vi sono segni.

    Restituisce None se il testo porta un segno, se l'autore non è un comandante (confronto
    senza badare alle maiuscole), se manca `/bottega`, se il comando non è valido o se
    un comando `consulta` è privo di domanda.
    """
    if _SEGNO_GENERICO.search(corpo):
        return None

    if not autore:
        return None

    comandanti_normalizzati = {c.strip().lower() for c in comandanti}
    if autore.strip().lower() not in comandanti_normalizzati:
        return None

    righe = corpo.splitlines()
    indice_prima_riga = None
    for idx, riga in enumerate(righe):
        if riga.strip():
            indice_prima_riga = idx
            break

    if indice_prima_riga is None:
        return None

    prima_riga = righe[indice_prima_riga].strip()
    altre_righe = righe[indice_prima_riga + 1 :]

    parti = prima_riga.split(None, 2)
    if not parti or parti[0] != "/bottega":
        return None

    if len(parti) < 2:
        return None

    nome = parti[1].lower()
    if nome not in _COMANDI_VALIDI:
        return None

    argomento_prima_riga = parti[2].strip() if len(parti) > 2 else ""
    resto_righe = "\n".join(altre_righe).strip()

    if argomento_prima_riga and resto_righe:
        argomento = f"{argomento_prima_riga}\n{resto_righe}"
    elif argomento_prima_riga:
        argomento = argomento_prima_riga
    else:
        argomento = resto_righe

    if nome == "consulta" and not argomento:
        return None

    return Comando(nome=nome, argomento=argomento)


def nota(testo: str | None) -> dict[str, str]:
    """Interpreta la nota del giro (`chiave=valore; ...`) in un dizionario.

    Restituisce `{}` se il testo è vuoto o None.
    """
    if not testo or not testo.strip():
        return {}
    risultato: dict[str, str] = {}
    for pezzo in testo.split(";"):
        pezzo = pezzo.strip()
        if not pezzo or "=" not in pezzo:
            continue
        chiave, _, valore = pezzo.partition("=")
        chiave = chiave.strip()
        valore = valore.strip()
        if chiave:
            risultato[chiave] = valore
    return risultato


def scrivi_nota(valori: Mapping[str, str]) -> str:
    """Scrive i valori della nota con chiavi in ordine alfabetico e caratteri speciali ripuliti.

    Un valore non può contenere `;`, `=` o a capo: vengono sostituiti con uno spazio.
    """
    if not valori:
        return ""
    elementi: list[str] = []
    for chiave in sorted(valori.keys()):
        val = str(valori[chiave])
        val_pulito = re.sub(r"[;=\r\n]", " ", val)
        elementi.append(f"{chiave}={val_pulito}")
    return "; ".join(elementi)
