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
# B1-R3: né la skill, né le pagine, né i modelli nominano modelli. `\w*` copre le varianti, per esempio «opusplan».
# «Gemini» conta solo col nome del modello dopo (`Gemini Pro`, `gemini-3-pro`): `GEMINI.md` e `~/.gemini/` sono nomi di
# file e percorsi della CLI, che le pagine per porta descrivono.
NOMI_DI_MODELLO = re.compile(
    r"\b(opus|sonnet|haiku|fable|gpt|argon|hydrogen|carbon|flash|gemma|llama|mistral|grok|codex|deepseek)\w*"
    r"|\bgemini(?:[ \t]+|-)\w"
    r"|\bo[34]\b",
    re.IGNORECASE,
)
PAGINE_SENZA_MODELLI = [
    SKILL / "SKILL.md",
    *(SKILL / "porte" / f"{porta}.md" for porta in PORTE),
    *sorted((SKILL / "modelli").glob("*.md")),
]
# Un file con uno di questi nomi, in qualunque maiuscola, o una cartella .agents o rules dentro plugin/ diventerebbe una
# regola in ogni progetto che installa il plugin. `modelli/agents.md` è ammesso per nome esatto: è il modello del file
# di un progetto, non una regola.
REGOLE = {"agents.md", "agents.override.md", "gemini.md", "claude.md", "copilot-instructions.md"}
CARTELLE_DI_REGOLE = {".agents", "rules"}
AMMESSO = "skills/bottega/modelli/agents.md"


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


def _errori_marketplace(dati: dict) -> list[str]:
    """I plugin del marketplace: ciascuno si chiama `bottega`, ha la versione dei manifesti e l'autore comune."""
    errori = []
    for voce in dati["plugins"]:
        if voce.get("name") != "bottega" or voce.get("version") != VERSIONE:
            errori.append(f"plugin {voce.get('name')!r}: nome o versione sbagliati")
        if voce.get("author") != AUTORE:
            errori.append(f"plugin {voce.get('name')!r}: autore diverso da quello della bottega")
    return errori


def _errori_frontmatter(testo: str) -> list[str]:
    """Che cosa non va nel frontmatter della skill: va letto come lo leggerebbe un lettore YAML vero."""
    intestazione = re.match(r"---\n(.*?)\n---\n", testo, re.DOTALL)
    if not intestazione:
        return ["senza frontmatter"]
    righe = intestazione.group(1).splitlines()
    errori = []
    if any(riga[:1] in (" ", "\t") for riga in righe):
        errori.append(RIENTRATA)
    campi = {}
    for riga in righe:
        chiave, due_punti, valore = riga.partition(":")
        if due_punti:
            campi[chiave.strip()] = valore.strip()
    if campi.get("name") != "bottega":
        errori.append("name diverso da bottega")
    descrizione = campi.get("description", "")
    if not descrizione:
        errori.append("description vuota")
    elif descrizione[0] in "|>":
        errori.append(BLOCCO)
    if re.search(r":(\s|$)", descrizione):
        errori.append(DUE_PUNTI)
    return errori


def _regole_in(plugin: Path) -> list[str]:
    """Le regole di progetto dentro `plugin`, per percorso relativo: `AMMESSO` passa per nome esatto."""
    trovate = []
    for percorso in plugin.rglob("*"):
        relativo = percorso.relative_to(plugin).as_posix()
        if relativo == AMMESSO:
            continue
        if percorso.is_dir() and percorso.name.lower() in CARTELLE_DI_REGOLE:
            trovate.append(relativo)
        elif percorso.is_file() and percorso.name.lower() in REGOLE:
            trovate.append(relativo)
    return sorted(trovate)


def test_manifesti_validi():
    for percorso in MANIFESTI:
        dati = _carica(percorso)
        assert dati.get("author", dati.get("owner")) == AUTORE, _nome(percorso)
        assert "email" not in set(_chiavi(dati)), _nome(percorso)
    marketplace = _carica(MANIFESTI[0])
    assert marketplace["name"] == "bottega"
    assert _errori_marketplace(marketplace) == []
    for percorso in MANIFESTI[1:]:
        dati = _carica(percorso)
        assert dati["name"] == "bottega", _nome(percorso)
        assert dati["version"] == VERSIONE, _nome(percorso)
        assert dati["license"] == "MIT", _nome(percorso)


