"""Prove per il comando bottega correggi (B14-R2)."""

import argparse
from pathlib import Path

import pytest

from bottega.__main__ import ARGOMENTI, COMANDI, main
from bottega.board import ErroreBoard, Lavoro
import bottega.brief as brief
from bottega.correggi import argomenti_correggi, comando_correggi
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    argomenti_correggi(parser)
    return parser.parse_args(argv)


def test_correggi_compito_di_un_lavoro_con_testo_e_rilievi(capsys: pytest.CaptureFixture) -> None:
    """R2: compito N sotto lavoro M; copia 'Fatto quando' così com'è e scrive esito, rilievo e consiglio."""
    comando_fq = "uv run pytest -q attrezzi/tests/test_esempio.py"
    forgia = ForgiaFinta(
        [
            Issue(numero=10, titolo="Lavoro madre", corpo="Piano"),
            Issue(
                numero=11,
                titolo="Compito 1",
                corpo=f"Dettagli.\n\n## Fatto quando\n\n```bash\n{comando_fq}\n```\n",
            ),
        ]
    )
    forgia._madri[11] = 10
    forgia._sotto_issue[10] = [11]

    board = BoardFinta(
        [
            Lavoro(numero=10, titolo="Lavoro madre", stato="consegnato"),
            Lavoro(numero=11, titolo="Compito 1", stato=""),
        ]
    )

    args = _parse(
        [
            "11",
            "--testo",
            "Sistema il caso limite sul bordo",
            "--origine",
            "esecuzione",
            "--consiglio",
        ]
    )
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 0

    out = capsys.readouterr().out.strip().splitlines()
    nuovo = int(out[0])
    assert out[1] == "poi: bottega lancia 10"

    iss_nuova = forgia.issue(nuovo)
    assert forgia.madre_di(nuovo) == 10
    assert iss_nuova.titolo == "Correzione di #11: Sistema il caso limite sul bordo"
    assert "Corregge: #11" in iss_nuova.corpo
    assert brief.fatto_quando(iss_nuova.corpo) == comando_fq

    assert board.lavoro(nuovo) is not None
    lav_11 = board.lavoro(11)
    assert lav_11 is not None
    assert lav_11.campi.get("Esito del compito") == "corretto"
    assert lav_11.campi.get("Rilievi dell'esecuzione") == "1"
    assert lav_11.campi.get("Consigli accolti") == "1"

    lav_10 = board.lavoro(10)
    assert lav_10 is not None
    assert lav_10.esito == "correzioni"


