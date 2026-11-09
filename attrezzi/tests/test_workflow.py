"""Prove sui workflow di GitHub Actions della bottega e sui loro modelli."""

import os
from pathlib import Path
import pytest
import re
import shutil
import subprocess

RADICE = Path(__file__).resolve().parent.parent.parent
DISTRIBUTORE_RIUSABILE = RADICE / ".github" / "workflows" / "distributore.yml"
ESECUTORE_RIUSABILE = RADICE / ".github" / "workflows" / "esecutore.yml"
CONTROLLO = RADICE / ".github" / "workflows" / "controllo.yml"
DISTRIBUTORE_MODELLO = (
    RADICE / "plugin" / "skills" / "bottega" / "modelli" / "workflows" / "bottega-distributore.yml"
)
ESECUTORE_MODELLO = (
    RADICE / "plugin" / "skills" / "bottega" / "modelli" / "workflows" / "bottega-esecutore.yml"
)
QUATTRO_WORKFLOW = (
    DISTRIBUTORE_RIUSABILE,
    ESECUTORE_RIUSABILE,
    DISTRIBUTORE_MODELLO,
    ESECUTORE_MODELLO,
)


def estrai_blocchi_run(testo: str) -> list[str]:
    """Estrae tutti i blocchi di codice eseguiti dalle chiavi 'run:' in uno YAML."""
    blocchi: list[str] = []
    righe = testo.splitlines()
    i = 0
    while i < len(righe):
        riga = righe[i]
        match = re.match(r"^(\s*)run:\s*(.*)$", riga)
        if match:
            indent, resto = match.groups()
            resto = resto.strip()
            if resto in ("|", "|-", ">", ">-", ""):
                blocco: list[str] = []
                base_indent = len(indent)
                i += 1
                while i < len(righe):
                    curr = righe[i]
                    if not curr.strip():
                        blocco.append(curr)
                        i += 1
                        continue
                    curr_indent = len(curr) - len(curr.lstrip())
                    if curr_indent <= base_indent:
                        break
                    blocco.append(curr)
                    i += 1
                blocchi.append("\n".join(blocco))
                continue
            else:
                blocchi.append(resto)
        i += 1
    return blocchi


def test_quattro_file_esistono():
    """Tutti e quattro i file di workflow devono esistere ed essere non vuoti."""
    for percorso in QUATTRO_WORKFLOW:
        assert percorso.is_file(), f"Manca il file: {percorso}"
        assert percorso.stat().st_size > 0, f"Il file è vuoto: {percorso}"


def test_eventi_dei_workflow():
    """I riusabili accettano solo workflow_call; i modelli dichiarano i loro eventi precisi."""
    # Riusabili: solo on: workflow_call
    for riusabile in (DISTRIBUTORE_RIUSABILE, ESECUTORE_RIUSABILE):
        testo = riusabile.read_text(encoding="utf-8")
        assert "workflow_call:" in testo, f"{riusabile.name} deve definire workflow_call"
        # Non devono rispondere a eventi diretti
        for evento in ("push:", "pull_request:", "schedule:"):
            assert evento not in testo, f"{riusabile.name} non deve avere l'evento {evento}"

    # Modello distributore: issues: labeled, issue_comment: created, schedule, workflow_dispatch
    testo_dist = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    assert "issues:" in testo_dist
    assert "labeled" in testo_dist
    assert "issue_comment:" in testo_dist
    assert "created" in testo_dist
    assert "schedule:" in testo_dist
    assert "cron:" in testo_dist
    assert "workflow_dispatch:" in testo_dist

    # Modello esecutore: workflow_dispatch con input lavoro
    testo_esec = ESECUTORE_MODELLO.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in testo_esec
    assert "lavoro:" in testo_esec
    for evento in ("issues:", "issue_comment:", "schedule:", "push:", "pull_request:"):
        assert evento not in testo_esec, f"L'esecutore non deve avere l'evento {evento}"


def test_gruppi_di_concorrenza():
    """I modelli devono definire i gruppi di concorrenza con cancel-in-progress: false."""
    testo_dist = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    assert "bottega-rumore" in testo_dist
    assert "bottega-distributore" in testo_dist
    assert "cancel-in-progress: false" in testo_dist

    testo_esec = ESECUTORE_MODELLO.read_text(encoding="utf-8")
    assert "group: bottega-esecutore-<id>" in testo_esec
    assert "cancel-in-progress: false" in testo_esec


