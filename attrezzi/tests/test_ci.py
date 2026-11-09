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


def test_g6_chiave_quotata():
    # Una chiave d'evento fra apici sotto on: ('push':, "pull_request":) si legge come quella senza apici;
    # ogni riga sotto on: che non sai leggere è un dubbio, cioè un rischio.
    wf_singoli = """
on:
  'push':
    branches: ['**']
jobs:
  a:
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    r_singoli = rischi({"singoli.yml": wf_singoli})
    assert len(r_singoli) == 1
    assert "push" in r_singoli[0].motivo and "self-hosted" in r_singoli[0].motivo

    wf_doppi = """
on:
  "push":
    branches: ['**']
jobs:
  a:
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    r_doppi = rischi({"doppi.yml": wf_doppi})
    assert len(r_doppi) == 1
    assert "push" in r_doppi[0].motivo and "self-hosted" in r_doppi[0].motivo

    wf_illeggibile = """
on:
  ??? riga strana
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: make
"""
    r_dubbio = rischi({"dubbio.yml": wf_illeggibile})
    assert len(r_dubbio) == 1
    assert "dubbio" in r_dubbio[0].motivo or "non riconosciuto" in r_dubbio[0].motivo


def test_g6_secrets_in_ogni_forma():
    # È un rischio ogni uso di secrets in un'espressione ${{ … }}, in qualunque forma:
    # secrets.X, secrets['X'], toJSON(secrets), secrets[format(...)], e anche secrets: inherit.
    # Fuori dai commenti YAML.
    wf_tojson = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo '${{ toJSON(secrets) }}' > s; make
"""
    r_tojson = rischi({"tojson.yml": wf_tojson})
    assert len(r_tojson) == 1
    assert "secrets" in r_tojson[0].motivo

    wf_parentesi = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      T: ${{ secrets['TOKEN'] }}
    steps:
      - run: make
"""
    r_parentesi = rischi({"parentesi.yml": wf_parentesi})
    assert len(r_parentesi) == 1
    assert "secrets" in r_parentesi[0].motivo

    wf_format = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets[format('{0}', 'KEY')] }}
"""
    r_format = rischi({"format.yml": wf_format})
    assert len(r_format) == 1
    assert "secrets" in r_format[0].motivo

    # Commento YAML non deve attivare il rischio se non ci sono altri segreti
    wf_commento = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      # ${{ toJSON(secrets) }} nel commento
      - run: echo ok
"""
    assert rischi({"commento.yml": wf_commento}) == []


def test_g6_runs_on_a_mappa():
    # runs-on: scritto come mappa (group:/labels:) o in una forma che non è una stringa né una lista è un dubbio.
    wf_gruppo = """
on: push
jobs:
  a:
    runs-on:
      group: casa
      labels: bottega
    steps:
      - run: make
"""
    r_gruppo = rischi({"gruppo.yml": wf_gruppo})
    assert len(r_gruppo) == 1
    assert "runs-on" in r_gruppo[0].motivo

    wf_inline_map = """
on: push
jobs:
  a:
    runs-on: { group: 'casa', labels: 'bottega' }
    steps:
      - run: make
"""
    r_inline = rischi({"inline.yml": wf_inline_map})
    assert len(r_inline) == 1
    assert "runs-on" in r_inline[0].motivo


def test_g6_etichette_di_github_esatte():
    # Un runner è di GitHub solo con un'etichetta di questo elenco esatto:
    # ubuntu-latest, ubuntu-24.04, ubuntu-22.04, ubuntu-24.04-arm, ubuntu-22.04-arm,
    # windows-latest, windows-2025, windows-2022, macos-latest, macos-15, macos-14, macos-13.
    # Ogni altra (anche ubuntu-bottega) è self-hosted. Un'espressione ${{ … }} in runs-on è un dubbio.
    etichette_valide = [
        "ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "ubuntu-24.04-arm", "ubuntu-22.04-arm",
        "windows-latest", "windows-2025", "windows-2022", "macos-latest", "macos-15", "macos-14", "macos-13",
    ]
    for et in etichette_valide:
        wf_ok = f"""
on: push
jobs:
  a:
    runs-on: {et}
    steps:
      - run: make
"""
        assert rischi({f"{et}.yml": wf_ok}) == [], f"Dovrebbe essere valido: {et}"

    wf_ubuntu_bottega = """
on: push
jobs:
  a:
    runs-on: ubuntu-bottega
    steps:
      - run: make
"""
    r_bottega = rischi({"bottega.yml": wf_ubuntu_bottega})
    assert len(r_bottega) == 1
    assert "ubuntu-bottega" in r_bottega[0].motivo or "non GitHub" in r_bottega[0].motivo or "self-hosted" in r_bottega[0].motivo

    wf_espressione = """
on: push
jobs:
  a:
    runs-on: ${{ matrix.runner }}
    steps:
      - run: make
"""
    r_expr = rischi({"expr.yml": wf_espressione})
    assert len(r_expr) == 1
    assert "runs-on con espressione" in r_expr[0].motivo


def test_g6_guardia_in_or_non_protegge():
    # La guardia !startsWith(github.head_ref, 'bottega/') conta solo se la condizione if: è esattamente quella
    # (spazi a parte, con o senza ${{ }}) o se è unita al resto solo con && al livello più esterno;
    # con un || (o parentesi che non sai leggere) non protegge.
    wf_or = """
on: pull_request
jobs:
  a:
    if: github.actor == 'me' || !startsWith(github.head_ref, 'bottega/')
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    r_or = rischi({"or.yml": wf_or})
    assert len(r_or) == 1
    assert "pull_request" in r_or[0].motivo

    wf_and_ok = """
