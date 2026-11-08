"""La firma del ramo principale: prepara le chiavi e verifica i sigilli.

Solo libreria standard. I processi git e ssh-keygen eseguono le operazioni crittografiche.
"""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from bottega.forgia import Forgia, ForgiaGh

TITOLO_AVVISO = "Avviso della bottega: firma del ramo principale"
CHIAVE_AVVISO = "firma"


class ErroreFirma(RuntimeError):
    """Errore nella preparazione o configurazione della firma."""


@dataclass(frozen=True)
class EsitoFirma:
    """Esito del controllo di firma su un commit."""

    buona: bool
    motivo: str
    principale: str | None = None
    sha: str | None = None
    sha_intero: str | None = None


# Il percorso dei programmi della verifica: fisso, mai quello dell'ambiente (un passo di prima può averlo cambiato).
PATH_FIDATO = "/usr/bin:/bin"

# Chiavi della configurazione git che la verifica fissa da riga di comando (vincono su quella del clone, che un passo
# di prima può aver scritto): i programmi di firma, l'elenco, gli hook, fsmonitor.
_OPZIONI_GIT_FIDATE: tuple[str, ...] = (
    # Gli oggetti come sono: niente refs/replace né grafts, che un passo di prima può aver scritto nel clone.
    "--no-replace-objects",
    "-c", "core.useReplaceRefs=false",
    "-c", "core.commitGraph=false",
    "-c", "gpg.program=false",
    "-c", "gpg.openpgp.program=false",
    "-c", "gpg.x509.program=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
)

_SHA_INTERO = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _ambiente_fidato() -> dict[str, str]:
    """Ambiente minimo per git e ssh-keygen: PATH fisso, niente configurazione globale o di sistema, messaggi in C."""
    env = {
        "PATH": PATH_FIDATO,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_GRAFT_FILE": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
        "LANG": "C",
    }
    if os.environ.get("HOME"):
        env["HOME"] = os.environ["HOME"]
    return env


def _ssh_keygen_fidato() -> str:
    """ssh-keygen dal PATH fisso, col percorso assoluto."""
    return shutil.which("ssh-keygen", path=PATH_FIDATO) or "/usr/bin/ssh-keygen"


def _git(clone: Path, *argomenti: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "git", *_OPZIONI_GIT_FIDATE, "-c", f"gpg.ssh.program={_ssh_keygen_fidato()}",
            "-C", str(clone), *argomenti,
        ],
        capture_output=True,
        text=True,
        errors="replace",
        env=_ambiente_fidato(),
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def verifica(
    clone: Path,
    punta: str = "HEAD",
    rilascio: str | None = None,
    primo: bool = False,
) -> EsitoFirma:
    """Verifica la firma della punta rispetto alle chiavi ammesse nel rilascio (o nella punta con primo).

    Il rilascio è lo SHA intero dell'ultima punta verificata, tenuto fuori dal repo: un tag o un ramo li può spingere
    chiunque abbia il token. Solo firme SSH. Non solleva mai: ogni errore è un EsitoFirma con buona=False.
    """
    try:
        return _verifica(clone, punta, rilascio, primo)
    except Exception as e:  # noqa: BLE001 - B4-R2.7: nessuna eccezione esce, ogni errore è un rifiuto
        return EsitoFirma(buona=False, motivo=f"errore: {e}")


