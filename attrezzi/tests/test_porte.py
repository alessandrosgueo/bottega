"""Prove del pacchetto `bottega.porte`: Claude Code, Antigravity, Pi e Copilot CLI.

Nessuna CLI vera viene mai eseguita nelle prove: ogni prova scrive uno script Python eseguibile
in `tmp_path` che simula l'uscita della porta e registra gli argomenti ricevuti.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import stat
import sys
import pytest

from bottega import configurazione
from bottega.porte import (
    Controllo,
    Lancio,
    Porta,
    porta,
    ambiente_ripulito,
    costruisci_comando,
)
from bottega.porte.claude_code import ClaudeCode, parse_rinnovo_claude
from bottega.porte.antigravity import Antigravity
from bottega.porte.pi import Pi
from bottega.porte.copilot_cli import CopilotCli


def _crea_script_finto(tmp_path: Path, nome: str, corpo_python: str) -> Path:
    """Crea uno script eseguibile in `tmp_path` con l'intestazione python3."""
    percorso = tmp_path / nome
    testo = f"#!/usr/bin/env python3\n{corpo_python}\n"
    percorso.write_text(testo, encoding="utf-8")
    percorso.chmod(percorso.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR)
    return percorso


def test_porta_nomi_validi_e_sconosciuti(tmp_path: Path) -> None:
    """La funzione `porta` accetta tutti e soli i nomi di `configurazione.PORTE`."""
    assert configurazione.PORTE == ("claude-code", "antigravity", "pi", "copilot-cli")

    p1 = porta("claude-code")
    assert isinstance(p1, ClaudeCode)
    assert p1.nome == "claude-code"
    assert p1.eseguibile == "claude"

    p2 = porta("antigravity")
    assert isinstance(p2, Antigravity)
    assert p2.nome == "antigravity"
    assert p2.eseguibile == "agy"

    p3 = porta("pi")
    assert isinstance(p3, Pi)
    assert p3.nome == "pi"
    assert p3.eseguibile == "pi"

    p4 = porta("copilot-cli")
    assert isinstance(p4, CopilotCli)
    assert p4.nome == "copilot-cli"
    assert p4.eseguibile == "copilot"

    # Con eseguibile personalizzato
    finto = str(tmp_path / "mio-bin")
    p_pers = porta("claude-code", eseguibile=finto)
    assert p_pers.eseguibile == finto

    with pytest.raises(ValueError, match="porta sconosciuta"):
        porta("porta-non-esistente")


def test_b6_porta_dalla_variabile(monkeypatch: pytest.MonkeyPatch) -> None:
    """B6: se manca eseguibile, la fabbrica legge BOTTEGA_PORTA_<NOME> dall'ambiente."""
    monkeypatch.setenv("BOTTEGA_PORTA_CLAUDE_CODE", "/opt/bin/mio-claude")
    monkeypatch.setenv("BOTTEGA_PORTA_ANTIGRAVITY", "/opt/bin/mio-agy")
    monkeypatch.setenv("BOTTEGA_PORTA_PI", "/opt/bin/mio-pi")
    monkeypatch.setenv("BOTTEGA_PORTA_COPILOT_CLI", "/opt/bin/mio-copilot")

    p1 = porta("claude-code")
    assert p1.eseguibile == "/opt/bin/mio-claude"

    p2 = porta("antigravity")
    assert p2.eseguibile == "/opt/bin/mio-agy"

    p3 = porta("pi")
    assert p3.eseguibile == "/opt/bin/mio-pi"

    p4 = porta("copilot-cli")
    assert p4.eseguibile == "/opt/bin/mio-copilot"

    # L'argomento esplicito vince sulla variabile d'ambiente
    p_espl = porta("claude-code", eseguibile="/usr/bin/claude-esplicito")
    assert p_espl.eseguibile == "/usr/bin/claude-esplicito"


def test_controlla_eseguibile_assente(tmp_path: Path) -> None:
    """`controlla()` con l'eseguibile assente restituisce ok=False col motivo, mai eccezioni."""
    assente = str(tmp_path / "non_esiste_affatto")
    for nome in configurazione.PORTE:
        p = porta(nome, eseguibile=assente)
        c = p.controlla()
        assert isinstance(c, Controllo)
        assert c.ok is False
        assert c.versione is None
        assert c.motivo is not None
        assert "non trovato" in c.motivo.lower() or "no such" in c.motivo.lower()


