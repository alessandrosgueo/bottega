"""Prove per i giri pianificati del distributore (Ruling B9-R2)."""

from datetime import date
from pathlib import Path
import re

from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.progetto import (
    cron_di_riserva,
    file_dell_installazione,
    minuto_sicuro,
)

try:
    import yaml
except ImportError:
    import sys
    for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
        if p not in sys.path:
            sys.path.append(p)
    try:
        import yaml
    except ImportError:
        yaml = None

RADICE = Path(__file__).resolve().parent.parent.parent
DISTRIBUTORE_MODELLO = (
    RADICE / "plugin" / "skills" / "bottega" / "modelli" / "workflows" / "bottega-distributore.yml"
)

VALORI_BASE = {
    "proprietario": "prop",
    "sha": "0123456789abcdef0123456789abcdef01234567",
    "tag": "v1.0.0",
    "etichetta del runner": "runner-principale",
    "id": "principale",
}


def _configurazione_base(notte: str | None = "02:00", fuso: str = "Europe/Rome") -> Configurazione:
    return Configurazione(
        versione=1,
        progetto=Progetto(
            comandanti=("comandante",),
            adattatore=None,
            fuso=fuso,
            notte=notte,
            manutenzione=(),
            project=1,
            liberi=(),
        ),
        botteghe={
            "principale": Bottega(id="principale", quota="normale", porte=("claude-code",)),
        },
        candidati={
            "maestro": Candidato(
                id="maestro",
                nome="Maestro Modello",
                bottega="principale",
                porta="claude-code",
                modello="modello-forte",
                funzioni=("decidere", "rivedere"),
                runner="runner-principale",
            ),
        },
    )


def _carica_yaml(testo: str) -> dict:
    if yaml is not None:
        return yaml.safe_load(testo)
    risultato: dict = {True: {"schedule": []}}
    in_schedule = False
    for riga in testo.splitlines():
        if riga.strip().startswith("schedule:"):
            in_schedule = True
            continue
        if in_schedule:
            if riga.strip().startswith("- cron:"):
                m = re.search(r"- cron:\s*['\"]([^'\"]+)['\"]", riga)
                if m:
                    risultato[True]["schedule"].append({"cron": m.group(1)})
            elif riga.strip() and not riga.strip().startswith("#") and not riga.startswith("    "):
                in_schedule = False
    return risultato


def test_minuto_sicuro() -> None:
    """minuto_sicuro: 0 → 17; 30 → 30; 59 → 59."""
    assert minuto_sicuro(0) == 17
    assert minuto_sicuro(30) == 30
    assert minuto_sicuro(59) == 59


def test_cron_di_riserva() -> None:
    """cron_di_riserva: '17 0 * * *' → '47 * * * *'; '45 1 * * *' → '15 * * * *'; None → '47 * * * *'."""
    assert cron_di_riserva("17 0 * * *") == "47 * * * *"
    assert cron_di_riserva("45 1 * * *") == "15 * * * *"
    assert cron_di_riserva(None) == "47 * * * *"


