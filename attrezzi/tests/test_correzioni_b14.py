"""Prove per le correzioni della revisione finale di B14 (G1, G2, G3, M1)."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bottega.board import BoardProject, ErroreBoard, Lavoro
from bottega.conti import _ha_misura, comando_conti, conti
from bottega.correggi import argomenti_correggi, comando_correggi
from bottega.finta import BoardFinta, ForgiaFinta
import bottega.forgia as forgia_mod
from bottega.forgia import ErroreForgia, ForgiaGh, Issue
from bottega.lancio import comando_lancia, comando_segui
from bottega.segni import scrivi_nota
from bottega.segno import tocca


# --- G1: il repo vuoto ---


def test_repo_della_cartella_esegui_e_errore() -> None:
    def esegui_ok(args: list[str]) -> str:
        assert args == ["repo", "view", "--json", "nameWithOwner"]
        return json.dumps({"nameWithOwner": "prop/repo-locale"})

    assert forgia_mod.repo_della_cartella(esegui=esegui_ok) == "prop/repo-locale"

    def esegui_vuoto(args: list[str]) -> str:
        return json.dumps({})

    with pytest.raises(ErroreForgia):
        forgia_mod.repo_della_cartella(esegui=esegui_vuoto)


def test_repo_del_comando_tre_casi(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate = 0

    def finto_repo_cartella() -> str:
        nonlocal chiamate
        chiamate += 1
        return "prop/da-cartella"

    monkeypatch.setattr(forgia_mod, "repo_della_cartella", finto_repo_cartella)

    # 1. Da argomento: non chiama repo_della_cartella
    assert forgia_mod.repo_del_comando("prop/da-arg", {"GITHUB_REPOSITORY": "prop/da-env"}) == "prop/da-arg"
    assert chiamate == 0

    # 2. Da variabile d'ambiente: non chiama repo_della_cartella
    assert forgia_mod.repo_del_comando(None, {"GITHUB_REPOSITORY": "prop/da-env"}) == "prop/da-env"
    assert forgia_mod.repo_del_comando("", {"GITHUB_REPOSITORY": "prop/da-env"}) == "prop/da-env"
    assert chiamate == 0

    # 3. Senza argomento né variabile: chiama repo_della_cartella una volta
    assert forgia_mod.repo_del_comando(None, {}) == "prop/da-cartella"
    assert chiamate == 1


def test_board_project_repo_vuoto_non_scarta_elementi() -> None:
    graphql = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "title": "Bottega Project",
                    "fields": {
                        "nodes": [
                            {"id": "F_BOTTEGA", "name": "Bottega", "dataType": "SINGLE_SELECT", "options": [{"id": "O1", "name": "pronto"}]},
                            {"id": "F_ESITO", "name": "Esito", "dataType": "SINGLE_SELECT", "options": []},
                            {"id": "F_ESECUTORE", "name": "Esecutore", "dataType": "TEXT"},
                            {"id": "F_NOTA", "name": "Nota del giro", "dataType": "TEXT"},
                        ]
                    },
                    "items": {
                        "nodes": [
                            {
                                "id": "ITEM_1",
                                "content": {
                                    "number": 10,
                                    "title": "Compito 10",
                                    "repository": {"nameWithOwner": "prop/repo-uno"},
                                    "labels": {"nodes": []},
                                },
                                "fieldValues": {"nodes": [{"field": {"name": "Bottega"}, "name": "pronto"}]},
                            },
                            {
                                "id": "ITEM_2",
                                "content": {
                                    "number": 20,
                                    "title": "Compito 20",
                                    "repository": {"nameWithOwner": "prop/repo-due"},
                                    "labels": {"nodes": []},
                                },
                                "fieldValues": {"nodes": [{"field": {"name": "Bottega"}, "name": "pronto"}]},
                            },
                        ]
                    },
                }
            }
        }
    }

    board = BoardProject(
        proprietario="prop",
        numero=1,
        repo="",
        esegui=lambda args, ing=None: json.dumps(graphql),
    )
    assert board.repo is None
    assert [l.numero for l in board.elenco()] == [10, 20]


_CFG_MINIMA = """versione = 1

[progetto]
fuso = "Europe/Rome"
project = 7

[botteghe.principale]
quota = "scarsa"
porte = ["claude-code"]