def test_controlla_eseguibile_presente(tmp_path: Path) -> None:
    """`controlla()` esegue `--version` e restituisce la versione se l'uscita è 0."""
    script = _crea_script_finto(
        tmp_path,
        "finto_versione.py",
        """
import sys
if "--version" in sys.argv:
    print("1.2.3 (finto)")
    sys.exit(0)
sys.exit(1)
""",
    )
    p = porta("claude-code", eseguibile=str(script))
    c = p.controlla()
    assert c.ok is True
    assert c.versione == "1.2.3 (finto)"
    assert c.motivo is None


def test_controlla_eseguibile_ambiente_ripulito_senza_gh_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attacco 11: `controlla()` con un falso eseguibile che scrive su file il suo ambiente (non deve contenere GH_TOKEN)."""
    env_dump = tmp_path / "ambiente.json"
    script = _crea_script_finto(
        tmp_path,
        "falso_dump_env.py",
        f"""
import json, os, sys
with open({repr(str(env_dump))}, "w") as f:
    json.dump(dict(os.environ), f)
if "--version" in sys.argv:
    print("1.0.0")
    sys.exit(0)
sys.exit(1)
""",
    )
    monkeypatch.setenv("GH_TOKEN", "finto")
    monkeypatch.setenv("BOTTEGA_TOKEN", "finto")
    p = porta("claude-code", eseguibile=str(script))
    c = p.controlla()
    assert c.ok is True
    import json
    dumped = json.loads(env_dump.read_text(encoding="utf-8"))
    assert "GH_TOKEN" not in dumped
    assert "BOTTEGA_TOKEN" not in dumped


def test_controlla_eseguibile_con_prefisso(tmp_path: Path) -> None:
    """RV9: `controlla()` gira col prefisso."""
    out_file = tmp_path / "prefisso_ok.txt"
    script = _crea_script_finto(
        tmp_path,
        "falso_prefisso.py",
        f"""
import sys
if "--version" in sys.argv:
    print("2.0.0")
    sys.exit(0)
sys.exit(1)
""",
    )
    prefisso = ["sh", "-c", f"touch {out_file} && exec \"$@\"", "--"]
    p = porta("antigravity", eseguibile=str(script))
    c = p.controlla(prefisso=prefisso)
    assert c.ok is True
    assert c.versione == "2.0.0"
    assert out_file.exists()




def test_controlla_eseguibile_errore(tmp_path: Path) -> None:
    """`controlla()` con uscita diversa da 0 restituisce ok=False col messaggio."""
    script = _crea_script_finto(
        tmp_path,
        "finto_errore.py",
        """
import sys
sys.stderr.write("errore interno fatale\\n")
sys.exit(2)
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    c = p.controlla()
    assert c.ok is False
    assert c.versione is None
    assert c.motivo is not None
    assert "errore interno fatale" in c.motivo


def test_ambiente_ripulito() -> None:
    """L'ambiente ripulito include solo le variabili ammesse (elenco esplicito e LC_*)."""
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/utente",
        "USER": "utente",
        "LOGNAME": "utente",
        "SHELL": "/bin/bash",
        "LANG": "it_IT.UTF-8",
        "LANGUAGE": "it_IT",
        "TERM": "xterm-256color",
        "TMPDIR": "/tmp",
        "TZ": "UTC",
        "LC_ALL": "it_IT.UTF-8",
        "LC_CTYPE": "it_IT.UTF-8",
        "GH_TOKEN": "segreto-gh",
        "BOTTEGA_TOKEN": "segreto-bottega",
        "GITHUB_TOKEN": "segreto-github",
        "ACTIONS_RUNTIME_TOKEN": "segreto-actions",
        "QUALCOSA_SECRET": "segreto-ignoto",
        "ALTRA_VARIABILE": "valore-scartato",
    }
    pulito = ambiente_ripulito(base)
    assert "GH_TOKEN" not in pulito
    assert "BOTTEGA_TOKEN" not in pulito
    assert "GITHUB_TOKEN" not in pulito
    assert "ACTIONS_RUNTIME_TOKEN" not in pulito
    assert "QUALCOSA_SECRET" not in pulito
    assert "ALTRA_VARIABILE" not in pulito
    assert pulito["PATH"] == "/usr/bin"
    assert pulito["HOME"] == "/home/utente"
    assert pulito["USER"] == "utente"
    assert pulito["LC_ALL"] == "it_IT.UTF-8"
    assert pulito["LC_CTYPE"] == "it_IT.UTF-8"


