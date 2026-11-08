"""Prove per i segni di chi decide (Compito B5.2)."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import pytest

from bottega.finta import BoardFinta
from bottega.porte import porta
from bottega.segno import (
    argomenti_segno,
    comando_segno,
    fine,
    inizio,
    porta_della_sessione,
)
from bottega.segni import nota


@pytest.fixture(autouse=True)
def isola_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    casa = tmp_path / "casa"
    casa.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(casa))
    for var in (
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_SESSION_ID",
        "ANTIGRAVITY_APP_DATA_DIR",
        "ANTIGRAVITY_CONVERSATION_ID",
        "PI_CODING_AGENT_SESSION_DIR",
        "PI_SESSION_FILE",
        "COPILOT_HOME",
        "COPILOT_AGENT_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    return casa


def _scrivi_trascrizione_claude(casa: Path, cartella: Path, sessione_id: str, tokens: int, ts_iso: str) -> Path:
    import re

    norm = re.sub(r"[^a-zA-Z0-9]", "-", str(cartella.resolve()))
    dest_dir = casa / ".claude" / "projects" / norm
    dest_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "type": "assistant",
        "timestamp": ts_iso,
        "message": {
            "usage": {
                "input_tokens": tokens,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }
        },
    }
    f = dest_dir / f"{sessione_id}.jsonl"
    f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return f


def _scrivi_trascrizione_antigravity(casa: Path, sessione_id: str, tokens: int, ts_iso: str) -> Path:
    dest_dir = casa / ".gemini" / "antigravity-cli" / "brain" / sessione_id / ".system_generated" / "logs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "created_at": ts_iso,
        "input_tokens": tokens,
        "output_tokens": 0,
        "cache_read_tokens": 0,
    }
    f = dest_dir / "transcript.jsonl"
    f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return f


def test_porta_della_sessione() -> None:
    # 1. Claude ha la precedenza
    env = {
        "CLAUDE_CODE_SESSION_ID": "s-claude",
        "ANTIGRAVITY_CONVERSATION_ID": "s-agy",
        "PI_SESSION_FILE": "/tmp/pi.jsonl",
        "COPILOT_AGENT_SESSION_ID": "s-copilot",
    }
    assert porta_della_sessione(env) == ("claude-code", "s-claude")

    # 2. Poi Antigravity
    del env["CLAUDE_CODE_SESSION_ID"]
    assert porta_della_sessione(env) == ("antigravity", "s-agy")

    # 3. Poi Pi (la sessione è il percorso)
    del env["ANTIGRAVITY_CONVERSATION_ID"]
    # Solo il nome del file: il percorso contiene la casa di chi decide (B5-R11).
    assert porta_della_sessione(env) == ("pi", "pi.jsonl")

    # 4. Poi Copilot
    del env["PI_SESSION_FILE"]
    assert porta_della_sessione(env) == ("copilot-cli", "s-copilot")

    # 5. Nessuna
    del env["COPILOT_AGENT_SESSION_ID"]
    assert porta_della_sessione(env) is None


def test_inizio_scrive_il_segno() -> None:
    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    adesso = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)

    avviso = inizio(board, 10, "claude-code", "sess-1", adesso)
    assert avviso is None

    lav = board.lavoro(10)
    assert lav is not None
    segno_val = lav.campi.get("Segno")
    assert segno_val is not None
    dati = nota(segno_val)
    assert dati["porta"] == "claude-code"
    assert dati["sessione"] == "sess-1"
    assert dati["inizio"] == adesso.isoformat()


def test_inizio_sopra_un_segno_aperto() -> None:
    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    t1 = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)
    inizio(board, 10, "claude-code", "sess-1", t1)

    t2 = datetime(2026, 11, 8, 14, 30, 0, tzinfo=timezone.utc)
    avviso = inizio(board, 10, "claude-code", "sess-2", t2)
    assert avviso is not None
    assert "già aperto" in avviso or "sostituito" in avviso

    lav = board.lavoro(10)
    assert lav is not None
    dati = nota(lav.campi.get("Segno"))
    assert dati["sessione"] == "sess-2"
    assert dati["inizio"] == t2.isoformat()


def test_fine_aggiunge_i_token(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    t_inizio = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)
    t_fine = datetime(2026, 11, 8, 15, 0, 0, tzinfo=timezone.utc)

    _scrivi_trascrizione_claude(casa, cartella, "sess-1", 150, "2026-11-08T14:30:00+00:00")

    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    board.campo(10, "Token di chi decide", 50)
    inizio(board, 10, "claude-code", "sess-1", t_inizio)

    env = {"HOME": str(casa)}
    p = porta("claude-code")
    aggiunti, msg = fine(board, 10, [(p, "sess-1")], cartella, env, t_fine)

    assert aggiunti == 150
    lav = board.lavoro(10)
    assert lav is not None
    assert lav.campi.get("Token di chi decide") == "200"
    assert lav.campi.get("Segno") is None


def test_fine_senza_segno_niente_numero(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)
    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")

    env = {"HOME": str(casa)}
    p = porta("claude-code")
    adesso = datetime.now(timezone.utc)
    aggiunti, msg = fine(board, 10, [(p, "sess-1")], cartella, env, adesso)

    assert aggiunti is None
    assert "nessun segno aperto" in msg
    lav = board.lavoro(10)
    assert lav is not None
    assert "Token di chi decide" not in lav.campi


def test_fine_trascrizione_assente_niente_numero(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)
    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    adesso = datetime.now(timezone.utc)
    inizio(board, 10, "claude-code", "sess-non-esiste", adesso)

    env = {"HOME": str(casa)}
    p = porta("claude-code")
    aggiunti, msg = fine(board, 10, [(p, "sess-non-esiste")], cartella, env, adesso)

    assert aggiunti is None
    assert "niente numero" in msg
    lav = board.lavoro(10)
    assert lav is not None
    assert "Token di chi decide" not in lav.campi


def test_segno_due_sessioni(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    t_inizio = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)
    t_fine = datetime(2026, 11, 8, 16, 0, 0, tzinfo=timezone.utc)

    # Prima sessione (all'inizio): 100 token
    f1 = _scrivi_trascrizione_claude(casa, cartella, "sess-1", 100, "2026-11-08T14:15:00+00:00")
    # Seconda sessione (alla fine): 150 token
    f2 = _scrivi_trascrizione_claude(casa, cartella, "sess-2", 150, "2026-11-08T15:15:00+00:00")

    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    inizio(board, 10, "claude-code", "sess-1", t_inizio)

    env = {"HOME": str(casa)}
    p = porta("claude-code")
    # Se passiamo sess-2 come corrente, più una ripetizione di sess-1: nessuna riga contata due volte
    aggiunti, msg = fine(board, 10, [(p, "sess-2"), (p, "sess-1")], cartella, env, t_fine)

    assert aggiunti == 250
    lav = board.lavoro(10)
    assert lav is not None
    assert lav.campi.get("Token di chi decide") == "250"
    assert lav.campi.get("Segno") is None


def test_fine_parziale_segna_misure_parziali(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    t_inizio = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)
    t_fine = datetime(2026, 11, 8, 15, 0, 0, tzinfo=timezone.utc)

    _scrivi_trascrizione_antigravity(casa, "conv-1", 300, "2026-11-08T14:20:00+00:00")

    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")
    board.campo(10, "Misure parziali", "Durata")
    inizio(board, 10, "antigravity", "conv-1", t_inizio)

    env = {"HOME": str(casa)}
    p = porta("antigravity")
    aggiunti, msg = fine(board, 10, [(p, "conv-1")], cartella, env, t_fine)

    assert aggiunti == 300
    lav = board.lavoro(10)
    assert lav is not None
    parziali = [s.strip() for s in lav.campi.get("Misure parziali", "").split(",")]
    assert "Durata" in parziali
    assert "Token di chi decide" in parziali
    assert parziali.count("Token di chi decide") == 1


def test_comando_segno_codici(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cartella)

    board = BoardFinta()
    board.aggiungi(10, titolo="Compito 10")

    parser = argparse.ArgumentParser()
    argomenti_segno(parser)

    # 1. Uso sbagliato: codice 2 (niente azione o numero non intero)
    args_err = parser.parse_args(["inizio", "dieci"]) if False else argparse.Namespace(azione="sconosciuta", numero=10)
    assert comando_segno(args_err, board=board) == 2

    # 2. Inizio con successo: codice 0
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-cli")
    _scrivi_trascrizione_claude(casa, cartella, "sess-cli", 40, "2026-11-08T14:10:00+00:00")

    args_inizio = parser.parse_args(["inizio", "10"])
    res_inizio = comando_segno(args_inizio, board=board)
    assert res_inizio == 0
    assert board.lavoro(10).campi.get("Segno") is not None

    # 3. Fine con successo: codice 0. Il messaggio sta fra l'inizio (adesso) e la fine: B5-R11 vuole almeno un
    # messaggio nell'intervallo, altrimenti niente numero.
    from datetime import datetime as _dt, timezone as _tz

    _scrivi_trascrizione_claude(
        casa, cartella, "sess-cli", 40, _dt.now(_tz.utc).isoformat()
    )
    args_fine = parser.parse_args(["fine", "10"])
    res_fine = comando_segno(args_fine, board=board)
    assert res_fine == 0
    assert board.lavoro(10).campi.get("Token di chi decide") is not None

    # 4. Fine senza segno: codice 1 (niente numero, motivo su stderr)
    args_fine_vuoto = parser.parse_args(["fine", "10"])
    res_fine_vuoto = comando_segno(args_fine_vuoto, board=board)
    assert res_fine_vuoto == 1
    err = capsys.readouterr().err
    assert "niente numero" in err
