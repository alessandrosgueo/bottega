"""Prove per i tempi del giro e l'involucro cronometrato di board e forgia (B14-R9)."""

from __future__ import annotations

import builtins
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import ErroreForgia, Issue
import bottega.giro as modulo_giro
from bottega.giro import giro
from bottega.porte import Controllo, Lancio


class _OrologioFinto:
    """Orologio finto che avanza solo su comando."""

    def __init__(self, iniziale: float = 1000.0) -> None:
        self.adesso = iniziale

    def __call__(self) -> float:
        return self.adesso

    def avanza(self, secondi: float) -> None:
        self.adesso += secondi


class _PortaFintaTempi:
    """Porta finta configurabile che avanza l'orologio finto nei lanci."""

    nome = "finta"
    eseguibile = "finta"

    def __init__(
        self,
        orologio: _OrologioFinto,
        *,
        controllo_ok: bool = True,
        secondi_controllo: float = 0.0,
        secondi_esecutore: float = 0.0,
        secondi_rilettura: float = 0.0,
        callback_esecutore: Any = None,
    ) -> None:
        self._orologio = orologio
        self._controllo_ok = controllo_ok
        self._secondi_controllo = secondi_controllo
        self._secondi_esecutore = secondi_esecutore
        self._secondi_rilettura = secondi_rilettura
        self._callback_esecutore = callback_esecutore

    def controlla(self, prefisso: tuple[str, ...] = ()) -> Controllo:
        self._orologio.avanza(self._secondi_controllo)
        motivo = None if self._controllo_ok else "porta spenta"
        return Controllo(ok=self._controllo_ok, versione="1.0", motivo=motivo)

    def lancia(
        self,
        cartella: Path | str,
        prompt: str,
        modello: str,
        *,
        conversazione: str | None = None,
        sola_lettura: bool = False,
        prefisso: tuple[str, ...] = (),
        tempo: int | float = 3600,
    ) -> Lancio:
        if sola_lettura:
            self._orologio.avanza(self._secondi_rilettura)
            return Lancio(esito="fatto", testo="SEGRETO_RILETTURA_MODELLO\nnessun rilievo")
        self._orologio.avanza(self._secondi_esecutore)
        if self._callback_esecutore is not None:
            return self._callback_esecutore(cartella, prompt)
        p_cartella = Path(cartella)
        (p_cartella / "fatto.txt").write_text("fatto\n", encoding="utf-8")
        subprocess.run(["git", "add", "fatto.txt"], cwd=str(p_cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: fatto"], cwd=str(p_cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="SEGRETO_ESECUTORE_MODELLO\ncompletato")


class _BoardCronometrata(BoardFinta):
    """BoardFinta che avanza l'orologio finto a ogni chiamata ai suoi metodi."""

    def __init__(
        self,
        orologio: _OrologioFinto,
        secondi_per_chiamata: float,
        lavori: list[Lavoro],
    ) -> None:
        super().__init__(lavori=lavori)
        self._orologio = orologio
        self._sec = secondi_per_chiamata
        self.contate = 0

    def _tic(self) -> None:
        self.contate += 1
        self._orologio.avanza(self._sec)

    def elenco(self) -> list[Lavoro]:
        self._tic()
        return super().elenco()

    def lavoro(self, numero: int) -> Lavoro | None:
        self._tic()
        return super().lavoro(numero)

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None:
        self._tic()
        super().stato(numero, stato, nota=nota)

    def consegna(self, numero: int, pr: int) -> None:
        self._tic()
        super().consegna(numero, pr)

    def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
        self._tic()
        super().campo(numero, nome, valore)

    def aggiungi(self, lavoro: int | Lavoro, titolo: str = "", stato: str = "pronto") -> None:
        self._tic()
        super().aggiungi(lavoro, titolo=titolo, stato=stato)


class _ForgiaCronometrata(ForgiaFinta):
    """ForgiaFinta che avanza l'orologio finto a ogni chiamata ai suoi metodi."""

    def __init__(
        self,
        orologio: _OrologioFinto,
        secondi_per_chiamata: float,
        issues: list[Issue],
    ) -> None:
        super().__init__(issues=issues)
        self._orologio = orologio
        self._sec = secondi_per_chiamata
        self.contate = 0

    def _tic(self) -> None:
        self.contate += 1
        self._orologio.avanza(self._sec)

    def issue(self, n: int) -> Issue:
        self._tic()
        return super().issue(n)

    def sotto_issue(self, n: int) -> list[Issue]:
        self._tic()
        return super().sotto_issue(n)

    def commenti(self, n: int) -> list[Any]:
        self._tic()
        return super().commenti(n)

    def commenta(self, n: int, testo: str, ruolo: str) -> None:
        self._tic()
        super().commenta(n, testo, ruolo)

    def pr_del_ramo(self, ramo: str) -> int | None:
        self._tic()
        return super().pr_del_ramo(ramo)

    def apri_pr(self, ramo: str, titolo: str, corpo: str) -> int:
        self._tic()
        return super().apri_pr(ramo, titolo, corpo)

    def variabile(self, nome: str) -> str | None:
        self._tic()
        return super().variabile(nome)

    def avvia_workflow(self, file: str, input: dict[str, Any]) -> None:
        self._tic()
        super().avvia_workflow(file, input)

    def avviso(self, chiave: str, titolo: str, motivo: str | None) -> None:
        self._tic()
        super().avviso(chiave, titolo, motivo)

    def ramo_principale(self) -> str:
        self._tic()
        return super().ramo_principale()

    def proprietario(self) -> str:
        self._tic()
        return super().proprietario()


def _crea_repo(tmp_path: Path) -> Path:
    """Inizializza un repository git bare e il clone del runner."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    clone = tmp_path / "progetto"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )
    (clone / "app.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "iniziale"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)
    return clone


def _configurazione(*, con_consigliere: bool = True) -> Configurazione:
    progetto = Progetto(
        comandanti=("maestro",),
        adattatore=None,
        fuso="UTC",
        notte=None,
        manutenzione=(),
        project=1,
    )
    botteghe = {
        "principale": Bottega(id="principale", quota="abbondante", porte=("finta",)),
        "consiglio": Bottega(id="consiglio", quota="stretta", porte=("finta",)),
    }
    candidati = {
        "esecutore": Candidato(
            id="esecutore",
            nome="Esecutore Finto",
            bottega="principale",
            porta="finta",
            modello="finto-1",
            funzioni=("eseguire",),
            runner="linux-x64",
        ),
    }
    if con_consigliere:
        candidati["consigliere"] = Candidato(
            id="consigliere",
            nome="Consigliere Finto",
            bottega="consiglio",
            porta="finta",
            modello="finto-2",
            funzioni=("consigliare",),
            runner="linux-x64",
        )
    return Configurazione(1, progetto, botteghe, candidati)


def _issue_standard(numero: int = 1) -> Issue:
    corpo = "Brief del compito.\n\n## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    return Issue(numero=numero, titolo="Compito Tempi", corpo=corpo, autore="maestro")


def _righe_fasi(stdout: str) -> dict[str, int]:
    """Estrae le righe `fase <nome>: <sec> s` in ordine."""
    fasi: dict[str, int] = {}
    for riga in stdout.splitlines():
        m = re.fullmatch(r"fase ([a-z]+): (\d+) s", riga)
        if m:
            nome, sec = m.group(1), int(m.group(2))
            assert nome not in fasi, f"Fase {nome} stampata più di una volta"
            fasi[nome] = sec
    return fasi


def _riga_tempi(stdout: str) -> str:
    righe = [r for r in stdout.splitlines() if r.startswith("tempi del giro: ")]
    assert len(righe) == 1, f"Attesa una sola riga 'tempi del giro:', trovate {len(righe)}: {stdout!r}"
    return righe[0]


def test_giro_completo_stampa_tutte_le_fasi_e_riepilogo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B14-R9: un giro completo stampa tutte e sei le fasi e la riga finale con i numeri esatti."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(1000.0)
    board = _BoardCronometrata(
        orologio,
        9.0,
        [Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")],
    )
    forgia = _ForgiaCronometrata(orologio, 2.0, [_issue_standard(1)])
    porta = _PortaFintaTempi(
        orologio,
        secondi_controllo=3.0,
        secondi_esecutore=300.0,
        secondi_rilettura=45.0,
    )

    orig_verifica = modulo_giro._verifica_e_consegna_bundle

    def fake_verifica(*args: Any, **kwargs: Any) -> Any:
        orologio.avanza(20.0)
        return orig_verifica(*args, **kwargs)

    orig_oracolo = modulo_giro.esegui_oracolo

    def fake_oracolo(*args: Any, **kwargs: Any) -> Any:
        orologio.avanza(120.0)
        return orig_oracolo(*args, **kwargs)

    monkeypatch.setattr(modulo_giro, "_verifica_e_consegna_bundle", fake_verifica)
    monkeypatch.setattr(modulo_giro, "esegui_oracolo", fake_oracolo)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(con_consigliere=True),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "consegnato"

    out = capsys.readouterr().out
    fasi = _righe_fasi(out)
    assert list(fasi) == ["preparazione", "esecutore", "consegna", "oracolo", "rilettura", "chiusura"]
    assert fasi["esecutore"] == 300
    assert fasi["rilettura"] >= 45
    assert fasi["oracolo"] >= 120
    assert fasi["consegna"] >= 20

    totale_atteso = int(orologio.adesso - 1000.0)
    assert sum(fasi.values()) <= totale_atteso

    riga = _riga_tempi(out)
    b_sec = board.contate * 9
    f_sec = forgia.contate * 2
    assert riga == (
        f"tempi del giro: totale {totale_atteso} s; "
        f"preparazione {fasi['preparazione']} s, "
        f"esecutore {fasi['esecutore']} s, "
        f"consegna {fasi['consegna']} s, "
        f"oracolo {fasi['oracolo']} s, "
        f"rilettura {fasi['rilettura']} s, "
        f"chiusura {fasi['chiusura']} s; "
        f"board {board.contate} chiamate {b_sec} s; "
        f"forgia {forgia.contate} chiamate {f_sec} s"
    )
    assert "SEGRETO_ESECUTORE_MODELLO" not in out
    assert "SEGRETO_RILETTURA_MODELLO" not in out


def test_giro_senza_rilettura_non_stampa_fase_rilettura(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B14-R9: un giro senza consigliere non stampa la fase `rilettura`."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(500.0)
    board = _BoardCronometrata(orologio, 1.0, [Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")])
    forgia = _ForgiaCronometrata(orologio, 1.0, [_issue_standard(1)])
    porta = _PortaFintaTempi(orologio, secondi_esecutore=50.0)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(con_consigliere=False),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "consegnato"

    out = capsys.readouterr().out
    fasi = _righe_fasi(out)
    assert "rilettura" not in fasi
    assert list(fasi) == ["preparazione", "esecutore", "consegna", "oracolo", "chiusura"]
    riga = _riga_tempi(out)
    assert "rilettura" not in riga


def test_giro_cade_prima_del_lancio_stampa_solo_preparazione_e_totale(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B14-R9: su errore prima del lancio non si stampano fasi mai avvenute, ma `tempi del giro:` esce dal finally."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(200.0)
    board = _BoardCronometrata(orologio, 3.0, [Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")])

    class _ForgiaRotta(_ForgiaCronometrata):
        def issue(self, n: int) -> Issue:
            self._tic()
            raise ErroreForgia("errore simulato prima del lancio SEGRETO")

    forgia = _ForgiaRotta(orologio, 4.0, [_issue_standard(1)])
    porta = _PortaFintaTempi(orologio)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "errore"

    out = capsys.readouterr().out
    fasi = _righe_fasi(out)
    assert list(fasi) == ["preparazione"]
    riga = _riga_tempi(out)
    assert f"board {board.contate} chiamate {board.contate * 3} s" in riga
    assert f"forgia {forgia.contate} chiamate {forgia.contate * 4} s" in riga
    assert "SEGRETO" not in out


def test_giro_cade_a_meta_dopo_lancio_stampa_tempi_dal_finally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B14-R9: se un errore scatta nell'oracolo dopo la consegna, il finally chiude e stampa la riga finale."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(300.0)
    board = _BoardCronometrata(orologio, 1.0, [Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")])
    forgia = _ForgiaCronometrata(orologio, 1.0, [_issue_standard(1)])
    porta = _PortaFintaTempi(orologio, secondi_esecutore=40.0)

    def oracolo_rotto(*args: Any, **kwargs: Any) -> Any:
        orologio.avanza(12.0)
        raise RuntimeError("oracolo esploso")

    monkeypatch.setattr(modulo_giro, "esegui_oracolo", oracolo_rotto)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "errore"

    out = capsys.readouterr().out
    fasi = _righe_fasi(out)
    assert "preparazione" in fasi
    assert fasi["esecutore"] == 40
    assert "consegna" in fasi
    assert fasi["oracolo"] >= 12
    assert "rilettura" not in fasi
    assert "chiusura" in fasi
    assert sum(fasi.values()) <= int(orologio.adesso - 300.0)
    _riga_tempi(out)


def test_involucro_trasparente_isinstance_attributi_e_metodi_finti(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """L'involucro mantiene isinstance, attributi non chiamabili (`registro`) e metodi aggiunti sui finti."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(100.0)
    board = BoardFinta(
        lavori=[Lavoro(numero=1, titolo="Compito Tempi", stato="pronto", repo="org/repo")],
        repo="org/repo",
    )
    forgia = ForgiaFinta(issues=[_issue_standard(1)])
    porta = _PortaFintaTempi(orologio, secondi_esecutore=10.0)

    osservato: dict[str, Any] = {}
    orig_scrivi = modulo_giro._scrivi_misure

    def spia_scrivi_misure(*args: Any, **kwargs: Any) -> Any:
        board_passata = kwargs["board"]
        passata_forgia = kwargs["forgia"]
        osservato["avvolta"] = type(board_passata) is not BoardFinta and type(passata_forgia) is not ForgiaFinta
        osservato["isinstance_board"] = isinstance(board_passata, BoardFinta)
        osservato["isinstance_forgia"] = isinstance(passata_forgia, ForgiaFinta)
        osservato["repo"] = board_passata.repo
        osservato["registro_stesso"] = board_passata.registro is board.registro
        osservato["registro_len_prima"] = len(board_passata.registro)
        # Chiama un metodo extra presente solo su ForgiaFinta (`chiudi_come`) attraverso l'involucro
        orologio.avanza(7.0)
        passata_forgia.chiudi_come(1, "completed", datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        return orig_scrivi(*args, **kwargs)

    monkeypatch.setattr(modulo_giro, "_scrivi_misure", spia_scrivi_misure)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(con_consigliere=False),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "consegnato"
    assert osservato["avvolta"] is True
    assert osservato["isinstance_board"] is True
    assert osservato["isinstance_forgia"] is True
    assert osservato["repo"] == "org/repo"
    assert osservato["registro_stesso"] is True
    assert osservato["registro_len_prima"] > 0
    assert forgia.chiusura(1) == ("completed", datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
    assert board.registro[-1][0] == "campo"
    assert any(r[0] == "chiudi_come" for r in forgia.registro)

    out = capsys.readouterr().out
    _riga_tempi(out)


def test_frazioni_secondi_accumulate_e_stampate_intere(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le durate frazionarie delle chiamate si sommano in float e si stampano come secondi interi."""
    clone = _crea_repo(tmp_path)
    orologio = _OrologioFinto(0.0)
    board = _BoardCronometrata(orologio, 0.5, [Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")])
    forgia = _ForgiaCronometrata(orologio, 0.25, [_issue_standard(1)])
    porta = _PortaFintaTempi(orologio, secondi_esecutore=2.7)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(con_consigliere=False),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio,
    )
    assert esito.esito == "consegnato"

    out = capsys.readouterr().out
    riga = _riga_tempi(out)
    b_sec_atteso = int(board.contate * 0.5)
    f_sec_atteso = int(forgia.contate * 0.25)
    assert b_sec_atteso > 0
    assert f_sec_atteso > 0
    assert f"board {board.contate} chiamate {b_sec_atteso} s" in riga
    assert f"forgia {forgia.contate} chiamate {f_sec_atteso} s" in riga
    assert "." not in riga


def test_errore_del_cronometro_o_della_stampa_non_fa_fallire_il_giro(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un errore nell'orologio o in print() viene ingoiato e il giro completa normalmente."""
    clone = _crea_repo(tmp_path)
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Tempi", stato="pronto")])
    forgia = ForgiaFinta(issues=[_issue_standard(1)])
    orologio_ok = _OrologioFinto(0.0)
    porta = _PortaFintaTempi(orologio_ok)

    def orologio_rotto() -> float:
        raise RuntimeError("orologio guasto")

    orig_print = builtins.print

    def print_rotto(*args: Any, **kwargs: Any) -> None:
        if args and isinstance(args[0], str) and args[0].startswith(("fase ", "tempi del giro:")):
            raise OSError("stdout chiuso")
        orig_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", print_rotto)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=_configurazione(con_consigliere=False),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(1),
        orologio=orologio_rotto,
    )
    assert esito.esito == "consegnato"
    assert board.lavoro(1).stato == "consegnato"