def test_processo_riceve_ambiente_ripulito(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Lo script finto lanciato verifica che le variabili vietate non ci siano nell'ambiente."""
    file_env = tmp_path / "env.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_env.py",
        f"""
import json, os, sys
with open({repr(str(file_env))}, "w", encoding="utf-8") as f:
    json.dump(dict(os.environ), f)
print(json.dumps({{"session_id": "s1", "result": "ok"}}))
""",
    )
    monkeypatch.setenv("GH_TOKEN", "segreto_gh")
    monkeypatch.setenv("BOTTEGA_TOKEN", "segreto_bottega")
    monkeypatch.setenv("GITHUB_TOKEN", "segreto_github")
    monkeypatch.setenv("GITHUB_ACTOR", "qualcuno")

    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(tmp_path, "ciao", "sonnet")
    assert res.esito == "fatto"

    dati_env = json.loads(file_env.read_text(encoding="utf-8"))
    assert "GH_TOKEN" not in dati_env
    assert "BOTTEGA_TOKEN" not in dati_env
    assert "GITHUB_TOKEN" not in dati_env
    assert "GITHUB_ACTOR" not in dati_env


def test_costruisci_comando_e_prefisso(tmp_path: Path) -> None:
    """`prefisso` viene anteposto intero alla riga di comando."""
    prefisso = ["sudo", "-n", "-u", "lavorante", "--"]
    cmd = ["claude", "-p", "prova"]
    completo = costruisci_comando(prefisso, cmd)
    assert completo == ["sudo", "-n", "-u", "lavorante", "--", "claude", "-p", "prova"]

    # Verifica con prefisso vuoto
    assert costruisci_comando((), cmd) == cmd


def test_esecuzione_con_prefisso_reale(tmp_path: Path) -> None:
    """Lo script riceve il prefisso anteposto e gli argomenti esatti."""
    log_file = tmp_path / "argv.json"
    script = _crea_script_finto(
        tmp_path,
        "script_target.py",
        f"""
import json, sys
with open({repr(str(log_file))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv, f)
print(json.dumps({{"session_id": "s2", "result": "fatto con prefisso"}}))
""",
    )
    # Usiamo sys.executable come prefisso per simulare un wrapper
    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(tmp_path, "fai lavoro", "sonnet", prefisso=[sys.executable])
    assert res.esito == "fatto"
    registrati = json.loads(log_file.read_text(encoding="utf-8"))
    # argv[0] è script_target.py, seguito dagli argomenti di claude
    assert registrati[0] == str(script)
    assert "-p" in registrati
    assert "fai lavoro" in registrati


def test_claude_code_lancia_fatto_e_argomenti(tmp_path: Path) -> None:
    """Claude Code: parametri standard, uscita json, contatori e id di sessione."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_claude.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
uscita = {{
    "session_id": "ses-claude-123",
    "result": "Tutto eseguito con successo",
    "usage": {{
        "input_tokens": 120,
        "output_tokens": 60,
        "cache_read_input_tokens": 30
    }}
}}
print(json.dumps(uscita))
""",
    )
    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(tmp_path, "scrivi il modulo", "claude-sonnet-4.6")
    assert res.esito == "fatto"
    assert res.testo == "Tutto eseguito con successo"
    assert res.conversazione == "ses-claude-123"
    assert res.rinnovo is None
    assert res.contatori == {
        "input_tokens": 120,
        "output_tokens": 60,
        "cache_read_input_tokens": 30,
    }

    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert ricevuti == [
        "-p",
        "scrivi il modulo",
        "--model",
        "claude-sonnet-4.6",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    ]


def test_claude_code_ripresa_e_sola_lettura(tmp_path: Path) -> None:
    """Claude Code con ripresa sessione e modalità sola lettura."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_claude_ripresa.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"session_id": "ses-ripresa", "result": "letto"}}))
""",
    )
    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(
        tmp_path,
        "continua",
        "sonnet",
        conversazione="ses-ripresa",
        sola_lettura=True,
    )
    assert res.esito == "fatto"
    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert "--resume" in ricevuti
    idx_resume = ricevuti.index("--resume")
    assert ricevuti[idx_resume + 1] == "ses-ripresa"
    assert "--permission-mode" in ricevuti
    idx_perm = ricevuti.index("--permission-mode")
    assert ricevuti[idx_perm + 1] == "plan"
    assert "--dangerously-skip-permissions" not in ricevuti