def test_modello_distributore() -> None:
    """Il modello ha due righe - cron: sotto schedule:, nessuna al minuto 0; notte: controlla il cron di notte."""
    testo = DISTRIBUTORE_MODELLO.read_text(encoding="utf-8")
    righe_cron = re.findall(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", testo, re.MULTILINE)
    assert len(righe_cron) == 2
    for cron in righe_cron:
        minuto = int(cron.split()[0])
        assert minuto != 0

    match_notte = re.search(r"-\s*cron:\s*['\"]([^'\"]+)['\"]\s*#\s*<ora in UTC>", testo)
    assert match_notte is not None
    cron_notte_modello = match_notte.group(1)

    match_riga_notte = re.search(r"notte:\s*\${{.*github\.event\.schedule == '([^']+)'.*}}", testo)
    assert match_riga_notte is not None
    assert "github.event.schedule ==" in match_riga_notte.group(0)
    assert match_riga_notte.group(1) == cron_notte_modello


def test_file_dell_installazione_notte_02_00() -> None:
    """Con notte 02:00 e Europe/Rome: cron notte al minuto 17, commento spostamento, riserva 47, notte: coerente."""
    cfg = _configurazione_base(notte="02:00", fuso="Europe/Rome")
    file_pr = file_dell_installazione(cfg, VALORI_BASE, [])
    testo = file_pr[".github/workflows/bottega-distributore.yml"]

    dati = _carica_yaml(testo)
    schedule = dati.get(True, dati.get("on", {})).get("schedule", [])
    assert len(schedule) == 2

    cron_notte = schedule[0]["cron"]
    cron_riserva = schedule[1]["cron"]

    assert cron_notte.split()[0] == "17"
    assert "spostato dal minuto 0" in testo
    assert cron_riserva == "47 * * * *"

    match_notte = re.search(r"notte:\s*\${{.*github\.event\.schedule == '([^']+)'.*}}", testo)
    assert match_notte is not None
    assert match_notte.group(1) == cron_notte


def test_file_dell_installazione_notte_01_30() -> None:
    """Con notte 01:30: notte al minuto 30, riserva al minuto 17 (non 0), cron_di_riserva usa minuto_sicuro."""
    cfg = _configurazione_base(notte="01:30", fuso="Europe/Rome")
    file_pr = file_dell_installazione(cfg, VALORI_BASE, [])
    testo = file_pr[".github/workflows/bottega-distributore.yml"]

    dati = _carica_yaml(testo)
    schedule = dati.get(True, dati.get("on", {})).get("schedule", [])
    assert len(schedule) == 2

    cron_notte = schedule[0]["cron"]
    cron_riserva = schedule[1]["cron"]

    assert cron_notte.split()[0] == "30"
    assert "spostato dal minuto 0" not in testo
    assert cron_riserva == "17 * * * *"

    match_notte = re.search(r"notte:\s*\${{.*github\.event\.schedule == '([^']+)'.*}}", testo)
    assert match_notte is not None
    assert match_notte.group(1) == cron_notte


def test_file_dell_installazione_senza_notte() -> None:
    """Senza notte: nessun cron di notte né # <ora in UTC>, riserva '47 * * * *', notte: inputs.notte == true."""
    cfg = _configurazione_base(notte=None, fuso="Europe/Rome")
    file_pr = file_dell_installazione(cfg, VALORI_BASE, [])
    testo = file_pr[".github/workflows/bottega-distributore.yml"]

    assert "# <ora in UTC>" not in testo
    assert "<riserva>" not in testo

    dati = _carica_yaml(testo)
    schedule = dati.get(True, dati.get("on", {})).get("schedule", [])
    assert len(schedule) == 1
    assert schedule[0]["cron"] == "47 * * * *"

    assert re.search(r"^\s*notte:\s*\${{\s*inputs\.notte == true\s*}}", testo, re.MULTILINE) is not None
    assert not re.findall(r"<([^!>\n.][^>\n]*)>", testo)


def test_distributore_yaml_valido_e_cron_5_campi() -> None:
    """Il distributore generato con e senza notte è YAML valido e ogni cron ha 5 campi."""
    for notte in ("02:00", "01:30", None):
        cfg = _configurazione_base(notte=notte, fuso="Europe/Rome")
        file_pr = file_dell_installazione(cfg, VALORI_BASE, [])
        testo = file_pr[".github/workflows/bottega-distributore.yml"]

        dati = _carica_yaml(testo)
        schedule = dati.get(True, dati.get("on", {})).get("schedule", [])
        assert len(schedule) >= 1
        for voce in schedule:
            cron = voce["cron"]
            campi = cron.split()
            assert len(campi) == 5, f"Cron non ha 5 campi: '{cron}'"


def test_fuso_a_mezz_ora_evita_il_minuto_zero_in_utc() -> None:
    """05:30 a Kolkata è 00:00 UTC: il cron va al minuto 17 in UTC e il commento dice 05:47."""
    cfg = _configurazione_base(notte="05:30", fuso="Asia/Kolkata")
    testo = file_dell_installazione(cfg, VALORI_BASE, [])[".github/workflows/bottega-distributore.yml"]
    righe = [r for r in testo.splitlines() if "- cron:" in r]
    notte = next(r for r in righe if "Kolkata" in r)
    assert "'17 0 * * *'" in notte and "05:47" in notte and "spostato dal minuto 0" in notte
