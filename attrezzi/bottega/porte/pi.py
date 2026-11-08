"""Adattatore per la porta Pi (`pi`).

Gestisce il lancio non interattivo con `--mode json`, la ripresa con `--session`,
la sola lettura (`--tools read,grep,find,ls`), l'estrazione di sessione e messaggi e gli errori di quota/accesso.
Solo libreria standard.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import json

from bottega.porte import Controllo, Lancio, controlla_eseguibile, esegui_porta


@dataclass
class Pi:
    """Porta verso Pi (`pi`)."""

    nome: str = "pi"
    eseguibile: str = "pi"

    def controlla(self) -> Controllo:
        """Verifica se l'eseguibile di Pi risponde a --version."""
        return controlla_eseguibile(self.eseguibile)

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
        """Lancia Pi con prompt, modello, modalità JSONL e permessi adeguati."""
        cmd = [self.eseguibile, "--mode", "json", prompt, "--model", modello]
        if conversazione:
            cmd.extend(["--session", conversazione])
        if sola_lettura:
            cmd.extend(["--tools", "read,grep,find,ls"])

        ret, stdout, stderr, err_ecc = esegui_porta(cmd, cartella, tempo, prefisso)
        if err_ecc is not None:
            return Lancio(esito="errore", testo=err_ecc, conversazione=conversazione, rinnovo=None, contatori={})

        session_id = conversazione
        testi: list[str] = []
        contatori: dict[str, int] = {}
        ha_errore = False
        motivo_errore = ""

        for linea in stdout.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                rec = json.loads(linea)
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(rec, dict):
                continue

            tipo = rec.get("type")
            if tipo == "session" and "id" in rec:
                session_id = str(rec["id"])
            elif tipo in ("message", "assistant"):
                if rec.get("role") == "assistant" or tipo == "assistant":
                    c = rec.get("content") or rec.get("message")
                    if isinstance(c, str):
                        testi.append(c)
                usage = rec.get("usage")
                if isinstance(usage, dict):
                    for k, v in usage.items():
                        if isinstance(v, int):
                            contatori[k] = v
            elif tipo == "usage":
                usage = rec.get("usage")
                if isinstance(usage, dict):
                    for k, v in usage.items():
                        if isinstance(v, int):
                            contatori[k] = v

            if rec.get("stopReason") == "error" or rec.get("errorMessage"):
                ha_errore = True
                if not motivo_errore:
                    motivo_errore = str(rec.get("errorMessage") or "stopReason: error")

        testo_tutto = f"{motivo_errore}\n{stdout}\n{stderr}"
        testo_tutto_lower = testo_tutto.lower()

        if ha_errore or ret != 0:
            parole_quota = ("quota", "exhausted", "resource_exhausted", "rate limit", "429")
            parole_accesso = ("/login", "login required", "not logged in", "unauthorized", "authentication required")

            if any(k in testo_tutto_lower for k in parole_quota):
                esito = "quota"
            elif any(k in testo_tutto_lower for k in parole_accesso):
                esito = "accesso"
            else:
                esito = "errore"
            testo = "\n".join(testi).strip() or motivo_errore or stderr.strip() or stdout.strip()
        else:
            esito = "fatto"
            testo = "\n".join(testi).strip() or stdout.strip()

        return Lancio(
            esito=esito,
            testo=testo,
            conversazione=session_id,
            rinnovo=None,
            contatori=contatori,
        )