def test_claude_code_quota_e_parse_rinnovo(tmp_path: Path) -> None:
    """Claude Code: testi di quota esaurita e parsing orario di rinnovo."""
    script = _crea_script_finto(
        tmp_path,
        "finto_claude_quota.py",
        """
import sys
print("You've hit your session limit · resets 3:45pm")
sys.exit(1)
""",
    )
    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(tmp_path, "fai qualcosa", "sonnet")
    assert res.esito == "quota"
    assert res.rinnovo is not None
    assert res.rinnovo.hour == 15
    assert res.rinnovo.minute == 45

    # Casi di rinnovo con orario fisso adesso
    # Domenica 2026-11-08 14:00 UTC
    adesso = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)
    # resets 3:45pm oggi -> oggi 15:45
    r1 = parse_rinnovo_claude("You've hit your session limit · resets 3:45pm", adesso=adesso)
    assert r1 == datetime(2026, 11, 8, 15, 45, tzinfo=timezone.utc)

    # resets 1:30pm (già passata oggi) -> domani 13:30
    r2 = parse_rinnovo_claude("limit · resets 1:30pm", adesso=adesso)
    assert r2 == datetime(2026, 11, 9, 13, 30, tzinfo=timezone.utc)

    # resets Mon 12:00am (domani lunedì alle 00:00)
    r3 = parse_rinnovo_claude("You've hit your weekly limit · resets Mon 12:00am", adesso=adesso)
    assert r3 == datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)

    # resets Sun 12:00pm (domenica a mezzogiorno, già passata oggi) -> domenica prossima
    r4 = parse_rinnovo_claude("resets Sun 12:00pm", adesso=adesso)
    assert r4 == datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    # Quota senza orario di rinnovo leggibile -> rinnovo None
    r5 = parse_rinnovo_claude("You've hit your monthly spend limit", adesso=adesso)
    assert r5 is None


def test_claude_code_accesso_e_errore(tmp_path: Path) -> None:
    """Claude Code: accesso scaduto ed errore generico."""
    script_auth = _crea_script_finto(
        tmp_path,
        "finto_claude_auth.py",
        """
import sys
sys.stderr.write("Authentication required: please run claude auth login\\n")
sys.exit(1)
""",
    )
    p_auth = porta("claude-code", eseguibile=str(script_auth))
    res_auth = p_auth.lancia(tmp_path, "ciao", "sonnet")
    assert res_auth.esito == "accesso"

    script_err = _crea_script_finto(
        tmp_path,
        "finto_claude_err.py",
        """
import sys
sys.stderr.write("SyntaxError: unexpected token\\n")
sys.exit(2)
""",
    )
    p_err = porta("claude-code", eseguibile=str(script_err))
    res_err = p_err.lancia(tmp_path, "ciao", "sonnet")
    assert res_err.esito == "errore"
    assert "SyntaxError" in res_err.testo


def test_antigravity_lancia_fatto_e_argomenti(tmp_path: Path) -> None:
    """Antigravity: formato json busta con conversation_id, status, response, usage."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_agy.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
uscita = {{
    "conversation_id": "c-agy-987",
    "status": "SUCCESS",
    "response": "Funzione implementata",
    "duration_seconds": 3.4,
    "num_turns": 1,
    "usage": {{
        "input_tokens": 200,
        "output_tokens": 80,
        "thinking_tokens": 10,
        "cache_read_tokens": 50,
        "total_tokens": 340
    }}
}}
print(json.dumps(uscita))
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(tmp_path, "risolvi", "gemini-3.8-flash")
    assert res.esito == "fatto"
    assert res.testo == "Funzione implementata"
    assert res.conversazione == "c-agy-987"
    assert res.contatori["total_tokens"] == 340

    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert ricevuti == [
        "-p",
        "risolvi",
        "--model",
        "gemini-3.8-flash",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    ]


def test_antigravity_ripresa_e_sola_lettura(tmp_path: Path) -> None:
    """Antigravity: ripresa con --conversation e sola lettura con --mode plan."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_agy_ripresa.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"conversation_id": "c-agy-987", "status": "SUCCESS", "response": "ok"}}))
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(
        tmp_path,
        "analizza",
        "gemini-3.8-flash",
        conversazione="c-agy-987",
        sola_lettura=True,
    )
    assert res.esito == "fatto"
    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert "--conversation" in ricevuti
    idx_conv = ricevuti.index("--conversation")
    assert ricevuti[idx_conv + 1] == "c-agy-987"
    assert "--mode" in ricevuti
    idx_mode = ricevuti.index("--mode")
    assert ricevuti[idx_mode + 1] == "plan"


