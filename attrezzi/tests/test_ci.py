"""Prove del controllo della CI del progetto sui rami `bottega/*`."""

import subprocess
from pathlib import Path

import pytest

from bottega.__main__ import main
from bottega.ci import Rischio, rischi, rischi_del_ramo

BASE_CONFIG = """versione = 1

[progetto]
fuso = "Europe/Rome"

[botteghe.principale]
quota = "scarsa"
porte = ["claude-code"]

[candidati.maestro]
nome = "Maestro <modello forte>"
bottega = "principale"
porta = "claude-code"
modello = "<modello forte>"
funzioni = ["decidere", "rivedere"]
"""


def test_push_senza_filtri():
    pericoloso = """
name: test
on:
  push:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.CHIAVE }}
"""
    sicuro = """
name: test
on:
  push:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert r_pericolo[0].file == "pericolo.yml"
    assert "push" in r_pericolo[0].motivo and "secrets.CHIAVE" in r_pericolo[0].motivo

    assert rischi({"sicuro.yml": sicuro}) == []


def test_on_push_stringa():
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "push" in r_pericolo[0].motivo and "secrets.DEPLOY_KEY" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_on_lista():
    pericoloso = """
name: test
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    sicuro = """
name: test
on: [workflow_dispatch]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert rischi({"sicuro.yml": sicuro}) == []


def test_on_lista_a_trattini():
    pericoloso = """
name: test
on:
  - push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    sicuro = """
name: test
on:
  - workflow_dispatch
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert rischi({"sicuro.yml": sicuro}) == []


def test_branches_ignore_con_bottega_sicuro():
    sicuro = """
name: test
on:
  push:
    branches-ignore:
      - 'bottega/**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    pericoloso = """
name: test
on:
  push:
    branches-ignore:
      - 'feature/**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1


def test_branches_ignore_senza_bottega():
    pericoloso = """
name: test
on:
  push:
    branches-ignore:
      - 'main'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    sicuro = """
name: test
on:
  push:
    branches-ignore:
      - 'bottega/*'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert rischi({"sicuro.yml": sicuro}) == []


def test_branches_solo_main_sicuro():
    sicuro = """
name: test
on:
  push:
    branches:
      - 'main'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    pericoloso = """
name: test
on:
  push:
    branches:
      - 'main'
      - 'bottega/**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1


def test_branches_doppio_asterisco():
    pericoloso = """
name: test
on:
  push:
    branches:
      - '**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    sicuro = """
name: test
on:
  push:
    branches:
      - '*'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert rischi({"sicuro.yml": sicuro}) == []


def test_branches_con_esclusione_sicuro():
    sicuro = """
name: test
on:
  push:
    branches:
      - '**'
      - '!bottega/**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    pericoloso = """
name: test
on:
  push:
    branches:
      - '**'
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1


def test_pull_request_senza_guardia():
    pericoloso = """
name: test
on:
  pull_request:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    sicuro = """
name: test
on:
  pull_request:
jobs:
  build:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "pull_request" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_pull_request_con_guardia_in_ogni_job_sicuro():
    sicuro = """
name: test
on:
  pull_request:
jobs:
  job1:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
  job2:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.BAR }}
"""
    pericoloso = """
name: test
on:
  pull_request:
jobs:
  job1:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
  job2:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.BAR }}
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1


def test_pull_request_guardia_in_un_job_solo():
    pericoloso = """
name: test
on:
  pull_request:
jobs:
  job1:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
  job2:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.BAR }}
"""
    sicuro = """
name: test
on:
  pull_request:
jobs:
  job1:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.FOO }}
  job2:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.BAR }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert rischi({"sicuro.yml": sicuro}) == []


def test_pull_request_target():
    pericoloso = """
name: test
on:
  pull_request_target:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.GITHUB_TOKEN }}
"""
    sicuro = """
name: test
on:
  pull_request_target:
jobs:
  build:
    if: "!startsWith(github.head_ref, 'bottega/')"
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.GITHUB_TOKEN }}
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "pull_request_target" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_secrets_inherit():
    pericoloso = """
name: test
on: push
jobs:
  call:
    uses: owner/repo/.github/workflows/reusable.yml@main
    secrets: inherit
"""
    # Il gemello sicuro chiama il riusabile solo a mano: su push lo stesso job è un rischio (il chiamato non si vede).
    sicuro = """
name: test
on: workflow_dispatch
jobs:
  call:
    uses: owner/repo/.github/workflows/reusable.yml@main
    secrets: inherit
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "secrets: inherit" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_runs_on_self_hosted_lista():
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: [self-hosted, linux]
    steps:
      - run: echo ok
