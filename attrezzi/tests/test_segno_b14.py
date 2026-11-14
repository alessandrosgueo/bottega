"""Prove per il segno automatico (B14-K5: Ruling R4 e R5)."""

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any

import pytest

from bottega.board import ErroreBoard, Lavoro
from bottega.conti import comando_conti
from bottega.correggi import argomenti_correggi, comando_correggi
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import ErroreForgia, Issue
from bottega.lancio import argomenti_lancia, comando_lancia, comando_segui
from bottega.porte import porta
from bottega.segni import nota
from bottega.segno import chiudi_segni_dei_chiusi, fine, inizio, tocca


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


class _BoardConChiusi(BoardFinta):
    """BoardFinta che conserva aperta=False dei lavori e conta le chiamate."""

    def __init__(self, lavori: Sequence[Lavoro] | None = None, repo: str | None = None) -> None:
        self._chiuse = {lav.numero for lav in (lavori or []) if not lav.aperta}
        self.chiamate: list[str] = []
        super().__init__(lavori, repo=repo)

    def _a_lavoro(self, d: dict[str, Any]) -> Lavoro:
        lav = super()._a_lavoro(d)
        if lav.numero in self._chiuse:
            return replace(lav, aperta=False)
        return lav

    def elenco(self) -> list[Lavoro]:
        self.chiamate.append("elenco")
        return super().elenco()

    def lavoro(self, numero: int) -> Lavoro | None:
        self.chiamate.append("lavoro")
        return super().lavoro(numero)

    def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
        self.chiamate.append("campo")
        super().campo(numero, nome, valore)