def _verifica(clone: Path, punta: str, rilascio: str | None, primo: bool) -> EsitoFirma:
    # 1. Risolve la punta
    res_punta = _git(clone, "rev-parse", "--verify", "--end-of-options", f"{punta}^{{commit}}")
    if res_punta.returncode != 0:
        if "dubious ownership" in res_punta.stderr:
            return EsitoFirma(buona=False, motivo="clone di un altro utente: git lo rifiuta (safe.directory)")
        return EsitoFirma(buona=False, motivo=f"riferimento sconosciuto: {punta}")
    punta_commit = res_punta.stdout.strip()
    sha_corto = punta_commit[:7]

    # 2. Il rilascio: uno SHA intero (o --primo)
    if primo:
        ref_elenco = punta_commit
    else:
        if not rilascio:
            return EsitoFirma(buona=False, motivo="serve un rilascio o --primo", sha=sha_corto)
        if not _SHA_INTERO.fullmatch(rilascio):
            return EsitoFirma(
                buona=False, motivo="il rilascio va dato come SHA intero, mai un tag o un ramo", sha=sha_corto
            )
        res_ril = _git(clone, "rev-parse", "--verify", "--end-of-options", f"{rilascio}^{{commit}}")
        if res_ril.returncode != 0:
            return EsitoFirma(buona=False, motivo=f"riferimento sconosciuto: {rilascio}", sha=sha_corto)
        rilascio_commit = res_ril.stdout.strip()

        # 3. La punta deve discendere dal rilascio
        res_anc = _git(clone, "merge-base", "--is-ancestor", rilascio_commit, punta_commit)
        if res_anc.returncode != 0:
            return EsitoFirma(buona=False, motivo="punta non discende dal rilascio", sha=sha_corto)
        ref_elenco = rilascio_commit

    # 4. L'elenco dall'oggetto git del rilascio (o della punta con primo), mai dall'albero di lavoro
    res_show = _git(clone, "show", f"{ref_elenco}:.github/bottega/firme-ammesse")
    if res_show.returncode != 0:
        return EsitoFirma(buona=False, motivo="elenco assente nel rilascio", sha=sha_corto)
    elenco_testo = res_show.stdout
    righe_chiavi = [r for r in elenco_testo.splitlines() if r.strip() and not r.strip().startswith("#")]
    if not righe_chiavi:
        return EsitoFirma(buona=False, motivo="elenco vuoto", sha=sha_corto)

    # 5. La firma: solo l'intestazione del commit (fino alla prima riga vuota), solo SSH
    res_cat = _git(clone, "cat-file", "commit", punta_commit)
    intestazione = res_cat.stdout.split("\n\n", 1)[0].splitlines()
    firme = [i for i, r in enumerate(intestazione) if r.startswith(("gpgsig ", "gpgsig-sha256 "))]
    if not firme:
        return EsitoFirma(buona=False, motivo="punta non firmata", sha=sha_corto)
    if any(intestazione[i].split(" ", 1)[1].strip() != "-----BEGIN SSH SIGNATURE-----" for i in firme):
        return EsitoFirma(buona=False, motivo="firma non SSH", sha=sha_corto)

    # 6. git verify-commit con l'elenco in un file temporaneo
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f_elenco:
        f_elenco.write(elenco_testo)
        percorso_elenco = Path(f_elenco.name)
    try:
        res_v = _git(clone, "-c", f"gpg.ssh.allowedSignersFile={percorso_elenco}", "verify-commit", "--raw", punta_commit)
        uscita = (res_v.stdout or "") + "\n" + (res_v.stderr or "")
        match = re.search(r'Good "git" signature for (\S+)', uscita)
        if res_v.returncode == 0 and match:
            return EsitoFirma(
                buona=True, motivo="", principale=match.group(1), sha=sha_corto, sha_intero=punta_commit
            )
        return EsitoFirma(buona=False, motivo="firma di una chiave non ammessa", sha=sha_corto)
    finally:
        percorso_elenco.unlink(missing_ok=True)