def test_antigravity_quota_accesso_errore(tmp_path: Path) -> None:
    """Antigravity: gestione status di errore (quota, accesso, errore generico)."""
    script_quota = _crea_script_finto(
        tmp_path,
        "finto_agy_quota.py",
        """
import json, sys
print(json.dumps({"status": "ERROR", "error": "RESOURCE_EXHAUSTED: rate limit exceeded (429)"}))
sys.exit(1)
""",
    )
    p_quota = porta("antigravity", eseguibile=str(script_quota))
    res_quota = p_quota.lancia(tmp_path, "run", "model")
    assert res_quota.esito == "quota"

    script_auth = _crea_script_finto(
        tmp_path,
        "finto_agy_auth.py",
        """
import json, sys
print(json.dumps({"status": "ERROR", "error": "Authentication required: no active credentials"}))
sys.exit(1)
""",
    )
    p_auth = porta("antigravity", eseguibile=str(script_auth))
    res_auth = p_auth.lancia(tmp_path, "run", "model")
    assert res_auth.esito == "accesso"

    script_err = _crea_script_finto(
        tmp_path,
        "finto_agy_err.py",
        """
import json, sys
print(json.dumps({"status": "ERROR", "error": "Something went wrong"}))
sys.exit(1)
""",
    )
    p_err = porta("antigravity", eseguibile=str(script_err))
    res_err = p_err.lancia(tmp_path, "run", "model")
    assert res_err.esito == "errore"


def test_pi_lancia_fatto_e_argomenti(tmp_path: Path) -> None:
    """Pi: modalità JSONL, record session per id e record assistant per testo/contatori."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_pi.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"type": "session", "id": "pi-sess-456"}}))
print(json.dumps({{
    "type": "message",
    "role": "assistant",
    "content": "Risposta completata da Pi",
    "usage": {{"input": 150, "output": 75, "totalTokens": 225}}
}}))
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(tmp_path, "fai modifica", "anthropic/claude-3-5-sonnet")
    assert res.esito == "fatto"
    assert res.testo == "Risposta completata da Pi"
    assert res.conversazione == "pi-sess-456"
    assert res.contatori["totalTokens"] == 225

    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert ricevuti == [
        "--mode",
        "json",
        "fai modifica",
        "--model",
        "anthropic/claude-3-5-sonnet",
    ]


def test_pi_ripresa_e_sola_lettura(tmp_path: Path) -> None:
    """Pi: ripresa con --session e sola lettura con --tools."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_pi_ripresa.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"type": "session", "id": "pi-sess-456"}}))
print(json.dumps({{"type": "message", "role": "assistant", "content": "esaminato"}}))
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(
        tmp_path,
        "esamina",
        "modello",
        conversazione="pi-sess-456",
        sola_lettura=True,
    )
    assert res.esito == "fatto"
    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert "--session" in ricevuti
    idx_sess = ricevuti.index("--session")
    assert ricevuti[idx_sess + 1] == "pi-sess-456"
    assert "--tools" in ricevuti
    idx_tools = ricevuti.index("--tools")
    assert ricevuti[idx_tools + 1] == "read,grep,find,ls"


def test_pi_quota_accesso_errore(tmp_path: Path) -> None:
    """Pi: gestione errori di quota, login e anomalie."""
    script_quota = _crea_script_finto(
        tmp_path,
        "finto_pi_quota.py",
        """
import json, sys
print(json.dumps({"type": "session", "id": "pi-q"}))
print(json.dumps({"type": "message", "stopReason": "error", "errorMessage": "Rate limit exceeded (429 quota)"}))
sys.exit(1)
""",
    )
    p_quota = porta("pi", eseguibile=str(script_quota))
    res_quota = p_quota.lancia(tmp_path, "run", "model")
    assert res_quota.esito == "quota"

    script_auth = _crea_script_finto(
        tmp_path,
        "finto_pi_auth.py",
        """
import json, sys
print(json.dumps({"type": "message", "stopReason": "error", "errorMessage": "not logged in: run /login"}))
sys.exit(1)
""",
    )
    p_auth = porta("pi", eseguibile=str(script_auth))
    res_auth = p_auth.lancia(tmp_path, "run", "model")
    assert res_auth.esito == "accesso"


def test_copilot_cli_lancia_fatto_e_argomenti(tmp_path: Path) -> None:
    """Copilot CLI: formato JSONL, session.start, assistant.message, session.shutdown."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_copilot.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"type": "session.start", "data": {{"sessionId": "uuid-copilot-777"}}}}))
print(json.dumps({{"type": "assistant.message", "data": {{"content": "Codice generato da Copilot"}}}}))
print(json.dumps({{
    "type": "session.shutdown",
    "data": {{
        "totalPremiumRequests": 1,
        "conversationTokens": 180,
        "modelMetrics": {{
            "claude-sonnet-4.6": {{
                "usage": {{"inputTokens": 130, "outputTokens": 50}}
            }}
        }}
    }}
}}))
""",
    )
    p = porta("copilot-cli", eseguibile=str(script))
    res = p.lancia(tmp_path, "crea test", "claude-sonnet-4.6")
    assert res.esito == "fatto"
    assert res.testo == "Codice generato da Copilot"
    assert res.conversazione == "uuid-copilot-777"
    assert res.contatori["conversationTokens"] == 180
    assert res.contatori["inputTokens"] == 130

    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert ricevuti == [
        "-p",
        "crea test",
        "--model",
        "claude-sonnet-4.6",
        "--output-format",
        "json",
        "--allow-all-tools",
    ]