def test_sha_checkout_uguale_a_controllo():
    """Lo SHA di actions/checkout deve essere identico a quello di controllo.yml."""
    testo_controllo = CONTROLLO.read_text(encoding="utf-8")
    match_sha = re.search(r"actions/checkout@([0-9a-f]{40})", testo_controllo)
    assert match_sha is not None, "Non trovo lo SHA di actions/checkout in controllo.yml"
    sha_atteso = match_sha.group(1)

    for riusabile in (DISTRIBUTORE_RIUSABILE, ESECUTORE_RIUSABILE):
        testo = riusabile.read_text(encoding="utf-8")
        trovati = re.findall(r"actions/checkout@([0-9a-f]{40})", testo)
        assert len(trovati) >= 2, f"{riusabile.name} deve contenere almeno due azioni di checkout"
        for sha in trovati:
            assert sha == sha_atteso, f"In {riusabile.name} lo SHA {sha} non corrisponde a quello atteso ({sha_atteso})"
        assert "persist-credentials: false" in testo, f"In {riusabile.name} manca persist-credentials: false"


def test_nessuna_espressione_dentro_run():
    """Mai un'espressione ${{ }} dentro il testo di run: tutto passa da env:."""
    for percorso in QUATTRO_WORKFLOW:
        testo = percorso.read_text(encoding="utf-8")
        blocchi = estrai_blocchi_run(testo)
        for blocco in blocchi:
            assert "${{" not in blocco, (
                f"Trovata espressione ${{ }} dentro run: in {percorso.name}:\n{blocco}"
            )


def test_nessun_github_token_ai_comandi():
    """Nessun GITHUB_TOKEN passato ai comandi o all'ambiente; si usa BOTTEGA_TOKEN."""
    for percorso in QUATTRO_WORKFLOW:
        testo = percorso.read_text(encoding="utf-8")
        assert "secrets.GITHUB_TOKEN" not in testo
        assert "github.token" not in testo
        assert "GITHUB_TOKEN:" not in testo

    for riusabile in (DISTRIBUTORE_RIUSABILE, ESECUTORE_RIUSABILE):
        testo = riusabile.read_text(encoding="utf-8")
        assert "BOTTEGA_TOKEN" in testo
        assert "GH_TOKEN: ${{ secrets.BOTTEGA_TOKEN }}" in testo


def test_input_e_permessi_dei_riusabili():
    """I riusabili devono dichiarare gli input richiesti, il runner da JSON e i permessi minimi."""
    testo_dist = DISTRIBUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "bottega_repo:" in testo_dist
    assert "bottega_ref:" in testo_dist
    assert "runner:" in testo_dist
    assert "notte:" in testo_dist
    assert "runs-on: ${{ fromJSON(inputs.runner) }}" in testo_dist
    assert "permissions:\n  contents: read" in testo_dist or "permissions:\n    contents: read" in testo_dist
    assert "BOTTEGA_VARIABILI: ${{ toJSON(vars) }}" in testo_dist
    assert "PYTHONPATH:" in testo_dist
    assert "python3 -P -m bottega distribuisci" in testo_dist

    testo_esec = ESECUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "bottega_repo:" in testo_esec
    assert "bottega_ref:" in testo_esec
    assert "runner:" in testo_esec
    assert "bottega:" in testo_esec
    assert "lavoro:" in testo_esec
    assert "runs-on: ${{ fromJSON(inputs.runner) }}" in testo_esec
    assert "permissions:\n  contents: read" in testo_esec or "permissions:\n    contents: read" in testo_esec
    assert "BOTTEGA_VARIABILI: ${{ toJSON(vars) }}" in testo_esec
    assert "PYTHONPATH:" in testo_esec
    assert "python3 -P -m bottega giro" in testo_esec
    assert "--lavoro" in testo_esec
    assert "--bottega" in testo_esec


def test_modelli_chiamanti_segnaposto_e_notte():
    """I chiamanti modello devono usare i segnaposto e gestire notte."""
    testo_dist = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    assert "<proprietario>" in testo_dist
    assert "<tag>" in testo_dist
    assert "<etichetta del runner>" in testo_dist
    assert "notte:" in testo_dist
    # Deve passare notte: true per schedule e false per issues/issue_comment
    assert "github.event_name == 'schedule'" in testo_dist

    testo_esec = ESECUTORE_MODELLO.read_text(encoding="utf-8")
    assert "<proprietario>" in testo_esec
    assert "<tag>" in testo_esec
    assert "<etichetta del runner>" in testo_esec
    assert "<id>" in testo_esec
    assert "bottega: <id>" in testo_esec
    assert "inputs.lavoro" in testo_esec


