"""Prove per le categorie del diff, il verdetto del revisore e `bottega categoria` (A1)."""

import json
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from bottega.categorie import (
    ETICHETTE_DELICATE,
    EsitoCategoria,
    Verdetto,
    analizza_verdetto,
    argomenti_categoria,
    classifica_diff,
    comando_categoria,
    corrisponde_glob,
    file_del_diff,
    percorso_protetto,
)
from bottega.configurazione import PERCORSO_PREDEFINITO


def _git(cartella: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=cartella,
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout


def test_corrisponde_glob_casi_principali():
    assert corrisponde_glob("docs/a.md", "docs/**") is True
    assert corrisponde_glob("docs/a/b.md", "docs/**") is True
    assert corrisponde_glob("docs-2/a.md", "docs/**") is False
    assert corrisponde_glob("x/docs/a.md", "docs/**") is False

    assert corrisponde_glob("LEGGIMI.md", "*.md") is True
    assert corrisponde_glob("docs/a.md", "*.md") is False

    assert corrisponde_glob("a.py", "**/*.py") is True
    assert corrisponde_glob("attrezzi/bottega/a.py", "**/*.py") is True
    assert corrisponde_glob("attrezzi/bottega/a.txt", "**/*.py") is False

    assert corrisponde_glob("a/x/b.txt", "a/?/b.txt") is True
    assert corrisponde_glob("a/xy/b.txt", "a/?/b.txt") is False

    assert corrisponde_glob("./docs/a.md", "docs/**") is True
    assert corrisponde_glob("./LEGGIMI.md", "*.md") is True


def test_percorso_protetto():
    assert percorso_protetto(".github/workflows/x.yml") is True
    assert percorso_protetto(".bottega/a") is True
    assert percorso_protetto(".gitleaksignore") is True
    assert percorso_protetto("sub/.gitleaks.toml") is True
    assert percorso_protetto("./.github/x.md") is True
    assert percorso_protetto("docs/github.md") is False


def test_classifica_diff_non_delicata():
    categorie = {
        "documenti": ("docs/**", "*.md"),
        "prove": ("attrezzi/tests/**",),
    }
    esito = classifica_diff(["docs/guida.md", "attrezzi/tests/test_a.py"], categorie)
    assert isinstance(esito, EsitoCategoria)
    assert esito.delicata is False
    assert esito.categorie_toccate == ("documenti", "prove")
    assert esito.fuori_elenco == ()


def test_classifica_diff_file_fuori_elenco():
    categorie = {"documenti": ("docs/**",)}
    esito = classifica_diff(["docs/a.md", "attrezzi/bottega/giro.py"], categorie)
    assert esito.delicata is True
    assert esito.fuori_elenco == ("attrezzi/bottega/giro.py",)


def test_classifica_diff_pavimento_protetto_vince():
    categorie = {"documenti": ("**/*.md",)}
    esito = classifica_diff([".github/x.md"], categorie)
    assert esito.delicata is True
    assert ".github/x.md" in esito.fuori_elenco


def test_classifica_diff_vuoto_e_delicato():
    esito = classifica_diff([], {"documenti": ("docs/**",)})
    assert esito.delicata is True
    assert any("nessun file" in m for m in esito.motivi)


def test_classifica_diff_etichette_e_sicurezza():
    categorie = {"documenti": ("docs/**",)}
    assert "bottega: prove cambiate" in ETICHETTE_DELICATE
    assert "bottega: segreti" in ETICHETTE_DELICATE

    for etichetta in ("BOTTEGA: PROVE CAMBIATE", "bottega: segreti"):
        esito = classifica_diff(["docs/a.md"], categorie, etichette_pr=[etichetta])
        assert esito.delicata is True

    esito_sic = classifica_diff(["docs/a.md"], categorie, sicurezza=True)
    assert esito_sic.delicata is True


def test_analizza_verdetto_approvato_gravi_sicurezza():
    v_ok = analizza_verdetto("VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 2\n\nTutto ok.")
    assert isinstance(v_ok, Verdetto)
    assert v_ok.valido is True
    assert v_ok.stato == "APPROVATO"
    assert v_ok.gravi == 0
    assert v_ok.minori == 2
    assert v_ok.sicurezza is False
    assert v_ok.approvato is True
    assert v_ok.bloccante is False

    v_md = analizza_verdetto("- **VERDETTO:** RILIEVI GRAVI\n> **GRAVI:** 3\n* MINORI: 1")
    assert v_md.valido is True
    assert v_md.stato == "RILIEVI_GRAVI"
    assert v_md.gravi == 3
    assert v_md.minori == 1
    assert v_md.approvato is False
    assert v_md.bloccante is True

    v_sic = analizza_verdetto("VERDETTO: SICUREZZA\nGRAVI: 0\nMINORI: 0")
    assert v_sic.valido is True
    assert v_sic.stato == "SICUREZZA"
    assert v_sic.sicurezza is True
    assert v_sic.gravi >= 1
    assert v_sic.approvato is False
    assert v_sic.bloccante is True

    v_recinto = analizza_verdetto(
        "Esempio:\n```text\nVERDETTO: APPROVATO\nGRAVI: 0\n```\n\nVERDETTO: RILIEVI_GRAVI\nGRAVI: 1\nMINORI: 0\n"
    )
    assert v_recinto.valido is True
    assert v_recinto.stato == "RILIEVI_GRAVI"
    assert v_recinto.gravi == 1


def test_analizza_verdetto_fail_closed():
    v_contr = analizza_verdetto("VERDETTO: APPROVATO\nGRAVI: 2\nMINORI: 0")
    assert v_contr.valido is True
    assert v_contr.stato == "RILIEVI_GRAVI"
    assert v_contr.approvato is False
    assert v_contr.bloccante is True

    v_vuoto = analizza_verdetto("Risposta a testo libero senza intestazione.")
    assert v_vuoto.valido is False
    assert v_vuoto.stato == "non_valido"
    assert v_vuoto.approvato is False
    assert v_vuoto.bloccante is False


def test_file_del_diff_con_rinomina_e_spazi(tmp_path: Path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Prova")
    _git(tmp_path, "config", "user.email", "prova@example.com")

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("ciao\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")

    _git(tmp_path, "checkout", "-b", "ramo")
    (tmp_path / "src").mkdir()
    _git(tmp_path, "mv", "docs/a.md", "src/a.md")
    (tmp_path / "docs" / "file con spazi.md").write_text("spazi\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "rinomina e spazi")

    percorsi = file_del_diff("main", "HEAD", cartella=tmp_path)
    assert "docs/a.md" in percorsi
    assert "src/a.md" in percorsi
    assert "docs/file con spazi.md" in percorsi


def _scrivi_toml(percorso: Path) -> Path:
    percorso.write_text(
        """versione = 1

[progetto]
fuso = "Europe/Rome"

[botteghe.b1]
quota = "normale"
porte = ["claude-code"]

[candidati.c1]
nome = "C1"
bottega = "b1"
porta = "claude-code"
modello = "m1"
funzioni = ["decidere", "eseguire", "rivedere"]

[categorie]
documenti = ["docs/**"]
""",
        encoding="utf-8",
    )
    return percorso


def test_comando_categoria_codici_uscita(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    import argparse

    parser = argparse.ArgumentParser()
    argomenti_categoria(parser)

    toml = _scrivi_toml(tmp_path / "bottega.toml")
    percorsi_ok = tmp_path / "ok.txt"
    percorsi_ok.write_text("docs/guida.md\n", encoding="utf-8")
    percorsi_del = tmp_path / "del.txt"
    percorsi_del.write_text("docs/guida.md\nsrc/app.py\n", encoding="utf-8")

    verd_ok = tmp_path / "verd_ok.txt"
    verd_ok.write_text("VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 0\n", encoding="utf-8")
    verd_gravi = tmp_path / "verd_gravi.txt"
    verd_gravi.write_text("VERDETTO: RILIEVI_GRAVI\nGRAVI: 1\nMINORI: 0\n", encoding="utf-8")
    verd_sic = tmp_path / "verd_sic.txt"
    verd_sic.write_text("VERDETTO: SICUREZZA\nGRAVI: 1\nMINORI: 0\n", encoding="utf-8")
    verd_nv = tmp_path / "verd_nv.txt"
    verd_nv.write_text("senza intestazione\n", encoding="utf-8")

    # 0: non delicata + verdetto approvato + --json
    args = parser.parse_args(
        ["--file", str(toml), "--percorsi", str(percorsi_ok), "--verdetto", str(verd_ok), "--json"]
    )
    assert comando_categoria(args) == 0
    out_json = json.loads(capsys.readouterr().out)
    assert out_json["delicata"] is False
    assert out_json["categorie_toccate"] == ["documenti"]
    assert out_json["verdetto"]["approvato"] is True

    # 1: delicata per file fuori elenco
    args = parser.parse_args(["--file", str(toml), "--percorsi", str(percorsi_del)])
    assert comando_categoria(args) == 1
    capsys.readouterr()

    # 1: SICUREZZA nel verdetto
    args = parser.parse_args(["--file", str(toml), "--percorsi", str(percorsi_ok), "--verdetto", str(verd_sic)])
    assert comando_categoria(args) == 1
    capsys.readouterr()

    # 3: non delicata ma verdetto RILIEVI_GRAVI o non valido
    args = parser.parse_args(["--file", str(toml), "--percorsi", str(percorsi_ok), "--verdetto", str(verd_gravi)])
    assert comando_categoria(args) == 3
    capsys.readouterr()

    args = parser.parse_args(["--file", str(toml), "--percorsi", str(percorsi_ok), "--verdetto", str(verd_nv)])
    assert comando_categoria(args) == 3
    capsys.readouterr()

    # 2: configurazione mancante o file verdetto assente
    args = parser.parse_args(["--file", str(tmp_path / "mancante.toml"), "--percorsi", str(percorsi_ok)])
    assert comando_categoria(args) == 2
    capsys.readouterr()

    args = parser.parse_args(
        ["--file", str(toml), "--percorsi", str(percorsi_ok), "--verdetto", str(tmp_path / "manca.txt")]
    )
    assert comando_categoria(args) == 2
    capsys.readouterr()

    # Verifica predefinito --file
    assert parser.parse_args([]).file == PERCORSO_PREDEFINITO
    assert isinstance(Namespace(), Namespace)


def test_gravi_malformato_rende_il_verdetto_non_valido():
    for testo in (
        "VERDETTO: APPROVATO\nGRAVI: uno\nMINORI: 0\n",
        "VERDETTO: APPROVATO\nGRAVI: -1\nMINORI: 0\n",
        "VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: due\n",
        "VERDETTO: APPROVATO\nGRAVI:\nMINORI: 0\n",
    ):
        v = analizza_verdetto(testo)
        assert v.valido is False
        assert v.stato == "non_valido"
        assert v.approvato is False


def test_gravi_con_punto_finale_conta():
    v = analizza_verdetto("VERDETTO: APPROVATO\nGRAVI: 1.\nMINORI: 0\n")
    assert v.valido is True
    assert v.gravi == 1
    assert v.stato == "RILIEVI_GRAVI"
    assert v.approvato is False
    assert v.bloccante is True

    v2 = analizza_verdetto("VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 2.\n")
    assert v2.valido is True
    assert v2.minori == 2
    assert v2.approvato is True


def test_percorso_con_due_punti_e_delicato():
    categorie = {"documenti": ("docs/**",)}
    for percorso in ("docs/../segreto.py", "../docs/a.md"):
        esito = classifica_diff([percorso], categorie)
        assert esito.delicata is True
        assert percorso in esito.fuori_elenco
        assert any("percorso con .." in m for m in esito.motivi)
