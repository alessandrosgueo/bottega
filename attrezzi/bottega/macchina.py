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


_NOME_DI_SISTEMA = re.compile(r"[a-z_][a-z0-9_-]{0,31}")


@dataclass(frozen=True)
class Utenti:
    """Configurazione degli utenti e dello spazio di macchina."""

    runner: str = "bottega-runner"
    esecutore: str = "bottega-esecutore"
    gruppo: str = "bottega"
    spazio: str = "/var/lib/bottega/spazio"
    # I runner dei progetti: fuori dalle case, accanto allo spazio.
    radice_runner: str = "/var/lib/bottega"

    def __post_init__(self) -> None:
        # I nomi finiscono in useradd, nel sudoers e nel nome del suo file: sudo salta in silenzio i file di
        # /etc/sudoers.d con un punto nel nome, e un nome strano nel sudoers cambierebbe la regola.
        for nome in (self.runner, self.esecutore, self.gruppo):
            if not _NOME_DI_SISTEMA.fullmatch(nome):
                raise ValueError(f"nome di utente o gruppo non valido: {nome!r}")


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
    # Un file per utente dell'esecutore (B6-R12): un secondo progetto aggiunge il suo, non riscrive quello del primo.
    dest_sudoers = f"/etc/sudoers.d/{u.esecutore}"

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
                "-K",
                "HOME_MODE=0700",
                "--shell",
                "/usr/sbin/nologin",
                "--user-group",
                "--groups",
                u.gruppo,
                u.runner,
            ),
            # Già fatto solo col gruppo principale suo: un utente creato col gruppo comune come principale non basta.
            controllo=("sh", "-c", f"[ \"$(id -gn {u.runner} 2>/dev/null)\" = {u.runner} ]"),
        ),
        Passo(
            descrizione=f"utente esecutore {u.esecutore}",
            comando=(
                "sudo",
                "-n",
                "useradd",
                "--system",
                "--create-home",
                "-K",
                "HOME_MODE=0700",
                "--shell",
                "/usr/sbin/nologin",
                "--user-group",
                "--groups",
                u.gruppo,
                u.esecutore,
            ),
            controllo=("sh", "-c", f"[ \"$(id -gn {u.esecutore} 2>/dev/null)\" = {u.esecutore} ]"),
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
            # 3770: il bit sticky impedisce all'esecutore di rinominare o togliere le cartelle dei giri del runner.
            comando=("sudo", "-n", "install", "-d", "-o", u.runner, "-g", u.gruppo, "-m", "3770", u.spazio),
            controllo=(
                "sh",
                "-c",
                f"[ \"$(stat -c '%U:%G:%a' {u.spazio} 2>/dev/null)\" = \"{u.runner}:{u.gruppo}:3770\" ]",
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


_NOME_RUNNER = re.compile(r"[A-Za-z0-9._-]{1,64}")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_VERSIONE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_NOME_PORTA = re.compile(r"[a-z][a-z0-9-]{0,31}")
_PERCORSO_PORTA = re.compile(r"/[A-Za-z0-9._/+-]{1,255}")
_ARCHITETTURE = ("x64", "arm64", "arm")


def nome_del_servizio(repo: str) -> str:
    """Il nome dell'unità systemd del runner di un progetto, scelto da noi (non da `svc.sh`)."""
    owner, nome = repo.split("/", 1)
    return f"bottega-runner-{owner}-{nome}.service"


def testo_unita_runner(u: Utenti, repo: str, cartella: str) -> str:
    """L'unità systemd del runner, scritta da noi come root: `svc.sh` non gira mai come root (G7)."""
    return (
        "[Unit]\n"
        f"Description=Runner della bottega per {repo}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        f"ExecStart={cartella}/runsvc.sh\n"
        f"User={u.runner}\n"
        f"WorkingDirectory={cartella}\n"
        "KillMode=process\n"
        "KillSignal=SIGTERM\n"
        "TimeoutStopSec=5min\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


testo_unita_runner.__test__ = False  # type: ignore[attr-defined]


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
    """Genera i passi di installazione e registrazione del runner self-hosted di GitHub Actions.

    La cartella del runner è sua (`0750`, il suo gruppo): l'esecutore non ci entra. Root non esegue mai un file del
    runner: l'unità systemd la scriviamo noi, e `svc.sh` non si usa. Il token di registrazione passa a `config.sh` solo
    nell'ambiente (`ACTIONS_RUNNER_INPUT_TOKEN`, conservato da `sudo --preserve-env`), mai in un argomento.
    """
    if not _REPO.fullmatch(repo):
        raise ValueError(f"repo non valido: {repo!r}")
    for valore, regola, che in (
        (nome, _NOME_RUNNER, "nome del runner"),
        (etichetta, _NOME_RUNNER, "etichetta"),
        (versione, _VERSIONE, "versione"),
    ):
        if not regola.fullmatch(valore):
            raise ValueError(f"{che} non valido: {valore!r}")
    if arch not in _ARCHITETTURE:
        raise ValueError(f"architettura non valida: {arch!r}")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("sha256 non valido")
    for nome_porta, percorso in porte.items():
        if not _NOME_PORTA.fullmatch(nome_porta) or not _PERCORSO_PORTA.fullmatch(percorso):
            raise ValueError(f"porta non valida: {nome_porta!r}={percorso!r}")

    owner, repo_nome = repo.split("/", 1)
    prefisso_repo = f"{owner}-{repo_nome}"
    q = shlex.quote
    cartella = posixpath.join(u.radice_runner, f"runner-{prefisso_repo}")
    tar_nome = f"actions-runner-linux-{arch}-{versione}.tar.gz"
    archivio = f"{cartella}/{tar_nome}"
    url = f"https://github.com/actions/runner/releases/download/v{versione}/{tar_nome}"

    tok = token or os.environ.get("BOTTEGA_TOKEN_REGISTRAZIONE", "")
    ambiente_config = (("ACTIONS_RUNNER_INPUT_TOKEN", tok),) if tok else ()

    file_env = f"{cartella}/.env"
    servizio = nome_del_servizio(repo)
    come_runner = ("sudo", "-n", "-u", u.runner, "-H")

    # M9: si scarica in un temporaneo e si rinomina solo dopo la verifica: un archivio troncato non resta mai.
    scarica = (
        f"set -e; t=$(mktemp -p {q(cartella)} .scarica-XXXXXX); trap 'rm -f \"$t\"' EXIT; "
        f"curl -fsSL -o \"$t\" {q(url)}; echo {q(sha256)}\"  $t\" | sha256sum -c --status; mv \"$t\" {q(archivio)}"
    )

    return [
        Passo(
            descrizione=f"cartella runner in {cartella}",
            comando=("sudo", "-n", "install", "-d", "-o", u.runner, "-g", u.runner, "-m", "0750", cartella),
            controllo=(
                "sh",
                "-c",
                f"[ \"$(sudo -n stat -c '%U:%G:%a' {q(cartella)} 2>/dev/null)\" = \"{u.runner}:{u.runner}:750\" ]",
            ),
        ),
        Passo(
            descrizione=f"scarica e verifica runner v{versione} ({arch})",
            comando=(*come_runner, "sh", "-c", scarica),
            controllo=(*come_runner, "sh", "-c", f"echo {q(sha256 + '  ' + archivio)} | sha256sum -c --status"),
        ),
        Passo(
            descrizione=f"estrai runner v{versione}",
            comando=(*come_runner, "tar", "xzf", archivio, "-C", cartella),
            controllo=("sudo", "-n", "test", "-f", f"{cartella}/config.sh"),
        ),
        Passo(
            descrizione=f"configura runner {nome}",
            comando=(
                "sudo",
                "--preserve-env=ACTIONS_RUNNER_INPUT_TOKEN",
                "-n",
                "-u",
                u.runner,
                "-H",
                "sh",
                "-c",
                f"cd {q(cartella)} && ./config.sh --unattended --url {q('https://github.com/' + repo)} "
                f"--name {q(nome)} --labels {q(etichetta)} --work _work --replace",
            ),
            controllo=("sudo", "-n", "test", "-f", f"{cartella}/.runner"),
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
            descrizione="lanciatore del servizio",
            comando=(*come_runner, "install", "-m", "0755", f"{cartella}/bin/runsvc.sh", f"{cartella}/runsvc.sh"),
            controllo=("sudo", "-n", "test", "-x", f"{cartella}/runsvc.sh"),
        ),
        passo_file(
            f"unità systemd {servizio}",
            testo_unita_runner(u, repo, cartella),
            f"/etc/systemd/system/{servizio}",
            "0644",
        ),
        Passo(
            descrizione="ricarica configurazione systemd",
            comando=("sudo", "-n", "systemctl", "daemon-reload"),
            controllo=("sh", "-c", f"[ \"$(systemctl show -p NeedDaemonReload --value {q(servizio)})\" = no ]"),
        ),
        Passo(
            descrizione=f"avvia servizio {servizio}",
            comando=("sudo", "-n", "systemctl", "enable", "--now", servizio),
            controllo=("sh", "-c", f"systemctl is-enabled --quiet {q(servizio)} && systemctl is-active --quiet {q(servizio)}"),
        ),
    ]


def systemd_attivo(esegui: Esecutore) -> bool:
    """Verifica se systemd è attivo tramite systemctl is-system-running (running o degraded)."""
    _, uscita = esegui(["systemctl", "is-system-running"], None)
    return uscita.strip() in ("running", "degraded")