class _ForgiaContata(ForgiaFinta):
    """ForgiaFinta che conta le chiamate ai propri metodi."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chiamate: list[str] = []

    def chiusura(self, n: int) -> tuple[str, datetime] | None:
        self.chiamate.append("chiusura")
        return super().chiusura(n)

    def sotto_issue(self, n: int) -> list[Issue]:
        self.chiamate.append("sotto_issue")
        return super().sotto_issue(n)

    def madre_di(self, n: int) -> int | None:
        self.chiamate.append("madre_di")
        return super().madre_di(n)


def _scrivi_messaggi_claude(
    casa: Path,
    cartella: Path,
    sessione_id: str,
    voci: Sequence[tuple[int, str]],
) -> Path:
    norm = re.sub(r"[^a-zA-Z0-9]", "-", str(cartella.resolve()))
    dest_dir = casa / ".claude" / "projects" / norm
    dest_dir.mkdir(parents=True, exist_ok=True)
    righe: list[str] = []
    for idx, (tokens, ts_iso) in enumerate(voci):
        rec = {
            "type": "assistant",
            "timestamp": ts_iso,
            "message": {
                "id": f"msg-{sessione_id}-{idx}",
                "usage": {
                    "input_tokens": tokens,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        }
        righe.append(json.dumps(rec))
    f = dest_dir / f"{sessione_id}.jsonl"
    f.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return f


def _scrivi_messaggio_antigravity(
    casa: Path,
    sessione_id: str,
    tokens: int,
    ts_iso: str,
) -> Path:
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


def _esecutore_lancia_ok(numero: int) -> Any:
    def _esegui(cmd: Sequence[str], _: Mapping[str, str] | None = None) -> tuple[int, str]:
        s = " ".join(cmd)
        if "issue view" in s and "--json labels" in s:
            return 0, json.dumps({"labels": [{"name": "bottega: fuori"}]})
        if "workflow run" in s:
            return 0, ""
        if "run list" in s:
            return 0, json.dumps([{"databaseId": 101, "createdAt": "2026-11-14T10:00:05Z"}])
        if "run view 101 --json" in s:
            return 0, json.dumps({"status": "completed"})
        if "run view 101 --log" in s:
            return 0, f"lavoro {numero}: assegnato a «x» (b), workflow f.yml avviato\n"
        return 1, f"comando inatteso: {s}"

    return _esegui


def _esecutore_segui_finito(numero: int) -> Any:
    def _esegui(cmd: Sequence[str], _: Mapping[str, str] | None = None) -> tuple[int, str]:
        s = " ".join(cmd)
        if f"issues/{numero}/sub_issues" in s:
            return 0, json.dumps([{"number": numero + 1, "state": "closed"}])
        if "workflow list" in s:
            return 0, "[]"
        if "issue view" in s and "--json comments" in s:
            return 0, json.dumps({"comments": []})
        return 0, ""

    return _esegui


def test_tocca_senza_sessione_non_chiama_board_ne_forgia(tmp_path: Path) -> None:
    """Senza sessione riconosciuta (workflow), tocca esce subito senza chiamate."""
    board = _BoardConChiusi([Lavoro(numero=10, titolo="Lavoro 10", stato="pronto")])
    forgia = _ForgiaContata([Issue(numero=10, titolo="Lavoro 10")])
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    righe = tocca(board, forgia, 10, {}, tmp_path, adesso)

    assert righe == []
    assert board.chiamate == []
    assert forgia.chiamate == []
    assert board.registro == []


def test_tocca_idempotente_e_rispetta_altra_sessione(tmp_path: Path) -> None:
    """Chiamata due volte sullo stesso lavoro non riscrive; segno altrui resta intatto."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t1 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 14, 10, 15, tzinfo=timezone.utc)

    board = _BoardConChiusi([
        Lavoro(numero=10, titolo="Lavoro 10", stato="pronto"),
        Lavoro(numero=20, titolo="Lavoro 20", stato="pronto"),
    ])
    forgia = _ForgiaContata([
        Issue(numero=10, titolo="Lavoro 10"),
        Issue(numero=20, titolo="Lavoro 20"),
    ])
    env_mia = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "sess-mia"}

    # 1. Prima chiamata su #10: apre il segno
    assert tocca(board, forgia, 10, env_mia, cartella, t1) == []
    lav10 = board.lavoro(10)
    assert lav10 is not None
    assert nota(lav10.campi.get("Segno", "")) == {
        "porta": "claude-code",
        "sessione": "sess-mia",
        "inizio": t1.isoformat(),
    }

    # 2. Seconda chiamata su #10: nessuna scrittura nuova, orario invariato
    len_registro = len(board.registro)
    assert tocca(board, forgia, 10, env_mia, cartella, t2) == []
    assert len(board.registro) == len_registro
    assert nota(board.lavoro(10).campi["Segno"])["inizio"] == t1.isoformat()  # type: ignore[union-attr]

    # 3. Segno di un'altra sessione su #20: tocca(20) non lo sovrascrive
    _scrivi_messaggi_claude(casa, cartella, "sess-mia", [(50, "2026-11-14T10:05:00+00:00")])
    inizio(board, 20, "claude-code", "sess-altra", t1)
    len_prima = len(board.registro)
    assert tocca(board, forgia, 20, env_mia, cartella, t2) == []
    assert not any(op[1] == 20 for op in board.registro[len_prima:])
    assert nota(board.lavoro(20).campi["Segno"])["sessione"] == "sess-altra"  # type: ignore[union-attr]


