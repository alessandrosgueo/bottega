"""Lettura del brief di un compito e convenzioni del ramo."""

import re
import unicodedata

_TITOLO_FATTO_QUANDO = re.compile(r"^##\s+Fatto quando(?:\s*:)?\s*$", re.IGNORECASE | re.MULTILINE)
_PROSSIMO_TITOLO = re.compile(r"^#{1,2}\s+\S", re.MULTILINE)
_PRIMO_BLOCCO = re.compile(
    r"^[ \t]*(`{3,})[^\r\n]*\r?\n(.*?)\r?\n[ \t]*\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def fatto_quando(corpo: str) -> str | None:
    """Il comando del primo blocco recintato dopo «## Fatto quando» e prima della sezione seguente.

    Restituisce None se manca il titolo, se manca il blocco o se il blocco è vuoto.
    """
    if not corpo:
        return None

    m = _TITOLO_FATTO_QUANDO.search(corpo)
    if not m:
        return None

    testo_dopo = corpo[m.end() :]
    m_fine = _PROSSIMO_TITOLO.search(testo_dopo)
    sezione = testo_dopo[: m_fine.start()] if m_fine else testo_dopo

    m_blocco = _PRIMO_BLOCCO.search(sezione)
    if not m_blocco:
        return None

    contenuto = m_blocco.group(2).strip()
    return contenuto if contenuto else None


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
