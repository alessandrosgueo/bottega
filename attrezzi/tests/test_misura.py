"""Prove per token_dei_contatori e per il comando bottega misura (B5-R6, B5-R7)."""

import argparse
from bottega.board import Lavoro
from bottega.finta import BoardFinta
import bottega.misure as misure
from bottega.misura import argomenti_misura, comando_misura


def test_token_dei_contatori_per_porta() -> None:
    """B5-R5 e R6: si sommano le parti con la lettura dalla cache a un decimo; il totale solo se mancano le parti."""
    c_claude = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 1000,
    }
    assert misure.token_dei_contatori("claude-code", c_claude) == 270
    assert misure.token_dei_contatori("claude-code", {"input_tokens": 100}) == 100

    # antigravity: le parti vincono sul totale (che conta la cache per intero)
    assert misure.token_dei_contatori("antigravity", {"total_tokens": 500, "input_tokens": 100}) == 100
    assert misure.token_dei_contatori("antigravity", {"total_tokens": 500}) == 500
    c_antigravity = {"input_tokens": 100, "output_tokens": 50, "thinking_tokens": 30, "cache_read_tokens": 200}
    assert misure.token_dei_contatori("antigravity", c_antigravity) == 200

    assert misure.token_dei_contatori("pi", {"totalTokens": 350}) == 350
    assert misure.token_dei_contatori("pi", {"input": 100, "output": 50, "cacheRead": 100, "cacheWrite": 10}) == 170

    c_copilot = {"inputTokens": 100, "outputTokens": 50, "cacheReadTokens": 100, "cacheWriteTokens": 10}
    assert misure.token_dei_contatori("copilot-cli", c_copilot) == 170

    # porta sconosciuta: solo un totale; contatori non interi valgono 0
    assert misure.token_dei_contatori("altra", {"total_tokens": 7}) == 7
    assert misure.token_dei_contatori("claude-code", {"input_tokens": "100", "output_tokens": 5}) == 5

def test_misura_esito_e_rilievi() -> None:
    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1")])

    parser = argparse.ArgumentParser()
    argomenti_misura(parser)

    args = parser.parse_args([
        "1",
        "--esito", "unito",
        "--rilievi-piano", "2",
        "--rilievi-brief", "1",
        "--rilievi-esecuzione", "3",
        "--consigli-accolti", "4",
        "--consigli-respinti", "0",
        "--porta", "claude-code",
        "--dove", "sessione",
    ])

    codice = comando_misura(args, board=board)
    assert codice == 0

    lav = board.lavoro(1)
    assert lav is not None
    assert lav.campi.get("Esito del compito") == "unito com'era"
    assert lav.campi.get("Rilievi del piano") == "2"
    assert lav.campi.get("Rilievi del brief") == "1"
    assert lav.campi.get("Rilievi dell'esecuzione") == "3"
    assert lav.campi.get("Consigli accolti") == "4"
    assert lav.campi.get("Consigli respinti") == "0"
    assert lav.campi.get("Porta") == "claude-code"
    assert lav.campi.get("Dove") == "sessione"

    # Verifica anche 'corretto' e 'rifiutato'
    args_corr = parser.parse_args(["1", "--esito", "corretto"])
    assert comando_misura(args_corr, board=board) == 0
    assert board.lavoro(1).campi.get("Esito del compito") == "corretto"

    args_rif = parser.parse_args(["1", "--esito", "rifiutato"])
    assert comando_misura(args_rif, board=board) == 0
    assert board.lavoro(1).campi.get("Esito del compito") == "rifiutato"


def test_misura_si_somma() -> None:
    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1")])
    parser = argparse.ArgumentParser()
    argomenti_misura(parser)

    # Primo giro di misure
    args1 = parser.parse_args([
        "1",
        "--durata", "15",
        "--giri", "1",
        "--token-esecutore", "1000",
        "--rilievi-piano", "1",
    ])
    assert comando_misura(args1, board=board) == 0

    lav = board.lavoro(1)
    assert lav.campi.get("Durata") == "15"
    assert lav.campi.get("Giri") == "1"
    assert lav.campi.get("Token esecutore") == "1000"
    assert lav.campi.get("Rilievi del piano") == "1"

    # Secondo giro di misure: i numeri si sommano
    args2 = parser.parse_args([
        "1",
        "--durata", "25",
        "--giri", "2",
        "--token-esecutore", "500",
        "--rilievi-piano", "2",
    ])
    assert comando_misura(args2, board=board) == 0

    lav2 = board.lavoro(1)
    assert lav2.campi.get("Durata") == "40"
    assert lav2.campi.get("Giri") == "3"
    assert lav2.campi.get("Token esecutore") == "1500"
    assert lav2.campi.get("Rilievi del piano") == "3"


def test_misura_senza_opzioni() -> None:
    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1")])
    parser = argparse.ArgumentParser()
    argomenti_misura(parser)

    args = parser.parse_args(["1"])
    codice = comando_misura(args, board=board)
    assert codice == 2


def test_misura_dove_sbagliato() -> None:
    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1")])
    parser = argparse.ArgumentParser()
    argomenti_misura(parser)

    args = argparse.Namespace(
        numero=1,
        dove="sbagliato",
        esito=None,
        porta=None,
        durata=None,
        giri=None,
        token_esecutore=None,
        rilievi_piano=None,
        rilievi_brief=None,
        rilievi_esecuzione=None,
        consigli_accolti=None,
        consigli_respinti=None,
        configurazione=None,
    )
    codice = comando_misura(args, board=board)
    assert codice == 2