"""
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: [ubuntu-latest]
    steps:
      - run: echo ok
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "self-hosted" in r_pericolo[0].motivo or "non GitHub" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_runs_on_etichetta_strana():
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: gpu-runner
    steps:
      - run: echo ok
"""
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - run: echo ok
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "gpu-runner" in r_pericolo[0].motivo or "non GitHub" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_runs_on_espressione():
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: ${{ matrix.os }}
    steps:
      - run: echo ok
"""
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "espressione" in r_pericolo[0].motivo
    assert rischi({"sicuro.yml": sicuro}) == []


def test_niente_da_dare_sicuro():
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - run: echo "nessun segreto, runner github standard"
"""
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - run: echo ${{ secrets.DEPLOY_KEY }}
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1


def test_commenti_e_apici():
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # secrets.FALSO_POSITIVO non conta perché è commento
      - run: echo "# non commento"
"""
    pericoloso = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "secrets.DEPLOY_KEY" # secrets.ALTRO non conta
"""
    assert rischi({"sicuro.yml": sicuro}) == []
    r_pericolo = rischi({"pericolo.yml": pericoloso})
    assert len(r_pericolo) == 1
    assert "secrets.DEPLOY_KEY" in r_pericolo[0].motivo


def test_ancora_yaml_e_dubbio():
    ancora = """
name: test
.base: &base
  runs-on: ubuntu-latest
on: push
jobs:
  build:
    <<: *base
    steps:
      - run: echo ok
"""
    flusso = """
name: test
on: {
  push
}
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
    sicuro = """
name: test
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
    r_ancora = rischi({"ancora.yml": ancora})
    assert len(r_ancora) == 1
    assert "ancor" in r_ancora[0].motivo or "dubbio" in r_ancora[0].motivo or "non supportat" in r_ancora[0].motivo

    r_flusso = rischi({"flusso.yml": flusso})
    assert len(r_flusso) == 1
    assert "flusso" in r_flusso[0].motivo or "multilinea" in r_flusso[0].motivo

    assert rischi({"sicuro.yml": sicuro}) == []


def test_rischi_del_ramo(tmp_path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    cartella = tmp_path / ".github" / "workflows"
    cartella.mkdir(parents=True)
    (cartella / "sicuro.yml").write_text("""
name: sicuro
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)

    # Workflow pericoloso solo nell'albero di lavoro (non tracciato o non in refs/remotes/origin/main)
    (cartella / "pericolo.yml").write_text("""
name: pericolo
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.TOKEN }}
""", encoding="utf-8")

    # Non conta perché non è nel ramo remoto
    assert rischi_del_ramo(tmp_path, "main") == []

    # Se aggiunto al ramo remoto, conta
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "aggiungi pericolo"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)

    trovati = rischi_del_ramo(tmp_path, "main")
    assert len(trovati) == 1
    assert trovati[0].file == ".github/workflows/pericolo.yml"


def test_comando_configurazione_avvisa(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cartella_b = tmp_path / ".github" / "bottega"
    cartella_b.mkdir(parents=True)
    (cartella_b / "bottega.toml").write_text(BASE_CONFIG, encoding="utf-8")

    cartella_wf = tmp_path / ".github" / "workflows"
    cartella_wf.mkdir(parents=True)
    (cartella_wf / "ci.yml").write_text("""
name: ci
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.TOKEN }}
""", encoding="utf-8")

    assert main(["configurazione"]) == 1
    out = capsys.readouterr().out
    assert "avviso: .github/workflows/ci.yml:" in out

    # Caso gemello sicuro
    (cartella_wf / "ci.yml").write_text("""
name: ci
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""", encoding="utf-8")
    assert main(["configurazione"]) == 0
    out_sicuro = capsys.readouterr().out
    assert "avviso:" not in out_sicuro
    assert "nessun errore" in out_sicuro


def test_chiama_workflow_riusabile_locale_e_esterno() -> None:
    """Dalla revisione del maestro: un job che chiama un workflow riusabile non mostra runs-on né segreti, ma il
    chiamato può averli (il caso di Jarvis: sviluppo.yml chiama prove.yml, che gira sul runner self-hosted)."""
    locale = "on: push\njobs:\n  prove:\n    uses: ./.github/workflows/prove.yml\n"
    esterno = "on: push\njobs:\n  prove:\n    uses: org/repo/.github/workflows/x.yml@v1\n"
    azione = (
        "on: push\njobs:\n  a:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@v4\n      - name: setup\n        uses: actions/setup-python@v5\n"
    )
    trovati = {r.file: r.motivo for r in rischi({"locale.yml": locale, "esterno.yml": esterno, "azione.yml": azione})}
    assert "riusabile" in trovati["locale.yml"]
    assert "riusabile" in trovati["esterno.yml"]
    assert "azione.yml" not in trovati
