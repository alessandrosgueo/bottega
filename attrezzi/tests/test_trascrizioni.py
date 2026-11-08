"""Prove per la lettura delle trascrizioni delle quattro porte (Compito B5.2)."""

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from bottega.porte import Token, porta
from bottega.porte.antigravity import Antigravity
from bottega.porte.claude_code import ClaudeCode
from bottega.porte.copilot_cli import CopilotCli
from bottega.porte.pi import Pi


@pytest.fixture(autouse=True)
def isola_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola l'ambiente di prova con HOME finta in tmp_path."""
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


def _prepara_file_porta(
    nome_porta: str,
    casa: Path,
    cartella: Path,
    sessione_id: str,
    linee_json: list[dict],
) -> Path:
    """Crea una trascrizione finta nella posizione convenzionale della porta."""
    testo = "\n".join(json.dumps(r) for r in linee_json) + "\n"

    if nome_porta == "claude-code":
        # Normalizzazione cartella: caratteri non alfanumerici -> '-'
        import re

        norm = re.sub(r"[^a-zA-Z0-9]", "-", str(cartella.resolve()))
        dest_dir = casa / ".claude" / "projects" / norm
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / f"{sessione_id}.jsonl"
        file_path.write_text(testo, encoding="utf-8")
        return file_path

    if nome_porta == "antigravity":
        dest_dir = casa / ".gemini" / "antigravity-cli" / "brain" / sessione_id / ".system_generated" / "logs"
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / "transcript.jsonl"
        file_path.write_text(testo, encoding="utf-8")
        return file_path

    if nome_porta == "pi":
        import re

        s = str(cartella.resolve()).lstrip("/\\")
        s = re.sub(r"[/\\:]", "-", s)
        dest_dir = casa / ".pi" / "agent" / "sessions" / f"--{s}--"
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / f"2026-11-08T10-00-00_{sessione_id}.jsonl"
        file_path.write_text(testo, encoding="utf-8")
        return file_path

    if nome_porta == "copilot-cli":
        dest_dir = casa / ".copilot" / "session-state" / sessione_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = dest_dir / "workspace.yaml"
        yaml_path.write_text(f"cwd: {cartella.resolve()}\n", encoding="utf-8")
        file_path = dest_dir / "events.jsonl"
        file_path.write_text(testo, encoding="utf-8")
        return file_path

    raise ValueError(f"porta non supportata nel helper: {nome_porta}")


