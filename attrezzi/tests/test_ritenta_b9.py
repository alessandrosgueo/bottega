"""Prove per i ritentativi su errori passeggeri di GitHub (Ruling B9-R1)."""

import subprocess
from typing import Any

import pytest
from bottega.board import BoardComando, BoardProject, ErroreBoard
from bottega.forgia import ErroreForgia, ForgiaGh
from bottega.ritenta import di_sola_lettura, non_consegnato, passeggero, ritenta

_ERR_503 = (
    "HTTP 503: No server is currently available to service your request. "
    "Please try again in a few minutes. (https://api.github.com/graphql)"
)


def test_1_passeggero_e_non_consegnato() -> None:
    # 1. passeggero: veri
    assert passeggero(_ERR_503)
    assert passeggero("HTTP 502: Bad Gateway")
    assert passeggero("read: connection reset by peer")
    assert passeggero("dial tcp: i/o timeout")
    assert passeggero("could not resolve host: api.github.com")
    assert passeggero("gh non ha risposto in 120 secondi")

    # passeggero: falsi
    assert not passeggero("HTTP 404: Not Found")
    assert not passeggero("HTTP 422: Validation Failed")
    assert not passeggero("HTTP 401: Bad credentials")
    assert not passeggero("HTTP 5000 righe")

    # non_consegnato: veri
    assert non_consegnato("no server is currently available")
    assert non_consegnato("connection refused")
    assert non_consegnato("could not resolve host")
    assert non_consegnato("temporary failure in name resolution")

    # non_consegnato: falsi
    assert not non_consegnato("HTTP 502: Bad Gateway")
    assert not non_consegnato("read: connection reset by peer")
    assert not non_consegnato("dial tcp: i/o timeout")
    assert not non_consegnato("HTTP 404: Not Found")


def test_2_di_sola_lettura() -> None:
    # veri
    assert di_sola_lettura(["issue", "view", "3"])
    assert di_sola_lettura(["run", "list"])
    assert di_sola_lettura(["api", "graphql", "-f", "query=query { viewer { login } }"])
    assert di_sola_lettura(["api", "repos/o/r/issues/3"])

    # falsi
    assert not di_sola_lettura(["issue", "comment", "3"])
    assert not di_sola_lettura(["issue", "edit", "3"])
    assert not di_sola_lettura(["workflow", "run", "x.yml"])
    assert not di_sola_lettura(["api", "graphql", "-f", "query=mutation { x }"])
    assert not di_sola_lettura(["api", "-X", "POST", "repos/o/r/issues"])
    assert not di_sola_lettura(["api", "--method=PATCH", "repos/o/r"])
    assert not di_sola_lettura(["api", "repos/o/r/issues", "-f", "title=x"])
    assert not di_sola_lettura(["label", "create", "x"])