def test_actionlint_se_disponibile():
    """Se actionlint c'è (nel PATH o nella variabile ACTIONLINT), controlla tutti e quattro i workflow."""
    eseguibile = os.environ.get("ACTIONLINT") or shutil.which("actionlint")
    if not eseguibile:
        pytest.skip("actionlint non disponibile né nel PATH né in ACTIONLINT")

    cmd = [eseguibile] + [str(p) for p in QUATTRO_WORKFLOW]
    risultato = subprocess.run(cmd, capture_output=True, text=True)
    assert risultato.returncode == 0, f"actionlint ha segnalato errori:\n{risultato.stderr or risultato.stdout}"


def test_rv15_workflow():
    """RV15: fetch-depth: 0, BOTTEGA_CLONE, segreto passato per nome, uses per SHA."""
    testo_esec_riu = ESECUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "fetch-depth: 0" in testo_esec_riu
    assert "BOTTEGA_CLONE: ${{ github.workspace }}/bottega" in testo_esec_riu

    testo_dist_riu = DISTRIBUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "BOTTEGA_CLONE: ${{ github.workspace }}/bottega" in testo_dist_riu

    # La bottega sta accanto al progetto, mai dentro: il giro pulisce il clone con `git clean -fdx`.
    for testo in (testo_esec_riu, testo_dist_riu):
        assert "path: progetto" in testo
        assert "working-directory: progetto" in testo
        assert "path: .bottega" not in testo
    assert "BOTTEGA_SPAZIO: ${{ runner.temp }}/bottega-spazio" not in testo_esec_riu
    assert 'export BOTTEGA_SPAZIO="${BOTTEGA_SPAZIO:-$RUNNER_TEMP/bottega-spazio}"' in testo_esec_riu

    for mod in (DISTRIBUTORE_MODELLO, ESECUTORE_MODELLO):
        testo = mod.read_text(encoding="utf-8")
        assert "secrets: inherit" not in testo
        assert "BOTTEGA_TOKEN: ${{ secrets.BOTTEGA_TOKEN }}" in testo
        assert "@<sha>" in testo


def test_c5_ci_segreto_senza_codice_del_ramo():
    testo = CONTROLLO.read_text(encoding="utf-8")
    blocchi = re.split(r"\n  ([a-zA-Z0-9_-]+):\n", testo)
    jobs = {}
    for i in range(1, len(blocchi), 2):
        jobs[blocchi[i]] = blocchi[i + 1]

    job_segreto = None
    for nome, contenuto in jobs.items():
        if "secrets.PAROLE_VIETATE" in contenuto:
            job_segreto = contenuto
            break

    assert job_segreto is not None, "Nessun job usa secrets.PAROLE_VIETATE"
    assert "uv" not in job_segreto
    assert "pytest" not in job_segreto
    assert "ref: ${{ github.event.repository.default_branch }}" in job_segreto
    assert "python3 -P" in job_segreto


def test_c5_workflow_tetti_e_comandi():
    testo_esec = ESECUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "timeout-minutes:" in testo_esec
    assert "python3 -P -m bottega" in testo_esec

    testo_dist = DISTRIBUTORE_RIUSABILE.read_text(encoding="utf-8")
    assert "python3 -P -m bottega" in testo_dist

    testo_modello_dist = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    assert "bottega-comando-" in testo_modello_dist




def test_c6_commenti_solo_da_chi_ha_accesso():
    """C6: un commento fa partire il job solo se contiene /bottega e viene da chi ha accesso al repo."""
    testo = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    assert "contains(github.event.comment.body, '/bottega')" in testo
    assert "author_association" in testo
    assert '"COLLABORATOR"' in testo


def test_g2_spazio_dal_env_del_runner():
    """G2: esecutore.yml non imposta BOTTEGA_SPAZIO nell'env del passo (coprirebbe il .env del runner); lo esporta nel run col ripiego."""
    testo = ESECUTORE_RIUSABILE.read_text(encoding="utf-8")
    env_blocco = re.search(r"env:\s*\n((?:\s+[A-Z0-9_]+:[^\n]*\n)+)", testo)
    assert env_blocco is not None
    assert "BOTTEGA_SPAZIO" not in env_blocco.group(1)
    assert 'export BOTTEGA_SPAZIO="${BOTTEGA_SPAZIO:-$RUNNER_TEMP/bottega-spazio}"' in testo
