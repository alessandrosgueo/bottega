"""Prove per i comandi bottega installa, ferma, riparti, aggiorna (Compito B6.5)."""

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import subprocess
import pytest

from bottega.installa import (
    argomenti_aggiorna,
    argomenti_ferma,
    argomenti_installa,
    argomenti_riparti,
    comando_aggiorna,
    comando_ferma,
    comando_installa,
    comando_macchina,
    comando_progetto,
    comando_riparti,
    comando_runner,
)
from bottega.macchina import Esecutore
import bottega.__main__ as main_mod


class EsecutoreRegistratore:
    """Esecutore finto per simulare e registrare ogni chiamata di processo esterno."""

    def __init__(self, risposte: Mapping[str, tuple[int, str]] | None = None) -> None:
        self.risposte = dict(risposte or {})
        self.chiamate: list[tuple[tuple[str, ...], Mapping[str, str] | None]] = []

    def __call__(
        self,
        comando: Sequence[str],
        ambiente: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        cmd_tuple = tuple(comando)
        env_dict = dict(ambiente) if ambiente else None
        self.chiamate.append((cmd_tuple, env_dict))

        # Cerca corrispondenza su comando esatto o prefisso
        cmd_str = " ".join(comando)
        if cmd_str in self.risposte:
            return self.risposte[cmd_str]
        for prefisso, esito in self.risposte.items():
            if cmd_str.startswith(prefisso):
                return esito

        # Predefiniti generici per controlli comuni
        if len(comando) >= 2 and comando[0] == "systemctl" and comando[1] == "is-system-running":
            return 0, "running\n"
        if "is-active" in cmd_str or "is-enabled" in cmd_str:
            return 1, ""
        if "NeedDaemonReload" in cmd_str:
            return 1, ""
        if "test" in comando:
            return 1, ""
        if "stat -c" in cmd_str:
            return 1, ""
        if "id -gn" in cmd_str:
            return 1, ""
        if "sha256sum" in cmd_str and "curl" not in cmd_str:
            return 1, ""
        if "cmp" in cmd_str:
            return 1, ""
        if len(comando) >= 2 and comando[0] == "git" and "rev-parse" in comando:
            return 1, "fatal: not a valid object name\n"
        if len(comando) >= 2 and comando[0] == "git" and "ls-remote" in comando:
            return 0, ""
        if len(comando) >= 2 and comando[0] == "git" and "remote" in comando and "get-url" in comando:
            return 0, "https://github.com/owner/bottega.git\n"
        if len(comando) >= 2 and comando[0] == "gh" and "repo" in comando and "view" in comando:
            return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
        if len(comando) >= 2 and comando[0] == "gh" and ("commits" in cmd_str or "git/ref/tags" in cmd_str):
            return 0, f"commit {'1' * 40}\n"

        return 0, ""


def _parser_installa():
    import argparse
    p = argparse.ArgumentParser()
    argomenti_installa(p)
    return p


def _parser_ferma():
    import argparse
    p = argparse.ArgumentParser()
    argomenti_ferma(p)
    return p


def _parser_riparti():
    import argparse
    p = argparse.ArgumentParser()
    argomenti_riparti(p)
    return p


def _parser_aggiorna():
    import argparse
    p = argparse.ArgumentParser()
    argomenti_aggiorna(p)
    return p


def _crea_repo_git(cartella: Path) -> tuple[Path, Path]:
    """Crea una repo bare origin e un clone locale con commit iniziale."""
    origin = cartella / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)

    clone = cartella / "clone"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )

    docs = clone / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "costituzione.md").write_text("# Costituzione\nRegole.\n", encoding="utf-8")
    (clone / "test_base.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "commit iniziale"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)
    return origin, clone


_CONFIGURAZIONE_BASE = """versione = 1

[progetto]
comandanti = ["decisore"]
adattatore = "gh"
fuso = "Europe/Rome"
notte = "02:00"
manutenzione = ["01:00-02:00"]
project = 1

[botteghe.principale]
quota = "normale"
porte = ["claude-code"]

[candidati.principale]
nome = "Principale"
bottega = "principale"
porta = "claude-code"
modello = "claude-sonnet"
funzioni = ["decidere", "eseguire", "rivedere", "consigliare"]
runner = "bottega-runner"
"""


def test_macchina_senza_systemd(capsys: pytest.CaptureFixture[str]) -> None:
    """Senza systemd attivo, bottega installa macchina esce con codice 2 e cita /etc/wsl.conf."""
    esecutore = EsecutoreRegistratore(
        {"systemctl is-system-running": (1, "System has not been booted with systemd as init system\n")}
    )
    p = _parser_installa()
    args = p.parse_args(["macchina"])

    codice = comando_macchina(args, esegui=esecutore)
    assert codice == 2

    catturato = capsys.readouterr()
    assert "/etc/wsl.conf" in catturato.err or "/etc/wsl.conf" in catturato.out


def test_macchina_prova(capsys: pytest.CaptureFixture[str]) -> None:
    """Con --prova elenca i passi che farebbe ('farei:') senza eseguire comandi reali."""
    esecutore = EsecutoreRegistratore(
        {
            "systemctl is-system-running": (0, "running\n"),
            "getent group bottega": (1, ""),
            'sh -c [ "$(id -gn bottega-runner 2>/dev/null)" = bottega-runner ]': (1, ""),
            'sh -c [ "$(id -gn bottega-esecutore 2>/dev/null)" = bottega-esecutore ]': (1, ""),
        }
    )
    p = _parser_installa()
    args = p.parse_args(["macchina", "--prova"])

    codice = comando_macchina(args, esegui=esecutore)
    assert codice == 0

    catturato = capsys.readouterr()
    assert "farei: gruppo bottega" in catturato.out
    assert "farei: utente runner bottega-runner" in catturato.out
    assert "farei: utente esecutore bottega-esecutore" in catturato.out


def test_macchina_passo_fallito(capsys: pytest.CaptureFixture[str]) -> None:
    """Se un passo fallisce esce 1 e riporta il motivo dell'errore."""
    esecutore = EsecutoreRegistratore(
        {
            "systemctl is-system-running": (0, "running\n"),
            "getent group bottega": (1, ""),
            "sudo -n groupadd --system bottega": (1, "permesso negato nel creare il gruppo\n"),
        }
    )
    p = _parser_installa()
    args = p.parse_args(["macchina"])

    codice = comando_macchina(args, esegui=esecutore)
    assert codice == 1

    catturato = capsys.readouterr()
    assert "permesso negato nel creare il gruppo" in (catturato.err + catturato.out)


def test_runner_senza_sha_niente_download(capsys: pytest.CaptureFixture[str]) -> None:
    """Senza lo SHA valido nella release, non tenta il download ed esce 1."""
    release_senza_sha = json.dumps({"tag_name": "v2.320.0", "body": "Release senza marcatore SHA."})
    esecutore = EsecutoreRegistratore(
        {
            "gh api repos/actions/runner/releases/latest": (0, release_senza_sha),
        }
    )
    p = _parser_installa()
    args = p.parse_args(["runner", "--repo", "owner/repo", "--etichetta", "etichetta-1", "--nome", "runner-1"])

    codice = comando_runner(args, esegui=esecutore)
    assert codice == 1

    # Nessun comando curl per il download deve essere stato chiamato
    for cmd, _ in esecutore.chiamate:
        assert "curl" not in cmd

    catturato = capsys.readouterr()
    assert "sha" in (catturato.err + catturato.out).lower()


def test_runner_token_solo_nell_ambiente(capsys: pytest.CaptureFixture[str]) -> None:
    """Il token di registrazione è posto solo nell'ambiente del passo config.sh e mai stampato né negli argomenti."""
    sha_finto = "a" * 64
    body = f"<!-- BEGIN SHA linux-x64 -->\n{sha_finto}\n<!-- END SHA linux-x64 -->"
    release_json = json.dumps({"tag_name": "v2.320.0", "body": body})
    token_segreto = "TOKEN_REG_MOLTO_SEGRETO_xyz123"

    esecutore = EsecutoreRegistratore(
        {
            "gh api repos/actions/runner/releases/latest": (0, release_json),
            "gh api -X POST repos/owner/repo/actions/runners/registration-token --jq .token": (0, token_segreto + "\n"),
        }
    )
    p = _parser_installa()
    args = p.parse_args([
        "runner",
        "--repo", "owner/repo",
        "--etichetta", "etichetta-1",
        "--nome", "runner-1",
    ])

    codice = comando_runner(args, esegui=esecutore)
    assert codice == 0

    # 1. Il token non compare in nessun comando o argomento
    for cmd, _ in esecutore.chiamate:
        for arg in cmd:
            assert token_segreto not in arg

    # 2. Il token non compare in stdout o stderr
    catturato = capsys.readouterr()
    assert token_segreto not in catturato.out
    assert token_segreto not in catturato.err

    # 3. Il token è presente nell'ambiente del passo che invoca config.sh
    passi_config = [
        (cmd, env)
        for cmd, env in esecutore.chiamate
        if any("config.sh" in str(arg) for arg in cmd)
    ]
    assert len(passi_config) >= 1
    assert any(
        env and env.get("ACTIONS_RUNNER_INPUT_TOKEN") == token_segreto
        for _, env in passi_config
    )


def test_runner_prova_niente_token(capsys: pytest.CaptureFixture[str]) -> None:
    """Con --prova niente richiesta di token e niente download: solo righe farei:."""
    sha_finto = "b" * 64
    body = f"<!-- BEGIN SHA linux-x64 -->\n{sha_finto}\n<!-- END SHA linux-x64 -->"
    release_json = json.dumps({"tag_name": "v2.320.0", "body": body})

    esecutore = EsecutoreRegistratore(
        {
            "gh api repos/actions/runner/releases/latest": (0, release_json),
        }
    )
    p = _parser_installa()
    args = p.parse_args([
        "runner",
        "--repo", "owner/repo",
        "--etichetta", "etichetta-1",
        "--nome", "runner-1",
        "--prova",
    ])

    codice = comando_runner(args, esegui=esecutore)
    assert codice == 0

    # Nessuna chiamata per il registration-token
    assert not any("registration-token" in " ".join(cmd) for cmd, _ in esecutore.chiamate)

    catturato = capsys.readouterr()
    assert "farei:" in catturato.out


def test_progetto_ci_pericolosa_si_ferma(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Se la CI del progetto contiene rischi sui rami bottega/*, stampa i rischi ed esce 1."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    wf_dir = cartella / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "rischioso.yml").write_text(
        "on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ secrets.SUPER }}\n",
        encoding="utf-8",
    )
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore()
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 1

    catturato = capsys.readouterr()
    assert "secrets.SUPER" in (catturato.out + catturato.err)
    # Nessun branch o commit tentato
    assert not any("git" in cmd[0] for cmd, _ in esecutore.chiamate if cmd)


def test_progetto_prova_niente_scritto(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Con --prova stampa i file che scriverebbe e i campi che creerebbe, senza scrivere nulla."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    query_user_resp = json.dumps({
        "data": {
            "user": {
                "projectV2": {
                    "id": "PROJ_123",
                    "fields": {"nodes": []},
                }
            }
        }
    })
    esecutore = EsecutoreRegistratore(
        {
            "gh api graphql": (0, query_user_resp),
        }
    )
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
        "--prova",
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 0

    catturato = capsys.readouterr()
    # Verifica che siano elencati i file che verrebbero scritti e i campi mancanti
    assert ".github/bottega/bottega.toml" in catturato.out
    assert "Bottega" in catturato.out
    assert "Esito" in catturato.out

    # Nessun file nuovo scritto su disco (tranne la configurazione preparata)
    assert not (cartella / ".github" / "bottega" / "bottega.toml").exists()
    assert not (cartella / "AGENTS.md").exists()


def test_progetto_ramo_gia_presente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Se il ramo bottega/installazione esiste già, esce con codice 1."""
    origin, clone = _crea_repo_git(tmp_path)
    # Crea il ramo bottega/installazione
    subprocess.run(["git", "branch", "bottega/installazione"], cwd=str(clone), check=True)

    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    def esecutore_git(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_git)
    assert codice == 1

    catturato = capsys.readouterr()
    assert "bottega/installazione" in (catturato.err + catturato.out)


def test_progetto_completo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Installazione completa su repo git veri: committa solo i file preparati, apre PR e imposta segreto."""
    origin, clone = _crea_repo_git(tmp_path)

    # Aggiunge un file non tracciato che NON deve entrare nel commit
    file_estraneo = clone / "non_preparato.txt"
    file_estraneo.write_text("estraneo", encoding="utf-8")

    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    query_user_resp = json.dumps({
        "data": {
            "user": {
                "projectV2": {
                    "id": "PROJ_123",
                    "fields": {"nodes": []},
                }
            }
        }
    })

    pipe_chiamate: list[tuple[list[str], list[str]]] = []

    def pipe_finta(cmd1: list[str], cmd2: list[str]) -> int:
        pipe_chiamate.append((cmd1, cmd2))
        return 0

    def esecutore_completo(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "graphql" in cmd_l:
                return 0, query_user_resp
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {'1' * 40}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/101\n"
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_completo, esegui_pipe=pipe_finta)
    assert codice == 0

    # Verifica i file inclusi nell'ultimo commit di bottega/installazione
    out_files = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "bottega/installazione"],
        cwd=str(clone),
        text=True,
    ).splitlines()

    assert "non_preparato.txt" not in out_files
    assert ".github/bottega/bottega.toml" in out_files
    assert ".github/workflows/bottega-distributore.yml" in out_files
    assert ".github/workflows/bottega-esecutore-principale.yml" in out_files
    assert "AGENTS.md" in out_files

    # Verifica che la pipe del segreto sia stata chiamata
    assert len(pipe_chiamate) == 1
    assert "BOTTEGA_TOKEN" in pipe_chiamate[0][1]



def test_progetto_senza_segreto(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Con --senza-segreto la PR si apre lo stesso, la pipe del segreto non parte e il comando da lanciare sulla
    macchina del runner è stampato (senza alcun token)."""
    origin, clone = _crea_repo_git(tmp_path)

    # Aggiunge un file non tracciato che NON deve entrare nel commit
    file_estraneo = clone / "non_preparato.txt"
    file_estraneo.write_text("estraneo", encoding="utf-8")

    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    query_user_resp = json.dumps({
        "data": {
            "user": {
                "projectV2": {
                    "id": "PROJ_123",
                    "fields": {"nodes": []},
                }
            }
        }
    })

    pipe_chiamate: list[tuple[list[str], list[str]]] = []

    def pipe_finta(cmd1: list[str], cmd2: list[str]) -> int:
        pipe_chiamate.append((cmd1, cmd2))
        return 0

    def esecutore_completo(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "graphql" in cmd_l:
                return 0, query_user_resp
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {'1' * 40}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/101\n"
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
        "--senza-segreto",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_completo, esegui_pipe=pipe_finta)
    assert codice == 0

    assert pipe_chiamate == []
    uscita = capsys.readouterr().out
    assert "gh auth token | gh secret set BOTTEGA_TOKEN --repo owner/repo" in uscita
    assert "sudo -u bottega-runner -H" in uscita

def test_ferma_e_riparti(capsys: pytest.CaptureFixture[str]) -> None:
    """Verifica comandi bottega ferma e bottega riparti con output di una riga per workflow."""
    wf_attivi = json.dumps([
        {"path": ".github/workflows/bottega-distributore.yml", "state": "active"},
        {"path": ".github/workflows/bottega-esecutore-principale.yml", "state": "active"},
        {"path": ".github/workflows/ci.yml", "state": "active"},
    ])
    wf_spenti = json.dumps([
        {"path": ".github/workflows/bottega-distributore.yml", "state": "disabled_manually"},
        {"path": ".github/workflows/bottega-esecutore-principale.yml", "state": "disabled_manually"},
        {"path": ".github/workflows/ci.yml", "state": "active"},
    ])
    cmd_wf_list = "gh workflow list --all --limit 200 --repo owner/repo --json path,state"
    esecutore = EsecutoreRegistratore(
        {
            cmd_wf_list: (0, wf_attivi),
        }
    )

    p_f = _parser_ferma()
    args_f = p_f.parse_args(["--repo", "owner/repo"])
    codice_f = comando_ferma(args_f, esegui=esecutore)
    assert codice_f == 0

    catturato_f = capsys.readouterr()
    assert "bottega-distributore.yml" in catturato_f.out
    assert "bottega-esecutore-principale.yml" in catturato_f.out
    assert "ci.yml" not in catturato_f.out

    # Riparti
    esecutore.risposte[cmd_wf_list] = (0, wf_spenti)
    p_r = _parser_riparti()
    args_r = p_r.parse_args(["--repo", "owner/repo"])
    codice_r = comando_riparti(args_r, esegui=esecutore)
    assert codice_r == 0

    catturato_r = capsys.readouterr()
    assert "bottega-distributore.yml" in catturato_r.out
    assert "bottega-esecutore-principale.yml" in catturato_r.out
    assert "ci.yml" not in catturato_r.out


def test_g5_nessun_workflow_e_un_errore(capsys: pytest.CaptureFixture[str]) -> None:
    # comando_ferma e comando_riparti escono 1 con errore: nessun workflow bottega-*.yml in <repo> se l'elenco è vuoto.
    esecutore = EsecutoreRegistratore(
        {
            "gh workflow list --all --limit 200 --repo owner/repo --json path,state": (0, "[]"),
        }
    )
    p_f = _parser_ferma()
    args_f = p_f.parse_args(["--repo", "owner/repo"])
    codice_f = comando_ferma(args_f, esegui=esecutore)
    assert codice_f == 1
    catturato_f = capsys.readouterr()
    assert "errore: nessun workflow bottega-*.yml in owner/repo" in catturato_f.err

    p_r = _parser_riparti()
    args_r = p_r.parse_args(["--repo", "owner/repo"])
    codice_r = comando_riparti(args_r, esegui=esecutore)
    assert codice_r == 1
    catturato_r = capsys.readouterr()
    assert "errore: nessun workflow bottega-*.yml in owner/repo" in catturato_r.err


def test_g5_gia_nello_stato_giusto_non_e_un_errore(capsys: pytest.CaptureFixture[str]) -> None:
    """Un secondo ferma (tutto già spento) e un secondo riparti (tutto già acceso) escono 0 senza toccare niente."""
    spenti = json.dumps([{"path": ".github/workflows/bottega-distributore.yml", "state": "disabled_manually"}])
    accesi = json.dumps([{"path": ".github/workflows/bottega-distributore.yml", "state": "active"}])
    elenco = "gh workflow list --all --limit 200 --repo owner/repo --json path,state"

    esecutore_f = EsecutoreRegistratore({elenco: (0, spenti)})
    assert comando_ferma(_parser_ferma().parse_args(["--repo", "owner/repo"]), esegui=esecutore_f) == 0
    assert "già spenti" in capsys.readouterr().out
    assert not any("disable" in " ".join(c) for c, *_ in esecutore_f.chiamate)

    esecutore_r = EsecutoreRegistratore({elenco: (0, accesi)})
    assert comando_riparti(_parser_riparti().parse_args(["--repo", "owner/repo"]), esegui=esecutore_r) == 0
    assert "già accesi" in capsys.readouterr().out
    assert not any("enable" in " ".join(c) for c, *_ in esecutore_r.chiamate)



def test_aggiorna(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Aggiorna i workflow chiamanti, crea ramo, committa, spinge e apre la PR in bozza."""
    origin, clone = _crea_repo_git(tmp_path)
    wf_dir = clone / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_dist = wf_dir / "bottega-distributore.yml"
    wf_dist.write_text(
        "uses: sorgente/bottega/.github/workflows/distributore.yml@1111111111111111111111111111111111111111\n"
        "with:\n"
        "  bottega_ref: v0.1.0\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True)
    subprocess.run(["git", "commit", "-m", "aggiungi distributore"], cwd=str(clone), check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True)

    nuovo_sha = "2" * 40

    def esecutore_aggiorna(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {nuovo_sha}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/202\n"
        return 0, ""

    p = _parser_aggiorna()
    args = p.parse_args([
        "--repo", "owner/repo",
        "--tag", "v0.2.0",
        "--bottega", "sorgente/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_aggiorna(args, esegui=esecutore_aggiorna)
    assert codice == 0

    # Verifica file aggiornato su disco
    testo_aggiornato = wf_dist.read_text(encoding="utf-8")
    assert f"@{nuovo_sha} # v0.2.0" in testo_aggiornato
    assert f"bottega_ref: {nuovo_sha}" in testo_aggiornato

    # Verifica ramo creato e presente
    rami = subprocess.check_output(["git", "branch"], cwd=str(clone), text=True)
    assert "bottega/aggiorna-v0.2.0" in rami



def test_progetto_valore_non_sovrascrive_la_bottega(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Tentare di sovrascrivere proprietario, tag o sha tramite --valore produce uscita 2 e nessun file scritto."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore()
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--valore", "sha=" + ("a" * 40),
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "sha viene dal repo della bottega, non da --valore" in catturato.err
    # Nessun file scritto oltre a bottega.toml
    assert list(cartella.iterdir()) == [cfg_file]


@pytest.mark.parametrize("tag_cattivo", ["v1\nx", "../x"])
def test_progetto_tag_non_valido(tmp_path: Path, tag_cattivo: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Un tag con ritorni a capo o tentativi di traversal causa uscita 2 senza alcuna chiamata a gh."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore()
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", tag_cattivo,
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "tag non valido" in catturato.err
    # Nessuna chiamata a gh
    assert not any(cmd[0] == "gh" for cmd, _ in esecutore.chiamate)


@pytest.mark.parametrize("risposta_gh", [(1, "Not Found\n"), (0, "pippo\n")])
def test_progetto_senza_sha_si_ferma(
    tmp_path: Path,
    risposta_gh: tuple[int, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Se il recupero dello SHA fallisce o non restituisce 40 cifre hex, esce 1 senza scrivere rami né file."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore({
        "gh api repos/owner/bottega/git/ref/tags/v1.0.0 --jq .object.type + \" \" + .object.sha": risposta_gh,
    })
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 1
    catturato = capsys.readouterr()
    assert "non trovo lo SHA del tag" in catturato.err
    # Nessun ramo creato (nessun switch)
    assert not any("switch" in cmd for cmd, _ in esecutore.chiamate)
    # Nessun file scritto
    assert list(cartella.iterdir()) == [cfg_file]


def test_progetto_bottega_dal_suo_clone(tmp_path: Path) -> None:
    """Senza --bottega, l'origin viene prelevato dalla radice della bottega e mai dalla cartella del progetto."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    from bottega.installa import _RADICE_BOTTEGA

    esecutore = EsecutoreRegistratore({
        f"git -C {str(_RADICE_BOTTEGA)} remote get-url origin": (0, "https://github.com/proprietario/bottega.git\n"),
    })
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--prova",
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 0

    chiamate_cmd = [cmd for cmd, _ in esecutore.chiamate]
    # Ha interrogato la radice della bottega
    assert any(cmd == ("git", "-C", str(_RADICE_BOTTEGA), "remote", "get-url", "origin") for cmd in chiamate_cmd)
    # Non ha MAI fatto remote get-url sulla cartella del progetto
    assert not any("remote" in cmd and "get-url" in cmd and str(cartella) in cmd for cmd in chiamate_cmd)


def test_progetto_repo_bottega_con_altro_nome(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Se il repo della bottega ha un nome diverso da 'bottega' (es. o/officina), esce 2."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore()
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "o/officina",
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "o/officina" in catturato.err


def test_progetto_workflow_puntano_alla_bottega(tmp_path: Path) -> None:
    """I workflow chiamanti nel commit del ramo bottega/installazione contengono uses e bottega_ref corretti."""
    origin, clone = _crea_repo_git(tmp_path)
    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    sha_finto = "a" * 40

    def pipe_finta(cmd1: list[str], cmd2: list[str]) -> int:
        return 0

    def esecutore_finto(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "graphql" in cmd_l:
                return 0, json.dumps({"data": {"user": {"projectV2": {"id": "P_1", "fields": {"nodes": []}}}}})
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {sha_finto}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/1\n"
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v2.0.0",
        "--bottega", "o/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_finto, esegui_pipe=pipe_finta)
    assert codice == 0

    testo_wf = subprocess.check_output(
        ["git", "show", "bottega/installazione:.github/workflows/bottega-esecutore-principale.yml"],
        cwd=str(clone),
        text=True,
    )
    assert f"uses: o/bottega/.github/workflows/esecutore.yml@{sha_finto} # v2.0.0" in testo_wf
    assert f"bottega_ref: {sha_finto}" in testo_wf


def test_progetto_esecutore_senza_pipe_si_ferma(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Se viene passato un esecutore iniettato senza esegui_pipe, esce 1 e nessun comando sudo viene lanciato."""
    origin, clone = _crea_repo_git(tmp_path)
    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    chiamate_cmd: list[list[str]] = []

    def esecutore_finto(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        chiamate_cmd.append(cmd_l)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "graphql" in cmd_l:
                return 0, json.dumps({"data": {"user": {"projectV2": {"id": "P_1", "fields": {"nodes": []}}}}})
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {'1' * 40}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/1\n"
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_finto, esegui_pipe=None)
    assert codice == 1
    catturato = capsys.readouterr()
    assert "con un esecutore iniettato serve anche la sua pipe" in catturato.err
    # Nessun sudo lanciato
    assert not any("sudo" in cmd for cmd in chiamate_cmd)


def test_aggiorna_bottega_dal_suo_clone(tmp_path: Path) -> None:
    """Senza --bottega, comando_aggiorna legge l'origin dalla radice della bottega e mai dalla cartella del progetto."""
    origin, clone = _crea_repo_git(tmp_path)
    wf_dir = clone / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "bottega-distributore.yml").write_text(
        "uses: o/bottega/.github/workflows/distributore.yml@1111111111111111111111111111111111111111\n"
        "with:\n  bottega_ref: v0.1.0\n",
        encoding="utf-8",
    )

    from bottega.installa import _RADICE_BOTTEGA

    esecutore = EsecutoreRegistratore({
        f"git -C {str(_RADICE_BOTTEGA)} remote get-url origin": (0, "https://github.com/o/bottega.git\n"),
        "gh api repos/o/bottega/git/ref/tags/v0.2.0 --jq .object.type + \" \" + .object.sha": (0, f"commit {'2' * 40}\n"),
    })
    p = _parser_aggiorna()
    args = p.parse_args([
        "--repo", "owner/repo",
        "--tag", "v0.2.0",
        "--prova",
    ])
    setattr(args, "cartella", clone)

    codice = comando_aggiorna(args, esegui=esecutore)
    assert codice == 0

    chiamate_cmd = [cmd for cmd, _ in esecutore.chiamate]
    assert any(cmd == ("git", "-C", str(_RADICE_BOTTEGA), "remote", "get-url", "origin") for cmd in chiamate_cmd)
    assert not any("remote" in cmd and "get-url" in cmd and str(clone) in cmd for cmd in chiamate_cmd)


@pytest.mark.parametrize("tag_cattivo", ["v1\nx", "../x"])
def test_aggiorna_tag_non_valido(tmp_path: Path, tag_cattivo: str, capsys: pytest.CaptureFixture[str]) -> None:
    """In comando_aggiorna un tag non valido esce 2 senza interrogare gh."""
    esecutore = EsecutoreRegistratore()
    p = _parser_aggiorna()
    args = p.parse_args([
        "--repo", "owner/repo",
        "--tag", tag_cattivo,
    ])
    setattr(args, "cartella", tmp_path)

    codice = comando_aggiorna(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "tag non valido" in catturato.err
    assert not any(cmd[0] == "gh" for cmd, _ in esecutore.chiamate)


def test_progetto_solo_sessione(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Con --solo-sessione la PR ha solo bottega.toml, crea campi del Project, nessuna chiamata a segreto né a commits."""
    origin, clone = _crea_repo_git(tmp_path)
    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    pipe_chiamate: list[tuple[list[str], list[str]]] = []
    gh_chiamate: list[list[str]] = []

    def pipe_finta(cmd1: list[str], cmd2: list[str]) -> int:
        pipe_chiamate.append((cmd1, cmd2))
        return 0

    def esecutore_solo_sessione(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            gh_chiamate.append(cmd_l)
            if "graphql" in cmd_l:
                return 0, json.dumps({"data": {"user": {"projectV2": {"id": "P_1", "fields": {"nodes": []}}}}})
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/1\n"
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--solo-sessione",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_solo_sessione, esegui_pipe=pipe_finta)
    assert codice == 0

    out_files = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "bottega/installazione"],
        cwd=str(clone),
        text=True,
    ).splitlines()
    assert out_files == [".github/bottega/bottega.toml"]

    assert not any("workflows" in f for f in out_files)
    assert len(pipe_chiamate) == 0
    assert not any("commits" in " ".join(cmd) for cmd in gh_chiamate)
    catturato = capsys.readouterr()
    assert "creato campo: Bottega" in catturato.out


def test_progetto_include_le_firme_ammesse(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Se presente .github/bottega/firme-ammesse entra nel commit; con --prova stampa includerei: .github/bottega/firme-ammesse."""
    origin, clone = _crea_repo_git(tmp_path)
    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    firme_dir = clone / ".github" / "bottega"
    firme_dir.mkdir(parents=True, exist_ok=True)
    firme_file = firme_dir / "firme-ammesse"
    firme_file.write_text("chiave-ammessa-123\n", encoding="utf-8")

    def esecutore_firme(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "graphql" in cmd_l:
                return 0, json.dumps({"data": {"user": {"projectV2": {"id": "P_1", "fields": {"nodes": []}}}}})
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
            if "git/ref/tags" in " ".join(cmd_l) or "commits" in " ".join(cmd_l):
                return 0, f"commit {'1' * 40}\n"
            if "pr" in cmd_l and "create" in cmd_l:
                return 0, "https://github.com/owner/repo/pull/1\n"
        return 0, ""

    p = _parser_installa()
    # 1. Con --prova
    args_prova = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
        "--prova",
    ])
    setattr(args_prova, "cartella", clone)
    codice_prova = comando_progetto(args_prova, esegui=esecutore_firme)
    assert codice_prova == 0
    catturato_prova = capsys.readouterr()
    assert "includerei: .github/bottega/firme-ammesse" in catturato_prova.out

    # 2. Esecuzione reale: il file non tracciato entra nel commit
    args_vero = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args_vero, "cartella", clone)
    codice_vero = comando_progetto(args_vero, esegui=esecutore_firme, esegui_pipe=lambda c1, c2: 0)
    assert codice_vero == 0

    out_files = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "bottega/installazione"],
        cwd=str(clone),
        text=True,
    ).splitlines()
    assert ".github/bottega/firme-ammesse" in out_files


def test_progetto_ci_del_ramo_principale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Un workflow pericoloso presente solo in origin/<ramo_principale> (albero di lavoro pulito) causa uscita 1."""
    origin, clone = _crea_repo_git(tmp_path)

    # Workflow pericoloso sul ramo remoto
    wf_dir = clone / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_file = wf_dir / "pericoloso.yml"
    wf_file.write_text(
        "name: pericolo\n"
        "on: [push]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ${{ secrets.SUPER }}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True)
    subprocess.run(["git", "commit", "-m", "workflow pericoloso remoto"], cwd=str(clone), check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True)

    # Pulizia albero di lavoro locale
    subprocess.run(["git", "rm", ".github/workflows/pericoloso.yml"], cwd=str(clone), check=True)
    subprocess.run(["git", "commit", "-m", "pulisci albero locale"], cwd=str(clone), check=True)

    assert not wf_file.exists()

    cfg_file = clone / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    def esecutore_git(cmd: Sequence[str], env: Mapping[str, str] | None = None) -> tuple[int, str]:
        cmd_l = list(cmd)
        if cmd_l[0] == "git":
            res = subprocess.run(cmd_l, capture_output=True, text=True, cwd=str(clone))
            return res.returncode, res.stdout + res.stderr
        if cmd_l[0] == "gh":
            if "repo" in cmd_l and "view" in cmd_l:
                return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
        return 0, ""

    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "v1.0.0",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", clone)

    codice = comando_progetto(args, esegui=esecutore_git)
    assert codice == 1

    catturato = capsys.readouterr()
    assert "secrets.SUPER" in (catturato.out + catturato.err)


def test_runner_architettura_sconosciuta(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Su architettura sconosciuta _architettura_di_serie restituisce None e comando_runner esce 2 con usa --arch."""
    import platform
    from bottega.installa import _architettura_di_serie

    monkeypatch.setattr(platform, "machine", lambda: "riscv64")
    assert _architettura_di_serie() is None

    esecutore = EsecutoreRegistratore()
    p = _parser_installa()
    args = p.parse_args([
        "runner",
        "--repo", "owner/repo",
        "--etichetta", "etichetta-1",
        "--nome", "runner-1",
    ])

    codice = comando_runner(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "architettura sconosciuta, usa --arch" in catturato.err


@pytest.mark.parametrize(
    ("url", "atteso"),
    [
        ("https://codeberg.org/o/bottega.git", None),
        ("git" + "@gitlab.com:o/bottega.git", None),
        ("ssh://git" + "@gitlab.com/o/bottega", None),
        ("/ho" + "me/utente/bottega", None),
        ("https://github.com/o/bottega", "o/bottega"),
        ("https://github.com/o/bottega.git", "o/bottega"),
        ("git" + "@github.com:o/bottega.git", "o/bottega"),
        ("ssh://git" + "@github.com/o/bottega", "o/bottega"),
    ],
)
def test_g8_origin_non_github(url: str, atteso: str | None) -> None:
    """G8: _estrai_owner_repo accetta solo origin GitHub, altri host o cartelle locali restituiscono None."""
    from bottega.installa import _estrai_owner_repo
    assert _estrai_owner_repo(url) == atteso


def test_m2_tag_annotato_seguito() -> None:
    """M2: _sha_del_tag segue un tag annotato (tipo 'tag') fino al commit sottostante."""
    from bottega.installa import _sha_del_tag
    sha_tag = "a" * 40
    sha_commit = "b" * 40
    esecutore = EsecutoreRegistratore({
        "gh api repos/o/bottega/git/ref/tags/v1.0.0 --jq .object.type + \" \" + .object.sha": (0, f"tag {sha_tag}\n"),
        f"gh api repos/o/bottega/git/tags/{sha_tag} --jq .object.type + \" \" + .object.sha": (0, f"commit {sha_commit}\n"),
    })
    sha = _sha_del_tag(esecutore, "o/bottega", "v1.0.0")
    assert sha == sha_commit


def test_m2_ramo_non_e_un_tag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """M2: un ramo non è un tag; se git/ref/tags fallisce esce 1 e non chiama mai commits/."""
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(_CONFIGURAZIONE_BASE, encoding="utf-8")

    esecutore = EsecutoreRegistratore({
        "gh api repos/owner/bottega/git/ref/tags/main --jq .object.type + \" \" + .object.sha": (1, "Not Found\n"),
    })
    p = _parser_installa()
    args = p.parse_args([
        "progetto",
        "--repo", "owner/repo",
        "--project", "1",
        "--configurazione", str(cfg_file),
        "--tag", "main",
        "--bottega", "owner/bottega",
    ])
    setattr(args, "cartella", cartella)

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 1
    catturato = capsys.readouterr()
    assert "non trovo lo SHA del tag main" in catturato.err
    assert not any("commits/" in " ".join(cmd) for cmd, _ in esecutore.chiamate)


def test_m13_runner_argomenti_storti_prima_del_token(capsys: pytest.CaptureFixture[str]) -> None:
    """M13: se gli argomenti del runner sono invalidi, esce 2 e non chiede mai il registration-token."""
    esecutore = EsecutoreRegistratore({
        "gh api repos/actions/runner/releases/latest": (
            0,
            json.dumps({"tag_name": "v2.320.0", "body": f"<!-- BEGIN SHA linux-x64 -->{'0' * 64}<!-- END SHA linux-x64 -->"}),
        ),
    })
    p = _parser_installa()
    args = p.parse_args([
        "runner",
        "--repo", "owner/repo",
        "--etichetta", "etichetta",
        "--nome", "nome/storto",
    ])

    codice = comando_runner(args, esegui=esecutore)
    assert codice == 2
    catturato = capsys.readouterr()
    assert "nome del runner non valido" in catturato.err
    assert not any("registration-token" in " ".join(cmd) for cmd, _ in esecutore.chiamate)


def test_runner_gh_del_runner(capsys: pytest.CaptureFixture[str]) -> None:
    """Con --gh-del-runner la release e il token di registrazione passano dal gh del runner (sudo -u <runner>), mai
    dal gh di chi installa; il token resta solo nell'ambiente di config.sh."""
    sha_finto = "a" * 64
    body = f"<!-- BEGIN SHA linux-x64 -->\n{sha_finto}\n<!-- END SHA linux-x64 -->"
    release_json = json.dumps({"tag_name": "v2.320.0", "body": body})
    token_segreto = "TOKEN_DEL_RUNNER_xyz"
    via = "sudo -n -u bottega-runner -H gh"
    esecutore = EsecutoreRegistratore(
        {
            f"{via} api repos/actions/runner/releases/latest": (0, release_json),
            f"{via} api -X POST repos/owner/repo/actions/runners/registration-token --jq .token": (0, token_segreto),
        }
    )
    args = _parser_installa().parse_args(
        ["runner", "--repo", "owner/repo", "--etichetta", "e", "--nome", "n", "--gh-del-runner"]
    )
    assert comando_runner(args, esegui=esecutore) == 0
    comandi = [" ".join(cmd) for cmd, _ in esecutore.chiamate]
    assert any(c.startswith(f"{via} api -X POST") for c in comandi)
    assert not any(c.startswith("gh ") for c in comandi)
    assert all(token_segreto not in c for c in comandi)
    catturato = capsys.readouterr()
    assert token_segreto not in catturato.out + catturato.err
