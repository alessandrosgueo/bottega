"""Prove per bottega.firma (Compito B4.1)."""

import argparse
from pathlib import Path
import subprocess

import pytest

from bottega.finta import ForgiaFinta
from bottega.firma import (
    ErroreFirma,
    EsitoFirma,
    argomenti_firma,
    comando_firma,
    prepara,
    verifica,
)


@pytest.fixture(autouse=True)
def isola_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola l'ambiente di prova: HOME finta, gitconfig finto, niente configurazione di sistema."""
    casa = tmp_path / "casa"
    casa.mkdir(parents=True, exist_ok=True)
    gitconfig = tmp_path / "gitconfig"
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _crea_chiave(cartella: Path, nome: str = "chiave") -> tuple[Path, str]:
    """Crea una coppia di chiavi ed25519 vera e restituisce (percorso_privata, testo_pubblica)."""
    chiave = cartella / nome
    chiave.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(chiave)],
        check=True,
        capture_output=True,
    )
    pub = Path(str(chiave) + ".pub").read_text(encoding="utf-8").strip()
    return chiave, pub


def _crea_repo(cartella: Path, nome: str = "repo", email: str = "tester@example.com") -> Path:
    """Crea un repo git locale in tmp_path con utente configurato."""
    repo = cartella / nome
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
    if email:
        subprocess.run(["git", "config", "user.email", email], cwd=repo, check=True, capture_output=True)
    return repo


def _committa_firmato(
    repo: Path,
    chiave: Path,
    messaggio: str = "commit",
    nome_file: str = "file.txt",
    contenuto: str = "ciao\n",
    email: str = "tester@example.com",
    programma_ssh: Path | None = None,
) -> str:
    """Scrive un file, fa git add e git commit firmato con la chiave indicata."""
    file_path = repo / nome_file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(contenuto, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    cmd = [
        "git",
        "-c", f"user.email={email}",
        "-c", "gpg.format=ssh",
        "-c", f"user.signingkey={chiave}.pub",
    ]
    if programma_ssh is not None:
        cmd.extend(["-c", f"gpg.ssh.program={programma_ssh}"])
    cmd.extend(["commit", "-S", "-m", messaggio])
    subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True)
    return res.stdout.strip()


