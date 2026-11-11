"""Prove per la correzione B8-1: costituzione configurabile, avviso Item closed, prova r22."""

import argparse
import json
import random
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bottega.board import Lavoro
from bottega.configurazione import (
    Bottega,
    Candidato,
    Configurazione,
    Progetto,
    controlla_configurazione,
    leggi_configurazione,
)
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.installa import argomenti_installa, comando_progetto
from bottega.porte import Controllo, Lancio
from bottega.progetto import file_dell_installazione

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


class PortaFinta:
    """Porta finta per le prove di giro."""

    def __init__(self, callback=None) -> None:
        self.nome = "finta"
        self.eseguibile = "finta"
        self.callback = callback

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True, versione="1.0")

    def lancia(
        self,
        cartella: Path | str,
        prompt: str,
        modello: str,
        *,
        conversazione: str | None = None,
        sola_lettura: bool = False,
        prefisso: tuple[str, ...] = (),
        tempo: float = 3600,
    ) -> Lancio:
        if self.callback is not None:
            return self.callback(
                cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura
            )
        return Lancio(esito="fatto", testo="fatto")


class EsecutoreFinto:
    """Esecutore finto per simulare chiamate a gh e git (come EsecutoreRegistratore in test_installa)."""

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
        cmd_str = " ".join(comando)
        if cmd_str in self.risposte:
            return self.risposte[cmd_str]
        for prefisso, esito in self.risposte.items():
            if cmd_str.startswith(prefisso):
                return esito

        if len(comando) >= 2 and comando[0] == "git" and "rev-parse" in comando:
            return 1, "fatal: not a valid object name\n"
        if len(comando) >= 2 and comando[0] == "git" and "ls-remote" in comando:
            return 0, ""
        if (
            len(comando) >= 2
            and comando[0] == "git"
            and "remote" in comando
            and "get-url" in comando
        ):
            return 0, "https://github.com/owner/bottega.git\n"
        if (
            len(comando) >= 2
            and comando[0] == "gh"
            and "repo" in comando
            and "view" in comando
        ):
            return 0, json.dumps({"defaultBranchRef": {"name": "main"}})
        if (
            len(comando) >= 2
            and comando[0] == "gh"
            and ("commits" in cmd_str or "git/ref/tags" in cmd_str)
        ):
            return 0, f"commit {'1' * 40}\n"
        return 0, ""


def _scrivi(cartella: Path, testo: str) -> Path:
    percorso = cartella / "bottega.toml"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


def _parser_installa() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    argomenti_installa(p)
    return p


# 1. test_b8_costituzione_di_serie: una configurazione senza la chiave ha progetto.costituzione == "docs/costituzione.md"
def test_b8_costituzione_di_serie(tmp_path: Path) -> None:
    p = _scrivi(tmp_path, BASE_CONFIG)
    cfg = leggi_configurazione(p)
    assert cfg.progetto.costituzione == "docs/costituzione.md"


# 2. test_b8_costituzione_configurata: con costituzione = "docs/guide/regole.md" il valore è quello
def test_b8_costituzione_configurata(tmp_path: Path) -> None:
    testo = BASE_CONFIG.replace(
        "[progetto]\n",
        '[progetto]\ncostituzione = "docs/guide/regole.md"\n',
    )
    p = _scrivi(tmp_path, testo)
    cfg = leggi_configurazione(p)
    assert cfg.progetto.costituzione == "docs/guide/regole.md"


# 3. test_b8_costituzione_percorso_storto: parametrizzata su ...
@pytest.mark.parametrize(
    "valore",
    [
        "/etc/passwd",
        "../fuori.md",
        "docs/../x.md",
        "docs//x.md",
        "docs\\x.md",
        "-x.md",
        "",
        "a" * 201,
        3,
    ],
)
def test_b8_costituzione_percorso_storto(tmp_path: Path, valore: object) -> None:
    rep = json.dumps(valore) if isinstance(valore, str) else str(valore)
    testo = BASE_CONFIG.replace(
        'fuso = "Europe/Rome"',
        f'fuso = "Europe/Rome"\ncostituzione = {rep}',
    )
    err = controlla_configurazione(_scrivi(tmp_path, testo))
    assert any(
        "progetto.costituzione" in e and "chiave sconosciuta" not in e for e in err
    )


