"""Lo stato della quota di una bottega o di un secchio: variabile di Actions e controllo della disponibilità.

Una bottega (o secchio) con quota esaurita ha la variabile `BOTTEGA_QUOTA_<ID>` (o `BOTTEGA_QUOTA_<ID>__<SECCHIO>`)
impostata a `esaurita fino a <ISO 8601 con fuso>`. Un valore assente o vuoto indica quota disponibile. Un valore
malformato o senza fuso viene considerato disponibile con un avviso, per non bloccare mai una bottega per errore. Solo
libreria standard.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re

PREFISSO_QUOTA = "BOTTEGA_QUOTA_"
PREFISSO_PUNTI = "BOTTEGA_PUNTI_"
TESTO_ESAURITA = "esaurita fino a "
_EPOCH_ZERO = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_SPAZI_MULTIPLI = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class PuntoQuota:
    """Rilevazione dei punti percentuali residui di un gruppo di quota."""

    gruppo: str
    settimana: int
    rinnovo_settimana: datetime
    cinque_ore: int
    rinnovo_cinque_ore: datetime


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


def nome_variabile_punti(id_bottega: str) -> str:
    """Il nome della variabile di Actions per i punti di quota della bottega."""
    return f"{PREFISSO_PUNTI}{id_bottega.upper().replace('-', '_')}"


def _parse_iso_utc(testo: str) -> datetime | None:
    """Analizza una data ISO 8601 e la normalizza in UTC aware."""
    s = testo.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = f"{s[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _formatta_iso_utc(dt: datetime) -> str:
    """Formatta un datetime in ISO 8601 UTC con suffisso Z."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.isoformat().replace("+00:00", "Z")


def analizza_uscita_quota(testo: str) -> dict[str, PuntoQuota]:
    """Analizza l'uscita di `agy -p /quota` (TSV a 4 colonne o separata da spazi multipli)."""
    parziali: dict[str, dict[str, tuple[int, datetime]]] = {}
    for riga in testo.splitlines():
        pulita = riga.strip()
        if not pulita or pulita.casefold() == "quota:":
            continue
        if "\t" in pulita:
            campi = [c.strip() for c in pulita.split("\t")]
        else:
            campi = [c.strip() for c in _SPAZI_MULTIPLI.split(pulita)]
        if len(campi) != 4:
            continue
        gruppo, etichetta, perc_raw, data_raw = campi
        if not gruppo or not perc_raw.endswith("%"):
            continue
        try:
            perc = int(perc_raw[:-1].strip())
        except ValueError:
            continue
        if not (0 <= perc <= 100):
            continue
        dt = _parse_iso_utc(data_raw)
        if dt is None:
            continue
        et_cf = etichetta.casefold()
        if et_cf == "weekly limit remaining":
            parziali.setdefault(gruppo, {})["settimana"] = (perc, dt)
        elif et_cf == "five hour limit remaining":
            parziali.setdefault(gruppo, {})["cinque_ore"] = (perc, dt)

    risultato: dict[str, PuntoQuota] = {}
    for gruppo, voci in parziali.items():
        sett, rin_sett = voci.get("settimana", (100, _EPOCH_ZERO))
        c5h, rin_5h = voci.get("cinque_ore", (100, _EPOCH_ZERO))
        risultato[gruppo] = PuntoQuota(
            gruppo=gruppo,
            settimana=sett,
            rinnovo_settimana=rin_sett,
            cinque_ore=c5h,
            rinnovo_cinque_ore=rin_5h,
        )
    return risultato


def formatta_punti(punti: Mapping[str, PuntoQuota], rilevato: datetime) -> str:
    """Serializza i punti di quota in JSON compatto per la variabile di Actions."""
    payload = {
        "rilevato": _formatta_iso_utc(rilevato),
        "gruppi": {
            gruppo: {
                "settimana": p.settimana,
                "rinnovo_settimana": _formatta_iso_utc(p.rinnovo_settimana),
                "cinque_ore": p.cinque_ore,
                "rinnovo_cinque_ore": _formatta_iso_utc(p.rinnovo_cinque_ore),
            }
            for gruppo, p in punti.items()
        },
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def leggi_punti(valore: str | None) -> tuple[datetime | None, dict[str, PuntoQuota]]:
    """Legge il JSON di `BOTTEGA_PUNTI_*`; restituisce `(None, {})` su valori assenti o malformati."""
    if not valore or not isinstance(valore, str):
        return None, {}
    try:
        dati = json.loads(valore)
    except (json.JSONDecodeError, TypeError):
        return None, {}
    if not isinstance(dati, dict):
        return None, {}

    ril_raw = dati.get("rilevato")
    gruppi_raw = dati.get("gruppi")
    if not isinstance(ril_raw, str) or not isinstance(gruppi_raw, dict):
        return None, {}
    rilevato = _parse_iso_utc(ril_raw)
    if rilevato is None:
        return None, {}

    punti: dict[str, PuntoQuota] = {}
    for gruppo, voce in gruppi_raw.items():
        if not isinstance(gruppo, str) or not isinstance(voce, dict):
            return None, {}
        sett = voce.get("settimana")
        c5h = voce.get("cinque_ore")
        rin_sett_raw = voce.get("rinnovo_settimana")
        rin_5h_raw = voce.get("rinnovo_cinque_ore")
        if (
            type(sett) is not int
            or type(c5h) is not int
            or not isinstance(rin_sett_raw, str)
            or not isinstance(rin_5h_raw, str)
        ):
            return None, {}
        rin_sett = _parse_iso_utc(rin_sett_raw)
        rin_5h = _parse_iso_utc(rin_5h_raw)
        if rin_sett is None or rin_5h is None:
            return None, {}
        punti[gruppo] = PuntoQuota(
            gruppo=gruppo,
            settimana=sett,
            rinnovo_settimana=rin_sett,
            cinque_ore=c5h,
            rinnovo_cinque_ore=rin_5h,
        )
    return rilevato, punti


def differenza_punti(
    prima: Mapping[str, PuntoQuota] | None,
    dopo: Mapping[str, PuntoQuota] | None,
) -> dict[str, tuple[int, int]]:
    """Calcola i punti percentuali consumati fra `prima` e `dopo` per ogni gruppo variato."""
    if not prima or not dopo:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for gruppo, p1 in prima.items():
        p2 = dopo.get(gruppo)
        if p2 is None:
            continue
        d_sett = max(0, p1.settimana - p2.settimana)
        d_5h = max(0, p1.cinque_ore - p2.cinque_ore)
        if d_sett > 0 or d_5h > 0:
            out[gruppo] = (d_sett, d_5h)
    return out