def prepara(cartella: Path, chiave: Path, globale: bool = False) -> list[str]:
    """Prepara la chiave SSH di firma, configura git e registra la chiave ammessa."""
    chiave_pub = Path(str(chiave) + ".pub")

    # La radice del repo, anche se si lancia da una sottocartella: l'elenco sta sempre lì.
    res_radice = subprocess.run(
        ["git", "-C", str(cartella), "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if res_radice.returncode != 0 or not res_radice.stdout.strip():
        raise ErroreFirma(f"non è un repo git: {cartella}")
    cartella = Path(res_radice.stdout.strip())

    # Ricava l'email utente da git
    res_email = subprocess.run(
        ["git", "-C", str(cartella), "config", "user.email"],
        capture_output=True,
        text=True,
    )
    email = res_email.stdout.strip()
    if res_email.returncode != 0 or not email:
        raise ErroreFirma("configurazione git priva di user.email")

    if chiave.is_file() and not chiave_pub.is_file():
        raise ErroreFirma(f"chiave privata presente senza pubblica: {chiave_pub}")

    # Una .pub senza la privata è una chiave tenuta in un agente (un gestore di password, un token): si usa com'è.
    if not chiave.is_file() and not chiave_pub.is_file():
        if not chiave.parent.exists():
            chiave.parent.mkdir(parents=True, mode=0o700)
        # Il commento di serie sarebbe utente@macchina: la riga pubblica finisce in un repo che può essere pubblico.
        res_k = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "bottega firma", "-f", str(chiave)],
            capture_output=True,
            text=True,
        )
        if res_k.returncode != 0:
            raise ErroreFirma(f"creazione chiave fallita: {res_k.stderr.strip()}")

    if not chiave_pub.is_file():
        raise ErroreFirma(f"chiave pubblica non trovata: {chiave_pub}")

    pub_line = chiave_pub.read_text(encoding="utf-8").strip()


    # Configura git
    base_cmd = ["git"]
    if globale:
        base_cmd.extend(["config", "--global"])
    else:
        base_cmd.extend(["-C", str(cartella), "config", "--local"])

    def _imposta(k: str, v: str) -> None:
        res = subprocess.run([*base_cmd, k, v], capture_output=True, text=True)
        if res.returncode != 0:
            raise ErroreFirma(f"impostazione git config {k} fallita: {res.stderr.strip()}")

    # Solo le unioni si firmano (`git merge --no-ff -S`): con commit.gpgsign ogni commit di lavoro di chi decide, anche
    # su un ramo rifiutato, diventerebbe una punta rilasciabile.
    _imposta("gpg.format", "ssh")
    _imposta("user.signingkey", str(chiave_pub.resolve()))
    _imposta("tag.gpgsign", "true")

    # Aggiunge a .github/bottega/firme-ammesse della cartella corrente se non presente
    firme_dir = cartella / ".github" / "bottega"
    firme_dir.mkdir(parents=True, exist_ok=True)
    firme_file = firme_dir / "firme-ammesse"

    parti_pub = pub_line.split()
    corpo_chiave = f"{parti_pub[0]} {parti_pub[1]}" if len(parti_pub) >= 2 else pub_line
    testo_attuale = firme_file.read_text(encoding="utf-8") if firme_file.is_file() else ""
    # Presente solo se una riga attiva (non commentata) ha lo stesso tipo e la stessa chiave, come campi.
    tipo_e_chiave = corpo_chiave.split()
    gia_presente = False
    for riga in testo_attuale.splitlines():
        if not riga.strip() or riga.strip().startswith("#"):
            continue
        campi = riga.split()
        if any(campi[k : k + 2] == tipo_e_chiave for k in range(len(campi) - 1)):
            gia_presente = True
            break

    if not gia_presente:
        # Solo tipo e chiave: il commento della pubblica (anche di una chiave fatta prima) resta fuori dal repo.
        riga_nuova = f'{email} namespaces="git" {corpo_chiave}'
        with firme_file.open("a", encoding="utf-8") as f:
            if testo_attuale and not testo_attuale.endswith("\n"):
                f.write("\n")
            f.write(riga_nuova + "\n")

    return [
        f"chiave di firma: {chiave_pub}",
        f"configurazione git aggiornata ({'globale' if globale else 'locale'})",
        "il file .github/bottega/firme-ammesse va unito al ramo principale con una PR",
    ]


