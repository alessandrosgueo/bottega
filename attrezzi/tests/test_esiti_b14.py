"""Prove per il compito B14-K3: lo spazzino degli esiti nel distributore."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import random
from typing import Any

import pytest

from bottega.board import ErroreBoard, Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.distributore import _scrivi_esiti_dei_chiusi, distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import ErroreForgia, Issue
from bottega.segni import nota


class _BoardConChiusi(BoardFinta):
    """BoardFinta che conserva il campo aperta=False dei lavori caricati."""

    def __init__(self, lavori: Sequence[Lavoro] | None = None, repo: str | None = None) -> None:
        self._chiuse = {lav.numero for lav in (lavori or []) if not lav.aperta}
        super().__init__(lavori, repo=repo)

    def _a_lavoro(self, d: dict[str, Any]) -> Lavoro:
        lav = super()._a_lavoro(d)
        if lav.numero in self._chiuse:
            return replace(lav, aperta=False)
        return lav

    def pronti(self) -> list[Lavoro]:
        return [lav for lav in super().pronti() if lav.aperta]


class _ForgiaContata(ForgiaFinta):
    """ForgiaFinta che conta le chiamate a chiusura e sotto_issue."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chiamate_chiusura: list[int] = []
        self.chiamate_sotto_issue: list[int] = []

    def chiusura(self, n: int) -> tuple[str, datetime] | None:
        self.chiamate_chiusura.append(n)
        return super().chiusura(n)

    def sotto_issue(self, n: int) -> list[Issue]:
        self.chiamate_sotto_issue.append(n)
        return super().sotto_issue(n)


def _configurazione_base() -> Configurazione:
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso="UTC",
        notte="02:00",
        manutenzione=(),
        project=1,
        liberi=("bug",),
    )
    botteghe = {
        "b-claude": Bottega(id="b-claude", quota="abbondante", porte=("claude-code",)),
    }
    candidati = {
        "c-claude": Candidato(
            id="c-claude",
            nome="Claude",
            bottega="b-claude",
            porta="claude-code",
            modello="claude-3-7-sonnet",
            funzioni=("eseguire", "decidere"),
            runner="linux",
        ),
    }
    return Configurazione(versione=1, progetto=progetto, botteghe=botteghe, candidati=candidati)


def test_lavoro_aperto_non_riceve_esiti() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_madre = forgia.crea_issue("Lavoro aperto", "Corpo")
    num_comp = forgia.crea_issue("Compito chiuso", "Corpo", madre=num_madre)
    forgia.chiudi_come(num_comp, "completed", adesso - timedelta(hours=2))

    board = _BoardConChiusi([
        Lavoro(numero=num_madre, titolo="Lavoro aperto", stato="in corso", aperta=True),
        Lavoro(
            numero=num_comp,
            titolo="Compito chiuso",
            stato="",
            aperta=False,
            campi={"Giri": "1"},
        ),
    ])

    righe = _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert righe == []
    assert forgia.chiamate_chiusura == []
    assert board.lavoro(num_comp).campi.get("Esito del compito") is None


def test_esito_gia_scritto_non_si_sovrascrive() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_madre = forgia.crea_issue("Lavoro chiuso", "Corpo")
    c1 = forgia.crea_issue("Compito 1", "Corpo", madre=num_madre)
    c2 = forgia.crea_issue("Compito 2", "Corpo", madre=num_madre)
    forgia.chiudi_come(num_madre, "completed", adesso - timedelta(days=1))

    board = _BoardConChiusi([
        Lavoro(numero=num_madre, titolo="Lavoro chiuso", stato="consegnato", aperta=False),
        Lavoro(
            numero=c1,
            titolo="Compito 1",
            stato="",
            aperta=False,
            campi={"Giri": "2", "Esito del compito": "corretto"},
        ),
        Lavoro(
            numero=c2,
            titolo="Compito 2",
            stato="",
            aperta=False,
            campi={"Giri": "1"},
        ),
    ])

    righe = _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert board.lavoro(c1).campi["Esito del compito"] == "corretto"
    assert board.lavoro(c2).campi["Esito del compito"] == "unito com'era"
    assert righe == [f"lavoro {num_madre}: esiti scritti (1 uniti com'erano, 1 già scritti)"]
    assert nota(board.lavoro(num_madre).nota)["esiti"] == "scritti"


def test_chiuso_not_planned_scrive_rifiutato() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_madre = forgia.crea_issue("Lavoro rifiutato", "Corpo")
    c1 = forgia.crea_issue("Compito 1", "Corpo", madre=num_madre)
    forgia.chiudi_come(num_madre, "not_planned", adesso - timedelta(hours=5))

    board = _BoardConChiusi([
        Lavoro(numero=num_madre, titolo="Lavoro rifiutato", stato="bloccato", aperta=False),
        Lavoro(numero=c1, titolo="Compito 1", stato="", aperta=False, campi={"Giri": "1"}),
    ])

    righe = _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert board.lavoro(c1).campi["Esito del compito"] == "rifiutato"
    assert nota(board.lavoro(num_madre).nota)["esiti"] == "scritti"
    assert righe == [f"lavoro {num_madre}: esiti scritti (1 rifiutati, 0 già scritti)"]