def test_copilot_cli_ripresa_e_sola_lettura(tmp_path: Path) -> None:
    """Copilot CLI: ripresa con --resume e sola lettura con --available-tools."""
    log_args = tmp_path / "args.json"
    script = _crea_script_finto(
        tmp_path,
        "finto_copilot_ripresa.py",
        f"""
import json, sys
with open({repr(str(log_args))}, "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
print(json.dumps({{"type": "session.start", "data": {{"sessionId": "uuid-copilot-777"}}}}))
print(json.dumps({{"type": "assistant.message", "data": {{"content": "ispezione completata"}}}}))
""",
    )
    p = porta("copilot-cli", eseguibile=str(script))
    res = p.lancia(
        tmp_path,
        "ispeziona",
        "claude-sonnet-4.6",
        conversazione="uuid-copilot-777",
        sola_lettura=True,
    )
    assert res.esito == "fatto"
    ricevuti = json.loads(log_args.read_text(encoding="utf-8"))
    assert "--resume" in ricevuti
    idx_res = ricevuti.index("--resume")
    assert ricevuti[idx_res + 1] == "uuid-copilot-777"
    assert "--available-tools" in ricevuti
    idx_tools = ricevuti.index("--available-tools")
    assert ricevuti[idx_tools + 1] == "view,grep,glob"
    assert "--allow-tool" in ricevuti
    idx_allow = ricevuti.index("--allow-tool")
    assert ricevuti[idx_allow + 1] == "view,grep,glob"
    assert "--allow-all-tools" not in ricevuti


def test_copilot_cli_quota_accesso_errore(tmp_path: Path) -> None:
    """Copilot CLI: rilevamento quota (Quota exceeded, 402, rate limit) e accesso."""
    script_quota = _crea_script_finto(
        tmp_path,
        "finto_copilot_quota.py",
        """
import sys
sys.stderr.write("Quota exceeded. Upgrade to increase your limit: https://github.com/settings/copilot/features\\n")
sys.exit(1)
""",
    )
    p_quota = porta("copilot-cli", eseguibile=str(script_quota))
    res_quota = p_quota.lancia(tmp_path, "fai", "modello")
    assert res_quota.esito == "quota"

    script_auth = _crea_script_finto(
        tmp_path,
        "finto_copilot_auth.py",
        """
import sys
sys.stderr.write("Authentication required: please run gh auth status or copilot login\\n")
sys.exit(1)
""",
    )
    p_auth = porta("copilot-cli", eseguibile=str(script_auth))
    res_auth = p_auth.lancia(tmp_path, "fai", "modello")
    assert res_auth.esito == "accesso"


def test_lancia_tempo_scaduto(tmp_path: Path) -> None:
    """Un tempo scaduto durante il lancio restituisce esito='errore' col motivo."""
    script_lento = _crea_script_finto(
        tmp_path,
        "script_lento.py",
        """
import time
time.sleep(5)
""",
    )
    p = porta("claude-code", eseguibile=str(script_lento))
    res = p.lancia(tmp_path, "fai", "modello", tempo=0.1)
    assert res.esito == "errore"
    assert "scaduto" in res.testo.lower()


def test_lancia_eseguibile_assente(tmp_path: Path) -> None:
    """Lancia con eseguibile inesistente restituisce esito='errore' col motivo, mai eccezioni."""
    assente = str(tmp_path / "inesistente_bin")
    p = porta("copilot-cli", eseguibile=assente)
    res = p.lancia(tmp_path, "fai", "modello")
    assert res.esito == "errore"
    assert "non trovato" in res.testo.lower() or "no such" in res.testo.lower()


def test_claude_code_risposta_con_testi_quota_e_fatto(tmp_path: Path) -> None:
    """Claude Code: lancio riuscito la cui risposta contiene testi di quota -> esito fatto, rinnovo None."""
    script = _crea_script_finto(
        tmp_path,
        "finto_claude_quota_in_risposta.py",
        """
import json, sys
risposta = (
    "Testo del modello: You've hit your weekly limit · resets Mon 12:00am. "
    "Tratta anche rate_limit e Quota exceeded senza problemi."
)
print(json.dumps({
    "session_id": "ses-ok",
    "result": risposta,
    "is_error": False,
}))
""",
    )
    p = porta("claude-code", eseguibile=str(script))
    res = p.lancia(tmp_path, "spiega errore", "sonnet")
    assert res.esito == "fatto"
    assert res.rinnovo is None
    assert "weekly limit" in res.testo