def test_tocca_chiude_altro_lavoro_della_stessa_sessione_e_lascia_altre(tmp_path: Path) -> None:
    """Una sessione, un lavoro aperto: passare a #20 chiude #10 (sui compiti) ma non #30 altrui."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 14, 10, 30, tzinfo=timezone.utc)

    _scrivi_messaggi_claude(casa, cartella, "sess-1", [(600, "2026-11-14T10:15:00+00:00")])

    forgia = _ForgiaContata()
    n10 = forgia.crea_issue("Lavoro 10", "Corpo")
    c11 = forgia.crea_issue("Compito 11", "Corpo", madre=n10)
    c12 = forgia.crea_issue("Compito 12", "Corpo", madre=n10)
    n20 = forgia.crea_issue("Lavoro 20", "Corpo")
    n30 = forgia.crea_issue("Lavoro 30", "Corpo")

    board = _BoardConChiusi([
        Lavoro(numero=n10, titolo="Lavoro 10", stato="in corso"),
        Lavoro(numero=c11, titolo="Compito 11", stato=""),
        Lavoro(numero=c12, titolo="Compito 12", stato=""),
        Lavoro(numero=n20, titolo="Lavoro 20", stato="pronto"),
        Lavoro(numero=n30, titolo="Lavoro 30", stato="in corso"),
    ])
    inizio(board, n10, "claude-code", "sess-1", t0)
    inizio(board, n30, "claude-code", "sess-altra", t0)

    env = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "sess-1"}
    righe = tocca(board, forgia, n20, env, cartella, t1)

    assert righe == []
    assert board.lavoro(n10).campi.get("Segno") is None  # type: ignore[union-attr]
    assert "Token di chi decide" not in board.lavoro(n10).campi  # type: ignore[union-attr]
    assert board.lavoro(c11).campi.get("Token di chi decide") == "300"  # type: ignore[union-attr]
    assert board.lavoro(c12).campi.get("Token di chi decide") == "300"  # type: ignore[union-attr]
    assert nota(board.lavoro(n20).campi["Segno"])["sessione"] == "sess-1"  # type: ignore[union-attr]
    assert nota(board.lavoro(n30).campi["Segno"])["sessione"] == "sess-altra"  # type: ignore[union-attr]


def test_fine_divide_sui_compiti_con_resto_al_primo_e_misure_parziali(tmp_path: Path) -> None:
    """1000 token su 3 compiti -> 334, 333, 333, lavoro senza numero; Misure parziali sui compiti."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc)

    _scrivi_messaggio_antigravity(casa, "conv-parz", 1000, "2026-11-14T10:30:00+00:00")

    board = BoardFinta([
        Lavoro(numero=10, titolo="Lavoro 10", stato="consegnato"),
        Lavoro(numero=11, titolo="C1", stato=""),
        Lavoro(numero=12, titolo="C2", stato=""),
        Lavoro(numero=13, titolo="C3", stato=""),
    ])
    inizio(board, 10, "antigravity", "conv-parz", t0)

    env = {"HOME": str(casa)}
    aggiunti, _ = fine(
        board,
        10,
        [(porta("antigravity"), "conv-parz")],
        cartella,
        env,
        t1,
        compiti=[11, 12, 13],
    )

    assert aggiunti == 1000
    lav10 = board.lavoro(10)
    assert lav10 is not None
    assert lav10.campi.get("Segno") is None
    assert "Token di chi decide" not in lav10.campi
    assert "Misure parziali" not in lav10.campi

    assert board.lavoro(11).campi.get("Token di chi decide") == "334"  # type: ignore[union-attr]
    assert board.lavoro(12).campi.get("Token di chi decide") == "333"  # type: ignore[union-attr]
    assert board.lavoro(13).campi.get("Token di chi decide") == "333"  # type: ignore[union-attr]
    for cid in (11, 12, 13):
        assert "Token di chi decide" in board.lavoro(cid).campi.get("Misure parziali", "")  # type: ignore[union-attr]