def test_chiuso_altro_motivo_scrive_nota_saltati() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_madre = forgia.crea_issue("Lavoro duplicato", "Corpo")
    c1 = forgia.crea_issue("Compito 1", "Corpo", madre=num_madre)
    forgia.chiudi_come(num_madre, "duplicate", adesso - timedelta(hours=5))

    board = _BoardConChiusi([
        Lavoro(numero=num_madre, titolo="Lavoro duplicato", stato="consegnato", aperta=False),
        Lavoro(numero=c1, titolo="Compito 1", stato="", aperta=False, campi={"Giri": "1"}),
    ])

    _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert board.lavoro(c1).campi.get("Esito del compito") is None
    assert nota(board.lavoro(num_madre).nota)["esiti"] == "saltati"


def test_chiuso_da_piu_di_7_giorni_da_adesso_scrive_vecchi() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_vecchio = forgia.crea_issue("Lavoro vecchio", "Corpo")
    c_vecchio = forgia.crea_issue("Compito vecchio", "Corpo", madre=num_vecchio)
    forgia.chiudi_come(num_vecchio, "completed", adesso - timedelta(days=7, seconds=1))

    num_al_limite = forgia.crea_issue("Lavoro al limite", "Corpo")
    c_limite = forgia.crea_issue("Compito limite", "Corpo", madre=num_al_limite)
    forgia.chiudi_come(num_al_limite, "completed", adesso - timedelta(days=7))

    board = _BoardConChiusi([
        Lavoro(numero=num_vecchio, titolo="Lavoro vecchio", stato="consegnato", aperta=False),
        Lavoro(numero=c_vecchio, titolo="Compito vecchio", stato="", aperta=False, campi={"Giri": "1"}),
        Lavoro(numero=num_al_limite, titolo="Lavoro al limite", stato="consegnato", aperta=False),
        Lavoro(numero=c_limite, titolo="Compito limite", stato="", aperta=False, campi={"Giri": "1"}),
    ])

    _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert board.lavoro(c_vecchio).campi.get("Esito del compito") is None
    assert nota(board.lavoro(num_vecchio).nota)["esiti"] == "vecchi"
    assert board.lavoro(c_limite).campi["Esito del compito"] == "unito com'era"
    assert nota(board.lavoro(num_al_limite).nota)["esiti"] == "scritti"


def test_lavoro_riaperto_nel_frattempo_viene_saltato() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    num_madre = forgia.crea_issue("Lavoro riaperto", "Corpo")
    c1 = forgia.crea_issue("Compito 1", "Corpo", madre=num_madre)
    # In forgia l'issue è aperta (riaperta dopo la lettura dell'elenco), quindi chiusura() dà None.

    board = _BoardConChiusi([
        Lavoro(numero=num_madre, titolo="Lavoro riaperto", stato="consegnato", aperta=False),
        Lavoro(numero=c1, titolo="Compito 1", stato="", aperta=False, campi={"Giri": "1"}),
    ])

    righe = _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert righe == []
    assert board.lavoro(c1).campi.get("Esito del compito") is None
    assert "esiti" not in nota(board.lavoro(num_madre).nota)


def test_solo_compiti_lavorati_e_lavoro_senza_sotto_issue() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    m1 = forgia.crea_issue("Con sotto-issue", "Corpo")
    c_lavorato = forgia.crea_issue("Lavorato", "Corpo", madre=m1)
    c_zero = forgia.crea_issue("Non lavorato", "Corpo", madre=m1)
    forgia.chiudi_come(m1, "completed", adesso - timedelta(hours=3))

    m2 = forgia.crea_issue("Senza sotto-issue", "Corpo")
    forgia.chiudi_come(m2, "completed", adesso - timedelta(hours=3))

    board = _BoardConChiusi([
        Lavoro(numero=m1, titolo="Con sotto-issue", stato="consegnato", aperta=False),
        Lavoro(numero=c_lavorato, titolo="Lavorato", stato="", aperta=False, campi={"Giri": "2"}),
        Lavoro(numero=c_zero, titolo="Non lavorato", stato="", aperta=False, campi={"Giri": "0"}),
        Lavoro(numero=m2, titolo="Senza sotto-issue", stato="consegnato", aperta=False, campi={"Giri": "1"}),
    ])

    _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert board.lavoro(c_lavorato).campi["Esito del compito"] == "unito com'era"
    assert board.lavoro(c_zero).campi.get("Esito del compito") is None
    assert board.lavoro(m2).campi["Esito del compito"] == "unito com'era"