def test_antigravity_risposta_con_testi_quota_e_fatto(tmp_path: Path) -> None:
    """Antigravity: lancio riuscito la cui risposta contiene testi di quota -> esito fatto, rinnovo None."""
    script = _crea_script_finto(
        tmp_path,
        "finto_agy_quota_in_risposta.py",
        """
import json, sys
risposta = (
    "Spiegazione: RESOURCE_EXHAUSTED, rate limit, 429 e Quota exceeded. "
    "You've hit your weekly limit · resets Mon 12:00am."
)
print(json.dumps({
    "conversation_id": "c-ok",
    "status": "SUCCESS",
    "response": risposta,
}))
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(tmp_path, "spiega errore", "gemini-3.8-flash")
    assert res.esito == "fatto"
    assert res.rinnovo is None
    assert "RESOURCE_EXHAUSTED" in res.testo


def test_pi_risposta_con_testi_quota_e_fatto(tmp_path: Path) -> None:
    """Pi: lancio riuscito la cui risposta contiene testi di quota -> esito fatto, rinnovo None."""
    script = _crea_script_finto(
        tmp_path,
        "finto_pi_quota_in_risposta.py",
        """
import json, sys
risposta = (
    "Risposta Pi: You've hit your weekly limit · resets Mon 12:00am. "
    "Contiene anche rate_limit, Quota exceeded e 429."
)
print(json.dumps({"type": "session", "id": "pi-ok"}))
print(json.dumps({"type": "message", "role": "assistant", "content": risposta}))
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(tmp_path, "spiega errore", "model")
    assert res.esito == "fatto"
    assert res.rinnovo is None
    assert "weekly limit" in res.testo


def test_copilot_cli_risposta_con_testi_quota_e_fatto(tmp_path: Path) -> None:
    """Copilot CLI: lancio riuscito la cui risposta contiene testi di quota -> esito fatto, rinnovo None."""
    script = _crea_script_finto(
        tmp_path,
        "finto_copilot_quota_in_risposta.py",
        """
import json, sys
risposta = (
    "Risposta Copilot: You've hit your weekly limit · resets Mon 12:00am. "
    "Include Quota exceeded e rate_limit."
)
print(json.dumps({"type": "session.start", "data": {"sessionId": "copilot-ok"}}))
print(json.dumps({"type": "assistant.message", "data": {"content": risposta}}))
print(json.dumps({"type": "session.shutdown", "data": {"conversationTokens": 10}}))
""",
    )
    p = porta("copilot-cli", eseguibile=str(script))
    res = p.lancia(tmp_path, "spiega errore", "model")
    assert res.esito == "fatto"
    assert res.rinnovo is None
    assert "weekly limit" in res.testo


def test_rv16_antigravity_errore_con_quota_in_risposta_resta_errore(tmp_path: Path) -> None:
    """RV16: Antigravity in errore cerca la quota SOLO nei campi errore e stderr, mai nel testo del modello."""
    script = _crea_script_finto(
        tmp_path,
        "finto_agy_err_con_quota_in_risposta.py",
        """
import json, sys
print(json.dumps({
    "status": "ERROR",
    "error": "Internal crash in sandbox",
    "response": "Ho riscontrato quota 429 ed exhausted in precedenza",
}))
sys.exit(1)
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.esito == "errore"


def test_rv16_antigravity_quota_con_intero_429(tmp_path: Path) -> None:
    """RV16: Antigravity riconosce 429 come intero nei campi d'errore."""
    script = _crea_script_finto(
        tmp_path,
        "finto_agy_quota_429_int.py",
        """
import json, sys
print(json.dumps({
    "status": "ERROR",
    "error": {"code": 429, "message": "Too Many Requests"},
}))
sys.exit(1)
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.esito == "quota"


def test_antigravity_crediti_finiti_dal_vivo(tmp_path: Path) -> None:
    """PORTE-2: l'uscita vera di agy coi crediti AI finiti (2026-11-08) è quota, anche senza stderr."""
    script = _crea_script_finto(
        tmp_path,
        "finto_agy_crediti.py",
        """
import json, sys
print(json.dumps({
    "conversation_id": "00000000-0000-0000-0000-000000000000",
    "status": "ERROR",
    "response": "",
    "error": "Your AI credits balance is too low to continue.",
    "duration_seconds": 312.1,
    "num_turns": 1,
    "finished_reason": "error",
}))
sys.exit(3)
""",
    )
    p = porta("antigravity", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.esito == "quota"


def test_rv16_pi_errore_con_quota_in_risposta_resta_errore(tmp_path: Path) -> None:
    """RV16: Pi in errore cerca la quota SOLO in errorMessage e stderr, mai nei messaggi del modello."""
    script = _crea_script_finto(
        tmp_path,
        "finto_pi_err_con_quota_in_risposta.py",
        """
import json, sys
print(json.dumps({"type": "session", "id": "pi-err"}))
print(json.dumps({"type": "message", "role": "assistant", "content": "Attenzione: quota 429 esaurita nel modello"}))
print(json.dumps({"type": "message", "stopReason": "error", "errorMessage": "Connection reset by peer"}))
sys.exit(1)
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.esito == "errore"


def test_rv16_pi_quota_con_intero_429(tmp_path: Path) -> None:
    """RV16: Pi riconosce 429 come intero nei record d'errore."""
    script = _crea_script_finto(
        tmp_path,
        "finto_pi_quota_429_int.py",
        """
import json, sys
print(json.dumps({"type": "session", "id": "pi-429"}))
print(json.dumps({"type": "error", "code": 429, "errorMessage": "Rate limit exceeded"}))
sys.exit(1)
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.esito == "quota"


def test_c5_esegui_porta_orfano(tmp_path: Path) -> None:
    import subprocess
    import time
    from bottega.porte import esegui_porta

    script = tmp_path / "orfano.sh"
    script.write_text(
        '#!/bin/sh\n'
        'setsid sleep 21.6 &\n'
        'printf "{}"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)

    try:
        t0 = time.monotonic()
        codice, stdout, stderr, err = esegui_porta([str(script)], tmp_path, tempo=60)
        durata = time.monotonic() - t0
        assert durata < 10, f"esegui_porta ha impiegato {durata}s (atteso < 10s)"
        assert codice == 0
        assert stdout == "{}"
        assert err is None
    finally:
        subprocess.run(["pkill", "-f", "sleep 21.6"], capture_output=True)


def test_c5_esegui_porta_byte_non_utf8(tmp_path: Path) -> None:
    from bottega.porte import esegui_porta

    script = tmp_path / "non_utf8.py"
    script.write_text(
        '#!/usr/bin/env python3\n'
        'import sys\n'
        'sys.stdout.buffer.write(b"\\xff\\xfe")\n',
        encoding="utf-8",
    )
    script.chmod(0o755)

    codice, stdout, stderr, err = esegui_porta([str(script)], tmp_path, tempo=10)
    assert err is None
    assert "\ufffd" in stdout


def test_c1_pi_somma_i_messaggi(tmp_path: Path) -> None:
    script = _crea_script_finto(
        tmp_path,
        "finto_pi_somma.py",
        """
import json, sys
print(json.dumps({"type": "session", "id": "pi-sess"}))
print(json.dumps({"type": "message", "role": "assistant", "usage": {"input": 100, "output": 50}}))
print(json.dumps({"type": "message", "role": "assistant", "usage": {"input": 200, "output": 75}}))
print(json.dumps({"type": "message", "stopReason": "stop"}))
sys.exit(0)
""",
    )
    p = porta("pi", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.contatori == {"input": 300, "output": 125}


def test_c1_copilot_somma_i_modelli(tmp_path: Path) -> None:
    script = _crea_script_finto(
        tmp_path,
        "finto_copilot_modelli.py",
        """
import json, sys
print(json.dumps({"type": "session.start", "data": {"sessionId": "cop-sess"}}))
print(json.dumps({
    "type": "session.shutdown",
    "data": {
        "modelMetrics": {
            "modello-1": {"usage": {"inputTokens": 100, "outputTokens": 40}},
            "modello-2": {"usage": {"inputTokens": 200, "outputTokens": 60}},
        }
    }
}))
sys.exit(0)
""",
    )
    p = porta("copilot-cli", eseguibile=str(script))
    res = p.lancia(tmp_path, "esegui", "model")
    assert res.contatori == {"inputTokens": 300, "outputTokens": 100}


def test_r22_controlla_dalla_radice(monkeypatch: pytest.MonkeyPatch) -> None:
    """B6-R22: controlla_eseguibile lancia con cwd='/'."""
    import subprocess
    from bottega.porte import controlla_eseguibile

    cwd_ricevuta: list[str | None] = []

    def finto_run(cmd, **kwargs):
        cwd_ricevuta.append(kwargs.get("cwd"))
        return subprocess.CompletedProcess(cmd, 0, stdout="1.0.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", finto_run)
    res = controlla_eseguibile("eseguibile-finto")
    assert res.ok is True
    assert cwd_ricevuta == ["/"]