# 4. test_b8_giro_legge_la_costituzione_configurata: un giro con costituzione = "docs/altro.md"
def test_b8_giro_legge_la_costituzione_configurata(tmp_path: Path) -> None:
    from bottega.giro import giro

    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    clone = tmp_path / "progetto"
    subprocess.run(
        ["git", "clone", str(origin), str(clone)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )

    docs = clone / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    contenuto_speciale = "Costituzione Alternativa di Test B8\n"
    (docs / "altro.md").write_text(contenuto_speciale, encoding="utf-8")
    (clone / "test_file.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(clone), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )

    cfg = Configurazione(
        versione=1,
        progetto=Progetto(
            comandanti=("comandante1",),
            adattatore=None,
            fuso="UTC",
            notte=None,
            manutenzione=(),
            project=1,
            costituzione="docs/altro.md",
        ),
        botteghe={
            "principale": Bottega(id="principale", quota="abbondante", porte=("finta",))
        },
        candidati={
            "esecutore": Candidato(
                id="esecutore",
                nome="Esecutore Finto",
                bottega="principale",
                porta="finta",
                modello="finto-1",
                funzioni=("eseguire",),
                runner="linux-x64",
            )
        },
    )

    iss = Issue(
        numero=1,
        titolo="Compito 1",
        corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n",
    )
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    fascicolo_letto: dict[str, str] = {}

    def callback_esecutore(cartella, prompt, **kwargs):
        fasc_dir = Path(cartella) / ".bottega" / "fascicolo"
        for f in fasc_dir.iterdir():
            if f.is_file():
                fascicolo_letto[f.name] = f.read_text(encoding="utf-8")
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=callback_esecutore)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    assert "costituzione.md" in fascicolo_letto
    assert fascicolo_letto["costituzione.md"] == contenuto_speciale


# 5. test_b8_installa_costituzione_nel_percorso_configurato: file_dell_installazione con costituzione = "docs/altro.md"
def test_b8_installa_costituzione_nel_percorso_configurato() -> None:
    cfg = Configurazione(
        versione=1,
        progetto=Progetto(
            comandanti=("comandante1",),
            adattatore=None,
            fuso="UTC",
            notte=None,
            manutenzione=(),
            project=1,
            costituzione="docs/altro.md",
        ),
        botteghe={
            "principale": Bottega(id="principale", quota="abbondante", porte=("finta",))
        },
        candidati={
            "esecutore": Candidato(
                id="esecutore",
                nome="Esecutore Finto",
                bottega="principale",
                porta="finta",
                modello="finto-1",
                funzioni=("eseguire",),
                runner="linux-x64",
            )
        },
    )
    valori = {
        ".github/bottega/bottega.toml": "versione = 1\n",
        "proprietario": "mio-utente",
        "sha": "0123456789abcdef0123456789abcdef01234567",
        "tag": "v1.0.0",
        "etichetta del runner": "runner-principale",
        "id": "principale",
    }

    # Se docs/altro.md c'è già: nessuna costituzione
    res_con = file_dell_installazione(cfg, valori, ["docs/altro.md"])
    assert "docs/altro.md" not in res_con
    assert "docs/costituzione.md" not in res_con

    # Se manca: c'è docs/altro.md e non docs/costituzione.md
    res_senza = file_dell_installazione(cfg, valori, [])
    assert "docs/altro.md" in res_senza
    assert "docs/costituzione.md" not in res_senza


# 6. test_b8_flusso_chiusa_acceso: esegui_gh finto che risponde un JSON con Item closed acceso: True
def test_b8_flusso_chiusa_acceso() -> None:
    from bottega.progetto import flusso_chiusa_acceso

    dati = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PROJ_1",
                    "workflows": {
                        "nodes": [
                            {"name": "Item closed", "enabled": True},
                            {"name": "Auto-archive", "enabled": False},
                        ]
                    },
                }
            }
        }
    }

    def esegui_gh(cmd: list[str]) -> str:
        return json.dumps(dati)

    assert flusso_chiusa_acceso(esegui_gh, "owner", 1) is True


# 7. test_b8_flusso_chiusa_spento_o_assente: spento, e poi assente (solo altri flussi): False tutte e due
def test_b8_flusso_chiusa_spento_o_assente() -> None:
    from bottega.progetto import flusso_chiusa_acceso

    dati_spento = {
        "data": {
            "user": {
                "projectV2": {
                    "workflows": {
                        "nodes": [
                            {"name": "Item closed", "enabled": False},
                        ]
                    }
                }
            }
        }
    }
    assert (
        flusso_chiusa_acceso(lambda cmd: json.dumps(dati_spento), "owner", 1) is False
    )

    dati_assente = {
        "data": {
            "user": {
                "projectV2": {
                    "workflows": {
                        "nodes": [
                            {"name": "Altro flusso", "enabled": True},
                        ]
                    }
                }
            }
        }
    }
    assert (
        flusso_chiusa_acceso(lambda cmd: json.dumps(dati_assente), "owner", 1) is False
    )


# 8. test_b8_flusso_chiusa_illeggibile: esegui_gh che solleva un'eccezione: None; che risponde testo non JSON: None
def test_b8_flusso_chiusa_illeggibile() -> None:
    from bottega.progetto import flusso_chiusa_acceso

    def esegui_errore(cmd: list[str]) -> str:
        raise RuntimeError("errore gh")

    assert flusso_chiusa_acceso(esegui_errore, "owner", 1) is None

    def esegui_non_json(cmd: list[str]) -> str:
        return "non e' un json"

    assert flusso_chiusa_acceso(esegui_non_json, "owner", 1) is None


# 9. test_b8_installa_avvisa_flusso_spento: comando_progetto col gh finto delle prove che già esistono, con il flusso spento
def test_b8_installa_avvisa_flusso_spento(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cartella = tmp_path / "progetto"
    cartella.mkdir()
    cfg_file = cartella / "bottega.toml"
    cfg_file.write_text(BASE_CONFIG, encoding="utf-8")

    query_user_resp = json.dumps(
        {
            "data": {
                "user": {
                    "projectV2": {
                        "id": "PROJ_123",
                        "fields": {"nodes": []},
                        "workflows": {
                            "nodes": [{"name": "Item closed", "enabled": False}]
                        },
                    }
                }
            }
        }
    )
    esecutore = EsecutoreFinto(
        {
            "gh api graphql": (0, query_user_resp),
            "gh pr create": (0, "https://github.com/owner/repo/pull/101\n"),
        }
    )
    p = _parser_installa()
    args = p.parse_args(
        [
            "progetto",
            "--repo",
            "owner/repo",
            "--project",
            "1",
            "--configurazione",
            str(cfg_file),
            "--tag",
            "v1.0.0",
            "--bottega",
            "owner/bottega",
            "--senza-segreto",
        ]
    )
    args.cartella = cartella

    codice = comando_progetto(args, esegui=esecutore)
    assert codice == 0

    catturato = capsys.readouterr()
    righe_avviso = [r for r in catturato.err.splitlines() if r.startswith("avviso:")]
    assert len(righe_avviso) >= 1
    assert any("Item closed" in r for r in righe_avviso)
