"""Lettura del brief di un compito e convenzioni del ramo."""

import re
import unicodedata

_TITOLO_FATTO_QUANDO = re.compile(r"^##\s+Fatto quando(?:\s*:)?\s*$", re.IGNORECASE | re.MULTILINE)
_INIZIO_RECINTO = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_PROSSIMO_TITOLO = re.compile(r"^#{1,2}\s+\S")


def fatto_quando(corpo: str) -> str | None:
    """Il comando del primo blocco recintato dopo «## Fatto quando» e prima della sezione seguente.

    Trova prima i recinti di codice, poi i titoli fuori dai recinti. Un '#' di commento nel blocco
    non lo annulla. Restituisce None se manca il titolo, se manca il blocco o se il blocco è vuoto.
    """
    if not corpo:
        return None

    m = _TITOLO_FATTO_QUANDO.search(corpo)
    if not m:
        return None

    testo_dopo = corpo[m.end() :]
    righe = testo_dopo.splitlines()

    recinto_aperto: str | None = None
    contenuto_blocco: list[str] = []

    for riga in righe:
        if recinto_aperto is None:
            if _PROSSIMO_TITOLO.match(riga):
                break
            m_recinto = _INIZIO_RECINTO.match(riga)
            if m_recinto:
                recinto_aperto = m_recinto.group(1)
                contenuto_blocco = []
        else:
            if re.match(r"^[ \t]*" + re.escape(recinto_aperto) + r"[ \t]*$", riga):
                testo = "\n".join(contenuto_blocco).strip()
                return testo if testo else None
            contenuto_blocco.append(riga)

    return None


def ramo(numero: int, titolo: str) -> str:
    """Il nome del ramo git per un lavoro: `bottega/<numero>-<slug>`.

    Lo slug è in minuscolo, lettere accentate ridotte alla lettera base,
    caratteri non a-z0-9 convertiti in trattino, trattini ripetuti uniti,
    nessun trattino in testa e in coda, al più 40 caratteri senza lasciare
    trattini finali. Con titolo vuoto restituisce solo `bottega/<numero>`.
    """
    decomposto = unicodedata.normalize("NFKD", titolo or "")
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    minuscolo = senza_accenti.lower()
    con_trattini = re.sub(r"[^a-z0-9]+", "-", minuscolo)
    slug = con_trattini.strip("-")[:40].rstrip("-")

    if not slug:
        return f"bottega/{numero}"
    return f"bottega/{numero}-{slug}"