[candidati.maestro]
nome = "Maestro"
bottega = "principale"
porta = "claude-code"
modello = "modello"
funzioni = ["decidere"]
"""


def test_comando_correggi_senza_repo_e_senza_env_usa_repo_della_cartella(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(_CFG_MINIMA, encoding="utf-8")

    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_CONVERSATION_ID", raising=False)
    monkeypatch.delenv("PI_SESSION_FILE", raising=False)
    monkeypatch.delenv("COPILOT_AGENT_SESSION_ID", raising=False)

    monkeypatch.setattr(forgia_mod, "repo_della_cartella", lambda: "prop/rilevato")

    chiamate_gh: list[list[str]] = []

    def finto_esegui_forgia(self: ForgiaGh, argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate_gh.append(argomenti)
        if argomenti[:2] == ["issue", "view"]:
            return json.dumps({
                "number": 10,
                "title": "Lavoro",
                "body": "Testo\n\n## Fatto quando\n\n```bash\necho ok\n```\n",
                "state": "OPEN",
                "labels": [],
                "author": {"login": "prop"},
            })
        if argomenti[:4] == ["api", "-X", "POST", "repos/prop/rilevato/issues"]:
            return json.dumps({"number": 99, "id": 9900})
        if argomenti[:4] == ["api", "-X", "POST", "repos/prop/rilevato/issues/10/sub_issues"]:
            return json.dumps({})
        raise AssertionError(f"chiamata ForgiaGh inattesa: {argomenti}")

    graphql_board = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "title": "P",
                    "fields": {
                        "nodes": [
                            {"id": "F_B", "name": "Bottega", "dataType": "SINGLE_SELECT", "options": [{"id": "O_P", "name": "pronto"}]},
                            {"id": "F_E", "name": "Esito", "dataType": "SINGLE_SELECT", "options": [{"id": "O_C", "name": "correzioni"}]},
                            {"id": "F_ESEC", "name": "Esecutore", "dataType": "TEXT"},
                            {"id": "F_NOTA", "name": "Nota del giro", "dataType": "TEXT"},
                            {"id": "F_EC", "name": "Esito del compito", "dataType": "SINGLE_SELECT", "options": [{"id": "O_OK", "name": "corretto"}]},
                        ]
                    },
                    "items": {
                        "nodes": [
                            {
                                "id": "ITEM_10",
                                "content": {"number": 10, "title": "Lavoro", "state": "OPEN", "repository": {"nameWithOwner": "prop/rilevato"}, "labels": {"nodes": []}},
                                "fieldValues": {"nodes": [{"field": {"name": "Bottega"}, "name": "pronto"}]},
                            }
                        ]
                    },
                }
            }
        }
    }

    def finto_esegui_board(self: BoardProject, argomenti: list[str], ingresso: str | None = None) -> str:
        if argomenti[:2] == ["project", "item-add"]:
            return ""
        if argomenti[:2] == ["api", "graphql"] and "updateProjectV2ItemFieldValue" in str(argomenti):
            return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM_10"}}}})
        if argomenti[:2] == ["api", "graphql"]:
            return json.dumps(graphql_board)
        raise AssertionError(f"chiamata BoardProject inattesa: {argomenti}")

    monkeypatch.setattr(ForgiaGh, "_esegui_di_serie", finto_esegui_forgia)
    monkeypatch.setattr(BoardProject, "_esegui_di_serie", finto_esegui_board)

    parser = argparse.ArgumentParser()
    argomenti_correggi(parser)
    args = parser.parse_args(["10", "--testo", "Sistema il bug", "--configurazione", str(cfg_file)])
    rc = comando_correggi(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "99" in out
    assert any(c[:4] == ["api", "-X", "POST", "repos/prop/rilevato/issues"] for c in chiamate_gh)


def test_comando_correggi_e_segui_catturano_errore_forgia_su_costruzione_board(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(_CFG_MINIMA, encoding="utf-8")

    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(forgia_mod, "repo_della_cartella", lambda: "prop/repo")
    monkeypatch.setattr(ForgiaGh, "proprietario", lambda self: (_ for _ in ()).throw(ErroreForgia("boom forgia")))

    parser = argparse.ArgumentParser()
    argomenti_correggi(parser)
    args_corr = parser.parse_args(["10", "--testo", "Fix", "--configurazione", str(cfg_file)])
    rc_corr = comando_correggi(args_corr)
    assert rc_corr == 1
    assert "boom forgia" in capsys.readouterr().err

    args_segui = argparse.Namespace(
        numero=10,
        repo=None,
        intervallo=1,
        fermo=10.0,
        tetto=60.0,
        configurazione=cfg_file,
    )
    rc_segui = comando_segui(args_segui)
    assert rc_segui == 1
    assert "boom forgia" in capsys.readouterr().err


def test_fallimento_repo_della_cartella_non_cambia_esito_di_lancia_segui_conti(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-1")
    monkeypatch.setattr(forgia_mod, "repo_della_cartella", lambda: (_ for _ in ()).throw(ErroreForgia("no gh")))

    board = BoardFinta([Lavoro(numero=10, titolo="Lavoro", stato="consegnato")])

    # segui: board data, forgia None -> stampa segno: ... su stderr, esito 0 (finito)
    args_segui = argparse.Namespace(numero=10, repo=None, intervallo=1, fermo=10.0, tetto=60.0)
    rc_segui = comando_segui(
        args_segui,
        esegui=lambda cmd, env=None: (0, "[]"),
        board=board,
    )
    assert rc_segui == 0
    captured = capsys.readouterr()
    assert "finito" in captured.out
    assert "segno:" in captured.err

    # conti: board data, forgia None -> stampa segno: ... su stderr, esito 0
    args_conti = argparse.Namespace(json=True, repo=None)
    rc_conti = comando_conti(args_conti, board=board)
    assert rc_conti == 0
    captured = capsys.readouterr()
    assert "per_candidato" in captured.out
    assert "segno:" in captured.err

    # lancia: board data, forgia None -> stampa segno: ... su stderr, esito 0
    def esegui_lancia(cmd: list[str], env=None) -> tuple[int, str]:
        if cmd[:3] == ["gh", "issue", "view"]:
            return 0, json.dumps({"labels": []})
        if cmd[:3] == ["gh", "issue", "edit"]:
            return 0, ""
        if cmd[:3] == ["gh", "run", "list"]:
            return 0, json.dumps([{"databaseId": 1, "createdAt": "2026-11-14T08:00:00+00:00"}])
        if cmd[:3] == ["gh", "run", "view"] and "--json" in cmd:
            return 0, json.dumps({"status": "completed", "conclusion": "success"})
        if cmd[:3] == ["gh", "run", "view"] and "--log" in cmd:
            return 0, "lavoro 10: avviato\n"
        return 0, ""

    orologio_t = [datetime(2026, 11, 14, 8, 0, 0, tzinfo=timezone.utc)]
    rc_lancia = comando_lancia(
        argparse.Namespace(numero=10, repo=None, attesa=30, tetto=60),
        esegui=esegui_lancia,
        dormi=lambda _: None,
        adesso=lambda: orologio_t[0],
        board=board,
    )
    assert rc_lancia == 0
    captured = capsys.readouterr()
    assert "avviato" in captured.out
    assert "segno:" in captured.err


# --- G2: bottega conti ignora madre col solo Segno (e Misure parziali da sola) ---


def test_conti_ignora_madre_con_solo_segno_e_misure_parziali() -> None:
    madre = Lavoro(
        numero=1,
        titolo="Madre",
        stato="in corso",
        esecutore="Lavorante",
        campi={"Segno": "porta=claude-code; sessione=s1; inizio=2026-11-14T08:00:00+00:00"},
    )
    solo_parziale = Lavoro(
        numero=2,
        titolo="Altro solo parziale",
        stato="in corso",
        esecutore="Lavorante",
        campi={"Misure parziali": "Token di chi decide"},
    )
    assert not _ha_misura(madre)
    assert not _ha_misura(solo_parziale)

    lavori = [
        madre,
        solo_parziale,
        Lavoro(
            numero=11,
            titolo="Compito 1",
            stato="consegnato",
            esecutore="Lavorante",
            campi={
                "Dove": "fuori",
                "Esecutore": "Lavorante",
                "Giri": "1",
                "Durata": "100",
                "Token esecutore": "10000",
            },
        ),
        Lavoro(
            numero=12,
            titolo="Compito 2",
            stato="consegnato",
            esecutore="Lavorante",
            campi={
                "Dove": "fuori",
                "Esecutore": "Lavorante",
                "Giri": "1",
                "Durata": "100",
                "Token esecutore": "10000",
            },
        ),
    ]
    ris = conti(lavori)
    cand = ris["per_candidato"]["Lavorante"]
    assert cand["compiti"] == 2
    assert cand["giri_medi"] == 1.0
    assert cand["durata_media"] == 100.0


# --- G3: tocca non apre un secondo segno se la chiusura del primo fallisce ---


def test_tocca_non_apre_secondo_segno_se_chiusura_primo_fallisce(tmp_path: Path) -> None:
    adesso = datetime(2026, 11, 14, 9, 0, 0, tzinfo=timezone.utc)
    segno_10 = scrivi_nota({
        "porta": "claude-code",
        "sessione": "s1",
        "inizio": "2026-11-14T08:00:00+00:00",
    })
    board = BoardFinta([
        Lavoro(numero=10, titolo="Primo", stato="in corso", campi={"Segno": segno_10}),
        Lavoro(numero=20, titolo="Secondo", stato="pronto"),
    ])

    class _ForgiaSottoIssueRotta(ForgiaFinta):
        def sotto_issue(self, n: int) -> list[Issue]:
            if n == 10:
                raise ErroreForgia("errore sotto_issue 10")
            return super().sotto_issue(n)

    forgia = _ForgiaSottoIssueRotta([Issue(10, "Primo"), Issue(20, "Secondo")])
    env = {"CLAUDE_CODE_SESSION_ID": "s1"}

    righe = tocca(board, forgia, 20, env, tmp_path, adesso)

    lav_20 = board.lavoro(20)
    lav_10 = board.lavoro(10)
    assert lav_20 is not None and not lav_20.campi.get("Segno")
    assert lav_10 is not None and lav_10.campi.get("Segno") == segno_10
    assert "segno: #20: non aperto, il segno su #10 è ancora aperto" in righe


# --- M1: BoardFinta conserva aperta ---


def test_board_finta_conserva_aperta() -> None:
    board = BoardFinta([
        Lavoro(numero=1, titolo="Aperto"),
        Lavoro(numero=2, titolo="Chiuso", aperta=False),
    ])
    lav1 = board.lavoro(1)
    lav2 = board.lavoro(2)
    assert lav1 is not None and lav1.aperta is True
    assert lav2 is not None and lav2.aperta is False
    assert [(l.numero, l.aperta) for l in board.elenco()] == [(1, True), (2, False)]
