"""Passi di macchina dell'installazione della bottega (Compito B6.2).

Gestisce la preparazione della macchina Linux/WSL per la bottega: creazione di utenti e gruppo dedicati, permessi
sudoers ristretti, spazio di lavoro comune e installazione del runner self-hosted di GitHub Actions.
"""

import os
import posixpath
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Utenti:
    """Configurazione degli utenti e dello spazio di macchina."""

    runner: str = "bottega-runner"
    esecutore: str = "bottega-esecutore"
    gruppo: str = "bottega"
    spazio: str = "/var/lib/bottega/spazio"
    # I runner dei progetti: fuori dalle case, accanto allo spazio.
    radice_runner: str = "/var/lib/bottega"


@dataclass(frozen=True)
class Passo:
    """Un passo di configurazione di macchina."""

    descrizione: str
    comando: tuple[str, ...]
    controllo: tuple[str, ...] | None = None
    ambiente: tuple[tuple[str, str], ...] = ()


class ErroreMacchina(RuntimeError):
    """Errore durante l'esecuzione di un passo di macchina."""


Esecutore = Callable[[Sequence[str], Mapping[str, str] | None], tuple[int, str]]


def esecutore_vero(
    comando: Sequence[str],
    ambiente: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    """Esecutore reale con subprocess.run, ambiente esteso, tetto di 600 secondi e stdin nullo."""
    env = dict(os.environ)
    if ambiente:
        env.update(ambiente)
    res = subprocess.run(
        list(comando),
        env=env,
        timeout=600,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    uscita = (res.stdout or "") + (res.stderr or "")
    return res.returncode, uscita


def esegui_passi(
    passi: Sequence[Passo],
    esegui: Esecutore,
    prova: bool = False,
) -> list[str]:
    """Esegue una sequenza di passi verificando prima se ciascuno è già fatto."""
    righe: list[str] = []
    for passo in passi:
        if passo.controllo is not None:
            codice_ctl, _ = esegui(passo.controllo, None)
            if codice_ctl == 0:
                righe.append(f"già fatto: {passo.descrizione}")
                continue

        if prova:
            righe.append(f"farei: {passo.descrizione}")
            continue

        env_dict = dict(passo.ambiente) if passo.ambiente else None
        codice_cmd, uscita_cmd = esegui(passo.comando, env_dict)
        if codice_cmd != 0:
            motivo = uscita_cmd.strip() if uscita_cmd.strip() else f"codice {codice_cmd}"
            for _, val in passo.ambiente:
                if val:
                    motivo = motivo.replace(val, "***")
            raise ErroreMacchina(f"errore in '{passo.descrizione}': {motivo}")

        righe.append(f"fatto: {passo.descrizione}")

    return righe


def passo_file(
    descrizione: str,
    contenuto: str,
    destinazione: str,
    modo: str,
    proprietario: str = "root",
    gruppo: str = "root",
    controlla_sudoers: bool = False,
) -> Passo:
    """Installa un file di sistema in un passo solo, in una shell di root.

    Il contenuto (nostro, mai un segreto) va quotato nel comando, scritto in un `mktemp` privato di root, controllato
    con `visudo -c -f` se è un sudoers, e installato con `install`. Nessun file temporaneo dal nome prevedibile e
    nessuna finestra fra il controllo e l'installazione (un altro utente non può cambiarlo in mezzo). Il controllo
    «già fatto» confronta il contenuto con `cmp`.
    """
    q = shlex.quote
    visudo = 'visudo -c -q -f "$t"; ' if controlla_sudoers else ""
    script = (
        f"set -e; umask 077; t=$(mktemp); trap 'rm -f \"$t\"' EXIT; printf '%s' {q(contenuto)} > \"$t\"; "
        f"{visudo}mkdir -p {q(posixpath.dirname(destinazione))}; "
        f"install -m {q(modo)} -o {q(proprietario)} -g {q(gruppo)} \"$t\" {q(destinazione)}"
    )
    controllo = f"printf '%s' {q(contenuto)} | cmp -s - {q(destinazione)}"
    return Passo(
        descrizione=descrizione,
        comando=("sudo", "-n", "sh", "-c", script),
        controllo=("sudo", "-n", "sh", "-c", controllo),
    )


def testo_sudoers(u: Utenti) -> str:
    """Restituisce il testo restrittivo della configurazione sudoers per il runner."""
    return (
        f"Defaults:{u.runner} umask=0007, umask_override\n"
        f"{u.runner} ALL=({u.esecutore}) NOPASSWD: ALL\n"
    )


testo_sudoers.__test__ = False  # type: ignore[attr-defined]


def passi_macchina(u: Utenti) -> list[Passo]:
    """Genera i passi di configurazione della macchina: gruppo, utenti, spazio e sudoers."""
    dest_sudoers = "/etc/sudoers.d/bottega"

    return [
        Passo(
            descrizione=f"gruppo {u.gruppo}",
            comando=("sudo", "-n", "groupadd", "--system", u.gruppo),
            controllo=("getent", "group", u.gruppo),
        ),
        Passo(
            descrizione=f"utente runner {u.runner}",
            comando=(
                "sudo",
                "-n",
                "useradd",
                "--system",
                "--create-home",
                "--shell",
                "/usr/sbin/nologin",
                "--gid",
                u.gruppo,
                u.runner,
            ),
            controllo=("id", "-u", u.runner),
        ),
        Passo(
            descrizione=f"utente esecutore {u.esecutore}",
            comando=(
                "sudo",
                "-n",
                "useradd",
                "--system",
                "--create-home",
                "--shell",
                "/usr/sbin/nologin",
                "--gid",
                u.gruppo,
                u.esecutore,
            ),
            controllo=("id", "-u", u.esecutore),
        ),
        Passo(
            descrizione=f"appartenenza di {u.runner} al gruppo {u.gruppo}",
            comando=("sudo", "-n", "usermod", "-a", "-G", u.gruppo, u.runner),
            controllo=("sh", "-c", f"id -Gn {u.runner} 2>/dev/null | grep -qw {u.gruppo}"),
        ),
        Passo(
            descrizione=f"appartenenza di {u.esecutore} al gruppo {u.gruppo}",
            comando=("sudo", "-n", "usermod", "-a", "-G", u.gruppo, u.esecutore),
            controllo=("sh", "-c", f"id -Gn {u.esecutore} 2>/dev/null | grep -qw {u.gruppo}"),
        ),
        Passo(
            descrizione=f"spazio {u.spazio}",
            comando=("sudo", "-n", "install", "-d", "-o", u.runner, "-g", u.gruppo, "-m", "2770", u.spazio),
            controllo=(
                "sh",
                "-c",
                f"[ \"$(stat -c '%U:%G:%a' {u.spazio} 2>/dev/null)\" = \"{u.runner}:{u.gruppo}:2770\" ]",
            ),
        ),
        passo_file(
            f"sudoers in {dest_sudoers} (controllato con visudo prima di installarlo)",
            testo_sudoers(u),
            dest_sudoers,
            "0440",
            controlla_sudoers=True,
        ),
    ]


def sha_della_release(corpo: str, arch: str) -> str | None:
    """Estrae lo SHA-256 della release per l'architettura data se valido (64 caratteri esadecimali)."""
    tag_inizio = f"<!-- BEGIN SHA linux-{arch} -->"
    tag_fine = f"<!-- END SHA linux-{arch} -->"
    if tag_inizio not in corpo or tag_fine not in corpo:
        return None
    try:
        frammento = corpo.split(tag_inizio, 1)[1]
        candidato = frammento.split(tag_fine, 1)[0].strip()
    except IndexError:
        return None
    if re.fullmatch(r"[0-9a-fA-F]{64}", candidato):
        return candidato.lower()
    return None


def testo_env_runner(u: Utenti, etichetta: str, porte: Mapping[str, str]) -> str:
    """Genera il contenuto del file .env del runner ordinato alfabeticamente riga per riga."""
    righe = [
        f"BOTTEGA_PREFISSO_ESECUTORE=sudo -n -H -u {u.esecutore} --",
        f"BOTTEGA_SPAZIO={u.spazio}",
        f"BOTTEGA_RUNNER={etichetta}",
    ]
    for nome, percorso in porte.items():
        chiave = f"BOTTEGA_PORTA_{nome.upper().replace('-', '_')}"
        righe.append(f"{chiave}={percorso}")
    righe.sort()
    return "\n".join(righe) + "\n"


testo_env_runner.__test__ = False  # type: ignore[attr-defined]


def passi_runner(
    u: Utenti,
    repo: str,
    versione: str,
    arch: str,
    sha256: str,
    etichetta: str,
    nome: str,
    porte: Mapping[str, str],
    token: str = "",
) -> list[Passo]:
    """Genera i passi di installazione e registrazione del runner self-hosted di GitHub Actions."""
    owner, repo_nome = repo.split("/", 1)
    prefisso_repo = f"{owner}-{repo_nome}"
    q = shlex.quote
    cartella = posixpath.join(u.radice_runner, f"runner-{prefisso_repo}")
    tar_nome = f"actions-runner-linux-{arch}-{versione}.tar.gz"
    archivio = f"{cartella}/{tar_nome}"
    url = f"https://github.com/actions/runner/releases/download/v{versione}/{tar_nome}"

    tok = token or os.environ.get("BOTTEGA_TOKEN_REGISTRAZIONE", "")
    ambiente_config = (("BOTTEGA_TOKEN_REGISTRAZIONE", tok),) if tok else ()

    file_env = f"{cartella}/.env"

    servizio = f"actions.runner.{prefisso_repo}.{nome}.service"
    dir_dropin = f"/etc/systemd/system/{servizio}.d"
    file_dropin = f"{dir_dropin}/bottega.conf"

    return [
        Passo(
            descrizione=f"cartella runner in {cartella}",
            comando=("sudo", "-n", "install", "-d", "-o", u.runner, "-g", u.gruppo, "-m", "0755", cartella),
            controllo=("test", "-d", cartella),
        ),
        Passo(
            descrizione=f"scarica runner v{versione} ({arch})",
            comando=("sudo", "-n", "-u", u.runner, "-H", "curl", "-fsSL", "-o", archivio, url),
            controllo=("test", "-f", archivio),
        ),
        Passo(
            descrizione=f"verifica sha256 runner v{versione}",
            comando=(
                "sudo",
                "-n",
                "-u",
                u.runner,
                "-H",
                "sh",
                "-c",
                f"echo {q(sha256 + '  ' + archivio)} | sha256sum -c",
            ),
            controllo=("test", "-f", f"{cartella}/config.sh"),
        ),
        Passo(
            descrizione=f"estrai runner v{versione}",
            comando=("sudo", "-n", "-u", u.runner, "-H", "tar", "xzf", archivio, "-C", cartella),
            controllo=("test", "-f", f"{cartella}/config.sh"),
        ),
        Passo(
            descrizione=f"configura runner {nome}",
            comando=(
                "sudo",
                "-n",
                "-u",
                u.runner,
                "-H",
                "sh",
                "-c",
                f"cd {q(cartella)} && ./config.sh --unattended --url {q('https://github.com/' + repo)} "
                f"--token \"$BOTTEGA_TOKEN_REGISTRAZIONE\" --name {q(nome)} --labels {q(etichetta)} "
                "--work _work --replace",
            ),
            controllo=("test", "-f", f"{cartella}/.runner"),
            ambiente=ambiente_config,
        ),
        passo_file(
            f"file .env per runner {nome}",
            testo_env_runner(u, etichetta, porte),
            file_env,
            "0640",
            proprietario="root",
            gruppo=u.gruppo,
        ),
        Passo(
            descrizione=f"servizio systemd per runner {nome}",
            comando=("sudo", "-n", "sh", "-c", f"cd {q(cartella)} && ./svc.sh install {q(u.runner)}"),
            controllo=("test", "-f", f"/etc/systemd/system/{servizio}"),
        ),
        passo_file(f"drop-in systemd umask in {file_dropin}", "[Service]\nUMask=0007\n", file_dropin, "0644"),
        Passo(
            descrizione="ricarica configurazione systemd",
            comando=("sudo", "-n", "systemctl", "daemon-reload"),
            controllo=("systemctl", "is-active", "--quiet", servizio),
        ),
        Passo(
            descrizione=f"avvia servizio runner {nome}",
            comando=("sudo", "-n", "sh", "-c", f"cd {q(cartella)} && ./svc.sh start"),
            controllo=("systemctl", "is-active", "--quiet", servizio),
        ),
    ]


def systemd_attivo(esegui: Esecutore) -> bool:
    """Verifica se systemd è attivo tramite systemctl is-system-running (running o degraded)."""
    _, uscita = esegui(["systemctl", "is-system-running"], None)
    return uscita.strip() in ("running", "degraded")
