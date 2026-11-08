"""Prove per attrezzi/bottega/misure.py: campi, somma, risultati e costi propri."""

import random
from datetime import datetime, timezone
import pytest

from bottega.board import ErroreBoard, Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta
from bottega.misure import (
    CAMPI,
    OPZIONI_ESITO,
    costi_propri,
    numero,
    risultati,
    somma,
)
from bottega.scelta import Compito, Risultati, scegli


def _configurazione_di_base() -> Configurazione:
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso="Europe/Rome",
        notte="01:30",
        manutenzione=(),
    )
    botteghe = {
        "principale": Bottega("principale", "normale", ("porta1",)),
        "secondaria": Bottega("secondaria", "normale", ("porta2",)),
    }
    candidati = {
        "cand-a": Candidato(
            id="cand-a",
            nome="Candidato Alfa",
            bottega="principale",
            porta="porta1",
            modello="modello-a",
            funzioni=("eseguire",),
            runner=None,
        ),
        "cand-b": Candidato(
            id="cand-b",
            nome="Candidato Beta",
            bottega="secondaria",
            porta="porta2",
            modello="modello-b",
            funzioni=("eseguire",),
            runner=None,
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def test_campi_sono_quelli_del_piano() -> None:
    attesi = {
        "Porta": "TEXT",
        "Dove": "TEXT",
        "Durata": "NUMBER",
        "Giri": "NUMBER",
        "Consulti": "NUMBER",
        "Token esecutore": "NUMBER",
        "Token di chi decide": "NUMBER",
        "Segno": "TEXT",
        "Misure parziali": "TEXT",
        "Esito del compito": "SINGLE_SELECT",
        "Rilievi del piano": "NUMBER",
        "Rilievi del brief": "NUMBER",
        "Rilievi dell'esecuzione": "NUMBER",
        "Consigli accolti": "NUMBER",
        "Consigli respinti": "NUMBER",
    }
    assert CAMPI == attesi
    assert OPZIONI_ESITO == ("unito com'era", "corretto", "rifiutato")


def test_numero_vuoto_vale_zero() -> None:
    lav_vuoto = Lavoro(numero=1, titolo="Compito")
    assert numero(lav_vuoto, "Durata") == 0.0

    lav_testo = Lavoro(numero=2, titolo="Compito", campi={"Durata": "non-numero"})
    assert numero(lav_testo, "Durata") == 0.0

    lav_nan = Lavoro(numero=3, titolo="Compito", campi={"Durata": "nan"})
    assert numero(lav_nan, "Durata") == 0.0

    lav_inf = Lavoro(numero=4, titolo="Compito", campi={"Durata": "inf"})
    assert numero(lav_inf, "Durata") == 0.0

    lav_valido = Lavoro(numero=5, titolo="Compito", campi={"Durata": "42"})
    assert numero(lav_valido, "Durata") == 42.0

    lav_decimale = Lavoro(numero=6, titolo="Compito", campi={"Durata": "3.5"})
    assert numero(lav_decimale, "Durata") == 3.5


def test_somma_aggiunge() -> None:
    lav = Lavoro(numero=1, titolo="Compito", campi={"Durata": "10"})
    board = BoardFinta([lav])

    ok = somma(board, 1, "Durata", 5.0)
    assert ok is True
    aggiornato = board.lavoro(1)
    assert aggiornato is not None
    assert aggiornato.campi.get("Durata") == "15"

    ok2 = somma(board, 1, "Durata", 2.5)
    assert ok2 is True
    aggiornato2 = board.lavoro(1)
    assert aggiornato2 is not None
    assert aggiornato2.campi.get("Durata") == "17.5"


def test_somma_non_solleva(capsys: pytest.CaptureFixture[str]) -> None:
    class BoardRotta:
        def lavoro(self, numero: int) -> Lavoro | None:
            return Lavoro(numero=numero, titolo="Compito")

        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            raise ErroreBoard("connessione interrotta")

    board = BoardRotta()
    ok = somma(board, 42, "Durata", 10.0)  # type: ignore[arg-type]
    assert ok is False
    catturato = capsys.readouterr()
    assert "misure: Durata del #42 non scritta: connessione interrotta" in catturato.err


def test_somma_lavoro_assente(capsys: pytest.CaptureFixture[str]) -> None:
    board = BoardFinta([])
    ok = somma(board, 999, "Durata", 10.0)
    assert ok is False
    catturato = capsys.readouterr()
    assert "misure: Durata del #999 non scritta:" in catturato.err


def test_risultati_per_etichetta_e_totale() -> None:
    cfg = _configurazione_di_base()
    lavori = [
        Lavoro(
            numero=1,
            titolo="Compito 1",
            etichette=["backend", "veloce"],
            campi={"Esecutore": "cand-a", "Esito del compito": "unito com'era"},
        ),
        Lavoro(
            numero=2,
            titolo="Compito 2",
            etichette=["backend"],
            campi={"Esecutore": "cand-a", "Esito del compito": "corretto"},
        ),
        Lavoro(
            numero=3,
            titolo="Compito 3",
            etichette=["frontend"],
            campi={"Esecutore": "cand-a", "Esito del compito": "rifiutato"},
        ),
    ]

    res = risultati(lavori, cfg)
    assert res[("cand-a", "*")] == Risultati(uniti=1, corretti=1, rifiutati=1)
    assert res[("cand-a", "backend")] == Risultati(uniti=1, corretti=1, rifiutati=0)
    assert res[("cand-a", "veloce")] == Risultati(uniti=1, corretti=0, rifiutati=0)
    assert res[("cand-a", "frontend")] == Risultati(uniti=0, corretti=0, rifiutati=1)


def test_risultati_nome_o_id() -> None:
    cfg = _configurazione_di_base()
    lavori = [
        Lavoro(
            numero=1,
            titolo="Compito 1",
            campi={"Esecutore": "CAND-A", "Esito del compito": "unito com'era"},
        ),
        Lavoro(
            numero=2,
            titolo="Compito 2",
            campi={"Esecutore": "candidato alfa", "Esito del compito": "unito com'era"},
        ),
        Lavoro(
            numero=3,
            titolo="Compito 3",
            campi={"Esecutore": "Candidato Beta", "Esito del compito": "corretto"},
        ),
    ]

    res = risultati(lavori, cfg)
    assert res[("cand-a", "*")] == Risultati(uniti=2, corretti=0, rifiutati=0)
    assert res[("cand-b", "*")] == Risultati(uniti=0, corretti=1, rifiutati=0)


def test_risultati_salta_esecutore_sconosciuto() -> None:
    cfg = _configurazione_di_base()
    lavori = [
        Lavoro(
            numero=1,
            titolo="Compito 1",
            campi={"Esecutore": "sconosciuto", "Esito del compito": "unito com'era"},
        ),
        Lavoro(
            numero=2,
            titolo="Compito 2",
            campi={"Esecutore": "cand-a", "Esito del compito": "in corso"},  # non in OPZIONI_ESITO
        ),
    ]

    res = risultati(lavori, cfg)
    assert res == {}


def test_costi_propri() -> None:
    cfg = _configurazione_di_base()
    lavori = [
        # cand-a: 100 e 200 -> media 150
        Lavoro(numero=1, titolo="C1", campi={"Esecutore": "cand-a", "Token esecutore": "100"}),
        Lavoro(numero=2, titolo="C2", campi={"Esecutore": "cand-a", "Token esecutore": "200"}),
        # cand-b: 300 -> media 300
        Lavoro(numero=3, titolo="C3", campi={"Esecutore": "cand-b", "Token esecutore": "300"}),
        # lavoro con valore 0: deve essere escluso dal calcolo
        Lavoro(numero=4, titolo="C4", campi={"Esecutore": "cand-b", "Token esecutore": "0"}),
    ]

    # Media delle medie: (150 + 300) / 2 = 225
    # cand-a: 150 / 225 = 2/3
    # cand-b: 300 / 225 = 4/3
    costi = costi_propri(lavori, cfg)
    assert pytest.approx(costi["cand-a"], rel=1e-4) == 150 / 225
    assert pytest.approx(costi["cand-b"], rel=1e-4) == 300 / 225


def test_risultati_spostano_la_scelta() -> None:
    progetto = Progetto(("alice",), None, "Europe/Rome", None, ())
    botteghe = {
        "bottega": Bottega("bottega", "normale", ("porta",)),
    }
    candidati = {
        "nuovo": Candidato("nuovo", "Nuovo", "bottega", "porta", "m", ("eseguire",), None),
        "scarso": Candidato("scarso", "Scarso", "bottega", "porta", "m", ("eseguire",), None),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False)

    lavori = [
        Lavoro(
            numero=i,
            titolo=f"Compito {i}",
            campi={"Esecutore": "scarso", "Esito del compito": "rifiutato"},
        )
        for i in range(1, 11)
    ]
    res = risultati(lavori, cfg)

    vittorie_scarso = 0
    semi = 500
    for s in range(semi):
        scelta = scegli(compito, cfg, res, {}, adesso, random.Random(s))
        if scelta.candidato == "scarso":
            vittorie_scarso += 1

    percentuale_scarso = vittorie_scarso / semi
    assert percentuale_scarso < 0.15, f"Candidato scarso scelto troppo spesso: {percentuale_scarso:.1%}"
