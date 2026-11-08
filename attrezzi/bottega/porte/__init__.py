"""Le porte: adattatori verso le CLI dei modelli (Claude Code, Antigravity, Pi, Copilot CLI).

Ogni porta implementa il protocollo `Porta` con i metodi `controlla()` e `lancia()`.
L'ambiente dei processi lanciati è ripulito per non esporre token né chiavi al modello.
Solo libreria standard.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
import os
import signal
import subprocess
import tempfile

from bottega import configurazione


@dataclass(frozen=True)
class Controllo:
    """Esito del controllo dell'eseguibile di una porta."""

    ok: bool
    versione: str | None = None
    motivo: str | None = None


@dataclass(frozen=True)
class Lancio:
    """Esito del lancio senza mani di un modello attraverso una porta."""

    esito: str  # "fatto", "quota", "accesso", "errore"
    testo: str
    conversazione: str | None = None
    rinnovo: datetime | None = None
    contatori: dict[str, int] = field(default_factory=dict)


# I token «pesati» (B5-R5): una lettura dalla cache vale un decimo, come nei prezzi dei fornitori; senza peso le
# letture, che ripetono tutto il contesto a ogni chiamata, schiaccerebbero ogni altro numero.
PESO_CACHE_LETTA = 0.1


def somma_pesata(valori: Mapping[str, object], chiavi: Sequence[str], cache_letta: str) -> int | None:
    """La somma dei contatori presenti, con la lettura dalla cache pesata; None se uno non è un intero."""
    totale = 0.0
    for k in chiavi:
        if k in valori:
            v = valori[k]
            if isinstance(v, bool) or not isinstance(v, int):
                return None
            totale += v * (PESO_CACHE_LETTA if k == cache_letta else 1)
    return round(totale)


@dataclass(frozen=True)
class Token:
    """Totale dei token di una trascrizione e indicazione se la misura è parziale."""

    totale: int
    parziale: bool


class Porta(Protocol):
    """Interfaccia comune a tutte le porte della bottega."""

    nome: str
    eseguibile: str

    def controlla(self, prefisso: Sequence[str] = ()) -> Controllo:
        """Verifica la disponibilità e la versione dell'eseguibile senza mai sollevare eccezioni."""
        ...

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
        """Lancia il modello senza mani nella cartella di lavoro con i parametri indicati."""
        ...

    def trascrizione(
        self,
        env: Mapping[str, str],
        cartella: Path,
        sessione: str | None = None,
    ) -> Path | None:
        """Individua il percorso del file di trascrizione della sessione o l'ultima per cartella."""
        ...

    def token(
        self,
        percorso: Path,
        dopo: datetime,
        fino: datetime,
    ) -> Token:
        """Somma i contatori dei token registrati nel percorso compresi fra dopo e fino."""
        ...


VARIABILI_AMMESSE: frozenset[str] = frozenset({
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LANGUAGE",
    "TERM",
    "TMPDIR",
    "TZ",
})