on: pull_request
jobs:
  a:
    if: "!startsWith(github.head_ref, 'bottega/') && github.event_name == 'pull_request'"
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    assert rischi({"and_ok.yml": wf_and_ok}) == []

    wf_expr_ok = """
on: pull_request
jobs:
  a:
    if: ${{ !startsWith(github.head_ref, 'bottega/') }}
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    assert rischi({"expr_ok.yml": wf_expr_ok}) == []

    wf_or_dentro = """
on: pull_request
jobs:
  a:
    if: "!startsWith(github.head_ref, 'bottega/') || false"
    runs-on: [self-hosted]
    steps:
      - run: make
"""
    r_or_dentro = rischi({"or_dentro.yml": wf_or_dentro})
    assert len(r_or_dentro) == 1


CASI_REVISORE = {
    "chiave_quotata": "on:\n  'push':\n    branches: ['**']\njobs:\n  a:\n    runs-on: [self-hosted, x]\n    steps:\n      - run: make\n",
    "tojson_secrets": "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo '${{ toJSON(secrets) }}' > s; make\n",
    "secrets_parentesi": "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    env:\n      T: ${{ secrets['TOKEN'] }}\n    steps:\n      - run: make\n",
    "runs_on_gruppo": "on: push\njobs:\n  a:\n    runs-on:\n      group: casa\n      labels: bottega\n    steps:\n      - run: make\n",
    "etichetta_ubuntu": "on: push\njobs:\n  a:\n    runs-on: ubuntu-bottega\n    steps:\n      - run: make\n",
    "guardia_or": "on: pull_request\njobs:\n  a:\n    if: github.actor == 'me' || !startsWith(github.head_ref, 'bottega/')\n    runs-on: [self-hosted]\n    steps:\n      - run: make\n",
}


@pytest.mark.parametrize("nome", list(CASI_REVISORE))
def test_g6_casi_del_revisore(nome: str):
    r = rischi({nome: CASI_REVISORE[nome]})
    assert bool(r), f"Caso del revisore {nome} non ha prodotto rischi"


def test_g6_runs_on_in_flusso():
    # runs-on scritto dentro un flusso YAML (es. jobs: {b: {runs-on: self-hosted}} o b: {runs-on: self-hosted})
    # non letto come chiave di riga è un dubbio, quindi un rischio.
    wf1 = """
on: push
jobs: {b: {runs-on: self-hosted}}
"""
    r1 = rischi({"flusso1.yml": wf1})
    assert len(r1) == 1
    assert "runs-on" in r1[0].motivo

    wf2 = """
on: push
jobs:
  b: {runs-on: self-hosted}
"""
    r2 = rischi({"flusso2.yml": wf2})
    assert len(r2) == 1
    assert "runs-on" in r2[0].motivo


def test_g6_runs_on_fra_apici():
    # runs-on fra apici singoli o doppi con runner pericoloso è un rischio.
    wf_doppi = """
on: push
jobs:
  a:
    "runs-on": self-hosted
    steps:
      - run: make
"""
    r_doppi = rischi({"doppi.yml": wf_doppi})
    assert len(r_doppi) == 1
    assert "self-hosted" in r_doppi[0].motivo

    wf_singoli = """
on: push
jobs:
  a:
    'runs-on': [self-hosted]
    steps:
      - run: make
"""
    r_singoli = rischi({"singoli.yml": wf_singoli})
    assert len(r_singoli) == 1
    assert "self-hosted" in r_singoli[0].motivo


def test_g6_secrets_maiuscole():
    # I contesti di GitHub Actions non distinguono maiuscole: Secrets e SECRETS sono rischi.
    wf_cap = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ Secrets.CHIAVE }}
"""
    r_cap = rischi({"cap.yml": wf_cap})
    assert len(r_cap) == 1
    assert "secrets" in r_cap[0].motivo.lower()

    wf_upper = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ SECRETS.CHIAVE }}
"""
    r_upper = rischi({"upper.yml": wf_upper})
    assert len(r_upper) == 1
    assert "secrets" in r_upper[0].motivo.lower()


def test_c3_runs_on_maiuscolo():
    wf_upper = """
on: push
jobs:
  a:
    RUNS-ON: self-hosted
    steps:
      - run: make
"""
    r_upper = rischi({"upper.yml": wf_upper})
    assert len(r_upper) == 1
    assert "self-hosted" in r_upper[0].motivo or "non GitHub" in r_upper[0].motivo

    wf_mixed = """
on: push
jobs:
  a:
    Runs-On: [self-hosted, linux]
    steps:
      - run: make
"""
    r_mixed = rischi({"mixed.yml": wf_mixed})
    assert len(r_mixed) == 1
    assert "self-hosted" in r_mixed[0].motivo or "non GitHub" in r_mixed[0].motivo


def test_c3_chiave_con_escape():
    wf_escape_line = """
on: push
jobs:
  a:
    "\\x72uns-on": self-hosted
    steps:
      - run: make
"""
    r_escape = rischi({"escape.yml": wf_escape_line})
    assert len(r_escape) == 1
    assert "escape" in r_escape[0].motivo.lower()

    wf_escape_inline = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
        with: {"\\x72uns-on": self-hosted}
"""
    r_inline = rischi({"inline.yml": wf_escape_inline})
    assert len(r_inline) == 1
    assert "escape" in r_inline[0].motivo.lower()

    wf_sicuro = """
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo "a\\nb"
"""
    assert rischi({"sicuro.yml": wf_sicuro}) == []