def test_correggi_lavoro_senza_compiti(capsys: pytest.CaptureFixture) -> None:
    """R2: quando N è esso stesso il lavoro (stato Bottega non vuoto), M = N ed esito va su N."""
    forgia = ForgiaFinta(
        [
            Issue(
                numero=20,
                titolo="Lavoro singolo",
                corpo="## Fatto quando\n\n```\nuv run pytest -q\n```\n",
            ),
        ]
    )
    board = BoardFinta([Lavoro(numero=20, titolo="Lavoro singolo", stato="consegnato")])

    args = _parse(["20", "--testo", "Correggi direttamente il lavoro", "--origine", "piano"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 0

    out = capsys.readouterr().out.strip().splitlines()
    nuovo = int(out[0])
    assert out[1] == "poi: bottega lancia 20"
    assert forgia.madre_di(nuovo) == 20

    lav_20 = board.lavoro(20)
    assert lav_20 is not None
    assert lav_20.campi.get("Esito del compito") == "corretto"
    assert lav_20.campi.get("Rilievi del piano") == "1"
    assert lav_20.esito == "correzioni"


def test_correggi_issue_estranea_alla_bottega_rifiuta_senza_scrivere(capsys: pytest.CaptureFixture) -> None:
    """R2: issue senza stato Bottega né madre con stato Bottega -> esce 1 e non scrive nulla."""
    forgia = ForgiaFinta(
        [
            Issue(numero=30, titolo="Issue estranea", corpo="## Fatto quando\n```\necho ok\n```"),
            Issue(numero=31, titolo="Madre estranea", corpo="niente"),
        ]
    )
    forgia._madri[30] = 31
    board = BoardFinta(
        [
            Lavoro(numero=30, titolo="Issue estranea", stato=""),
            Lavoro(numero=31, titolo="Madre estranea", stato=""),
        ]
    )

    args = _parse(["30", "--testo", "Prova"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 1
    assert forgia.registro == []
    assert board.registro == []
    assert capsys.readouterr().err


def test_correggi_lavoro_chiuso_rifiuta_senza_scrivere(capsys: pytest.CaptureFixture) -> None:
    """R2: lavoro M chiuso -> esce 1 e non scrive nulla."""
    forgia = ForgiaFinta(
        [
            Issue(numero=40, titolo="Lavoro chiuso", corpo="Piano"),
            Issue(numero=41, titolo="Compito", corpo="## Fatto quando\n```\necho ok\n```"),
        ]
    )
    forgia._madri[41] = 40
    forgia.chiudi_issue(40)
    board = BoardFinta(
        [
            Lavoro(numero=40, titolo="Lavoro chiuso", stato="consegnato"),
            Lavoro(numero=41, titolo="Compito", stato=""),
        ]
    )

    args = _parse(["41", "--testo", "Non deve partire"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 1
    assert not any(op[0] == "crea_issue" for op in forgia.registro)
    assert board.registro == []
    assert capsys.readouterr().err


def test_correggi_testo_senza_fatto_quando_chiede_brief(capsys: pytest.CaptureFixture) -> None:
    """R2: --testo su N senza 'Fatto quando' -> esce 2 chiedendo --brief, niente scritto."""
    forgia = ForgiaFinta(
        [
            Issue(numero=50, titolo="Lavoro", corpo="Piano"),
            Issue(numero=51, titolo="Compito senza fq", corpo="Solo testo senza sezione"),
        ]
    )
    forgia._madri[51] = 50
    board = BoardFinta(
        [
            Lavoro(numero=50, titolo="Lavoro", stato="consegnato"),
            Lavoro(numero=51, titolo="Compito senza fq", stato=""),
        ]
    )

    args = _parse(["51", "--testo", "Correggi questo"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 2
    assert forgia.registro == []
    assert board.registro == []
    assert "--brief" in capsys.readouterr().err


def test_correggi_con_brief_valido_e_senza_fatto_quando(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """R2: --brief richiede 'Fatto quando' (altrimenti esce 2); se valido usa file com'è e --titolo."""
    forgia = ForgiaFinta([Issue(numero=60, titolo="Lavoro", corpo="Piano")])
    board = BoardFinta([Lavoro(numero=60, titolo="Lavoro", stato="consegnato")])

    brief_vuoto = tmp_path / "vuoto.md"
    brief_vuoto.write_text("Manca la sezione di verifica.\n", encoding="utf-8")
    rc_bad = comando_correggi(_parse(["60", "--brief", str(brief_vuoto)]), forgia=forgia, board=board)
    assert rc_bad == 2
    assert forgia.registro == []
    assert board.registro == []
    capsys.readouterr()

    contenuto = "# Correzione\n\nFai A e B.\n\n## Fatto quando\n\n```\nuv run pytest -q\n```\n"
    brief_ok = tmp_path / "ok.md"
    brief_ok.write_text(contenuto, encoding="utf-8")
    rc_ok = comando_correggi(
        _parse(["60", "--brief", str(brief_ok), "--titolo", "Titolo personalizzato"]),
        forgia=forgia,
        board=board,
    )
    assert rc_ok == 0
    nuovo = int(capsys.readouterr().out.strip().splitlines()[0])
    iss = forgia.issue(nuovo)
    assert iss.titolo == "Titolo personalizzato"
    assert iss.corpo == contenuto


def test_correggi_argomenti_mancanti_o_doppi(capsys: pytest.CaptureFixture) -> None:
    """R2: senza --brief/--testo oppure con entrambi -> esce 2."""
    forgia = ForgiaFinta([Issue(numero=70, titolo="Lavoro", corpo="")])
    board = BoardFinta([Lavoro(numero=70, titolo="Lavoro", stato="consegnato")])

    assert comando_correggi(_parse(["70"]), forgia=forgia, board=board) == 2
    with pytest.raises(SystemExit) as exc:
        _parse(["70", "--testo", "a", "--brief", "b.md"])
    assert exc.value.code == 2
    ns_doppio = argparse.Namespace(numero=70, brief=Path("b.md"), testo="a")
    assert comando_correggi(ns_doppio, forgia=forgia, board=board) == 2
    assert forgia.registro == []
    assert board.registro == []


def test_correggi_fallimento_a_meta_elenca_scritto_e_mancante(capsys: pytest.CaptureFixture) -> None:
    """R2: se una scrittura dopo crea_issue fallisce, esce 1 e stderr dice cosa è scritto e cosa manca."""

    class BoardCheFallisceSuCampo(BoardFinta):
        def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
            if nome == "Esito del compito":
                raise ErroreBoard("rete giù")
            super().campo(numero, nome, valore)

    forgia = ForgiaFinta(
        [
            Issue(numero=80, titolo="Lavoro", corpo="Piano"),
            Issue(numero=81, titolo="Compito", corpo="## Fatto quando\n```\necho ok\n```"),
        ]
    )
    forgia._madri[81] = 80
    board = BoardCheFallisceSuCampo(
        [
            Lavoro(numero=80, titolo="Lavoro", stato="consegnato"),
            Lavoro(numero=81, titolo="Compito", stato=""),
        ]
    )

    args = _parse(["81", "--testo", "Sistema errore", "--origine", "brief", "--consiglio"])
    rc = comando_correggi(args, forgia=forgia, board=board)
    assert rc == 1

    err = capsys.readouterr().err
    nuovi = [op[1] for op in forgia.registro if op[0] == "crea_issue"]
    assert len(nuovi) == 1
    nuovo = nuovi[0]
    assert f"#{nuovo}" in err
    assert "bottega misura 81 --esito corretto" in err
    assert "bottega misura 81 --rilievi-brief 1" in err
    assert "bottega misura 81 --consigli-accolti 1" in err


def test_correggi_registrato_in_main(capsys: pytest.CaptureFixture) -> None:
    """Il sottocomando correggi è registrato in COMANDI e ARGOMENTI."""
    assert "correggi" in COMANDI
    assert "correggi" in ARGOMENTI
    with pytest.raises(SystemExit) as exc:
        main(["correggi", "--help"])
    assert exc.value.code == 0
    assert "correggi" in capsys.readouterr().out
