"""Prove della ripresa dal rosso (0.2.8): dopo un oracolo rosso, un esecutore che non ha niente da aggiungere non conta
un tentativo fallito se da allora chi decide ha cambiato il ramo o il «Fatto quando»: il giro rilancia l'oracolo. Se
niente è cambiato vale ancora B9-R4 (`test_rosso_senza_commit_nel_giro_dopo_non_riprende_dall_oracolo`)."""

from dataclasses import replace
from pathlib import Path
import subprocess

from bottega.finta import ForgiaFinta
from bottega.porte import Lancio
from bottega.segni import nota, scrivi_nota

from test_giro_b9 import (
    RAMO_TAPPA,
    PortaFinta,
    _brief,
    _committa,
    _crea_ambiente_git,
    _giro,
    _tappa_con_due_compiti,
)


def _primo_giro_rosso(tmp_path: Path):
    """Primo giro: l'esecutore consegna `file.txt`, l'oracolo del compito 2 (`test -f corretto.txt`) è rosso."""
    origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _tappa_con_due_compiti()
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])
    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=0)
    assert (esito.esito, esito.oracolo_ok) == ("errore", False)
    porta.callback = lambda cartella, prompt, **kw: Lancio("fatto", "niente da correggere: il rosso viene dal comando")
    return origin, clone, forgia, board, porta


def _cambia_fatto_quando(forgia: ForgiaFinta, numero: int, comando: str) -> None:
    forgia._issues[numero] = replace(forgia.issue(numero), corpo=_brief(comando))


def _spingi_sul_ramo(tmp_path: Path, origin: Path, nome_file: str) -> None:
    """Chi decide spinge un commit sopra la consegna rossa, fra due giri."""
    copia = tmp_path / "copia-di-chi-decide"
    subprocess.run(["git", "clone", "-b", RAMO_TAPPA, str(origin), str(copia)], check=True, capture_output=True)
    for chiave, valore in (("user.name", "Chi decide"), ("user.email", "decide@example.com")):
        subprocess.run(["git", "config", chiave, valore], cwd=str(copia), check=True, capture_output=True)
    _committa(copia, nome_file)
    subprocess.run(["git", "push", "origin", RAMO_TAPPA], cwd=str(copia), check=True, capture_output=True)


def _esiti_dell_oracolo(forgia: ForgiaFinta, numero: int) -> list[str]:
    righe = (riga for c in forgia.commenti(numero) for riga in c.corpo.splitlines())
    return [riga for riga in righe if riga.startswith("Esito dell'oracolo:")]


def test_rosso_poi_fatto_quando_corretto_chiude_il_compito(tmp_path: Path) -> None:
    """Il rosso veniva dal comando: chi decide corregge il «Fatto quando», l'esecutore non committa, il giro rilancia
    l'oracolo nuovo, verde, e chiude il compito senza contare un tentativo."""
    _origin, clone, forgia, board, porta = _primo_giro_rosso(tmp_path)
    _cambia_fatto_quando(forgia, 2, "test -f file.txt")

    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    assert (esito.esito, esito.oracolo_ok) == ("consegnato", True)
    assert forgia.issue(2).stato == "CLOSED"
    assert forgia.issue(3).stato == "OPEN"
    assert _esiti_dell_oracolo(forgia, 2) == ["Esito dell'oracolo: ROSSO (codice 1)", "Esito dell'oracolo: VERDE (codice 0)"]
    assert any("riprende dall'oracolo" in c.corpo and "«Fatto quando»" in c.corpo for c in forgia.commenti(2))
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_nota = nota(lav.nota)
    for chiave in ("tentativi", "rosso", "consegnato"):
        assert chiave not in d_nota


def test_rosso_poi_commit_di_chi_decide_chiude_il_compito(tmp_path: Path) -> None:
    """Chi decide corregge lui sul ramo, sopra la consegna rossa: il giro rilancia l'oracolo sulla punta nuova. La
    rilettura e i controlli guardano solo la consegna dell'esecutore, non il commit di chi decide."""
    origin, clone, forgia, board, porta = _primo_giro_rosso(tmp_path)
    _spingi_sul_ramo(tmp_path, origin, "corretto.txt")

    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    assert (esito.esito, esito.oracolo_ok) == ("consegnato", True)
    assert forgia.issue(2).stato == "CLOSED"
    assert any("riprende dall'oracolo" in c.corpo and "ramo" in c.corpo for c in forgia.commenti(2))
    riletture = [lancio["prompt"] for lancio in porta.lanci if lancio["sola_lettura"]]
    assert "file.txt" in riletture[-1]
    assert "corretto.txt" not in riletture[-1]
    # Il ramo remoto non torna indietro: il commit di chi decide resta.
    assert subprocess.run(
        ["git", "show", f"{RAMO_TAPPA}:corretto.txt"], cwd=str(origin), capture_output=True, check=False
    ).returncode == 0


def test_rosso_ripreso_e_ancora_rosso_non_si_ripete(tmp_path: Path) -> None:
    """Un «Fatto quando» corretto ma ancora rosso conta un tentativo; il giro dopo, senza altri cambi, non rilancia
    l'oracolo (B9-R4): «nessun commit», e al terzo tentativo serve chi decide."""
    _origin, clone, forgia, board, porta = _primo_giro_rosso(tmp_path)
    _cambia_fatto_quando(forgia, 2, "test -f ancora-manca.txt")

    esito2 = _giro(tmp_path, clone, forgia, board, porta, minuti=10)
    assert (esito2.esito, esito2.motivo, esito2.oracolo_ok) == ("errore", "oracolo rosso", False)
    assert nota(board.lavoro(1).nota)["tentativi"] == "2"

    esito3 = _giro(tmp_path, clone, forgia, board, porta, minuti=20)
    assert (esito3.esito, esito3.motivo) == ("bloccato", "nessun commit")
    assert len(_esiti_dell_oracolo(forgia, 2)) == 2
    assert forgia.issue(2).stato == "OPEN"


def test_rosso_di_un_altro_compito_non_si_riprende(tmp_path: Path) -> None:
    """La nota del rosso vale solo per il suo compito: con un altro compito il giro conta «nessun commit»."""
    _origin, clone, forgia, board, porta = _primo_giro_rosso(tmp_path)
    d_nota = nota(board.lavoro(1).nota)
    pezzi = d_nota["rosso"].split(":")
    d_nota["rosso"] = ":".join(["99", *pezzi[1:]])
    board.stato(1, "pronto", nota=scrivi_nota(d_nota))
    _cambia_fatto_quando(forgia, 2, "test -f file.txt")

    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    assert (esito.esito, esito.motivo) == ("pronto", "nessun commit")
    assert forgia.issue(2).stato == "OPEN"
