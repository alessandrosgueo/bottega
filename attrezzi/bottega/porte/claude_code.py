"""Adattatore per la porta Claude Code (`claude`).

Gestisce il lancio non interattivo con `--output-format json`, la ripresa con `--resume`,
la modalità di sola lettura e il riconoscimento dei limiti di quota e di spesa con l'orario di rinnovo.
Solo libreria standard.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import re

from bottega.porte import Controllo, Lancio, controlla_eseguibile, esegui_porta

_REGEX_RINNOVO = re.compile(
    r"resets\s+(?:([A-Za-z]+)\s+)?(\d{1,2}):(\d{2})\s*(am|pm)",
    re.IGNORECASE,
)
_GIORNI = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def parse_rinnovo_claude(testo: str, adesso: datetime | None = None) -> datetime | None:
    """Estrae l'orario di rinnovo dai messaggi di Claude Code (es. 'resets 3:45pm' o 'resets Mon 12:00am').

    Restituisce il prossimo istante nel fuso orario di `adesso` (o nel fuso locale di sistema).
    Se non presente o non interpretabile, restituisce None.
    """
    match = _REGEX_RINNOVO.search(testo)
    if not match:
        return None
    giorno_str, ora_str, min_str, ampm = match.groups()
    ora = int(ora_str)
    minuto = int(min_str)
    if ampm.lower() == "am":
        if ora == 12:
            ora = 0
    else:
        if ora != 12:
            ora += 12

    if adesso is None:
        adesso = datetime.now().astimezone()
    else:
        if adesso.tzinfo is None or adesso.tzinfo.utcoffset(adesso) is None:
            adesso = adesso.astimezone()

    candidato = adesso.replace(hour=ora, minute=minuto, second=0, microsecond=0)
    if giorno_str:
        chiave_giorno = giorno_str[:3].lower()
        if chiave_giorno not in _GIORNI:
            return None
        target_giorno = _GIORNI[chiave_giorno]
        diff = (target_giorno - adesso.weekday()) % 7
        if diff == 0 and candidato <= adesso:
            diff = 7
        return candidato + timedelta(days=diff)
    else:
        if candidato <= adesso:
            candidato += timedelta(days=1)
        return candidato


@dataclass
class ClaudeCode:
    """Porta verso Claude Code (`claude`)."""

    nome: str = "claude-code"
    eseguibile: str = "claude"

    def controlla(self, prefisso: Sequence[str] = ()) -> Controllo:
        """Verifica se l'eseguibile di Claude Code risponde a --version, col prefisso dell'esecutore (RV9)."""
        return controlla_eseguibile(self.eseguibile, prefisso=prefisso)

    def lancia(
        self,
        cartella: Path | str,
        prompt: str,
        modello: str,
        *,
        conversazione: str | None = None,
        sola_lettura: bool = False,
        prefisso: Sequence[str] = (),
        tempo: int | float = 3600,
    ) -> Lancio:
        """Lancia Claude Code con prompt, modello, uscita JSON e permessi adeguati."""
        cmd = [self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]
        if conversazione:
            cmd.extend(["--resume", conversazione])
        if sola_lettura:
            cmd.extend(["--permission-mode", "plan"])
        else:
            cmd.append("--dangerously-skip-permissions")

        ret, stdout, stderr, err_ecc = esegui_porta(cmd, cartella, tempo, prefisso)
        if err_ecc is not None:
            return Lancio(esito="errore", testo=err_ecc, conversazione=conversazione, rinnovo=None, contatori={})

        dati = {}
        try:
            dati = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            pass

        session_id = None
        is_error = False
        if isinstance(dati, dict):
            session_id = dati.get("session_id") or conversazione
            testo = dati.get("result") or dati.get("response") or ""
            is_error = bool(dati.get("is_error"))
        else:
            session_id = conversazione
            testo = ""

        contatori: dict[str, int] = {}
        if isinstance(dati, dict):
            usage = dati.get("usage")
            if isinstance(usage, dict):
                for k, v in usage.items():
                    if isinstance(v, int):
                        contatori[k] = v

        ha_errore = is_error or (ret != 0)
        rinnovo = None

        if ha_errore:
            campo_result = dati.get("result", "") if isinstance(dati, dict) else ""
            testo_err = dati.get("error", "") if isinstance(dati, dict) else ""
            testo_non_json = stdout if not isinstance(dati, dict) or not dati else ""
            testo_controllo = f"{campo_result}\n{testo_err}\n{stderr}\n{testo_non_json}"
            testo_controllo_lower = testo_controllo.lower()

            rinnovo = parse_rinnovo_claude(testo_controllo)
            ha_quota = (
                rinnovo is not None
                or "you've hit your" in testo_controllo_lower
                or "limit · resets" in testo_controllo_lower
                or "spend limit" in testo_controllo_lower
                or "shared budget" in testo_controllo_lower
                or "rate_limit" in testo_controllo_lower
                or "billing_error" in testo_controllo_lower
            )

            if ha_quota:
                esito = "quota"
                if not testo:
                    testo = str(campo_result) or str(testo_err) or stderr.strip() or stdout.strip()
            else:
                parole_accesso = (
                    "authentication required",
                    "not logged in",
                    "please run claude auth",
                    "unauthorized",
                )
                if any(w in testo_controllo_lower for w in parole_accesso):
                    esito = "accesso"
                else:
                    esito = "errore"
                if not testo:
                    testo = str(testo_err) or str(campo_result) or stderr.strip() or stdout.strip()
        else:
            esito = "fatto"
            if not testo:
                testo = stdout.strip()

        return Lancio(
            esito=esito,
            testo=testo,
            conversazione=session_id,
            rinnovo=rinnovo,
            contatori=contatori,
        )
