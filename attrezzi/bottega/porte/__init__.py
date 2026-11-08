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
import subprocess

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


class Porta(Protocol):
    """Interfaccia comune a tutte le porte della bottega."""

    nome: str
    eseguibile: str

    def controlla(self) -> Controllo:
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


def ambiente_ripulito(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Restituisce una copia dell'ambiente priva di GH_TOKEN, BOTTEGA_TOKEN e variabili GITHUB_*."""
    sorgente = os.environ if base_env is None else base_env
    env = dict(sorgente)
    for k in list(env.keys()):
        if k in ("GH_TOKEN", "BOTTEGA_TOKEN") or k.startswith("GITHUB_"):
            del env[k]
    return env


def costruisci_comando(prefisso: Sequence[str], base_cmd: Sequence[str]) -> list[str]:
    """Antepone il prefisso per intero alla riga di comando."""
    return list(prefisso) + list(base_cmd)


def controlla_eseguibile(eseguibile: str) -> Controllo:
    """Controlla la presenza e la versione dell'eseguibile invocando `--version`."""
    try:
        proc = subprocess.run(
            [eseguibile, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return Controllo(ok=False, versione=None, motivo=f"eseguibile non trovato: {eseguibile}")
    except PermissionError:
        return Controllo(ok=False, versione=None, motivo=f"permesso negato: {eseguibile}")
    except subprocess.TimeoutExpired:
        return Controllo(ok=False, versione=None, motivo="tempo scaduto durante il controllo di versione")
    except OSError as e:
        return Controllo(ok=False, versione=None, motivo=f"errore di sistema: {e}")

    if proc.returncode == 0:
        return Controllo(ok=True, versione=proc.stdout.strip(), motivo=None)
    motivo = proc.stderr.strip() or proc.stdout.strip() or f"codice di uscita {proc.returncode}"
    return Controllo(ok=False, versione=None, motivo=motivo)


def esegui_porta(
    cmd: Sequence[str],
    cartella: Path | str,
    tempo: int | float,
    prefisso: Sequence[str] = (),
) -> tuple[int | None, str, str, str | None]:
    """Esegue il comando della porta nella cartella con ambiente ripulito e tetto di tempo.

    Restituisce (codice_uscita, stdout, stderr, errore_eccezione).
    """
    completo = costruisci_comando(prefisso, cmd)
    env = ambiente_ripulito()
    try:
        proc = subprocess.run(
            completo,
            cwd=str(cartella),
            capture_output=True,
            text=True,
            timeout=tempo,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr, None
    except FileNotFoundError:
        nome_cmd = completo[0] if completo else ""
        return None, "", "", f"eseguibile non trovato: {nome_cmd}"
    except PermissionError:
        nome_cmd = completo[0] if completo else ""
        return None, "", "", f"permesso negato: {nome_cmd}"
    except subprocess.TimeoutExpired:
        return None, "", "", f"tempo scaduto dopo {tempo} secondi"
    except OSError as e:
        return None, "", "", f"errore di sistema: {e}"


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
