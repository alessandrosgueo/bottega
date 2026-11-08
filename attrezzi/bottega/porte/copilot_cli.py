"""Adattatore per la porta GitHub Copilot CLI (`copilot`).

Gestisce il lancio non interattivo con `--output-format json`, la ripresa con `--resume`,
la modalità sola lettura (`--available-tools view,grep,glob`) o approvazione completa (`--allow-all-tools`),
l'estrazione di sessione, messaggi e contatori dall'evento shutdown, e gli errori di quota e accesso.
Solo libreria standard.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import json

from bottega.porte import Controllo, Lancio, controlla_eseguibile, esegui_porta


@dataclass
class CopilotCli:
    """Porta verso GitHub Copilot CLI (`copilot`)."""

    nome: str = "copilot-cli"
    eseguibile: str = "copilot"

    def controlla(self) -> Controllo:
        """Verifica se l'eseguibile di Copilot CLI risponde a --version."""
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
        """Lancia Copilot CLI con prompt, modello, uscita JSONL e permessi adeguati."""
        cmd = [self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]
        if conversazione:
            cmd.extend(["--resume", conversazione])
        if sola_lettura:
            cmd.extend(["--available-tools", "view,grep,glob"])
        else:
            cmd.append("--allow-all-tools")

        ret, stdout, stderr, err_ecc = esegui_porta(cmd, cartella, tempo, prefisso)
        if err_ecc is not None:
            return Lancio(esito="errore", testo=err_ecc, conversazione=conversazione, rinnovo=None, contatori={})

        session_id = conversazione
        testi: list[str] = []
        testi_errore: list[str] = []
        contatori: dict[str, int] = {}
        ha_evento_errore = False

        for linea in stdout.splitlines():
            linea_strip = linea.strip()
            if not linea_strip:
                continue
            try:
                rec = json.loads(linea_strip)
            except (json.JSONDecodeError, TypeError):
                testi_errore.append(linea_strip)
                continue

            if not isinstance(rec, dict):
                continue

            tipo = rec.get("type")
            data = rec.get("data")
            if not isinstance(data, dict):
                data = {}

            if tipo == "session.start" and "sessionId" in data:
                session_id = str(data["sessionId"])
            elif tipo == "assistant.message":
                c = data.get("content") or data.get("message")
                if isinstance(c, str):
                    testi.append(c)
            elif tipo == "session.shutdown":
                for k, v in data.items():
                    if isinstance(v, int):
                        contatori[k] = v
                mm = data.get("modelMetrics")
                if isinstance(mm, dict):
                    for _mod, mdata in mm.items():
                        if isinstance(mdata, dict):
                            u = mdata.get("usage")
                            if isinstance(u, dict):
                                for uk, uv in u.items():
                                    if isinstance(uv, int):
                                        contatori[uk] = uv

            # Rilevamento evento d'errore nel JSONL (senza mai leggere assistant.message)
            if tipo in ("error", "session.error") or (isinstance(tipo, str) and "error" in tipo):
                ha_evento_errore = True
                msg = data.get("message") or data.get("error") or rec.get("error") or rec.get("message")
                testi_errore.append(str(msg or linea_strip))
            elif "error" in rec or "error" in data:
                ha_evento_errore = True
                msg = data.get("error") or rec.get("error")
                testi_errore.append(str(msg or linea_strip))

        if stderr.strip():
            testi_errore.append(stderr.strip())

        ha_errore = (ret != 0) or ha_evento_errore

        if ha_errore:
            testo_controllo = "\n".join(testi_errore).lower()

            parole_quota = (
                "quota exceeded",
                "no remaining quota",
                "global rate limit",
                "weekly usage limit",
                "session usage limit",
                "402",
                "rate limit",
            )
            parole_accesso = (
                "gh auth status",
                "copilot login",
                "not logged in",
                "unauthorized",
                "authentication required",
            )

            if any(k in testo_controllo for k in parole_quota):
                esito = "quota"
            elif any(k in testo_controllo for k in parole_accesso):
                esito = "accesso"
            else:
                esito = "errore"
            testo = "\n".join(testi).strip() or "\n".join(testi_errore).strip() or stderr.strip() or stdout.strip()
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
