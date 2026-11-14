"""Lettura del brief di un compito e convenzioni del ramo."""

import re
import unicodedata

_TITOLO_FATTO_QUANDO = re.compile(r"^##\s+Fatto quando(?:\s*:)?\s*$", re.IGNORECASE | re.MULTILINE)
_TITOLO_FILE = re.compile(r"^##\s+File(?:\s*:)?\s*$", re.IGNORECASE)
_INIZIO_RECINTO = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_PROSSIMO_TITOLO = re.compile(r"^#{1,2}\s+\S")
_VOCE_FILE = re.compile(r"^[ \t]*[-*+][ \t]+`([^`\n]+)`")


def _chiude_recinto(riga: str, recinto_aperto: str) -> bool:
    return bool(
        re.match(r"^[ \t]*" + re.escape(recinto_aperto) + re.escape(recinto_aperto[0]) + r"*[ \t]*$", riga)
    )


def file_del_brief(corpo: str) -> list[str]:
    """I percorsi della sezione «## File» (elenco puntato fra apici inversi), in ordine e senza duplicati.

    Ignora i titoli e gli elenchi dentro i blocchi di codice recintati.
    """
    if not corpo:
        return []

    recinto_aperto: str | None = None
    in_sezione = False
    percorsi: list[str] = []
    visti: set[str] = set()

    for riga in corpo.splitlines():
        if recinto_aperto is not None:
            if _chiude_recinto(riga, recinto_aperto):
                recinto_aperto = None
            continue

        m_recinto = _INIZIO_RECINTO.match(riga)
        if m_recinto:
            recinto_aperto = m_recinto.group(1)
            continue

        if not in_sezione:
            if _TITOLO_FILE.match(riga):
                in_sezione = True
            continue

        if _PROSSIMO_TITOLO.match(riga):
            break

        m_voce = _VOCE_FILE.match(riga)
        if m_voce:
            percorso = m_voce.group(1).strip()
            if percorso and percorso not in visti:
                visti.add(percorso)
                percorsi.append(percorso)

    return percorsi


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
            # Chiude un recinto dello stesso carattere lungo almeno quanto quello d'apertura (CommonMark).
            if re.match(r"^[ \t]*" + re.escape(recinto_aperto) + re.escape(recinto_aperto[0]) + r"*[ \t]*$", riga):
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
