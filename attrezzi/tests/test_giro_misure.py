"""Prove per le misure scritte dal giro dell'esecutore (B5-R6)."""

from datetime import datetime, timezone
from pathlib import Path
import random
import subprocess
import time

import pytest

from bottega.board import ErroreBoard, Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import giro
from bottega.porte import Controllo, Lancio


class PortaFinta:
    """Porta finta per le prove di giro e misure."""

    def __init__(
        self,
        esito_controllo: bool = True,
        versione: str = "1.0",
        motivo_controllo: str | None = None,
        esito_lancio: str = "fatto",
        testo_lancio: str = "tutto fatto",
        conversazione: str | None = None,
        rinnovo: datetime | None = None,
        contatori: dict[str, int] | None = None,
        callback=None,
    ) -> None:
        self.nome = "finta"
        self.eseguibile = "finta"
        self.esito_controllo = esito_controllo
        self.versione = versione
        self.motivo_controllo = motivo_controllo
        self.esito_lancio = esito_lancio
        self.testo_lancio = testo_lancio
        self.conversazione = conversazione
        self.rinnovo = rinnovo
        self.contatori = contatori if contatori is not None else {}
        self.callback = callback
        self.gestisce_sola_lettura = False
        self.lanci: list[dict] = []

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=self.esito_controllo, versione=self.versione, motivo=self.motivo_controllo)

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
        self.lanci.append({
            "cartella": Path(cartella),
            "prompt": prompt,
            "modello": modello,
            "conversazione": conversazione,
            "sola_lettura": sola_lettura,
            "prefisso": prefisso,
            "tempo": tempo,
        })
        if sola_lettura and not self.gestisce_sola_lettura:
            return Lancio(esito="fatto", testo="revisione del consigliere: tutto bene")
        if self.callback is not None:
            return self.callback(cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura)
        return Lancio(
            esito=self.esito_lancio,
            testo=self.testo_lancio,
            conversazione=self.conversazione,
            rinnovo=self.rinnovo,
            contatori=self.contatori,
        )


def _crea_ambiente_git(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)

    clone = tmp_path / "progetto"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(clone), check=True, capture_output=True)

    docs = clone / "docs"
    docs.mkdir()
    (docs / "costituzione.md").write_text("# Costituzione\nRegole.\n", encoding="utf-8")
    (clone / "test_file.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "primo commit"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    return origin, clone


def _crea_configurazione() -> Configurazione:
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
        "consigliere": Candidato(
            id="consigliere",
            nome="Consigliere Finto",
            bottega="principale",
            porta="finta",
            modello="finto-consigliere",
            funzioni=("consigliare",),
            runner="linux-x64",
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def test_misure_dopo_una_consegna(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    t_base = 1000.0

    def mock_monotonic():
        nonlocal t_base
        val = t_base
        t_base += 2.0
        return val

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "file.txt"
        p.write_text("fatto\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "file.txt aggiunto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 1250})

    porta = PortaFinta(callback=committa)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    assert esito.esito == "consegnato"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.campi.get("Esecutore") == "Esecutore Finto"
    assert lav.campi.get("Porta") == "finta"
    assert lav.campi.get("Dove") == "fuori"
    assert int(lav.campi.get("Durata", 0)) > 0
    assert lav.campi.get("Giri") == "1"
    assert lav.campi.get("Token esecutore") == "1250"


def test_misure_si_sommano_su_due_giri(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    t_base = 100.0

    def mock_monotonic():
        nonlocal t_base
        val = t_base
        t_base += 5.0
        return val

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    # Primo giro: finisce in quota
    def in_quota(cartella, prompt, **kwargs):
        return Lancio(esito="quota", testo="quota finita", contatori={"total_tokens": 800})

    porta1 = PortaFinta(callback=in_quota)
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta1},
        clone_progetto=clone,
        spazio=tmp_path / "spazio1",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito1.esito == "quota"

    lav1 = board.lavoro(1)
    assert lav1.campi.get("Giri") == "1"
    assert lav1.campi.get("Token esecutore") == "800"
    durata1 = int(lav1.campi.get("Durata", 0))

    # Secondo giro: consegna con successo
    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "file.txt"
        p.write_text("fatto\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 1200})

    porta2 = PortaFinta(callback=committa)
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta2},
        clone_progetto=clone,
        spazio=tmp_path / "spazio2",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 13, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito2.esito == "consegnato"

    lav2 = board.lavoro(1)
    assert lav2.campi.get("Giri") == "2"
    assert lav2.campi.get("Token esecutore") == "2000"
    assert int(lav2.campi.get("Durata", 0)) > durata1


def test_misure_dopo_quota_e_dopo_errore(tmp_path: Path) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    # Caso quota
    porta_quota = PortaFinta(esito_lancio="quota", testo_lancio="quota superata", contatori={"total_tokens": 500})
    esito_q = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_quota},
        clone_progetto=clone,
        spazio=tmp_path / "spazio_q",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito_q.esito == "quota"
    lav_q = board.lavoro(1)
    assert lav_q.campi.get("Esecutore") == "Esecutore Finto"
    assert lav_q.campi.get("Porta") == "finta"
    assert lav_q.campi.get("Dove") == "fuori"
    assert lav_q.campi.get("Giri") == "1"
    assert lav_q.campi.get("Token esecutore") == "500"

    # Caso errore
    porta_err = PortaFinta(esito_lancio="errore", testo_lancio="errore fatale", contatori={"total_tokens": 300})
    esito_e = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_err},
        clone_progetto=clone,
        spazio=tmp_path / "spazio_e",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito_e.esito == "errore"
    lav_e = board.lavoro(1)
    assert lav_e.campi.get("Giri") == "2"
    assert lav_e.campi.get("Token esecutore") == "800"