def ambiente_ripulito(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Restituisce una copia dell'ambiente che conserva esclusivamente le variabili ammesse."""
    sorgente = os.environ if base_env is None else base_env
    env: dict[str, str] = {}
    for k, v in sorgente.items():
        if k in VARIABILI_AMMESSE or k.startswith("LC_"):
            env[k] = v
    return env


def costruisci_comando(prefisso: Sequence[str], base_cmd: Sequence[str]) -> list[str]:
    """Antepone il prefisso per intero alla riga di comando."""
    return list(prefisso) + list(base_cmd)


def controlla_eseguibile(
    eseguibile: str,
    prefisso: Sequence[str] = (),
    tempo: int | float = 30,
) -> Controllo:
    """Controlla la presenza e la versione dell'eseguibile invocando `--version` con ambiente ripulito."""
    completo = costruisci_comando(prefisso, [eseguibile, "--version"])
    env = ambiente_ripulito()
    try:
        proc = subprocess.run(
            completo,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=tempo,
            env=env,
        )
    except FileNotFoundError:
        nome_cmd = completo[0] if completo else eseguibile
        return Controllo(ok=False, versione=None, motivo=f"eseguibile non trovato: {nome_cmd}")
    except PermissionError:
        nome_cmd = completo[0] if completo else eseguibile
        return Controllo(ok=False, versione=None, motivo=f"permesso negato: {nome_cmd}")
    except subprocess.TimeoutExpired:
        return Controllo(ok=False, versione=None, motivo="tempo scaduto durante il controllo di versione")
    except OSError as e:
        return Controllo(ok=False, versione=None, motivo=f"errore di sistema: {e}")

    if proc.returncode == 0:
        return Controllo(ok=True, versione=proc.stdout.strip(), motivo=None)
    motivo = proc.stderr.strip() or proc.stdout.strip() or f"codice di uscita {proc.returncode}"
    return Controllo(ok=False, versione=None, motivo=motivo)


# Quanto si legge al più di ogni uscita: un processo rimasto vivo può continuare a scrivere.
LIMITE_USCITA = 50 * 1024 * 1024


def esegui_con_tetto(
    completo: Sequence[str],
    *,
    cwd: Path | str | None,
    env: Mapping[str, str],
    tempo: int | float,
) -> tuple[int | None, str, str, bool, str | None]:
    """Lancia un processo nel suo gruppo, con un tetto di tempo, e ne legge le uscite.

    Le uscite vanno su file anonimi, non su pipe: un processo staccato (`setsid`) che le tiene aperte non fa aspettare
    chi lancia. Si aspetta solo il processo; al tempo scaduto si uccide il gruppo. I byte che non sono UTF-8 si
    sostituiscono. Restituisce (codice, stdout, stderr, scaduto, errore_di_avvio); il codice è None se è scaduto.
    """
    with tempfile.TemporaryFile() as f_out, tempfile.TemporaryFile() as f_err:
        try:
            proc = subprocess.Popen(
                list(completo),
                cwd=None if cwd is None else str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=f_out,
                stderr=f_err,
                env=dict(env),
                start_new_session=True,
            )
        except FileNotFoundError:
            return None, "", "", False, f"eseguibile non trovato: {completo[0] if completo else ''}"
        except PermissionError:
            return None, "", "", False, f"permesso negato: {completo[0] if completo else ''}"
        except OSError as e:
            return None, "", "", False, f"errore di sistema: {e}"

        scaduto = False
        try:
            proc.wait(timeout=tempo)
        except subprocess.TimeoutExpired:
            scaduto = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass

        f_out.seek(0)
        f_err.seek(0)
        stdout = f_out.read(LIMITE_USCITA).decode("utf-8", errors="replace")
        stderr = f_err.read(LIMITE_USCITA).decode("utf-8", errors="replace")
        return (None if scaduto else proc.returncode), stdout, stderr, scaduto, None


def esegui_porta(
    cmd: Sequence[str],
    cartella: Path | str,
    tempo: int | float,
    prefisso: Sequence[str] = (),
) -> tuple[int | None, str, str, str | None]:
    """Esegue il comando della porta nella cartella con ambiente ripulito, gruppo di processi e tetto di tempo.

    Restituisce (codice_uscita, stdout, stderr, errore_eccezione).
    """
    completo = costruisci_comando(prefisso, cmd)
    codice, stdout, stderr, scaduto, errore = esegui_con_tetto(
        completo, cwd=cartella, env=ambiente_ripulito(), tempo=tempo
    )
    if errore is not None:
        return None, "", "", errore
    if scaduto:
        return None, "", "", f"tempo scaduto dopo {tempo} secondi"
    return codice, stdout, stderr, None


def porta(nome: str, eseguibile: str | None = None) -> Porta:
    """Restituisce l'adattatore della porta richiesta. Accetta solo i nomi di `configurazione.PORTE`."""
    if nome not in configurazione.PORTE:
        raise ValueError(f"porta sconosciuta: {nome}")
    if nome == "claude-code":
        from bottega.porte.claude_code import ClaudeCode

        return ClaudeCode(eseguibile=eseguibile or "claude")
    if nome == "antigravity":
        from bottega.porte.antigravity import Antigravity

        return Antigravity(eseguibile=eseguibile or "agy")
    if nome == "pi":
        from bottega.porte.pi import Pi

        return Pi(eseguibile=eseguibile or "pi")
    if nome == "copilot-cli":
        from bottega.porte.copilot_cli import CopilotCli

        return CopilotCli(eseguibile=eseguibile or "copilot")
    raise ValueError(f"porta sconosciuta: {nome}")
