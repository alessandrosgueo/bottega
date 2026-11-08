"""Adattatore per la porta Antigravity (`agy`).

Gestisce il lancio non interattivo con `--output-format json`, la ripresa con `--conversation`,
la modalità sola lettura (`--mode plan`), l'approvazione permessi e il rilevamento quota/accesso.
Solo libreria standard.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import json

from bottega.porte import Controllo, Lancio, controlla_eseguibile, esegui_porta


@dataclass
class Antigravity:
    """Porta verso Google Antigravity (`agy`)."""

    nome: str = "antigravity"
    eseguibile: str = "agy"

    def controlla(self, prefisso: Sequence[str] = ()) -> Controllo:
        """Verifica se l'eseguibile di Antigravity risponde a --version, col prefisso dell'esecutore (RV9)."""
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
        """Lancia Antigravity con prompt, modello, uscita JSON e permessi adeguati."""
        cmd = [self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]
        if conversazione:
            cmd.extend(["--conversation", conversazione])
        if sola_lettura:
            cmd.extend(["--mode", "plan"])
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

        conv_id = None
        status = None
        testo = ""
        errore = ""
        contatori: dict[str, int] = {}

        if isinstance(dati, dict):
            conv_id = dati.get("conversation_id") or conversazione
            status = dati.get("status")
            testo = dati.get("response") or ""
            errore = dati.get("error") or ""
            usage = dati.get("usage")
            if isinstance(usage, dict):
                for k, v in usage.items():
                    if isinstance(v, int):
                        contatori[k] = v
        else:
            conv_id = conversazione

        testo_errore_parti: list[str] = []
        ha_codice_429 = False

        if errore:
            if isinstance(errore, dict):
                testo_errore_parti.append(json.dumps(errore))
                if errore.get("code") == 429:
                    ha_codice_429 = True
            else:
                testo_errore_parti.append(str(errore))
        if isinstance(dati, dict):
            if dati.get("code") == 429:
                ha_codice_429 = True

        if stderr.strip():
            testo_errore_parti.append(stderr.strip())

        testo_controllo_errore = "\n".join(testo_errore_parti).lower()

        if status == "SUCCESS" and ret == 0:
            esito = "fatto"
            if not testo:
                testo = stdout.strip()
        else:
            # RV16: quota e accesso cercati solo nei campi d'errore e in stderr, mai nel testo del modello
            parole_quota = ("quota", "exhausted", "resource_exhausted", "rate limit", "429")
            parole_accesso = ("authentication required", "unauthorized", "login required", "not logged in")

            if ha_codice_429 or any(k in testo_controllo_errore for k in parole_quota):
                esito = "quota"
            elif any(k in testo_controllo_errore for k in parole_accesso):
                esito = "accesso"
            else:
                esito = "errore"
            if not testo:
                testo = (str(errore) if errore else "") or stderr.strip() or stdout.strip()

        return Lancio(
            esito=esito,
            testo=testo,
            conversazione=conv_id,
            rinnovo=None,
            contatori=contatori,
        )
