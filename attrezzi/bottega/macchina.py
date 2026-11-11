"""Passi di macchina dell'installazione della bottega (Compito B6.2).

Gestisce la preparazione della macchina Linux/WSL per la bottega: creazione di utenti e gruppo dedicati, permessi
sudoers ristretti, spazio di lavoro comune e installazione del runner self-hosted di GitHub Actions.
"""

import ipaddress
import os
import posixpath
import re
import shlex
import subprocess
import zlib
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


# Il PATH dei comandi di sistema che sudo dà di serie (Ubuntu e Debian).
_PATH_DI_SISTEMA = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"


def testo_sudoers(u: Utenti) -> str:
    """Restituisce il testo restrittivo della configurazione sudoers per il runner.

    Il `secure_path` dei comandi che il runner lancia come esecutore finisce con la `~/.local/bin` dell'esecutore, dove
    gli installatori ufficiali mettono i suoi strumenti (uv, le porte): in fondo, così `id`, `kill`, `git` restano
    quelli di sistema e l'esecutore non li può sostituire coi suoi.
    """
    return (
        f"Defaults:{u.runner} umask=0007, umask_override\n"
        f'Defaults:{u.runner} secure_path="{_PATH_DI_SISTEMA}:/home/{u.esecutore}/.local/bin"\n'
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
        *(
            Passo(
                descrizione=f"casa di {utente} chiusa (0700)",
                comando=("sudo", "-n", "sh", "-c", f'chmod 700 "$(getent passwd {utente} | cut -d: -f6)"'),
                controllo=(
                    "sh",
                    "-c",
                    f'[ "$(stat -c %a "$(getent passwd {utente} | cut -d: -f6)" 2>/dev/null)" = 700 ]',
                ),
            )
            for utente in (u.runner, u.esecutore)
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
_TETTO = re.compile(r"[1-9][0-9]{0,5}[KMG]")


def nome_del_servizio(repo: str) -> str:
    """Il nome dell'unità systemd del runner di un progetto, scelto da noi (non da `svc.sh`)."""
    owner, nome = repo.split("/", 1)
    return f"bottega-runner-{owner}-{nome}.service"


def testo_unita_runner(u: Utenti, repo: str, cartella: str, tetto: str | None = None) -> str:
    """L'unità systemd del runner, scritta da noi come root: `svc.sh` non gira mai come root (G7).

    Con `tetto` (per esempio `6G`) il servizio ha un tetto di memoria senza swap: l'esecutore, le sue porte e le sue
    prove sono figli del runner e stanno nel suo cgroup, quindi una macchina che fa anche altro resta viva.
    """
    righe_tetto = f"MemoryMax={tetto}\nMemorySwapMax=0\n" if tetto else ""
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
        f"{righe_tetto}"
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
    tetto: str | None = None,
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
    if tetto is not None and not _TETTO.fullmatch(tetto):
        raise ValueError(f"tetto non valido (per esempio 6G): {tetto!r}")
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
            # --no-overwrite-dir: la voce `./` dell'archivio (0755) non deve riaprire la cartella del runner (dal
            # vivo, 2026-11-09: dopo l'estrazione era 755 e l'esecutore ci entrava).
            comando=(*come_runner, "tar", "xzf", archivio, "--no-overwrite-dir", "-C", cartella),
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
            testo_unita_runner(u, repo, cartella, tetto),
            f"/etc/systemd/system/{servizio}",
            "0644",
        ),
        Passo(
            descrizione=f"cartella runner chiusa (0750) in {cartella}",
            comando=("sudo", "-n", "chmod", "0750", cartella),
            controllo=(
                "sh",
                "-c",
                f"[ \"$(sudo -n stat -c '%a' {q(cartella)} 2>/dev/null)\" = 750 ]",
            ),
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


# --- La rete dell'esecutore (B8-2, Debt della LAN del collaudo) ---

# Gli indirizzi IPv4 che l'esecutore non raggiunge fuori dalla macchina: reti private (RFC 1918), del gestore e delle
# VPN a maglia (RFC 6598), di questa rete (0/8), di loopback, locali di collegamento, riservate, di prova e multicast.
# Scritte in esadecimale come in `pubblico.py`, così il controllo pubblico non le trova come dati.
_CHIUSE4 = tuple(
    str(ipaddress.ip_network((indirizzo, bit)))
    for indirizzo, bit in (
        (0x00000000, 8),
        (0x0A000000, 8),
        (0x64400000, 10),
        (0x7F000000, 8),
        (0xA9FE0000, 16),
        (0xAC100000, 12),
        (0xC0000000, 24),
        (0xC0A80000, 16),
        (0xC6120000, 15),
        (0xE0000000, 4),
        (0xF0000000, 4),
    )
)


def nameserver_da_resolv(testo: str) -> tuple[str, ...]:
    """I server DNS di un `/etc/resolv.conf`: solo indirizzi IP letterali senza zona, nell'ordine, senza doppioni.

    Senza nessuna riga `nameserver` buona resta `127.0.0.1`, il server che usa la libreria C in quel caso.
    """
    visti: list[str] = []
    for riga in testo.splitlines():
        pezzi = riga.split()
        if len(pezzi) < 2 or pezzi[0] != "nameserver" or "%" in pezzi[1]:
            continue
        try:
            indirizzo = str(ipaddress.ip_address(pezzi[1]))
        except ValueError:
            continue
        if indirizzo not in visti:
            visti.append(indirizzo)
    return tuple(visti) or ("127.0.0.1",)


def tabella_rete(u: Utenti) -> str:
    """Il nome della tabella nftables della rete dell'esecutore."""
    return "rete_" + re.sub(r"[^a-z0-9_]", "_", u.esecutore)


def segno_rete(u: Utenti) -> int:
    """Il bit del `ct mark` che segna le connessioni locali aperte dall'esecutore: uno degli 8 bit alti, dal nome.

    Le VPN a maglia usano di solito i bit `0x00ff0000`. Due esecutori sulla stessa macchina (sconsigliato, B6-R12) hanno di regola bit
    diversi; con lo stesso bit cadono le connessioni locali fra processi dello stesso esecutore, mai il contrario.
    """
    return 1 << (24 + zlib.crc32(u.esecutore.encode("utf-8")) % 8)


def testo_rete_esecutore(u: Utenti, dns: Sequence[str]) -> str:
    """Il file nftables della rete dell'esecutore: internet sì, la rete di casa e i servizi della macchina no.

    - Verso i server DNS di `/etc/resolv.conf`, porta 53 TCP e UDP: sì.
    - Verso la macchina stessa (l'interfaccia `lo`, che porta anche gli indirizzi di LAN, Docker e VPN della macchina):
      solo TCP, e la connessione si apre solo se risponde un processo dell'esecutore. Il SYN-ACK di un servizio di un
      altro utente (un broker, un pannello, un tunnel) cade: le prove dell'esecutore aprono i loro server locali, i
      servizi della macchina restano chiusi. Gli altri protocolli verso `lo` sono rifiutati.
    - Verso gli indirizzi di `_CHIUSE4` fuori dalla macchina e verso ogni IPv6 fuori dalla macchina: rifiutato.
    - Verso l'IP pubblico della macchina (set `pubblici4`, riempito da `testo_ip_pubblico` ogni dieci minuti): un
      router col NAT loopback risponde lì anche dalla LAN, coi suoi servizi e gli inoltri di porte. Rifiutato.
    - Col conntrack spento sul loopback (`notrack`) il segno non varrebbe: rifiutato.
    - Il resto (internet in IPv4): sì.

    Le prime due righe rendono la ricarica atomica: `nft -f` toglie e rimette la tabella in una transazione sola.
    """
    righe_dns: list[str] = []
    for voce in dns:
        indirizzo = ipaddress.ip_address(voce)  # ValueError per tutto ciò che non è un indirizzo letterale
        if "%" in voce or str(indirizzo) != voce:
            raise ValueError(f"server DNS non valido: {voce!r}")
        famiglia = "ip" if indirizzo.version == 4 else "ip6"
        righe_dns.append(f"\t\t{famiglia} daddr {voce} meta l4proto {{ tcp, udp }} th dport 53 accept\n")
    t = tabella_rete(u)
    segno = hex(segno_rete(u))
    chi = u.esecutore
    return (
        f"# La rete dell'esecutore {chi}, scritta da `bottega installa macchina`: non cambiarla a mano.\n"
        f"table inet {t}\n"
        f"delete table inet {t}\n"
        f"table inet {t} {{\n"
        "\tset chiuse4 {\n"
        "\t\ttype ipv4_addr\n"
        "\t\tflags interval\n"
        f"\t\telements = {{ {', '.join(_CHIUSE4)} }}\n"
        "\t}\n"
        "\n"
        "\tset pubblici4 {\n"
        "\t\ttype ipv4_addr\n"
        "\t}\n"
        "\n"
        "\tchain uscita {\n"
        "\t\ttype filter hook output priority filter - 10; policy accept;\n"
        f'\t\tmeta skuid "{chi}" jump esecutore\n'
        f'\t\toifname "lo" ct direction reply ct mark & {segno} == {segno} jump risposta\n'
        "\t}\n"
        "\n"
        "\tchain esecutore {\n"
        f"{''.join(righe_dns)}"
        '\t\toifname "lo" ct state untracked reject\n'
        f'\t\toifname "lo" meta l4proto tcp ct mark set ct mark | {segno} accept\n'
        '\t\toifname "lo" reject\n'
        "\t\tip daddr @chiuse4 reject\n"
        "\t\tip daddr @pubblici4 reject\n"
        "\t\tmeta nfproto ipv6 reject\n"
        "\t}\n"
        "\n"
        "\tchain risposta {\n"
        f'\t\tmeta skuid "{chi}" accept\n'
        "\t\ttcp flags & (syn | ack) == syn | ack drop\n"
        "\t}\n"
        "}\n"
    )


testo_rete_esecutore.__test__ = False  # type: ignore[attr-defined]


def file_rete(u: Utenti) -> str:
    """Il file nftables della rete dell'esecutore."""
    return f"/etc/nftables.d/{u.esecutore}.nft"


def unita_rete(u: Utenti) -> str:
    """L'unità systemd che carica la rete dell'esecutore all'avvio."""
    return f"{u.esecutore}-rete.service"


def testo_unita_rete(u: Utenti) -> str:
    """L'unità della rete dell'esecutore: si carica prima della rete, come `nftables.service`, quindi prima dei runner."""
    return (
        "[Unit]\n"
        f"Description=Bottega: la rete dell'esecutore {u.esecutore}\n"
        "Wants=network-pre.target\n"
        "Before=network-pre.target shutdown.target\n"
        "After=nftables.service\n"
        "Conflicts=shutdown.target\n"
        "DefaultDependencies=no\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"ExecStart=/usr/sbin/nft -f {file_rete(u)}\n"
        f"ExecReload=/usr/sbin/nft -f {file_rete(u)}\n"
        f"ExecStop=/usr/sbin/nft delete table inet {tabella_rete(u)}\n"
        "\n"
        "[Install]\n"
        "WantedBy=sysinit.target\n"
    )


testo_unita_rete.__test__ = False  # type: ignore[attr-defined]


def passi_rete(u: Utenti, dns: Sequence[str]) -> list[Passo]:
    """I passi della rete dell'esecutore: `nft`, il file della regola, le unità, il carico e l'accensione all'avvio.

    La regola si ricarica sempre (`nft -f` è atomico): un file cambiato vale subito, senza fermare l'unità. Ricaricata
    la regola il set dell'IP pubblico è vuoto: lo riempie subito il programma dell'IP pubblico, poi il suo timer.
    """
    unita = unita_rete(u)
    ip = unita_ip_pubblico(u)
    return [
        Passo(
            descrizione="nft presente",
            comando=("sh", "-c", "echo 'manca nft: installa il pacchetto nftables' >&2; exit 1"),
            controllo=("sh", "-c", "test -x /usr/sbin/nft"),
        ),
        passo_file(f"rete dell'esecutore in {file_rete(u)}", testo_rete_esecutore(u, dns), file_rete(u), "0644"),
        passo_file(f"unità {unita}", testo_unita_rete(u), f"/etc/systemd/system/{unita}", "0644"),
        passo_file(f"programma {programma_ip_pubblico(u)}", testo_ip_pubblico(u), programma_ip_pubblico(u), "0755"),
        passo_file(f"unità {ip}.service", testo_unita_ip_pubblico(u), f"/etc/systemd/system/{ip}.service", "0644"),
        passo_file(f"timer {ip}.timer", testo_timer_ip_pubblico(u), f"/etc/systemd/system/{ip}.timer", "0644"),
        Passo(descrizione="rete dell'esecutore caricata", comando=("sudo", "-n", "nft", "-f", file_rete(u))),
        Passo(descrizione="configurazione di systemd ricaricata", comando=("sudo", "-n", "systemctl", "daemon-reload")),
        Passo(
            descrizione=f"unità {unita} accesa all'avvio",
            comando=("sudo", "-n", "systemctl", "enable", "--now", unita),
            controllo=("sh", "-c", f"systemctl is-enabled --quiet {unita} && systemctl is-active --quiet {unita}"),
        ),
        Passo(
            descrizione="IP pubblico nella rete dell'esecutore",
            comando=("sudo", "-n", "systemctl", "start", f"{ip}.service"),
        ),
        Passo(
            descrizione=f"timer {ip}.timer acceso",
            comando=("sudo", "-n", "systemctl", "enable", "--now", f"{ip}.timer"),
            controllo=(
                "sh",
                "-c",
                f"systemctl is-enabled --quiet {ip}.timer && systemctl is-active --quiet {ip}.timer",
            ),
        ),
    ]


# --- L'IP pubblico della macchina (B8-3, dalla revisione: G2) ---

# Da dove si legge l'IP pubblico: due servizi, il secondo se il primo non risponde. Solo IPv4: ogni IPv6 fuori dalla
# macchina è già rifiutato.
FONTI_IP_PUBBLICO = ("https://api.ipify.org", "https://ifconfig.me/ip")


def programma_ip_pubblico(u: Utenti) -> str:
    """Il percorso del programma che mette l'IP pubblico nella rete dell'esecutore."""
    return f"/usr/local/lib/bottega/{u.esecutore}-ip-pubblico"


def unita_ip_pubblico(u: Utenti) -> str:
    """L'unità (e il timer, con lo stesso nome) che tiene aggiornato l'IP pubblico."""
    return f"{u.esecutore}-ip-pubblico"


def testo_ip_pubblico(u: Utenti) -> str:
    """Il programma che mette l'IP pubblico della macchina nel set `pubblici4` della rete dell'esecutore.

    Un router che risponde sul suo IP pubblico anche dalla LAN (NAT loopback, gestione dal lato WAN, inoltri di porte)
    riaprirebbe la casa all'esecutore. L'IP si legge da fuori; se nessuna fonte risponde con un IPv4 il set resta
    com'era e il programma esce 1. Il cambio del set è una transazione sola.
    """
    t = tabella_rete(u)
    fonti = " ".join(FONTI_IP_PUBBLICO)
    return (
        "#!/bin/sh\n"
        f"# L'IP pubblico nella rete dell'esecutore {u.esecutore}, scritto da `bottega installa macchina`.\n"
        "set -u\n"
        f"for fonte in {fonti}; do\n"
        '\tip=$(curl -fsS -m 10 "$fonte" 2>/dev/null) || continue\n'
        "\tprintf '%s\\n' \"$ip\" | grep -Eqx '([0-9]{1,3}[.]){3}[0-9]{1,3}' || continue\n"
        f"\tprintf 'flush set inet {t} pubblici4\\nadd element inet {t} pubblici4 {{ %s }}\\n' \"$ip\" "
        "| /usr/sbin/nft -f - && exit 0\n"
        "done\n"
        "echo \"IP pubblico non letto: la rete dell'esecutore resta com'era\" >&2\n"
        "exit 1\n"
    )


testo_ip_pubblico.__test__ = False  # type: ignore[attr-defined]


def testo_unita_ip_pubblico(u: Utenti) -> str:
    """L'unità che lancia il programma dell'IP pubblico, dopo la rete dell'esecutore e con la rete su."""
    return (
        "[Unit]\n"
        f"Description=Bottega: l'IP pubblico nella rete dell'esecutore {u.esecutore}\n"
        f"After=network-online.target {unita_rete(u)}\n"
        "Wants=network-online.target\n"
        f"Requires={unita_rete(u)}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={programma_ip_pubblico(u)}\n"
    )


testo_unita_ip_pubblico.__test__ = False  # type: ignore[attr-defined]


def testo_timer_ip_pubblico(u: Utenti) -> str:
    """Il timer dell'IP pubblico: un minuto dopo l'avvio, poi ogni dieci minuti."""
    return (
        "[Unit]\n"
        f"Description=Bottega: l'IP pubblico nella rete dell'esecutore {u.esecutore}, ogni dieci minuti\n"
        "\n"
        "[Timer]\n"
        "OnBootSec=1min\n"
        "OnUnitActiveSec=10min\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


testo_timer_ip_pubblico.__test__ = False  # type: ignore[attr-defined]
