"""Prove per il comando bottega conti (bottega.conti)."""

import json
from argparse import Namespace
from bottega.board import Lavoro
from bottega.conti import (
    argomenti_conti,
    comando_conti,
    conti,
    testo_conti,
)
from bottega.finta import BoardFinta


def test_conti_per_candidato():
    lavori = [
        Lavoro(
            numero=1,
            titolo="Compito 1",
            esecutore="Alice",
            campi={
                "Esecutore": "Alice",
                "Dove": "fuori",
                "Giri": "2",
                "Durata": "120",
                "Token esecutore": "1000",
                "Token di chi decide": "500",
                "Esito del compito": "unito com'era",
                "Rilievi del piano": "1",
                "Consigli accolti": "2",
            },
        ),
        Lavoro(
            numero=2,
            titolo="Compito 2",
            esecutore="Alice",
            campi={
                "Esecutore": "Alice",
                "Dove": "fuori",
                "Giri": "4",
                "Durata": "240",
                "Token esecutore": "2000",
                "Token di chi decide": "700",
                "Esito del compito": "corretto",
                "Rilievi del brief": "2",
                "Consigli respinti": "1",
            },
        ),
        Lavoro(
            numero=3,
            titolo="Compito 3",
            esecutore="Bob",
            campi={
                "Esecutore": "Bob",
                "Dove": "sessione",
                "Giri": "1",
                "Durata": "60",
                "Token esecutore": "500",
                "Token di chi decide": "300",
                "Esito del compito": "rifiutato",
                "Rilievi dell'esecuzione": "3",
            },
        ),
        Lavoro(
            numero=4,
            titolo="Compito non misurato",
            campi={"Nota del giro": "testo qualsiasi"},
        ),
    ]

    res = conti(lavori)

    assert "Alice" in res["per_candidato"]
    assert "Bob" in res["per_candidato"]

    alice = res["per_candidato"]["Alice"]
    assert alice["compiti"] == 2
    assert alice["giri_medi"] == 3.0
    assert alice["durata_media"] == 180.0
    assert alice["token_esecutore_medi"] == 1500.0
    assert alice["token_decisore_medi"] == 600.0
    assert alice["senza_numero"] == 0
    assert alice["esiti"] == {"unito com'era": 1, "corretto": 1, "rifiutato": 0}
    assert alice["rilievi"] == {"piano": 1, "brief": 2, "esecuzione": 0}
    assert alice["consigli"] == {"accolti": 2, "respinti": 1}

    bob = res["per_candidato"]["Bob"]
    assert bob["compiti"] == 1
    assert bob["giri_medi"] == 1.0
    assert bob["durata_media"] == 60.0
    assert bob["token_esecutore_medi"] == 500.0
    assert bob["token_decisore_medi"] == 300.0
    assert bob["senza_numero"] == 0
    assert bob["esiti"] == {"unito com'era": 0, "corretto": 0, "rifiutato": 1}
    assert bob["rilievi"] == {"piano": 0, "brief": 0, "esecuzione": 3}
    assert bob["consigli"] == {"accolti": 0, "respinti": 0}


def test_conti_media_su_zero_e_none():
    res = conti([])
    assert res["per_candidato"] == {}
    for dove in ("fuori", "sessione"):
        stats = res["per_dove"][dove]
        assert stats["compiti"] == 0
        assert stats["giri_medi"] is None
        assert stats["durata_media"] is None
        assert stats["token_esecutore_medi"] is None
        assert stats["token_decisore_medi"] is None
        assert stats["senza_numero"] == 0
        assert stats["esiti"] == {"unito com'era": 0, "corretto": 0, "rifiutato": 0}
        assert stats["rilievi"] == {"piano": 0, "brief": 0, "esecuzione": 0}
        assert stats["consigli"] == {"accolti": 0, "respinti": 0}
    assert res["spia"] == {"fuori": None, "sessione": None}

    # Anche con soli lavori senza misure
    lavori_senza = [Lavoro(numero=1, titolo="Non misurato", campi={"Nota del giro": "x"})]
    assert conti(lavori_senza) == res


def test_conti_senza_numero():
    lavori = [
        Lavoro(
            numero=1,
            titolo="C1",
            campi={
                "Dove": "fuori",
                "Durata": "100",
                "Token esecutore": "500",
                "Token di chi decide": "1000",
            },
        ),
        Lavoro(
            numero=2,
            titolo="C2",
            campi={
                "Dove": "fuori",
                "Durata": "100",
                "Token esecutore": "500",
            },
        ),
    ]

    res = conti(lavori)
    fuori = res["per_dove"]["fuori"]
    assert fuori["compiti"] == 2
    assert fuori["senza_numero"] == 1
    assert fuori["token_decisore_medi"] == 1000.0


def test_conti_spia():
    lavori = [
        Lavoro(
            numero=1,
            titolo="C1",
            campi={
                "Dove": "fuori",
                "Durata": "100",
                "Token di chi decide": "1200",
            },
        ),
        Lavoro(
            numero=2,
            titolo="C2",
            campi={
                "Dove": "sessione",
                "Durata": "50",
                "Token di chi decide": "400",
            },
        ),
    ]

    res = conti(lavori)
    assert res["spia"] == {"fuori": 1200.0, "sessione": 400.0}


def test_testo_conti_trattino():
    d = conti([])
    testo = testo_conti(d)
    assert "—" in testo
    assert "fuori" in testo
    assert "sessione" in testo


def test_comando_conti_json(capsys):
    lavori = [
        Lavoro(
            numero=1,
            titolo="C1",
            campi={
                "Dove": "fuori",
                "Durata": "100",
                "Token di chi decide": "1000",
            },
        )
    ]
    board = BoardFinta(lavori=lavori)
    args = Namespace(json=True, file="bottega.toml", repo="")
    codice = comando_conti(args, board=board)
    assert codice == 0

    catturato = capsys.readouterr()
    dati = json.loads(catturato.out)
    assert "per_dove" in dati
    assert "spia" in dati
    assert dati["spia"]["fuori"] == 1000.0
