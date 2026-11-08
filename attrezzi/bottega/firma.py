"""La firma del ramo principale: prepara le chiavi e verifica i sigilli.

Solo libreria standard. I processi git e ssh-keygen eseguono le operazioni crittografiche.
"""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
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


def verifica(
    clone: Path,
    punta: str = "HEAD",
    rilascio: str | None = None,
    primo: bool = False,
) -> EsitoFirma:
    """Verifica la firma della punta rispetto alle chiavi ammesse nel rilascio indicato (o nella punta con primo).

    Non solleva mai eccezioni: qualsiasi errore di git o ssh-keygen restituisce un EsitoFirma con buona=False.
    """
    try:
        # 1. Risolve la punta
        res_punta = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "--verify", f"{punta}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if res_punta.returncode != 0:
            return EsitoFirma(buona=False, motivo=f"riferimento sconosciuto: {punta}")
        punta_commit = res_punta.stdout.strip()

        res_sha = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "--short", punta_commit],
            capture_output=True,
            text=True,
        )
        sha_corto = res_sha.stdout.strip() if res_sha.returncode == 0 else punta_commit[:7]

        # 2. Controlla il rilascio o il flag primo
        if not primo:
            if not rilascio:
                return EsitoFirma(buona=False, motivo="serve un rilascio o --primo", sha=sha_corto)
            res_ril = subprocess.run(
                ["git", "-C", str(clone), "rev-parse", "--verify", f"{rilascio}^{{commit}}"],
                capture_output=True,
                text=True,
            )
            if res_ril.returncode != 0:
                return EsitoFirma(buona=False, motivo=f"riferimento sconosciuto: {rilascio}", sha=sha_corto)
            rilascio_commit = res_ril.stdout.strip()

            # 3. La punta deve discendere dal rilascio
            res_anc = subprocess.run(
                ["git", "-C", str(clone), "merge-base", "--is-ancestor", rilascio_commit, punta_commit],
                capture_output=True,
            )
            if res_anc.returncode != 0:
                return EsitoFirma(buona=False, motivo="punta non discende dal rilascio", sha=sha_corto)

            ref_elenco = rilascio_commit
        else:
            ref_elenco = punta_commit

        # 4. Legge l'elenco delle chiavi ammesse dall'oggetto git del rilascio (o della punta se primo)
        res_show = subprocess.run(
            ["git", "-C", str(clone), "show", f"{ref_elenco}:.github/bottega/firme-ammesse"],
            capture_output=True,
            text=True,
        )
        if res_show.returncode != 0:
            return EsitoFirma(buona=False, motivo="elenco assente nel rilascio", sha=sha_corto)

        elenco_testo = res_show.stdout
        righe_chiavi = [r for r in elenco_testo.splitlines() if r.strip() and not r.strip().startswith("#")]
        if not righe_chiavi:
            return EsitoFirma(buona=False, motivo="elenco vuoto", sha=sha_corto)

        # 5. Verifica se il commit ha una firma
        res_cat = subprocess.run(
            ["git", "-C", str(clone), "cat-file", "commit", punta_commit],
            capture_output=True,
            text=True,
        )
        # Solo l'intestazione del commit (fino alla prima riga vuota): il messaggio può contenere la parola.
        intestazione = res_cat.stdout.split("\n\n", 1)[0]
        if not any(r.startswith("gpgsig ") for r in intestazione.splitlines()):
            return EsitoFirma(buona=False, motivo="punta non firmata", sha=sha_corto)

        # 6. Esegue il controllo con allowedSignersFile temporaneo
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f_elenco:
            f_elenco.write(elenco_testo)
            percorso_elenco = Path(f_elenco.name)

        try:
            res_v = subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone),
                    "-c",
                    f"gpg.ssh.allowedSignersFile={percorso_elenco}",
                    "verify-commit",
                    "--raw",
                    punta_commit,
                ],
                capture_output=True,
                text=True,
            )
            uscita = (res_v.stdout or "") + "\n" + (res_v.stderr or "")
            match = re.search(r'Good "git" signature for (\S+)', uscita)
            if res_v.returncode == 0 and match:
                principale = match.group(1)
                return EsitoFirma(buona=True, motivo="", principale=principale, sha=sha_corto)
            return EsitoFirma(buona=False, motivo="firma di una chiave non ammessa", sha=sha_corto)
        finally:
            percorso_elenco.unlink(missing_ok=True)

    except OSError as e:
        return EsitoFirma(buona=False, motivo=str(e))


def prepara(cartella: Path, chiave: Path, globale: bool = False) -> list[str]:
    """Prepara la chiave SSH di firma, configura git e registra la chiave ammessa."""
    chiave_pub = Path(str(chiave) + ".pub")

    if chiave.is_file() and not chiave_pub.is_file():
        raise ErroreFirma(f"chiave privata presente senza pubblica: {chiave_pub}")

    if not chiave.is_file():
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

    # Ricava l'email utente da git
    res_email = subprocess.run(
        ["git", "-C", str(cartella), "config", "user.email"],
        capture_output=True,
        text=True,
    )
    email = res_email.stdout.strip()
    if res_email.returncode != 0 or not email:
        raise ErroreFirma("configurazione git priva di user.email")

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

    _imposta("gpg.format", "ssh")
    _imposta("user.signingkey", str(chiave_pub.resolve()))
    _imposta("commit.gpgsign", "true")
    _imposta("tag.gpgsign", "true")

    # Aggiunge a .github/bottega/firme-ammesse della cartella corrente se non presente
    firme_dir = cartella / ".github" / "bottega"
    firme_dir.mkdir(parents=True, exist_ok=True)
    firme_file = firme_dir / "firme-ammesse"

    parti_pub = pub_line.split()
    corpo_chiave = f"{parti_pub[0]} {parti_pub[1]}" if len(parti_pub) >= 2 else pub_line
    testo_attuale = firme_file.read_text(encoding="utf-8") if firme_file.is_file() else ""
    gia_presente = any(corpo_chiave in r for r in testo_attuale.splitlines())

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
    gruppo = p_verifica.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("--rilascio", metavar="REF", help="riferimento dell'ultimo rilascio da cui leggere l'elenco")
    gruppo.add_argument("--primo", action="store_true", help="primo rilascio: legge l'elenco dalla punta stessa")
    p_verifica.add_argument("--avvisa", action="store_true", help="apre o chiude l'avviso sulla forgia GitHub")
    p_verifica.add_argument("--cartella", type=Path, default=Path("."), help=argparse.SUPPRESS)


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
        esito = verifica(clone=cartella, punta=args.punta, rilascio=args.rilascio, primo=args.primo)
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