def test_3_ritenta_scrittura_503_riprova_e_avvisa(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chiamate = 0
    dormite: list[float] = []

    def prova() -> tuple[int, str, str]:
        nonlocal chiamate
        chiamate += 1
        if chiamate == 1:
            return 1, "", _ERR_503
        return 0, "ok", ""

    ris = ritenta(prova, ["issue", "comment", "3"], dormi=dormite.append)
    assert ris == (0, "ok", "")
    assert chiamate == 2
    assert dormite == [10.0]
    catturato = capsys.readouterr()
    assert (
        "avviso: gh issue comment: errore passeggero, riprovo fra 10 s" in catturato.err
    )


def test_4_ritenta_scrittura_502_non_riprova() -> None:
    chiamate = 0
    dormite: list[float] = []

    def prova() -> tuple[int, str, str]:
        nonlocal chiamate
        chiamate += 1
        return 1, "", "HTTP 502: Bad Gateway"

    ris = ritenta(prova, ["issue", "comment", "3"], dormi=dormite.append)
    assert ris == (1, "", "HTTP 502: Bad Gateway")
    assert chiamate == 1
    assert dormite == []


def test_5_ritenta_lettura_502_tre_tentativi() -> None:
    chiamate = 0
    dormite: list[float] = []

    def prova() -> tuple[int, str, str]:
        nonlocal chiamate
        chiamate += 1
        return 1, "", "HTTP 502: Bad Gateway"

    ris = ritenta(prova, ["issue", "view", "3"], dormi=dormite.append)
    assert ris == (1, "", "HTTP 502: Bad Gateway")
    assert chiamate == 3
    assert dormite == [10.0, 30.0]


def test_6_ritenta_404_non_riprova() -> None:
    chiamate = 0
    dormite: list[float] = []

    def prova() -> tuple[int, str, str]:
        nonlocal chiamate
        chiamate += 1
        return 1, "", "HTTP 404: Not Found"

    ris = ritenta(prova, ["issue", "view", "3"], dormi=dormite.append)
    assert ris == (1, "", "HTTP 404: Not Found")
    assert chiamate == 1
    assert dormite == []


def test_7_forgia_gh_ritenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bottega.ritenta.ATTESE_S", (0.0, 0.0))
    forgia = ForgiaGh("proprietario/repo")

    # 7.1: un 503 poi un successo su issue view restituisce lo stdout del successo
    passi_503 = [
        subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr=_ERR_503
        ),
        subprocess.CompletedProcess(
            args=["gh"], returncode=0, stdout='{"ok": true}', stderr=""
        ),
    ]

    def run_503(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return passi_503.pop(0)

    monkeypatch.setattr("subprocess.run", run_503)
    out = forgia._esegui_di_serie(["issue", "view", "3"])
    assert out == '{"ok": true}'

    # 7.2: un timeout poi un successo idem
    primo_timeout = True

    def run_timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal primo_timeout
        if primo_timeout:
            primo_timeout = False
            raise subprocess.TimeoutExpired(cmd=["gh"], timeout=120)
        return subprocess.CompletedProcess(
            args=["gh"], returncode=0, stdout='{"ok": true}', stderr=""
        )

    monkeypatch.setattr("subprocess.run", run_timeout)
    out = forgia._esegui_di_serie(["issue", "view", "3"])
    assert out == '{"ok": true}'

    # 7.3: tre 503 sollevano ErroreForgia col testo del 503
    def run_sempre_503(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr=_ERR_503
        )

    monkeypatch.setattr("subprocess.run", run_sempre_503)
    with pytest.raises(ErroreForgia, match="HTTP 503"):
        forgia._esegui_di_serie(["issue", "view", "3"])


def test_8_board_project_ritenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bottega.ritenta.ATTESE_S", (0.0, 0.0))
    board = BoardProject("proprietario", 1)

    # 8.1: un 503 poi un successo
    passi_503 = [
        subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr=_ERR_503
        ),
        subprocess.CompletedProcess(
            args=["gh"], returncode=0, stdout='{"data": {}}', stderr=""
        ),
    ]

    def run_503(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return passi_503.pop(0)

    monkeypatch.setattr("subprocess.run", run_503)
    out = board._esegui_di_serie(
        ["api", "graphql", "-f", "query=query { viewer { login } }"]
    )
    assert out == '{"data": {}}'

    # 8.2: un timeout poi un successo
    primo_timeout = True

    def run_timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal primo_timeout
        if primo_timeout:
            primo_timeout = False
            raise subprocess.TimeoutExpired(cmd=["gh"], timeout=120)
        return subprocess.CompletedProcess(
            args=["gh"], returncode=0, stdout='{"data": {}}', stderr=""
        )

    monkeypatch.setattr("subprocess.run", run_timeout)
    out = board._esegui_di_serie(
        ["api", "graphql", "-f", "query=query { viewer { login } }"]
    )
    assert out == '{"data": {}}'

    # 8.3: tre 503 sollevano ErroreBoard col testo del 503
    def run_sempre_503(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr=_ERR_503
        )

    monkeypatch.setattr("subprocess.run", run_sempre_503)
    with pytest.raises(ErroreBoard, match="HTTP 503"):
        board._esegui_di_serie(
            ["api", "graphql", "-f", "query=query { viewer { login } }"]
        )


def test_9_board_comando_ritenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bottega.ritenta.ATTESE_S", (0.0, 0.0))
    board = BoardComando(["adattatore", "bottega"])

    # pronti() ripete dopo un 503 sullo stderr dell'adattatore
    passi_pronti = [
        subprocess.CompletedProcess(
            args=["adattatore"], returncode=1, stdout="", stderr=_ERR_503
        ),
        subprocess.CompletedProcess(
            args=["adattatore"], returncode=0, stdout="[]", stderr=""
        ),
    ]

    def run_pronti(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return passi_pronti.pop(0)

    monkeypatch.setattr("subprocess.run", run_pronti)
    assert board.pronti() == []

    # stato(...) (una scrittura) non ripete
    chiamate_stato = 0

    def run_stato(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal chiamate_stato
        chiamate_stato += 1
        return subprocess.CompletedProcess(
            args=["adattatore"], returncode=1, stdout="", stderr=_ERR_503
        )

    monkeypatch.setattr("subprocess.run", run_stato)
    with pytest.raises(ErroreBoard):
        board.stato(1, "in_corso")
    assert chiamate_stato == 1
