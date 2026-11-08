"""Adattatore per la porta GitHub Copilot CLI (`copilot`).

Gestisce il lancio non interattivo con `--output-format json`, la ripresa con `--resume`,
la modalità sola lettura (`--available-tools view,grep,glob`) o approvazione completa (`--allow-all-tools`),
l'estrazione di sessione, messaggi e contatori dall'evento shutdown, e gli errori di quota e accesso.
Solo libreria standard.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from bottega.porte import Controllo, Lancio, Token, controlla_eseguibile, esegui_porta, somma_pesata


@dataclass
class CopilotCli:
    """Porta verso GitHub Copilot CLI (`copilot`)."""

    nome: str = "copilot-cli"
    eseguibile: str = "copilot"

    def controlla(self, prefisso: Sequence[str] = ()) -> Controllo:
        """Verifica se l'eseguibile di Copilot CLI risponde a --version, col prefisso dell'esecutore (RV9)."""
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
        """Lancia Copilot CLI con prompt, modello, uscita JSONL e permessi adeguati."""
        cmd = [self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]
        if conversazione:
            cmd.extend(["--resume", conversazione])
        if sola_lettura:
            cmd.extend(["--available-tools", "view,grep,glob", "--allow-tool", "view,grep,glob"])
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
                                    if isinstance(uv, int) and not isinstance(uv, bool):
                                        contatori[uk] = contatori.get(uk, 0) + uv

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

    def trascrizione(
        self,
        env: Mapping[str, str],
        cartella: Path,
        sessione: str | None = None,
    ) -> Path | None:
        """Individua il file events.jsonl di Copilot CLI per la sessione o l'ultima per cartella."""
        casa = Path(env.get("HOME", "/"))
        copilot_home = Path(env["COPILOT_HOME"]) if "COPILOT_HOME" in env else (casa / ".copilot")
        session_state_dir = copilot_home / "session-state"
        if not session_state_dir.is_dir():
            return None

        sid = sessione or env.get("COPILOT_AGENT_SESSION_ID")
        if sid:
            candidato = session_state_dir / sid / "events.jsonl"
            return candidato if candidato.is_file() else None

        # Ricerca per cartella tramite workspace.yaml
        candidati: list[Path] = []
        c_res = str(cartella.resolve())
        c_raw = str(cartella)

        for d in session_state_dir.iterdir():
            if not d.is_dir():
                continue
            events = d / "events.jsonl"
            if not events.is_file():
                continue
            ws = d / "workspace.yaml"
            if ws.is_file():
                try:
                    for riga in ws.read_text(encoding="utf-8").splitlines():
                        riga = riga.strip()
                        if riga.startswith("cwd:"):
                            cwd_val = riga.split(":", 1)[1].strip().strip("'\"")
                            if cwd_val in (c_res, c_raw):
                                candidati.append(events)
                                break
                except Exception:
                    pass

        if not candidati:
            return None
        return max(candidati, key=lambda f: f.stat().st_mtime)

    def token(
        self,
        percorso: Path,
        dopo: datetime,
        fino: datetime,
        visti: set[str] | None = None,
    ) -> Token:
        """Somma i contatori dei token registrati nel percorso compresi fra dopo e fino."""
        if dopo.tzinfo is None:
            dopo = dopo.replace(tzinfo=timezone.utc)
        if fino.tzinfo is None:
            fino = fino.replace(tzinfo=timezone.utc)

        totale = 0
        messaggi = 0
        with percorso.open("r", encoding="utf-8") as f:
            for riga in f:
                riga = riga.strip()
                if not riga:
                    continue
                try:
                    rec = json.loads(riga)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue

                tipo = rec.get("type")
                if tipo not in ("assistant.usage", "subagent.completed"):
                    continue

                ts_raw = rec.get("timestamp")
                if not ts_raw or not isinstance(ts_raw, str):
                    continue
                try:
                    dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except Exception:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if not (dopo <= dt <= fino):
                    continue

                data = rec.get("data")
                if not isinstance(data, dict):
                    continue

                if tipo == "assistant.usage":
                    subtot = somma_pesata(
                        data,
                        ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"),
                        cache_letta="cacheReadTokens",
                    )
                    if subtot is None:
                        continue
                    totale += subtot
                    messaggi += 1
                elif tipo == "subagent.completed":
                    v = data.get("totalTokens")
                    if isinstance(v, bool) or not isinstance(v, int):
                        continue
                    totale += v
                    messaggi += 1

        return Token(totale=totale, parziale=False, messaggi=messaggi)
