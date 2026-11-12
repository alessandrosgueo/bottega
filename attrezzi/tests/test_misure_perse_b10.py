"""Prove delle misure perse (Compito B10.1): il giro le scrive sul lavoro madre, `bottega segui` le avvisa.

Solo finti in memoria, nessun comando esterno reale, nessuna attesa reale.
"""

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from bottega.board import ErroreBoard, Lavoro
from bottega.configurazione import Candidato
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import ErroreForgia, Issue
from bottega.giro import _scrivi_misure
from bottega.lancio import comando_segui

CANDIDATO = Candidato(
    id="esecutore-prova",
    nome="Esecutore di prova",
    bottega="principale",
    porta="finta",
    modello="modello-finto",
    funzioni=("eseguire",),
    runner=None,
)

MOTIVO_NON_ELENCATO = "il compito non è nell'elenco dell'adattatore (docs/adattatore.md)"
MOTIVO_BOARD = "errore della board, vedi il log del giro"

CORPO_MISURE = (
    "<!-- bottega:esecutore -->\n"
    f"Misure non scritte sulla board per il compito #591 (motivo: {MOTIVO_NON_ELENCATO}).\n"
    "\n"
    "Durata: 1620 · Giri: 1 · Consulti: 0 · Token esecutore: 4321"
)
AVVISO_MISURE = f"avviso: Misure non scritte sulla board per il compito #591 (motivo: {MOTIVO_NON_ELENCATO})."


def _madre() -> ForgiaFinta:
    return ForgiaFinta(issues=[Issue(numero=587, titolo="Madre", corpo="Brief del lavoro madre.", autore="maestro")])


def _commenti_scritti(forgia: ForgiaFinta) -> list[tuple]:
    return [r for r in forgia.registro if r[0] == "commenta"]


class BoardSenzaElenco:
    """Board finta che non trova il compito, come un adattatore che elenca solo i lavori madre."""

    def __init__(self) -> None:
        self.campi: dict[tuple[int, str], object] = {}
        self.letture = 0

    def lavoro(self, numero: int) -> Lavoro | None:
        self.letture += 1
        return None

    def aggiungi(self, numero: int) -> None:
        pass

    def campo(self, numero: int, nome: str, valore: object) -> None:
        self.campi[(numero, nome)] = valore


class BoardLetturaRotta(BoardSenzaElenco):
    """Come BoardSenzaElenco, ma la rilettura del compito (la sesta lettura) solleva."""

    def lavoro(self, numero: int) -> Lavoro | None:
        self.letture += 1
        if self.letture > 5:
            raise ErroreBoard("board non risponde")
        return None


class BoardContata(BoardFinta):
    """Board finta in memoria che conta le letture."""

    def __init__(self, lavori: Sequence[Lavoro]) -> None:
        super().__init__(lavori=lavori)
        self.letture = 0

    def lavoro(self, numero: int) -> Lavoro | None:
        self.letture += 1
        return super().lavoro(numero)


class BoardTokenRotto(BoardFinta):
    """Board finta in cui fallisce una sola scrittura, quella di Token esecutore."""

    def campo(self, numero: int, nome: str, valore) -> None:
        if nome == "Token esecutore":
            raise ErroreBoard("campo non scrivibile")
        super().campo(numero, nome, valore)


class ForgiaRotta(ForgiaFinta):
    """Forgia finta in cui il commento non parte."""

    def commenta(self, n: int, testo: str, ruolo: str) -> None:
        raise ErroreForgia("commento non scritto")


def test_misure_perse_commentano_sul_lavoro_madre() -> None:
    board = BoardSenzaElenco()
    forgia = _madre()

    perse = _scrivi_misure(
        board,
        591,
        CANDIDATO,
        durata_secondi=1620,
        consulti=0,
        token_esecutore=4321,
        forgia=forgia,
        lavoro_numero=587,
    )

    assert perse == [("Durata", 1620), ("Giri", 1), ("Consulti", 0), ("Token esecutore", 4321)]
    assert _commenti_scritti(forgia) == [("commenta", 587, CORPO_MISURE, "esecutore")]


def test_misure_scritte_nessun_commento() -> None:
    board = BoardContata([Lavoro(numero=591, titolo="Compito", stato="in corso")])
    forgia = _madre()

    perse = _scrivi_misure(
        board,
        591,
        CANDIDATO,
        durata_secondi=1620,
        consulti=0,
        token_esecutore=4321,
        forgia=forgia,
        lavoro_numero=587,
    )

    assert perse == []
    assert _commenti_scritti(forgia) == []
    # Una lettura del compito e una per ciascuna delle quattro misure: nessuna rilettura in più.
    assert board.letture == 5
    assert board.lavoro(591).campi["Token esecutore"] == "4321"


def test_una_sola_misura_persa() -> None:
    board = BoardTokenRotto([Lavoro(numero=591, titolo="Compito", stato="in corso")])
    forgia = _madre()

    perse = _scrivi_misure(
        board,
        591,
        CANDIDATO,
        durata_secondi=1620,
        consulti=0,
        token_esecutore=4321,
        forgia=forgia,
        lavoro_numero=587,
    )

    assert perse == [("Token esecutore", 4321)]
    testo = f"Misure non scritte sulla board per il compito #591 (motivo: {MOTIVO_BOARD}).\n\nToken esecutore: 4321"
    assert _commenti_scritti(forgia) == [("commenta", 587, f"<!-- bottega:esecutore -->\n{testo}", "esecutore")]