def test_non_rifa_chiamate_e_preserva_altre_chiavi_nota() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    cfg = _configurazione_base()
    forgia = _ForgiaContata()
    num = forgia.crea_issue("Lavoro singolo", "Corpo")
    forgia.chiudi_come(num, "completed", adesso - timedelta(hours=4))

    board = _BoardConChiusi([
        Lavoro(
            numero=num,
            titolo="Lavoro singolo",
            stato="consegnato",
            nota="precedente=Claude; tentativi=1",
            aperta=False,
            campi={"Giri": "1"},
        ),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )

    assert len(forgia.chiamate_chiusura) == 1
    assert len(forgia.chiamate_sotto_issue) == 1
    lav_dopo = board.lavoro(num)
    assert lav_dopo.stato == "consegnato"
    valori_nota = nota(lav_dopo.nota)
    assert valori_nota == {"precedente": "Claude", "tentativi": "1", "esiti": "scritti"}
    # Verifica che non sia stato usato board.stato(), ma solo board.campo("Nota del giro", ...)
    assert not any(reg[0] == "stato" for reg in board.registro)

    # Secondo giro: nessuna chiamata a chiusura o sotto_issue per quel lavoro
    forgia.chiamate_chiusura.clear()
    forgia.chiamate_sotto_issue.clear()
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )
    assert forgia.chiamate_chiusura == []
    assert forgia.chiamate_sotto_issue == []


def test_al_piu_10_candidati_dal_numero_piu_alto() -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    forgia = _ForgiaContata()
    lavori: list[Lavoro] = []
    for i in range(1, 13):
        num = forgia.crea_issue(f"Lavoro {i}", "Corpo")
        forgia.chiudi_come(num, "completed", adesso - timedelta(hours=1))
        lavori.append(
            Lavoro(numero=num, titolo=f"Lavoro {i}", stato="consegnato", aperta=False, campi={"Giri": "1"})
        )

    board = _BoardConChiusi(lavori)

    _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    assert forgia.chiamate_chiusura == list(range(12, 2, -1))
    for i in range(3, 13):
        assert nota(board.lavoro(i).nota)["esiti"] == "scritti"
    for i in (1, 2):
        assert "esiti" not in nota(board.lavoro(i).nota)

    # Secondo giro: prende i 2 rimasti
    forgia.chiamate_chiusura.clear()
    _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)
    assert forgia.chiamate_chiusura == [2, 1]
    for i in (1, 2):
        assert nota(board.lavoro(i).nota)["esiti"] == "scritti"


def test_errore_forgia_su_chiusura_non_ferma_distribuzione(capsys: pytest.CaptureFixture[str]) -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    cfg = _configurazione_base()

    class _ForgiaCheCadeSuChiusura(ForgiaFinta):
        def chiusura(self, n: int) -> tuple[str, datetime] | None:
            raise ErroreForgia("GitHub API 502")

    forgia = _ForgiaCheCadeSuChiusura()
    num_chiuso = forgia.crea_issue("Lavoro chiuso", "Corpo")
    forgia.chiudi_come(num_chiuso, "completed", adesso - timedelta(hours=1))
    num_pronto = forgia.crea_issue(
        "Lavoro pronto",
        "## Fatto quando\n```\nuv run pytest\n```",
    )

    board = _BoardConChiusi([
        Lavoro(numero=num_chiuso, titolo="Lavoro chiuso", stato="consegnato", aperta=False, campi={"Giri": "1"}),
        Lavoro(
            numero=num_pronto,
            titolo="Lavoro pronto",
            stato="pronto",
            etichette=["bottega: fuori"],
            aperta=True,
        ),
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )

    cattura = capsys.readouterr()
    assert "502" in cattura.err
    assert "esiti" not in nota(board.lavoro(num_chiuso).nota)
    assert any(f"lavoro {num_pronto}: assegnato" in r for r in righe)


def test_errore_board_su_campo_non_ferma_distribuzione(capsys: pytest.CaptureFixture[str]) -> None:
    adesso = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)

    class _BoardConErroreCampo(_BoardConChiusi):
        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            raise ErroreBoard("Scrittura fallita")

    forgia = _ForgiaContata()
    num_chiuso = forgia.crea_issue("Lavoro chiuso", "Corpo")
    forgia.chiudi_come(num_chiuso, "completed", adesso - timedelta(hours=1))

    board = _BoardConErroreCampo([
        Lavoro(numero=num_chiuso, titolo="Lavoro chiuso", stato="consegnato", aperta=False, campi={"Giri": "1"}),
    ])

    righe = _scrivi_esiti_dei_chiusi(board.elenco(), forgia, board, adesso)

    cattura = capsys.readouterr()
    assert "Scrittura fallita" in cattura.err
    assert righe == []
    assert "esiti" not in nota(board.lavoro(num_chiuso).nota)
