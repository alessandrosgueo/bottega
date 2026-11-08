"""Prove del plugin `bottega`: manifesti, skill, pagine per porta e cartelle delle CLI."""

import json
import re
from pathlib import Path

import pytest

from bottega import VERSIONE

RADICE = Path(__file__).resolve().parents[2]
PLUGIN = RADICE / "plugin"
SKILL = PLUGIN / "skills" / "bottega"
PORTE = ["claude-code", "antigravity", "pi", "copilot-cli"]
AUTORE = {"name": "gli autori della bottega"}
MANIFESTI = [
    RADICE / ".claude-plugin" / "marketplace.json",
    PLUGIN / ".claude-plugin" / "plugin.json",
    PLUGIN / ".antigravity-plugin" / "plugin.json",
    PLUGIN / "package.json",
]
SEZIONI = [
    "Installare dal clone e aggiornare",
    "Lavorare senza mani",
    "I modelli",
    "Trascrizioni e contatori",
    "Quota esaurita",
    "Versione e accesso",
    "Sotto-agenti",
    "Istruzioni e skill del progetto",
    "Da verificare in B3",
]
# B1-R3: né la skill né le pagine nominano modelli. `\w*` copre le varianti, per esempio «opusplan».
NOMI_DI_MODELLO = re.compile(
    r"\b(opus|sonnet|haiku|fable|gpt|argon|flash|gemma|llama|mistral|grok)\w*|\bgemini\s+\d",
    re.IGNORECASE,
)
PAGINE_SENZA_MODELLI = [SKILL / "SKILL.md", *(SKILL / "porte" / f"{porta}.md" for porta in PORTE)]


def _nome(percorso: Path) -> str:
    return str(percorso.relative_to(RADICE))


def _carica(percorso: Path):
    return json.loads(percorso.read_text(encoding="utf-8"))


def _chiavi(valore):
    """Tutte le chiavi di un JSON, anche quelle annidate."""
    if isinstance(valore, dict):
        for chiave, figlio in valore.items():
            yield chiave
            yield from _chiavi(figlio)
    elif isinstance(valore, list):
        for figlio in valore:
            yield from _chiavi(figlio)


def test_manifesti_validi():
    for percorso in MANIFESTI:
        dati = _carica(percorso)
        assert dati.get("author", dati.get("owner")) == AUTORE, _nome(percorso)
        assert "email" not in set(_chiavi(dati)), _nome(percorso)
    marketplace = _carica(MANIFESTI[0])
    assert marketplace["name"] == "bottega"
    [voce] = marketplace["plugins"]
    assert voce["name"] == "bottega" and voce["version"] == VERSIONE
    for percorso in MANIFESTI[1:]:
        dati = _carica(percorso)
        assert dati["name"] == "bottega", _nome(percorso)
        assert dati["version"] == VERSIONE, _nome(percorso)
        assert dati["license"] == "MIT", _nome(percorso)


@pytest.mark.parametrize("percorso", MANIFESTI, ids=_nome)
def test_nessun_manifesto_contiene_dati_personali(percorso):
    testo = percorso.read_text(encoding="utf-8")
    assert "@" not in testo and "http" not in testo, _nome(percorso)
    assert not set(_chiavi(_carica(percorso))) & {"homepage", "repository", "email"}, _nome(percorso)


def test_skill_ha_frontmatter():
    testo = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    intestazione = re.match(r"---\n(.*?)\n---\n", testo, re.DOTALL)
    assert intestazione, "SKILL.md senza frontmatter"
    campi = {}
    for riga in intestazione.group(1).splitlines():
        chiave, due_punti, valore = riga.partition(":")
        if due_punti:
            campi[chiave.strip()] = valore.strip()
    assert campi.get("name") == "bottega"
    assert campi.get("description")


def test_percorsi_dei_manifesti_esistono():
    [voce] = _carica(MANIFESTI[0])["plugins"]
    assert (RADICE / voce["source"]).resolve() == PLUGIN, voce["source"]
    assert (PLUGIN / ".claude-plugin" / "plugin.json").is_file()
    for percorso in _carica(PLUGIN / "package.json")["pi"]["skills"]:
        assert (PLUGIN / percorso / "bottega" / "SKILL.md").is_file(), percorso


@pytest.mark.parametrize("porta", PORTE)
def test_ogni_porta_ha_la_sua_pagina(porta):
    assert (SKILL / "porte" / f"{porta}.md").is_file()
    assert f"porte/{porta}.md" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("porta", PORTE)
def test_pagine_porta_stesse_sezioni_stesso_ordine(porta):
    testo = (SKILL / "porte" / f"{porta}.md").read_text(encoding="utf-8")
    assert re.findall(r"^## (.+)$", testo, re.MULTILINE) == SEZIONI


@pytest.mark.parametrize("percorso", PAGINE_SENZA_MODELLI, ids=_nome)
def test_skill_e_pagine_senza_nomi_di_modello(percorso):
    assert not NOMI_DI_MODELLO.search(percorso.read_text(encoding="utf-8")), _nome(percorso)


# Nessun file con questi nomi in plugin/, a nessuna profondità: il modello per i progetti si chiama modelli/agents.md.
@pytest.mark.parametrize("nome", ["AGENTS.md", "GEMINI.md", "CLAUDE.md"])
def test_plugin_senza_regole_di_progetto(nome):
    trovati = set(PLUGIN.rglob(nome))
    assert not trovati, f"{nome} dentro plugin/ diventerebbe una regola in ogni progetto: {sorted(trovati)}"
