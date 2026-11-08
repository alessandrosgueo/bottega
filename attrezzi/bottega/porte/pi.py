"""Adattatore per la porta Pi (`pi`).

Gestisce il lancio non interattivo con `--mode json`, la ripresa con `--session`,
la sola lettura (`--tools read,grep,find,ls`), l'estrazione di sessione e messaggi e gli errori di quota/accesso.
Solo libreria standard.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re

from bottega.porte import Controllo, Lancio, Token, controlla_eseguibile, esegui_porta, somma_pesata


@dataclass
class Pi:
    """Porta verso Pi (`pi`)."""

    nome: str = "pi"
    eseguibile: str = "pi"

    def controlla(self, prefisso: Sequence[str] = ()) -> Controllo:
        """Verifica se l'eseguibile di Pi risponde a --version, col prefisso dell'esecutore (RV9)."""
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
        ha_codice_429 = False

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

            if rec.get("stopReason") == "error" or rec.get("errorMessage") or rec.get("type") == "error":
                ha_errore = True
                if not motivo_errore:
                    motivo_errore = str(rec.get("errorMessage") or rec.get("error") or "stopReason: error")
            if rec.get("code") == 429 or (isinstance(rec.get("error"), dict) and rec["error"].get("code") == 429):
                ha_codice_429 = True

        testo_controllo_errore = f"{motivo_errore}\n{stderr}".lower()

        if ha_errore or ret != 0:
            # RV16: quota e accesso cercati solo nei campi d'errore e in stderr, mai nei messaggi del modello
            parole_quota = ("quota", "exhausted", "resource_exhausted", "rate limit", "429")
            parole_accesso = ("/login", "login required", "not logged in", "unauthorized", "authentication required")

            if ha_codice_429 or any(k in testo_controllo_errore for k in parole_quota):
                esito = "quota"
            elif any(k in testo_controllo_errore for k in parole_accesso):
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

    def trascrizione(
        self,
        env: Mapping[str, str],
        cartella: Path,
        sessione: str | None = None,
    ) -> Path | None:
        """Individua il file .jsonl di trascrizione per Pi."""
        casa = Path(env.get("HOME", "/"))
        sessions_dir = (
            Path(env["PI_CODING_AGENT_SESSION_DIR"])
            if "PI_CODING_AGENT_SESSION_DIR" in env
            else (casa / ".pi" / "agent" / "sessions")
        )

        sess = sessione or env.get("PI_SESSION_FILE")
        if sess:
            p_diretto = Path(sess)
            if p_diretto.is_file():
                return p_diretto
            if (sessions_dir / sess).is_file():
                return sessions_dir / sess

        if not sessions_dir.is_dir():
            return None

        # Nome cartella sessioni di Pi: --<percorso>-- con separatori trasformati in '-'
        s1 = str(cartella.resolve()).lstrip("/\\")
        s1 = re.sub(r"[/\\:]", "-", s1)
        folder = sessions_dir / f"--{s1}--"
        if not folder.is_dir():
            s2 = str(cartella).lstrip("/\\")
            s2 = re.sub(r"[/\\:]", "-", s2)
            folder = sessions_dir / f"--{s2}--"
            if not folder.is_dir():
                return None

        if sess:
            cands = [f for f in folder.glob(f"*{sess}*.jsonl") if f.is_file()] + [
                f for f in folder.glob(f"{sess}*") if f.is_file()
            ]
            if cands:
                return max(cands, key=lambda f: f.stat().st_mtime)
            return None

        candidati = [f for f in folder.glob("*.jsonl") if f.is_file()]
        if not candidati:
            return None
        return max(candidati, key=lambda f: f.stat().st_mtime)

    def token(
        self,
        percorso: Path,
        dopo: datetime,
        fino: datetime,
    ) -> Token:
        """Somma i contatori dei token registrati nel percorso compresi fra dopo e fino."""
        if dopo.tzinfo is None:
            dopo = dopo.replace(tzinfo=timezone.utc)
        if fino.tzinfo is None:
            fino = fino.replace(tzinfo=timezone.utc)

        totale = 0
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
                if tipo == "message":
                    role = rec.get("role") or (
                        rec.get("message", {}).get("role") if isinstance(rec.get("message"), dict) else None
                    )
                    if role != "assistant":
                        continue
                elif tipo not in ("usage", "compaction", "branch_summary"):
                    continue

                ts = rec.get("timestamp") or (
                    rec.get("message", {}).get("timestamp") if isinstance(rec.get("message"), dict) else None
                )
                if ts is None:
                    continue
                if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                elif isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except Exception:
                        continue
                else:
                    continue

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if not (dopo <= dt <= fino):
                    continue

                usage = rec.get("usage")
                if not isinstance(usage, dict) and isinstance(rec.get("message"), dict):
                    usage = rec["message"].get("usage")
                if not isinstance(usage, dict):
                    continue

                chiavi = ("input", "output", "cacheRead", "cacheWrite")
                trovati = [k for k in chiavi if k in usage]
                invalido = False
                subtot = 0
                if trovati:
                    pesata = somma_pesata(usage, chiavi, cache_letta="cacheRead")
                    if pesata is None:
                        invalido = True
                    else:
                        subtot = pesata
                elif "totalTokens" in usage:
                    v = usage["totalTokens"]
                    if isinstance(v, bool) or not isinstance(v, int):
                        invalido = True
                    else:
                        subtot += v
                else:
                    continue

                if invalido:
                    continue
                totale += subtot

        return Token(totale=totale, parziale=False)
