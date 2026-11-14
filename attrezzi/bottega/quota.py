"""Lo stato della quota di una bottega o di un secchio: variabile di Actions e controllo della disponibilità.

Una bottega (o secchio) con quota esaurita ha la variabile `BOTTEGA_QUOTA_<ID>` (o `BOTTEGA_QUOTA_<ID>__<SECCHIO>`)
impostata a `esaurita fino a <ISO 8601 con fuso>`. Un valore assente o vuoto indica quota disponibile. Un valore
malformato o senza fuso viene considerato disponibile con un avviso, per non bloccare mai una bottega per errore. Solo
libreria standard.
"""

from datetime import datetime

PREFISSO_QUOTA = "BOTTEGA_QUOTA_"
TESTO_ESAURITA = "esaurita fino a "


def nome_variabile(id_bottega: str, secchio: str | None = None) -> str:
    """Il nome della variabile di Actions per la quota della bottega (o di un suo secchio)."""
    base = f"{PREFISSO_QUOTA}{id_bottega.upper().replace('-', '_')}"
    if secchio:
        return f"{base}__{secchio.upper().replace('-', '_')}"
    return base


def valore_esaurita(fino_a: datetime) -> str:
    """Il valore della variabile di quota quando è esaurita fino a un dato istante (con fuso)."""
    if fino_a.tzinfo is None or fino_a.tzinfo.utcoffset(fino_a) is None:
        raise ValueError("fino_a deve avere un fuso orario")
    return f"{TESTO_ESAURITA}{fino_a.isoformat()}"


def disponibile(valore: str | None, adesso: datetime) -> tuple[bool, str | None]:
    """Verifica se la quota è disponibile rispetto all'istante `adesso`.

    Restituisce una tupla `(disponibile, avviso)`. Un valore vuoto o assente è disponibile senza avviso.
    Un valore non interpretabile o con data senza fuso vale disponibile con un avviso esplicativo.
    """
    if adesso.tzinfo is None or adesso.tzinfo.utcoffset(adesso) is None:
        raise ValueError("adesso deve avere un fuso orario")
    if valore is None:
        return True, None
    if not isinstance(valore, str):
        return True, f"valore della quota non valido (non è una stringa): «{valore}»"
    testo = valore.strip()
    if not testo:
        return True, None
    if not testo.startswith(TESTO_ESAURITA):
        return True, f"valore della quota non riconosciuto: «{testo}»"
    parte_data = testo[len(TESTO_ESAURITA) :].strip()
    try:
        fino_a = datetime.fromisoformat(parte_data)
    except (ValueError, TypeError) as e:
        return True, f"data della quota non valida: «{testo}» ({e})"
    if fino_a.tzinfo is None or fino_a.tzinfo.utcoffset(fino_a) is None:
        return True, f"data della quota senza fuso orario: «{testo}»"
    if adesso < fino_a:
        return False, None
    return True, None