def argomenti_firma(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il sottocomando firma."""
    sottoparsers = parser.add_subparsers(dest="azione", metavar="AZIONE", required=True)

    p_prepara = sottoparsers.add_parser("prepara", help="prepara la chiave di firma e configura git")
    p_prepara.add_argument(
        "--chiave",
        type=Path,
        default=None,
        metavar="PERCORSO",
        help="percorso della chiave (predefinito: ~/.ssh/bottega_firma)",
    )
    p_prepara.add_argument("--globale", action="store_true", help="scrive la configurazione in git globale")
    p_prepara.add_argument("--cartella", type=Path, default=Path("."), help=argparse.SUPPRESS)

    p_verifica = sottoparsers.add_parser("verifica", help="verifica la firma della punta del ramo principale")
    p_verifica.add_argument(
        "--punta",
        default="HEAD",
        metavar="REF",
        help="riferimento da verificare (predefinito: HEAD)",
    )
    gruppo = p_verifica.add_mutually_exclusive_group()
    gruppo.add_argument("--rilascio", metavar="SHA", help="SHA intero dell'ultimo rilascio verificato")
    gruppo.add_argument(
        "--stato",
        type=Path,
        metavar="FILE",
        help="file fuori dal repo con lo SHA dell'ultimo rilascio verificato; se la firma è buona vi scrive la punta",
    )
    p_verifica.add_argument(
        "--primo",
        action="store_true",
        help="primo rilascio: legge l'elenco dalla punta stessa (con --stato, solo se il file non c'è ancora)",
    )
    p_verifica.add_argument("--avvisa", action="store_true", help="apre o chiude l'avviso sulla forgia GitHub")
    p_verifica.add_argument("--cartella", type=Path, default=Path("."), help=argparse.SUPPRESS)


def _scrivi_stato(stato: Path, sha: str) -> None:
    """Scrive lo SHA verificato nel file di stato: file temporaneo nuovo nella stessa cartella, fsync, os.replace.

    Il temporaneo lo crea mkstemp (O_EXCL: un link messo lì prima non si segue), e un crollo a metà non lascia uno
    stato vuoto.
    """
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
        raise OSError(f"SHA non valido: {sha!r}")
    stato.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(dir=stato.parent, prefix=f".{stato.name}.", suffix=".nuovo")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(nome, stato)
    except BaseException:
        Path(nome).unlink(missing_ok=True)
        raise


def comando_firma(args: argparse.Namespace, forgia: Forgia | None = None) -> int:
    """Esegue l'azione del sottocomando firma (prepara o verifica)."""
    azione = getattr(args, "azione", None)
    if azione == "prepara":
        cartella = getattr(args, "cartella", Path("."))
        chiave = args.chiave if getattr(args, "chiave", None) is not None else Path.home() / ".ssh" / "bottega_firma"
        try:
            righe = prepara(cartella=cartella, chiave=chiave, globale=args.globale)
            for r in righe:
                print(r)
            return 0
        except ErroreFirma as e:
            print(f"errore: {e}", file=sys.stderr)
            return 1

    if azione == "verifica":
        cartella = getattr(args, "cartella", Path("."))
        stato: Path | None = getattr(args, "stato", None)
        rilascio = args.rilascio
        if rilascio is not None and args.primo:
            print("errore: --rilascio e --primo si escludono", file=sys.stderr)
            return 2
        if rilascio is None and stato is None and not args.primo:
            print("errore: serve --rilascio, --stato o --primo", file=sys.stderr)
            return 2
        if stato is not None:
            if stato.is_file():
                if args.primo:
                    print(f"errore: {stato} c'è già: --primo vale solo per il primo rilascio", file=sys.stderr)
                    return 2
                try:
                    rilascio = stato.read_text(encoding="utf-8").strip()
                except (OSError, UnicodeDecodeError) as e:
                    rilascio = f"(stato illeggibile: {e})"
            elif not args.primo:
                print(f"errore: {stato} non c'è: il primo rilascio si verifica con --primo", file=sys.stderr)
                return 2
        esito = verifica(clone=cartella, punta=args.punta, rilascio=rilascio, primo=args.primo)
        if esito.buona and stato is not None:
            try:
                _scrivi_stato(stato, esito.sha_intero or "")
            except OSError as e:
                esito = EsitoFirma(buona=False, motivo=f"stato non scritto: {e}", sha=esito.sha)
        if getattr(args, "avvisa", False):
            if forgia is None:
                repo = os.environ.get("GITHUB_REPOSITORY", "")
                forgia = ForgiaGh(repo)

        if esito.buona:
            print(f"firma: buona ({esito.principale}, {esito.sha})")
            if getattr(args, "avvisa", False) and forgia is not None:
                try:
                    forgia.avviso(CHIAVE_AVVISO, TITOLO_AVVISO, None)
                except Exception as e:
                    print(f"errore avviso: {e}", file=sys.stderr)
            return 0

        print(f"firma: rifiutata: {esito.motivo}")
        if getattr(args, "avvisa", False) and forgia is not None:
            try:
                forgia.avviso(CHIAVE_AVVISO, TITOLO_AVVISO, esito.motivo)
            except Exception as e:
                print(f"errore avviso: {e}", file=sys.stderr)
        return 1

    return 2