def test_misure_compito_assente_si_aggiunge(tmp_path: Path) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    madre = Issue(numero=10, titolo="Tappa Madre", corpo="Descrizione madre", autore="maestro")
    sotto = Issue(
        numero=20,
        titolo="Sotto-issue 20",
        corpo="Brief 20\n\n## Fatto quando\n```bash\ntest -f fatto.txt\n```\n",
        autore="maestro",
    )
    forgia = ForgiaFinta(issues=[madre, sotto])
    forgia._sotto_issue[10] = [20]

    # La board ha solo la madre #10, la sotto-issue #20 NON è presente sulla board
    board = BoardFinta(lavori=[Lavoro(numero=10, titolo="Tappa Madre", stato="pronto")])
    assert board.lavoro(20) is None

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "fatto.txt"
        p.write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "fatto.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 999})

    porta = PortaFinta(callback=committa)
    esito = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"

    # La sotto-issue #20 è stata aggiunta alla board e ha le misure
    lav_sotto = board.lavoro(20)
    assert lav_sotto is not None
    assert lav_sotto.campi.get("Esecutore") == "Esecutore Finto"
    assert lav_sotto.campi.get("Porta") == "finta"
    assert lav_sotto.campi.get("Dove") == "fuori"
    assert lav_sotto.campi.get("Giri") == "1"
    assert lav_sotto.campi.get("Token esecutore") == "999"


def test_misure_non_fanno_cadere_il_giro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    orig_campo = board.campo
    def campo_che_solleva(numero, nome, valore):
        if nome in ("Esecutore", "Porta", "Dove", "Durata", "Giri", "Consulti", "Token esecutore"):
            raise ErroreBoard(f"scrittura campo {nome} non consentita")
        return orig_campo(numero, nome, valore)

    monkeypatch.setattr(board, "campo", campo_che_solleva)

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "file.txt"
        p.write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 100})

    porta = PortaFinta(callback=committa)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    # L'esito del giro resta consegnato, non fallisce
    assert esito.esito == "consegnato"


def test_niente_misure_senza_lancio(tmp_path: Path) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    porta = PortaFinta(esito_controllo=False, motivo_controllo="porta non pronta")
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    assert esito.esito == "porta_non_pronta"
    lav = board.lavoro(1)
    campi_misura = {"Esecutore", "Porta", "Dove", "Durata", "Giri", "Consulti", "Token esecutore"}
    for c in campi_misura:
        assert c not in lav.campi


def test_consulti_contati(tmp_path: Path) -> None:
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    chiamata = 0

    def callback_lancio(cartella, prompt, sola_lettura=False, **kwargs):
        nonlocal chiamata
        if sola_lettura:
            return Lancio(esito="fatto", testo="RISPOSTA procedi pure")
        chiamata += 1
        if chiamata == 1:
            return Lancio(
                esito="fatto",
                testo="Ho un dubbio.\n\nDOMANDA PER CHI DECIDE: confermi file.txt?",
                contatori={"total_tokens": 150},
            )
        p = Path(cartella) / "file.txt"
        p.write_text("fatto dopo consulto\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="tutto completato", contatori={"total_tokens": 250})

    porta = PortaFinta(callback=callback_lancio)
    porta.gestisce_sola_lettura = True

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    assert esito.esito == "consegnato"
    lav = board.lavoro(1)
    assert lav.campi.get("Consulti") == "1"
    assert lav.campi.get("Token esecutore") == "400"
    assert lav.campi.get("Giri") == "1"
