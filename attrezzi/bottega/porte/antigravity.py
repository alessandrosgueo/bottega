"""Adattatore per la porta Antigravity (`agy`).

Gestisce il lancio non interattivo con `--output-format json`, la ripresa con `--conversation`,
la modalità sola lettura (`--mode plan`), l'approvazione permessi e il rilevamento quota/accesso.
Solo libreria standard.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from bottega.porte import Controllo, Lancio, Token, controlla_eseguibile, esegui_porta, somma_pesata


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
            # «credits balance» dal vivo: i crediti AI finiti arrivano come errore senza la parola quota (PORTE-2).
            parole_quota = ("quota", "exhausted", "resource_exhausted", "rate limit", "429", "credits balance")
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

    def trascrizione(
        self,
        env: Mapping[str, str],
        cartella: Path,
        sessione: str | None = None,
    ) -> Path | None:
        """Individua il file transcript.jsonl di Antigravity per la conversazione o l'ultima modificata."""
        casa = Path(env.get("HOME", "/"))
        app_dir = (
            Path(env["ANTIGRAVITY_APP_DATA_DIR"])
            if "ANTIGRAVITY_APP_DATA_DIR" in env
            else (casa / ".gemini" / "antigravity-cli")
        )
        brain_dir = app_dir / "brain"
        if not brain_dir.is_dir():
            return None

        conv_id = sessione or env.get("ANTIGRAVITY_CONVERSATION_ID")
        if conv_id:
            candidato = brain_dir / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
            return candidato if candidato.is_file() else None

        candidati = [f for f in brain_dir.glob("*/.system_generated/logs/transcript.jsonl") if f.is_file()]
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
                if rec.get("source") != "MODEL" or rec.get("type", "PLANNER_RESPONSE") != "PLANNER_RESPONSE":
                    continue

                ts_raw = rec.get("created_at")
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

                subtot = somma_pesata(
                    rec, ("input_tokens", "output_tokens", "cache_read_tokens"), cache_letta="cache_read_tokens"
                )
                if subtot is None:
                    continue
                totale += subtot

        return Token(totale=totale, parziale=True)