def test_il_commento_che_non_parte_non_fa_cadere_il_giro(capsys: pytest.CaptureFixture[str]) -> None:
    board = BoardSenzaElenco()
    forgia = ForgiaRotta(issues=[Issue(numero=587, titolo="Madre", corpo="Brief.", autore="maestro")])

    perse = _scrivi_misure(
        board,
        591,
        CANDIDATO,
        durata_secondi=1620,
        consulti=0,
        token_esecutore=4321,
        forgia=forgia,
        lavoro_numero=587,
    )

    assert perse == [("Durata", 1620), ("Giri", 1), ("Consulti", 0), ("Token esecutore", 4321)]
    _, err = capsys.readouterr()
    assert "misure: commento delle misure perse del #591 non scritto: commento non scritto" in err


def test_rilettura_che_solleva_conta_come_non_elencato(capsys: pytest.CaptureFixture[str]) -> None:
    board = BoardLetturaRotta()
    forgia = _madre()

    _scrivi_misure(
        board,
        591,
        CANDIDATO,
        durata_secondi=1620,
        consulti=0,
        token_esecutore=4321,
        forgia=forgia,
        lavoro_numero=587,
    )

    commenti = _commenti_scritti(forgia)
    assert len(commenti) == 1
    assert f"(motivo: {MOTIVO_NON_ELENCATO})." in commenti[0][2]
    _, err = capsys.readouterr()
    assert "misure: rilettura del #591 fallita: board non risponde" in err


def test_senza_forgia_nessun_commento() -> None:
    board = BoardSenzaElenco()

    perse = _scrivi_misure(board, 591, CANDIDATO, durata_secondi=1620, consulti=0, token_esecutore=4321)

    assert perse == [("Durata", 1620), ("Giri", 1), ("Consulti", 0), ("Token esecutore", 4321)]
    # Senza forgia niente rilettura e niente commento.
    assert board.letture == 5


class EsecutoreFinto:
    """Gh finto per `bottega segui`: risponde in base al contenuto del comando, mai alla posizione."""

    def __init__(
        self,
        commenti: Sequence[dict] = (),
        risposta_commenti: tuple[int, str] | None = None,
    ) -> None:
        self.commenti = list(commenti)
        self.risposta_commenti = risposta_commenti
        self.chiamate_commenti = 0

    def __call__(self, cmd: Sequence[str], _=None) -> tuple[int, str]:
        s = " ".join(cmd)
        if s == "gh issue view 42 --json comments":
            self.chiamate_commenti += 1
            if self.risposta_commenti is not None:
                return self.risposta_commenti
            return 0, json.dumps({"comments": self.commenti})
        if "sub_issues" in s or "workflow list" in s:
            return 0, "[]"
        return 0, ""


class BoardSequenza:
    """Board finta: il compito passa dagli stati dati, uno per passo, e resta sull'ultimo."""

    def __init__(self, stati: Sequence[str]) -> None:
        self.stati = list(stati)

    def lavoro(self, numero: int) -> Lavoro:
        stato = self.stati.pop(0) if len(self.stati) > 1 else self.stati[0]
        return Lavoro(numero=numero, titolo="Madre", stato=stato)


class Orologio:
    """Orologio finto che avanza quando si dorme."""

    def __init__(self, istante: datetime) -> None:
        self.istante = istante

    def adesso(self) -> datetime:
        return self.istante

    def dormi(self, secondi: float) -> None:
        self.istante += timedelta(seconds=secondi)


def _argomenti_segui() -> argparse.Namespace:
    return argparse.Namespace(
        numero=42,
        repo=None,
        intervallo=300,
        fermo=1200.0,
        tetto=18000.0,
        configurazione=Path("bottega.toml"),
    )


def test_segui_avvisa_delle_misure_perse_una_volta(capsys: pytest.CaptureFixture[str]) -> None:
    prima_dell_inizio = {"id": "IC_vecchio", "createdAt": "2026-11-12T09:00:00Z", "body": CORPO_MISURE}
    dopo_l_inizio = {"id": "IC_nuovo", "createdAt": "2026-11-12T10:01:00Z", "body": CORPO_MISURE}
    senza_segno = {"id": "IC_altro", "createdAt": "2026-11-12T10:02:00Z", "body": "Un commento qualunque."}
    esecutore = EsecutoreFinto(commenti=[prima_dell_inizio, dopo_l_inizio, senza_segno])
    orologio = Orologio(datetime(2026, 11, 12, 10, 0, tzinfo=UTC))

    rc = comando_segui(
        _argomenti_segui(),
        esegui=esecutore,
        dormi=orologio.dormi,
        adesso=orologio.adesso,
        board=BoardSequenza(["in corso", "consegnato"]),
    )

    out, _ = capsys.readouterr()
    assert rc == 0
    assert "finito" in out
    # Due passi, lo stesso commento visto due volte: una riga sola. Quello di prima dell'inizio non compare.
    assert out.splitlines().count(AVVISO_MISURE) == 1
    assert esecutore.chiamate_commenti == 2


@pytest.mark.parametrize(
    ("risposta", "atteso_in_err"),
    [
        ((1, "errore di rete"), "avviso: errore di rete"),
        ((0, "non è JSON"), "avviso: commenti #42:"),
    ],
)
def test_segui_commenti_illeggibili_va_avanti(
    capsys: pytest.CaptureFixture[str],
    risposta: tuple[int, str],
    atteso_in_err: str,
) -> None:
    esecutore = EsecutoreFinto(risposta_commenti=risposta)
    orologio = Orologio(datetime(2026, 11, 12, 10, 0, tzinfo=UTC))

    rc = comando_segui(
        _argomenti_segui(),
        esegui=esecutore,
        dormi=orologio.dormi,
        adesso=orologio.adesso,
        board=BoardSequenza(["in corso", "consegnato"]),
    )

    out, err = capsys.readouterr()
    assert rc == 0
    assert "finito" in out
    assert atteso_in_err in err
    assert "avviso: Misure" not in out