def test_marketplace_con_un_plugin_di_altro_autore_si_segnala():
    dati = {
        "plugins": [
            {"name": "bottega", "version": VERSIONE, "author": AUTORE},
            {"name": "bottega", "version": VERSIONE, "author": {"name": "un altro"}},
        ]
    }
    assert _errori_marketplace(dati) == ["plugin 'bottega': autore diverso da quello della bottega"]


@pytest.mark.parametrize("percorso", MANIFESTI, ids=_nome)
def test_nessun_manifesto_contiene_dati_personali(percorso):
    testo = percorso.read_text(encoding="utf-8")
    assert "@" not in testo and "http" not in testo, _nome(percorso)
    assert not set(_chiavi(_carica(percorso))) & {"homepage", "repository", "email"}, _nome(percorso)


DUE_PUNTI = "la description ha «:» seguito da spazio o a fine riga: YAML la legge come chiave"
RIENTRATA = "riga rientrata nel frontmatter: la description va su una riga sola"
BLOCCO = "description a blocco: va su una riga sola"


def test_skill_ha_frontmatter():
    assert _errori_frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "testo, atteso",
    [
        ("---\nname: bottega\ndescription: Una riga sola.\n---\n", []),
        ("---\nname: bottega\ndescription: Uso: quando serve.\n---\n", [DUE_PUNTI]),
        ("---\nname: bottega\ndescription: Uso:\n---\n", [DUE_PUNTI]),
        ("---\nname: bottega\ndescription: Una cosa\n  continua qui.\n---\n", [RIENTRATA]),
        ("---\nname: bottega\ndescription: |\n  testo\n---\n", [RIENTRATA, BLOCCO]),
        ("---\nname: altro\ndescription: Una riga.\n---\n", ["name diverso da bottega"]),
        ("---\nname: bottega\ndescription:\n---\n", ["description vuota"]),
        ("# Bottega\n", ["senza frontmatter"]),
    ],
)
def test_frontmatter_come_lo_legge_un_lettore_yaml(testo, atteso):
    assert _errori_frontmatter(testo) == atteso


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


def test_il_controllo_dei_modelli_copre_anche_i_modelli():
    assert SKILL / "modelli" / "brief.md" in PAGINE_SENZA_MODELLI


@pytest.mark.parametrize(
    "forma",
    ["Gemini Pro", "gemini-3-pro", "Gemini 3.8 Flash", "codex", "deepseek", "o3", "o4", "opus", "Hydrogen", "Carbon"],
)
def test_il_controllo_dei_modelli_prende_le_forme_senza_numero(forma):
    assert NOMI_DI_MODELLO.search(forma)


@pytest.mark.parametrize(
    "testo", ["GEMINI.md", "~/.gemini/antigravity-cli/settings.json", "modello", "Antigravity", "Scelta del formato"]
)
def test_il_controllo_dei_modelli_non_prende_file_percorsi_e_parole_comuni(testo):
    assert not NOMI_DI_MODELLO.search(testo)


@pytest.mark.parametrize(
    "creato, atteso",
    [
        ("AGENTS.md", ["AGENTS.md"]),
        ("Agents.md", ["Agents.md"]),
        ("AGENTS.override.md", ["AGENTS.override.md"]),
        ("GEMINI.md", ["GEMINI.md"]),
        ("CLAUDE.md", ["CLAUDE.md"]),
        ("copilot-instructions.md", ["copilot-instructions.md"]),
        (".agents/skills/x/SKILL.md", [".agents"]),
        ("rules/regola.md", ["rules"]),
        ("skills/bottega/modelli/AGENTS.md", ["skills/bottega/modelli/AGENTS.md"]),
        ("skills/bottega/modelli/agents.md", []),
    ],
)
def test_regole_di_progetto_dentro_il_plugin(tmp_path, creato, atteso):
    percorso = tmp_path / creato
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text("regola\n", encoding="utf-8")
    assert _regole_in(tmp_path) == atteso


def test_plugin_senza_regole_di_progetto():
    assert _regole_in(PLUGIN) == []