def test_verifica_buona(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    c2 = _committa_firmato(repo, chiave_alice, "lavoro su main", nome_file="f2.txt", email=email_alice)

    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is True
    assert esito.motivo == ""
    assert esito.principale == email_alice
    assert esito.sha == c2[:7]


def test_verifica_punta_non_firmata(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    # Commit non firmato
    (repo / "f2.txt").write_text("modifica non firmata\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "senza firma"], cwd=repo, check=True, capture_output=True)

    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "punta non firmata"


def test_verifica_chiave_aggiunta_nello_stesso_push(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    chiave_bob, pub_bob = _crea_chiave(tmp_path, "bob")
    email_alice = "alice@example.com"
    email_bob = "bob@example.com"

    # In v1.0 c'è solo alice
    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    # Nel commit 2 si aggiunge bob a firme-ammesse e il commit è firmato da bob
    firme.write_text(
        f"{email_alice} namespaces=\"git\" {pub_alice}\n{email_bob} namespaces=\"git\" {pub_bob}\n",
        encoding="utf-8",
    )
    _committa_firmato(repo, chiave_bob, "commit con chiave nuova", nome_file="f2.txt", email=email_bob)

    # La verifica deve leggere l'elenco da v1.0, quindi rifiutare bob!
    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "firma di una chiave non ammessa"


def test_verifica_punta_all_indietro(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    c1 = _committa_firmato(repo, chiave_alice, "commit 1", email=email_alice)
    c2 = _committa_firmato(repo, chiave_alice, "commit 2", nome_file="f2.txt", email=email_alice)
    subprocess.run(["git", "tag", "v2.0", c2], cwd=repo, check=True, capture_output=True)

    # Punta all'indietro: c1 punta a un commit precedente a v2.0
    esito = verifica(repo, punta=c1, rilascio="v2.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "punta non discende dal rilascio"


def test_verifica_namespace_sbagliato(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    # Wrapper ssh-keygen che usa namespace 'file' invece di 'git'
    wrapper = tmp_path / "ssh-wrapper.sh"
    wrapper.write_text(
        "#!/bin/sh\n"
        "args=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-n\" ]; then\n"
        "    shift\n"
        "    args=\"$args -n file\"\n"
        "  else\n"
        "    args=\"$args $1\"\n"
        "  fi\n"
        "  shift\n"
        "done\n"
        "exec ssh-keygen $args\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    _committa_firmato(
        repo,
        chiave_alice,
        "commit con namespace sbagliato",
        nome_file="f2.txt",
        email=email_alice,
        programma_ssh=wrapper,
    )

    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "firma di una chiave non ammessa"


def test_verifica_elenco_assente_nel_rilascio(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, _ = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    # Rilascio senza il file firme-ammesse
    _committa_firmato(repo, chiave_alice, "rilascio senza firme", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    _committa_firmato(repo, chiave_alice, "lavoro su main", nome_file="f2.txt", email=email_alice)

    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "elenco assente nel rilascio"


def test_verifica_elenco_vuoto(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, _ = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text("# solo commenti\n   \n# altra riga vuota\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio con firme vuote", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    _committa_firmato(repo, chiave_alice, "lavoro su main", nome_file="f2.txt", email=email_alice)

    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "elenco vuoto"


def test_verifica_riferimento_sconosciuto(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")
    _committa_firmato(repo, chiave_alice, "commit iniziale", email=email_alice)

    esito_punta = verifica(repo, punta="INESISTENTE", rilascio="v1.0", primo=False)
    assert esito_punta.buona is False
    assert esito_punta.motivo == "riferimento sconosciuto: INESISTENTE"

    esito_rilascio = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito_rilascio.buona is False
    assert esito_rilascio.motivo == "riferimento sconosciuto: v1.0"


def test_verifica_primo_legge_la_punta(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    c1 = _committa_firmato(repo, chiave_alice, "primo commit della storia", email=email_alice)

    esito = verifica(repo, punta="HEAD", rilascio=None, primo=True)
    assert esito.buona is True
    assert esito.motivo == ""
    assert esito.principale == email_alice
    assert esito.sha == c1[:7]


def test_verifica_non_legge_l_albero_di_lavoro(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path)
    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    chiave_attacco, pub_attacco = _crea_chiave(tmp_path, "attacco")
    email_alice = "alice@example.com"
    email_attacco = "attacco@example.com"

    # In v1.0 c'è solo alice
    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    # Punta firmata da chiave_attacco (ma firme-ammesse nel git tree non ha la chiave dell'attacco)
    _committa_firmato(repo, chiave_attacco, "punta dell'attacco", nome_file="f2.txt", email=email_attacco)

    # Nell'albero di lavoro (non committato) viene messa la chiave dell'attacco
    firme.write_text(
        f"{email_alice} namespaces=\"git\" {pub_alice}\n{email_attacco} namespaces=\"git\" {pub_attacco}\n",
        encoding="utf-8",
    )

    # La verifica DEVE ignorare l'albero di lavoro e leggere da v1.0: rifiuto!
    esito = verifica(repo, punta="HEAD", rilascio="v1.0", primo=False)
    assert esito.buona is False
    assert esito.motivo == "firma di una chiave non ammessa"


def test_prepara_crea_chiave_e_configura_git(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path, email="decisore@example.com")
    chiave = tmp_path / "chiavi" / "bottega_firma"

    righe = prepara(cartella=repo, chiave=chiave, globale=False)
    assert chiave.is_file()
    assert Path(str(chiave) + ".pub").is_file()

    firme = repo / ".github" / "bottega" / "firme-ammesse"
    assert firme.is_file()
    testo_firme = firme.read_text(encoding="utf-8")
    pub = Path(str(chiave) + ".pub").read_text(encoding="utf-8").strip()
    tipo, corpo, commento = pub.split(" ", 2)
    assert commento == "bottega firma"
    assert testo_firme == f"decisore@example.com namespaces=\"git\" {tipo} {corpo}\n"

    def _cfg(k: str) -> str:
        res = subprocess.run(["git", "config", "--local", k], cwd=repo, check=True, capture_output=True, text=True)
        return res.stdout.strip()

    assert _cfg("gpg.format") == "ssh"
    assert _cfg("user.signingkey") == str(chiave) + ".pub"
    assert _cfg("commit.gpgsign") == "true"
    assert _cfg("tag.gpgsign") == "true"

    assert any("PR" in r or "pr" in r.lower() for r in righe)


def test_prepara_due_volte(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path, email="decisore@example.com")
    chiave = tmp_path / "chiavi" / "bottega_firma"

    prepara(cartella=repo, chiave=chiave, globale=False)
    contenuto_privata_1 = chiave.read_bytes()
    firme = repo / ".github" / "bottega" / "firme-ammesse"
    righe_firme_1 = firme.read_text(encoding="utf-8").splitlines()

    prepara(cartella=repo, chiave=chiave, globale=False)
    contenuto_privata_2 = chiave.read_bytes()
    righe_firme_2 = firme.read_text(encoding="utf-8").splitlines()

    assert contenuto_privata_1 == contenuto_privata_2
    assert righe_firme_1 == righe_firme_2
    assert len(righe_firme_2) == 1


def test_prepara_privata_senza_pub(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path, email="decisore@example.com")
    chiave = tmp_path / "chiavi" / "bottega_firma"
    chiave.parent.mkdir(parents=True, exist_ok=True)
    chiave.write_text("chiave privata finta", encoding="utf-8")

    with pytest.raises(ErroreFirma, match="pubblica"):
        prepara(cartella=repo, chiave=chiave, globale=False)


def test_prepara_senza_email(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path, email="")
    chiave = tmp_path / "chiavi" / "bottega_firma"

    with pytest.raises(ErroreFirma, match="user.email"):
        prepara(cartella=repo, chiave=chiave, globale=False)


def test_prepara_globale(tmp_path: Path) -> None:
    repo = _crea_repo(tmp_path, email="decisore@example.com")
    chiave = tmp_path / "chiavi" / "bottega_firma"

    prepara(cartella=repo, chiave=chiave, globale=True)

    def _cfg_global(k: str) -> str:
        res = subprocess.run(["git", "config", "--global", k], cwd=repo, check=True, capture_output=True, text=True)
        return res.stdout.strip()

    assert _cfg_global("gpg.format") == "ssh"
    assert _cfg_global("user.signingkey") == str(chiave) + ".pub"
    assert _cfg_global("commit.gpgsign") == "true"
    assert _cfg_global("tag.gpgsign") == "true"

    # La configurazione locale non deve contenerli
    res_local = subprocess.run(["git", "config", "--local", "gpg.format"], cwd=repo, capture_output=True)
    assert res_local.returncode != 0


def test_comando_verifica_avvisa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    repo = _crea_repo(tmp_path)
    monkeypatch.chdir(repo)

    chiave_alice, pub_alice = _crea_chiave(tmp_path, "alice")
    email_alice = "alice@example.com"
    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f"{email_alice} namespaces=\"git\" {pub_alice}\n", encoding="utf-8")

    _committa_firmato(repo, chiave_alice, "rilascio v1.0", email=email_alice)
    subprocess.run(["git", "tag", "v1.0"], cwd=repo, check=True, capture_output=True)

    # Caso 1: rifiuto -> apre avviso
    (repo / "f2.txt").write_text("unsigned\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "non firmato"], cwd=repo, check=True, capture_output=True)

    forgia = ForgiaFinta()
    parser = argparse.ArgumentParser()
    argomenti_firma(parser)
    args_rifiuto = parser.parse_args(["verifica", "--rilascio", "v1.0", "--avvisa"])

    codice_1 = comando_firma(args_rifiuto, forgia=forgia)
    assert codice_1 == 1
    out_1 = capsys.readouterr().out
    assert "firma: rifiutata: punta non firmata" in out_1
    assert any(
        ch == "avviso" and k == "firma" and "Avviso della bottega" in tit and mot == "punta non firmata"
        for ch, k, tit, mot in forgia.registro
    )

    # Caso 2: buona -> chiude avviso
    _committa_firmato(repo, chiave_alice, "nuovo commit firmato", nome_file="f3.txt", email=email_alice)
    args_buona = parser.parse_args(["verifica", "--rilascio", "v1.0", "--avvisa"])
    codice_2 = comando_firma(args_buona, forgia=forgia)
    assert codice_2 == 0
    out_2 = capsys.readouterr().out
    assert "firma: buona (alice@example.com," in out_2
    assert ("avviso", "firma", "Avviso della bottega: firma del ramo principale", None) in forgia.registro


def test_comando_firma_codici_d_uscita(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _crea_repo(tmp_path)
    monkeypatch.chdir(repo)

    parser = argparse.ArgumentParser()
    argomenti_firma(parser)

    # Errore sintassi argomenti (manca rilascio o primo): argparse solleva SystemExit con codice 2
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["verifica"])
    assert exc_info.value.code == 2

    # Prepara con successo: codice 0
    chiave = tmp_path / "chiavi" / "k"
    args_prepara = parser.parse_args(["prepara", "--chiave", str(chiave)])
    assert comando_firma(args_prepara) == 0

    # Prepara con errore (privata senza pubblica): codice 1
    Path(str(chiave) + ".pub").unlink()
    assert comando_firma(args_prepara) == 1


def test_prepara_non_copia_il_commento_della_chiave(tmp_path: Path) -> None:
    """Una chiave fatta prima col commento di serie (utente@macchina): il commento non entra in firme-ammesse."""
    repo = _crea_repo(tmp_path, email="decisore@example.com")
    chiave = tmp_path / "chiavi" / "vecchia"
    chiave.parent.mkdir(parents=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "utente@macchina-di-casa", "-f", str(chiave)],
        check=True,
        capture_output=True,
    )
    prepara(cartella=repo, chiave=chiave, globale=False)
    testo = (repo / ".github" / "bottega" / "firme-ammesse").read_text(encoding="utf-8")
    assert "utente@macchina-di-casa" not in testo
    assert testo.startswith('decisore@example.com namespaces="git" ssh-ed25519 ')


def test_verifica_parola_gpgsig_nel_messaggio(tmp_path: Path) -> None:
    """Un commit non firmato con «gpgsig» nel messaggio è «non firmato», non «chiave non ammessa»."""
    repo = _crea_repo(tmp_path)
    _, pub = _crea_chiave(tmp_path, "alice")
    firme = repo / ".github" / "bottega" / "firme-ammesse"
    firme.parent.mkdir(parents=True, exist_ok=True)
    firme.write_text(f'tester@example.com namespaces="git" {pub}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "gpgsig finto nel messaggio"], cwd=repo, check=True, capture_output=True)
    esito = verifica(clone=repo, punta="HEAD", primo=True)
    assert esito.buona is False
    assert esito.motivo == "punta non firmata"