def _linea_buona(nome_porta: str, ts_iso: str, tokens: int) -> dict:
    """Genera un record valido con l'orario e il numero di token indicato."""
    if nome_porta == "claude-code":
        return {
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
    if nome_porta == "antigravity":
        return {
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "created_at": ts_iso,
            "input_tokens": tokens,
            "output_tokens": 0,
            "cache_read_tokens": 0,
        }
    if nome_porta == "pi":
        return {
            "type": "message",
            "role": "assistant",
            "timestamp": ts_iso,
            "usage": {
                "input": tokens,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
            },
        }
    if nome_porta == "copilot-cli":
        return {
            "type": "assistant.usage",
            "timestamp": ts_iso,
            "data": {
                "inputTokens": tokens,
                "outputTokens": 0,
                "cacheReadTokens": 0,
                "cacheWriteTokens": 0,
            },
        }
    raise ValueError(nome_porta)


PORTE = ["claude-code", "antigravity", "pi", "copilot-cli"]


@pytest.mark.parametrize("nome_porta", PORTE)
def test_trascrizione_dalla_variabile(nome_porta: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)
    sess_id = "sess-123"

    f = _prepara_file_porta(nome_porta, casa, cartella, sess_id, [])

    p = porta(nome_porta)
    env: dict[str, str] = {"HOME": str(casa)}
    if nome_porta == "claude-code":
        env["CLAUDE_CODE_SESSION_ID"] = sess_id
    elif nome_porta == "antigravity":
        env["ANTIGRAVITY_CONVERSATION_ID"] = sess_id
    elif nome_porta == "pi":
        env["PI_SESSION_FILE"] = str(f)
    elif nome_porta == "copilot-cli":
        env["COPILOT_AGENT_SESSION_ID"] = sess_id

    trovato = p.trascrizione(env, cartella)
    assert trovato is not None
    assert trovato.resolve() == f.resolve()


@pytest.mark.parametrize("nome_porta", PORTE)
def test_trascrizione_di_riserva_la_piu_recente(nome_porta: str, tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    f1 = _prepara_file_porta(nome_porta, casa, cartella, "sess-vecchia", [])
    f2 = _prepara_file_porta(nome_porta, casa, cartella, "sess-nuova", [])

    os.utime(f1, (1000, 1000))
    os.utime(f2, (2000, 2000))

    p = porta(nome_porta)
    env = {"HOME": str(casa)}
    trovato = p.trascrizione(env, cartella)
    assert trovato is not None
    assert trovato.resolve() == f2.resolve()


@pytest.mark.parametrize("nome_porta", PORTE)
def test_trascrizione_assente(nome_porta: str, tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    p = porta(nome_porta)
    env = {"HOME": str(casa)}
    trovato = p.trascrizione(env, cartella, sessione="non-esiste")
    assert trovato is None


@pytest.mark.parametrize("nome_porta", PORTE)
def test_token_somma_nell_intervallo(nome_porta: str, tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    dopo = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    fino = datetime(2026, 11, 8, 13, 0, 0, tzinfo=timezone.utc)

    linee = [
        _linea_buona(nome_porta, "2026-11-08T11:59:59+00:00", 10),
        _linea_buona(nome_porta, "2026-11-08T12:00:00+00:00", 25),
        _linea_buona(nome_porta, "2026-11-08T12:30:00+00:00", 35),
        _linea_buona(nome_porta, "2026-11-08T13:00:00+00:00", 40),
        _linea_buona(nome_porta, "2026-11-08T13:00:01+00:00", 50),
    ]
    f = _prepara_file_porta(nome_porta, casa, cartella, "sess-intervallo", linee)

    p = porta(nome_porta)
    tok = p.token(f, dopo, fino)
    # Contano solo quelle a 12:00:00, 12:30:00 e 13:00:00 (estremi inclusi) = 25 + 35 + 40 = 100
    assert tok.totale == 100


@pytest.mark.parametrize("nome_porta", PORTE)
def test_token_righe_rotte(nome_porta: str, tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    dopo = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    fino = datetime(2026, 11, 8, 13, 0, 0, tzinfo=timezone.utc)

    # 1. Riga buona dentro
    r1 = _linea_buona(nome_porta, "2026-11-08T12:10:00+00:00", 50)
    # 2. Orario senza fuso (vale UTC: deve essere conteggiata)
    r2_semza_fuso = _linea_buona(nome_porta, "2026-11-08T12:20:00", 30)
    # 3. Senza orario
    r3_no_ts = _linea_buona(nome_porta, "2026-11-08T12:20:00", 100)
    if "timestamp" in r3_no_ts:
        del r3_no_ts["timestamp"]
    if "created_at" in r3_no_ts:
        del r3_no_ts["created_at"]
    # 4. Contatore testo (deve essere saltata)
    r4_testo = _linea_buona(nome_porta, "2026-11-08T12:30:00+00:00", 999)
    if nome_porta == "claude-code":
        r4_testo["message"]["usage"]["input_tokens"] = "non-numero"
    elif nome_porta == "antigravity":
        r4_testo["input_tokens"] = "non-numero"
    elif nome_porta == "pi":
        r4_testo["usage"]["input"] = "non-numero"
    elif nome_porta == "copilot-cli":
        r4_testo["data"]["inputTokens"] = "non-numero"

    corpo = (
        "\n"  # riga vuota
        + json.dumps(r1)
        + "\n"
        + "{json non valido riga spezzata\n"  # JSON rotto
        + json.dumps(r2_semza_fuso)
        + "\n"
        + json.dumps(r3_no_ts)
        + "\n"
        + json.dumps(r4_testo)
        + "\n"
        + "   \n"  # altra riga vuota
    )

    f = _prepara_file_porta(nome_porta, casa, cartella, "sess-rotte", [])
    f.write_text(corpo, encoding="utf-8")

    p = porta(nome_porta)
    tok = p.token(f, dopo, fino)
    # Devono essere conteggiate r1 (50) e r2_semza_fuso (30) = 80
    assert tok.totale == 80


def test_antigravity_parziale(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)
    dopo = datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc)
    fino = datetime(2026, 11, 8, 23, 59, 59, tzinfo=timezone.utc)

    for nome in PORTE:
        rec = [_linea_buona(nome, "2026-11-08T12:00:00+00:00", 10)]
        f = _prepara_file_porta(nome, casa, cartella, f"sess-{nome}", rec)
        p = porta(nome)
        tok = p.token(f, dopo, fino)
        if nome == "antigravity":
            assert tok.parziale is True
        else:
            assert tok.parziale is False


def test_claude_sessione_in_un_altro_progetto(tmp_path, monkeypatch):
    """B5: con l'id della sessione la trascrizione si trova anche se la cartella corrente è un'altra (un worktree)."""
    from bottega.porte import porta

    casa = tmp_path / "casa"
    progetto = casa / ".claude" / "projects" / "-cartella-di-partenza"
    progetto.mkdir(parents=True)
    file_sessione = progetto / "abc-123.jsonl"
    file_sessione.write_text("", encoding="utf-8")
    altra = tmp_path / "worktree"
    altra.mkdir()
    env = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "abc-123"}
    assert porta("claude-code").trascrizione(env, altra) == file_sessione
    assert porta("claude-code").trascrizione({"HOME": str(casa)}, altra, sessione="../x") is None


def test_claude_un_usage_per_messaggio_e_cache_pesata(tmp_path):
    """B5-R5: i record dello stesso messaggio contano una volta; una lettura dalla cache vale un decimo."""
    import json as _json
    from datetime import datetime, timezone
    from bottega.porte import porta

    usage = {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5}
    righe = [
        {"type": "assistant", "timestamp": "2026-11-08T10:00:00Z", "message": {"id": "m1", "usage": usage}},
        {"type": "assistant", "timestamp": "2026-11-08T10:00:01Z", "message": {"id": "m1", "usage": usage}},
        {"type": "assistant", "timestamp": "2026-11-08T10:00:02Z", "message": {"id": "m2", "usage": usage}},
    ]
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(_json.dumps(r) for r in righe) + "\n", encoding="utf-8")
    t = porta("claude-code").token(
        f, datetime(2026, 11, 8, 9, tzinfo=timezone.utc), datetime(2026, 11, 8, 11, tzinfo=timezone.utc)
    )
    # Due messaggi, ognuno 10 + 100 + 1000 * 0,1 + 5 = 215.
    assert t.totale == 430


def test_somma_pesata():
    from bottega.porte import somma_pesata

    assert somma_pesata({"a": 10, "c": 1000}, ("a", "b", "c"), cache_letta="c") == 110
    assert somma_pesata({"a": "10"}, ("a",), cache_letta="c") is None


def test_c1_pi_segno_solo_nome(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "lavoro"
    cartella.mkdir(parents=True, exist_ok=True)

    nome_file = "2026-11-08T10-00-00_test-sessione.jsonl"
    sess_dir = casa / ".pi" / "agent" / "sessions" / "--qualsiasi--"
    sess_dir.mkdir(parents=True, exist_ok=True)
    file_pi = sess_dir / nome_file
    file_pi.write_text("{}", encoding="utf-8")

    env = {"HOME": str(casa)}
    p = porta("pi")
    assert p.trascrizione(env, cartella, sessione=nome_file) == file_pi
    assert p.trascrizione(env, cartella, sessione="../x") is None