def test_fine_fino_esclude_dopo_chiusura_e_chiude_se_vuoto(tmp_path: Path) -> None:
    """Con fino passato, i token dopo fino non contano; con 0 messaggi fino a fino il segno si chiude senza numero."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t_chiusura = datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc)
    adesso = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

    _scrivi_messaggi_claude(
        casa,
        cartella,
        "sess-taglio",
        [
            (400, "2026-11-14T10:30:00+00:00"),
            (900, "2026-11-14T11:30:00+00:00"),
        ],
    )
    _scrivi_messaggi_claude(
        casa,
        cartella,
        "sess-vuota",
        [(900, "2026-11-14T11:30:00+00:00")],
    )

    board = BoardFinta([
        Lavoro(numero=10, titolo="Con messaggi prima", stato="consegnato"),
        Lavoro(numero=20, titolo="Solo dopo chiusura", stato="consegnato"),
    ])
    inizio(board, 10, "claude-code", "sess-taglio", t0)
    inizio(board, 20, "claude-code", "sess-vuota", t0)

    env = {"HOME": str(casa)}
    aggiunti1, _ = fine(board, 10, [], cartella, env, adesso, fino=t_chiusura)
    assert aggiunti1 == 400
    assert board.lavoro(10).campi.get("Token di chi decide") == "400"  # type: ignore[union-attr]
    assert board.lavoro(10).campi.get("Segno") is None  # type: ignore[union-attr]

    aggiunti2, _ = fine(board, 20, [], cartella, env, adesso, fino=t_chiusura)
    assert aggiunti2 is None
    assert board.lavoro(20).campi.get("Segno") is None  # type: ignore[union-attr]
    assert "Token di chi decide" not in board.lavoro(20).campi  # type: ignore[union-attr]


def test_chiudi_segni_dei_chiusi_casi(tmp_path: Path) -> None:
    """R5: chiude lavori chiusi con segno (su compiti o lavoro), lascia aperto se manca trascrizione."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t_chiusura = datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc)
    adesso = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

    _scrivi_messaggi_claude(
        casa,
        cartella,
        "sess-chiuso",
        [
            (1000, "2026-11-14T10:30:00+00:00"),
            (5000, "2026-11-14T11:30:00+00:00"),
        ],
    )

    forgia = _ForgiaContata()
    l_compiti = forgia.crea_issue("Chiuso con compiti", "Corpo")
    c1 = forgia.crea_issue("C1", "Corpo", madre=l_compiti)
    c2 = forgia.crea_issue("C2", "Corpo", madre=l_compiti)
    c3 = forgia.crea_issue("C3", "Corpo", madre=l_compiti)
    forgia.chiudi_come(l_compiti, "completed", t_chiusura)

    l_altra_macchina = forgia.crea_issue("Chiuso altra macchina", "Corpo")
    forgia.chiudi_come(l_altra_macchina, "completed", t_chiusura)

    l_aperto = forgia.crea_issue("Aperto", "Corpo")

    board = _BoardConChiusi([
        Lavoro(numero=l_compiti, titolo="Chiuso con compiti", stato="consegnato", aperta=False),
        Lavoro(numero=c1, titolo="C1", stato="", aperta=False),
        Lavoro(numero=c2, titolo="C2", stato="", aperta=False),
        Lavoro(numero=c3, titolo="C3", stato="", aperta=False),
        Lavoro(numero=l_altra_macchina, titolo="Chiuso altra macchina", stato="consegnato", aperta=False),
        Lavoro(numero=l_aperto, titolo="Aperto", stato="in corso", aperta=True),
    ])
    inizio(board, l_compiti, "claude-code", "sess-chiuso", t0)
    inizio(board, l_altra_macchina, "claude-code", "sess-altra-macchina", t0)
    inizio(board, l_aperto, "claude-code", "sess-aperta", t0)

    env = {"HOME": str(casa)}
    righe = chiudi_segni_dei_chiusi(board, forgia, env, cartella, adesso)

    assert board.lavoro(l_compiti).campi.get("Segno") is None  # type: ignore[union-attr]
    assert "Token di chi decide" not in board.lavoro(l_compiti).campi  # type: ignore[union-attr]
    assert board.lavoro(c1).campi.get("Token di chi decide") == "334"  # type: ignore[union-attr]
    assert board.lavoro(c2).campi.get("Token di chi decide") == "333"  # type: ignore[union-attr]
    assert board.lavoro(c3).campi.get("Token di chi decide") == "333"  # type: ignore[union-attr]

    # Altra macchina: segno resta aperto, esattamente una riga d'avviso
    assert board.lavoro(l_altra_macchina).campi.get("Segno") is not None  # type: ignore[union-attr]
    assert len(righe) == 1
    assert f"#{l_altra_macchina}" in righe[0]

    # Lavoro aperto: non toccato
    assert board.lavoro(l_aperto).campi.get("Segno") is not None  # type: ignore[union-attr]


def test_comando_lancia_apre_segno_e_non_cambia_uscita_con_board_rotta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """lancia ha --configurazione, apre il segno se avviato, e non cambia uscita/stdout se la board fallisce."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-lancia")

    parser = argparse.ArgumentParser()
    argomenti_lancia(parser)
    args = parser.parse_args(["42", "--configurazione", str(tmp_path / "manca.toml")])

    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    # 1. Board sana: apre il segno sul lavoro 42
    board_ok = _BoardConChiusi([Lavoro(numero=42, titolo="Lavoro 42", stato="pronto")])
    forgia_ok = _ForgiaContata([Issue(numero=42, titolo="Lavoro 42")])
    rc_ok = comando_lancia(
        args,
        esegui=_esecutore_lancia_ok(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=board_ok,
        forgia=forgia_ok,
    )
    cap_ok = capsys.readouterr()
    assert rc_ok == 0
    assert board_ok.lavoro(42).campi.get("Segno") is not None  # type: ignore[union-attr]

    # 2. Board che fallisce (anche configurazione mancante senza board iniettata)
    class _BoardRotta(_BoardConChiusi):
        def elenco(self) -> list[Lavoro]:
            raise ErroreBoard("board giù")

        def lavoro(self, numero: int) -> Lavoro | None:
            raise ErroreBoard("board giù")

        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            raise ErroreBoard("board giù")

    rc_rotta = comando_lancia(
        args,
        esegui=_esecutore_lancia_ok(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=_BoardRotta(),
        forgia=forgia_ok,
    )
    cap_rotta = capsys.readouterr()
    assert rc_rotta == rc_ok
    assert cap_rotta.out == cap_ok.out
    assert "segno:" in cap_rotta.err

    # 3. Senza board né configurazione: non deve far fallire lancia
    rc_no_cfg = comando_lancia(
        args,
        esegui=_esecutore_lancia_ok(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
    )
    cap_no_cfg = capsys.readouterr()
    assert rc_no_cfg == rc_ok
    assert cap_no_cfg.out == cap_ok.out
    assert "segno:" in cap_no_cfg.err


    # 4. Esito != avviato (es. manutenzione): non apre il segno
    def _esegui_manutenzione(cmd: Sequence[str], _: Mapping[str, str] | None = None) -> tuple[int, str]:
        s = " ".join(cmd)
        if "run view 101 --log" in s:
            return 0, "finestra di manutenzione «06:00-07:00»: nessun lavoro avviato\n"
        return _esecutore_lancia_ok(42)(cmd, _)

    board_man = _BoardConChiusi([Lavoro(numero=42, titolo="Lavoro 42", stato="pronto")])
    rc_man = comando_lancia(
        args,
        esegui=_esegui_manutenzione,
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=board_man,
        forgia=forgia_ok,
    )
    capsys.readouterr()
    assert rc_man == 2
    assert "Segno" not in board_man.lavoro(42).campi  # type: ignore[union-attr]


def test_comando_lancia_senza_sessione_zero_chiamate_board_forgia(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In un workflow (nessuna sessione in env) lancia non tocca board né forgia."""
    monkeypatch.chdir(tmp_path)
    parser = argparse.ArgumentParser()
    argomenti_lancia(parser)
    args = parser.parse_args(["42"])
    board = _BoardConChiusi([Lavoro(numero=42, titolo="Lavoro 42", stato="pronto")])
    forgia = _ForgiaContata([Issue(numero=42, titolo="Lavoro 42")])
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    rc = comando_lancia(
        args,
        esegui=_esecutore_lancia_ok(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=board,
        forgia=forgia,
    )
    assert rc == 0
    assert board.chiamate == []
    assert forgia.chiamate == []


def test_comando_segui_apre_segno_e_non_cambia_uscita_con_board_rotta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """segui apre il segno all'inizio; se la board/forgia fallisce su tocca, uscita e stdout restano identici."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-segui")
    args = argparse.Namespace(
        numero=42,
        repo=None,
        intervallo=300,
        fermo=1200.0,
        tetto=18000.0,
        configurazione=tmp_path / "bottega.toml",
    )
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    board_ok = _BoardConChiusi([Lavoro(numero=42, titolo="Lavoro 42", stato="consegnato")])
    forgia_ok = _ForgiaContata([Issue(numero=42, titolo="Lavoro 42")])
    rc_ok = comando_segui(
        args,
        esegui=_esecutore_segui_finito(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=board_ok,
        forgia=forgia_ok,
    )
    cap_ok = capsys.readouterr()
    assert rc_ok == 0
    assert board_ok.lavoro(42).campi.get("Segno") is not None  # type: ignore[union-attr]

    class _BoardRottaSuSegno(_BoardConChiusi):
        def elenco(self) -> list[Lavoro]:
            raise ErroreBoard("elenco rotto")

        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            raise ErroreBoard("scrittura segno rotta")

    board_rotta = _BoardRottaSuSegno([Lavoro(numero=42, titolo="Lavoro 42", stato="consegnato")])
    rc_rotta = comando_segui(
        args,
        esegui=_esecutore_segui_finito(42),
        dormi=lambda _: None,
        adesso=lambda: t0,
        board=board_rotta,
        forgia=forgia_ok,
    )
    cap_rotta = capsys.readouterr()
    assert rc_rotta == rc_ok
    assert cap_rotta.out == cap_ok.out
    assert "segno:" in cap_rotta.err


def test_comando_correggi_apre_segno_sul_lavoro_madre_e_non_fallisce_su_errore_segno(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """correggi tocca il lavoro M (non il compito N); un errore del segno lascia uscita 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-corr")

    parser = argparse.ArgumentParser()
    argomenti_correggi(parser)

    forgia = _ForgiaContata([
        Issue(numero=10, titolo="Lavoro madre", corpo="Piano"),
        Issue(numero=11, titolo="Compito 11", corpo="## Fatto quando\n```\nuv run pytest -q\n```\n"),
    ])
    forgia._madri[11] = 10
    forgia._sotto_issue[10] = [11]

    board = _BoardConChiusi([
        Lavoro(numero=10, titolo="Lavoro madre", stato="consegnato"),
        Lavoro(numero=11, titolo="Compito 11", stato=""),
    ])

    args = parser.parse_args(["11", "--testo", "Sistema il bordo"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 0
    assert board.lavoro(10).campi.get("Segno") is not None  # type: ignore[union-attr]
    assert "Segno" not in board.lavoro(11).campi  # type: ignore[union-attr]
    capsys.readouterr()

    # Se la scrittura di Segno fallisce, correggi resta comunque 0
    class _BoardSegnoRotto(_BoardConChiusi):
        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            if nome == "Segno":
                raise ErroreBoard("segno rotto")
            super().campo(numero, nome, valore)

    board2 = _BoardSegnoRotto([
        Lavoro(numero=10, titolo="Lavoro madre", stato="consegnato"),
        Lavoro(numero=11, titolo="Compito 11", stato=""),
    ])
    rc2 = comando_correggi(args, forgia=forgia, board=board2)
    cap2 = capsys.readouterr()
    assert rc2 == 0
    assert "poi: bottega lancia 10" in cap2.out
    assert "segno:" in cap2.err


def test_comando_conti_chiude_segni_dei_chiusi_e_tollera_errori(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """conti chiama chiudi_segni_dei_chiusi prima di leggere; se fallisce stampa i conti lo stesso."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cartella)

    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t_chiusura = datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc)
    _scrivi_messaggi_claude(casa, cartella, "sess-conti", [(400, "2026-11-14T10:20:00+00:00")])

    forgia = _ForgiaContata()
    l_chiuso = forgia.crea_issue("Lavoro chiuso", "Corpo")
    c1 = forgia.crea_issue("Compito 1", "Corpo", madre=l_chiuso)
    c2 = forgia.crea_issue("Compito 2", "Corpo", madre=l_chiuso)
    forgia.chiudi_come(l_chiuso, "completed", t_chiusura)

    l_aperto = forgia.crea_issue("Lavoro aperto", "Corpo")

    board = _BoardConChiusi([
        Lavoro(numero=l_chiuso, titolo="Lavoro chiuso", stato="consegnato", aperta=False),
        Lavoro(numero=c1, titolo="Compito 1", stato="", aperta=False, campi={"Dove": "fuori"}),
        Lavoro(numero=c2, titolo="Compito 2", stato="", aperta=False, campi={"Dove": "fuori"}),
        Lavoro(numero=l_aperto, titolo="Lavoro aperto", stato="in corso", aperta=True),
    ])
    inizio(board, l_chiuso, "claude-code", "sess-conti", t0)
    inizio(board, l_aperto, "claude-code", "sess-aperta", t0)

    args = argparse.Namespace(json=True, file="bottega.toml", repo="")
    rc = comando_conti(args, board=board, forgia=forgia)
    assert rc == 0
    dati = json.loads(capsys.readouterr().out)
    assert dati["per_dove"]["fuori"]["token_decisore_medi"] == 200.0
    assert board.lavoro(l_chiuso).campi.get("Segno") is None  # type: ignore[union-attr]
    # conti non chiude né tocca lavori aperti
    assert board.lavoro(l_aperto).campi.get("Segno") is not None  # type: ignore[union-attr]

    # Se forgia.chiusura solleva, conti stampa i conti lo stesso
    class _ForgiaRotta(_ForgiaContata):
        def chiusura(self, n: int) -> tuple[str, datetime] | None:
            raise ErroreForgia("github giù")

    board_err = _BoardConChiusi([
        Lavoro(numero=l_chiuso, titolo="Lavoro chiuso", stato="consegnato", aperta=False),
        Lavoro(numero=c1, titolo="Compito 1", stato="", aperta=False, campi={"Dove": "fuori", "Durata": "10"}),
    ])
    inizio(board_err, l_chiuso, "claude-code", "sess-conti", t0)
    rc_err = comando_conti(args, board=board_err, forgia=_ForgiaRotta())
    cap_err = capsys.readouterr()
    assert rc_err == 0
    assert "per_dove" in json.loads(cap_err.out)
    assert "segno:" in cap_err.err


def test_tocca_due_lavori_di_fila_chiude_il_primo_senza_numero(tmp_path: Path) -> None:
    """Fra due comandi di fila non c'è nessun messaggio: il primo segno si chiude lo stesso, senza numero. Restando
    aperto, i messaggi di dopo si conterebbero su tutti e due i lavori."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=5)
    t2 = t0 + timedelta(minutes=30)
    _scrivi_messaggi_claude(casa, cartella, "sess-1", [(700, "2026-11-14T10:15:00+00:00")])

    forgia = _ForgiaContata()
    n10 = forgia.crea_issue("Lavoro 10", "Corpo")
    n20 = forgia.crea_issue("Lavoro 20", "Corpo")
    n30 = forgia.crea_issue("Lavoro 30", "Corpo")
    board = _BoardConChiusi([
        Lavoro(numero=n10, titolo="Lavoro 10", stato="in corso"),
        Lavoro(numero=n20, titolo="Lavoro 20", stato="pronto"),
        Lavoro(numero=n30, titolo="Lavoro 30", stato="pronto"),
    ])
    env = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "sess-1"}

    assert tocca(board, forgia, n10, env, cartella, t0) == []
    assert tocca(board, forgia, n20, env, cartella, t1) == []
    assert board.lavoro(n10).campi.get("Segno") is None  # type: ignore[union-attr]
    assert "Token di chi decide" not in board.lavoro(n10).campi  # type: ignore[union-attr]

    assert tocca(board, forgia, n30, env, cartella, t2) == []
    assert "Token di chi decide" not in board.lavoro(n10).campi  # type: ignore[union-attr]
    assert board.lavoro(n20).campi.get("Token di chi decide") == "700"  # type: ignore[union-attr]


def test_tocca_legge_l_elenco_una_volta_sola(tmp_path: Path) -> None:
    """Ogni lettura dell'elenco può costare secondi (un adattatore che rilegge tutto il Project): una per comando."""
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    forgia = _ForgiaContata()
    n10 = forgia.crea_issue("Lavoro 10", "Corpo")
    board = _BoardConChiusi([Lavoro(numero=n10, titolo="Lavoro 10", stato="pronto")])
    env = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "sess-1"}
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    assert tocca(board, forgia, n10, env, cartella, adesso) == []
    assert board.chiamate == ["elenco", "campo"]

    board.chiamate.clear()
    assert tocca(board, forgia, n10, env, cartella, adesso + timedelta(minutes=1)) == []
    assert board.chiamate == ["elenco"]
    assert forgia.chiamate == []


def test_tocca_non_apre_un_segno_su_un_lavoro_chiuso(tmp_path: Path) -> None:
    casa = tmp_path / "casa"
    cartella = tmp_path / "repo"
    cartella.mkdir(parents=True, exist_ok=True)
    forgia = _ForgiaContata()
    n10 = forgia.crea_issue("Lavoro 10", "Corpo")
    forgia.chiudi_issue(n10)
    board = _BoardConChiusi([Lavoro(numero=n10, titolo="Lavoro 10", stato="consegnato", aperta=False)])
    env = {"HOME": str(casa), "CLAUDE_CODE_SESSION_ID": "sess-1"}

    assert tocca(board, forgia, n10, env, cartella, datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)) == []
    assert board.lavoro(n10).campi.get("Segno") is None  # type: ignore[union-attr]
