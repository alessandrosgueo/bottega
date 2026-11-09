"""Prove per bottega.giro (Task 5, B3)."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import random
import subprocess

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Commento, Issue
from bottega.porte import Controllo, Lancio
from bottega.segni import nota


class PortaFinta:
    """Porta finta per le prove di giro."""

    def __init__(
        self,
        esito_controllo: bool = True,
        versione: str = "1.0",
        motivo_controllo: str | None = None,
        esito_lancio: str = "fatto",
        testo_lancio: str = "tutto fatto",
        conversazione: str | None = None,
        rinnovo: datetime | None = None,
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
        )


def _crea_ambiente_git(tmp_path: Path) -> tuple[Path, Path]:
    """Crea una repo bare di origine e un clone locale per il test."""
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

    docs = clone / "docs"
    docs.mkdir()
    (docs / "costituzione.md").write_text("# Costituzione\nRegole del repo.\n", encoding="utf-8")
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
        "secondaria": Bottega(id="secondaria", quota="abbondante", porte=("finta",)),
    }
    candidati = {
        "esecutore": Candidato(
            id="esecutore",
            nome="Esecutore Finto",
            bottega="principale",
            porta="finta",
            modello="finto-1",
            funzioni=("eseguire",),
            runner="linux-x64",  # un esecutore fuori ha il runner; il consigliere del giro lo stesso
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


def test_giro_fatto_quando_successo_completo(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = (
        "Brief compito 1\n\n"
        "## Fatto quando\n"
        "```bash\n"
        "test -f modifica.txt\n"
        "```\n"
    )
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "modifica.txt"
        p.write_text("modifica fatta\n", encoding="utf-8")
        subprocess.run(["git", "add", "modifica.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunta modifica"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=committa)
    porte = {"finta": porta}
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte=porte,
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    assert esito.oracolo_ok is True
    assert esito.pr is not None

    # Origin bare ha ricevuto il ramo
    ramo_atteso = "bottega/1-compito-uno"
    check = subprocess.run(["git", "rev-parse", "--verify", ramo_atteso], cwd=str(origin), capture_output=True)
    assert check.returncode == 0

    # Board consegnato
    lav = board.lavoro(1)
    assert lav.stato == "consegnato"

    # Spazio del giro ripulito
    assert not any(spazio.iterdir()) if spazio.exists() else True


def test_review_focus_1_modifica_github_rifiutata(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = (
        "Brief compito 1\n\n"
        "## Fatto quando\n"
        "```bash\n"
        "test -f .github/vietato.txt\n"
        "```\n"
    )
    iss = Issue(numero=1, titolo="Compito Vietato", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Vietato", stato="pronto")])

    def committa_vietato(cartella, prompt, **kwargs):
        gh_dir = Path(cartella) / ".github"
        gh_dir.mkdir(exist_ok=True)
        (gh_dir / "vietato.txt").write_text("vietato", encoding="utf-8")
        subprocess.run(["git", "add", ".github/vietato.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "modifica vietata"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_vietato)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    # L'origine nuda NON ha ricevuto il ramo
    ramo_atteso = "bottega/1-compito-vietato"
    check = subprocess.run(["git", "rev-parse", "--verify", ramo_atteso], cwd=str(origin), capture_output=True)
    assert check.returncode != 0

    lav = board.lavoro(1)
    assert lav.stato == "bloccato"
    assert "vietata" in lav.nota


def test_review_focus_3_quota_esaurita_salvataggio_e_ripresa(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = (
        "Brief compito 1\n\n"
        "## Fatto quando\n"
        "```bash\n"
        "test -f finale.txt\n"
        "```\n"
    )
    iss = Issue(numero=1, titolo="Compito Quota", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Quota", stato="pronto")])

    # 1. Primo giro: va in quota ma ha committato un salvataggio parziale
    def committa_parziale(cartella, prompt, **kwargs):
        p = Path(cartella) / "parziale.txt"
        p.write_text("parziale", encoding="utf-8")
        subprocess.run(["git", "add", "parziale.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "salvataggio parziale"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="quota", testo="quota finita", conversazione="conv_quota_123")

    porta = PortaFinta(callback=committa_parziale)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito1.esito == "quota"
    # Variabile quota impostata
    var_quota = forgia.variabile("BOTTEGA_QUOTA_PRINCIPALE")
    assert var_quota is not None
    assert var_quota.startswith("esaurita fino a ")

    # PR aperta in bozza come salvataggio
    ramo_atteso = "bottega/1-compito-quota"
    assert forgia.pr_del_ramo(ramo_atteso) is not None

    # Lavoro tornato pronto con conversazione (RV8: attese la cresce solo il distributore)
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    assert "conversazione=conv_quota_123" in lav.nota

    # 2. Secondo giro: riprende con la conversazione e completa
    def completa_lavoro(cartella, prompt, conversazione=None, **kwargs):
        assert conversazione == "conv_quota_123"
        p = Path(cartella) / "finale.txt"
        p.write_text("finito", encoding="utf-8")
        subprocess.run(["git", "add", "finale.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "completamento"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="tutto completato")

    porta2 = PortaFinta(callback=completa_lavoro)
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta2},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(hours=2),
        caso=caso,
    )

    assert esito2.esito == "consegnato"
    assert board.lavoro(1).stato == "consegnato"


def test_review_focus_4_porta_non_risponde_avviso_singolo_e_chiusura(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = (
        "Brief compito 1\n\n"
        "## Fatto quando\n"
        "```bash\n"
        "true\n"
        "```\n"
    )
    iss = Issue(numero=1, titolo="Compito Avviso", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Avviso", stato="pronto")])

    porta_guasta = PortaFinta(esito_controllo=False, motivo_controllo="porta offline")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    # 1. Primo giro: controllo fallito -> crea avviso, lavoro torna pronto
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_guasta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito1.esito == "porta_non_pronta"
    assert board.lavoro(1).stato == "pronto"

    avvisi = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi) == 1
    assert avvisi[0].titolo == "Avviso della bottega: porta finta"

    # 2. Secondo giro: porta ancora guasta -> nessun nuovo avviso, nessun commento duplicato
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_guasta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=5),
        caso=caso,
    )
    assert esito2.esito == "porta_non_pronta"
    avvisi2 = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi2) == 1

    # 3. Terzo giro: porta torna buona -> avviso si chiude
    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "ok.txt"
        p.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "ok.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "ok"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta_buona = PortaFinta(esito_controllo=True, callback=committa)
    esito3 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_buona},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=10),
        caso=caso,
    )
    assert esito3.esito == "consegnato"
    avvisi3 = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi3) == 0


def test_review_focus_5_ambiente_ripulito_e_prefisso(tmp_path: Path, monkeypatch):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    monkeypatch.setenv("GH_TOKEN", "segreto_gh")
    monkeypatch.setenv("GITHUB_TOKEN", "segreto_github")
    monkeypatch.setenv("BOTTEGA_TOKEN", "segreto_bottega")

    comando_oracolo = (
        'python3 -c "import os; '
        'assert \'GH_TOKEN\' not in os.environ, \'GH_TOKEN presente\'; '
        'assert \'GITHUB_TOKEN\' not in os.environ, \'GITHUB_TOKEN presente\'; '
        'assert \'BOTTEGA_TOKEN\' not in os.environ, \'BOTTEGA_TOKEN presente\'"'
    )
    corpo = f"Brief\n\n## Fatto quando\n```bash\n{comando_oracolo}\n```\n"
    iss = Issue(numero=1, titolo="Compito Sicurezza", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Sicurezza", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "dummy.txt"
        p.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "dummy.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "dummy"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    assert esito.oracolo_ok is True


def test_consulto_con_risposta_e_chi_decide(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = (
        "Brief compito 1\n\n"
        "## Fatto quando\n"
        "```bash\n"
        "test -f risposto.txt\n"
        "```\n"
    )
    iss = Issue(numero=1, titolo="Compito Consulto", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Consulto", stato="pronto")])

    # 1. Caso con risposta tecnica ordinaria
    passo = 0

    def callback_porta(cartella, prompt, **kwargs):
        nonlocal passo
        if kwargs.get("sola_lettura"):
            # È il consigliere
            return Lancio(esito="fatto", testo="RISPOSTA usa il metodo standard")
        if passo == 0:
            passo += 1
            return Lancio(
                esito="fatto",
                testo="Ho una domanda.\nDOMANDA PER CHI DECIDE: come faccio questa cosa?",
                conversazione="conv_consulto",
            )
        # Ripresa con la risposta del consigliere
        p = Path(cartella) / "risposto.txt"
        p.write_text("fatto", encoding="utf-8")
        subprocess.run(["git", "add", "risposto.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "fatto dopo consulto"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="completato")

    porta = PortaFinta(callback=callback_porta)
    porta.gestisce_sola_lettura = True
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    # Commenti con il segno presenti
    comms = forgia.commenti(1)
    testi_comms = [c.corpo for c in comms]
    assert any("<!-- bottega:esecutore -->" in t and "DOMANDA PER CHI DECIDE:" in t for t in testi_comms)
    assert any("<!-- bottega:consigliere -->" in t and "RISPOSTA" in t for t in testi_comms)


def test_consulto_a_chi_decide_mette_in_attesa(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Barriera", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Barriera", stato="pronto")])

    def callback_porta(cartella, prompt, **kwargs):
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="A CHI DECIDE tocca una barriera")
        return Lancio(
            esito="fatto",
            testo="DOMANDA PER CHI DECIDE: posso cancellare la banca dati?",
            conversazione="conv_barriera",
        )

    porta = PortaFinta(callback=callback_porta)
    porta.gestisce_sola_lettura = True
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "in_attesa"
    assert board.lavoro(1).stato == "in attesa"


def test_tappa_con_sotto_issue_stesso_ramo_e_chiusura(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    madre = Issue(numero=10, titolo="Tappa Due Compiti", corpo="Piano generale")
    sotto1 = Issue(
        numero=11,
        titolo="Compito Sotto 1",
        corpo="Brief 1\n\n## Fatto quando\n```bash\ntest -f file1.txt\n```\n",
        stato="OPEN",
    )
    sotto2 = Issue(
        numero=12,
        titolo="Compito Sotto 2",
        corpo="Brief 2\n\n## Fatto quando\n```bash\ntest -f file2.txt\n```\n",
        stato="OPEN",
    )

    forgia = ForgiaFinta(issues=[madre, sotto1, sotto2])
    forgia._sotto_issue[10] = [11, 12]
    board = BoardFinta(lavori=[Lavoro(numero=10, titolo="Tappa Due Compiti", stato="pronto")])

    # 1. Primo giro: esegue sotto1
    def committa_1(cartella, prompt, **kwargs):
        p = Path(cartella) / "file1.txt"
        p.write_text("file1", encoding="utf-8")
        subprocess.run(["git", "add", "file1.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file1"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto 1")

    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito1 = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=committa_1)},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito1.esito == "consegnato"
    # Sotto-issue 11 chiusa
    assert not forgia.issue(11).aperta
    # Madre torna pronto per il secondo compito
    lav_madre = board.lavoro(10)
    assert lav_madre.stato == "pronto"
    assert "precedente=esecutore" in lav_madre.nota

    # 2. Secondo giro: esegue sotto2 sullo stesso ramo
    def committa_2(cartella, prompt, **kwargs):
        p = Path(cartella) / "file2.txt"
        p.write_text("file2", encoding="utf-8")
        subprocess.run(["git", "add", "file2.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file2"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto 2")

    esito2 = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=committa_2)},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=10),
        caso=caso,
    )

    assert esito2.esito == "consegnato"
    # Sotto-issue 12 chiusa
    assert not forgia.issue(12).aperta
    # Ultima sotto-issue -> madre consegnata!
    assert board.lavoro(10).stato == "consegnato"
    # Ramo unico per la madre
    assert forgia.pr_del_ramo("bottega/10-tappa-due-compiti") is not None


def test_segnali_prove_cambiate(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Modifica Test", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Modifica Test", stato="pronto")])

    def committa_modifica_test(cartella, prompt, **kwargs):
        p = Path(cartella) / "test_file.py"
        p.write_text("def test_modificato(): assert True\n", encoding="utf-8")
        subprocess.run(["git", "add", "test_file.py"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "modificato test_file.py"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="modificato test")

    porta = PortaFinta(callback=committa_modifica_test)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    pr_num = esito.pr
    assert pr_num is not None
    # Verifica che la PR abbia l'etichetta bottega: prove cambiate
    etichette_pr = forgia._pr[pr_num].get("etichette", [])
    assert "bottega: prove cambiate" in etichette_pr


def test_oracolo_rosso_non_blocca_consegna(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\nfalse\n```\n"
    iss = Issue(numero=1, titolo="Compito Rosso", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Rosso", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "file.txt"
        p.write_text("file", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    assert esito.oracolo_ok is False
    assert esito.pr is not None
    # Commento oracolo rosso
    comms = forgia.commenti(1)
    assert any("ROSSO" in c.corpo for c in comms)


def test_consulto_massimo_due(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Tre Consulti", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Tre Consulti", stato="pronto")])

    def callback_porta(cartella, prompt, **kwargs):
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="RISPOSTA ecco la risposta")
        return Lancio(
            esito="fatto",
            testo="DOMANDA PER CHI DECIDE: ancora una domanda?",
            conversazione="conv_loop",
        )

    porta = PortaFinta(callback=callback_porta)
    porta.gestisce_sola_lettura = True
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "in_attesa"
    assert esito.motivo == "troppi consulti"
    lav = board.lavoro(1)
    assert lav.stato == "in attesa"
    assert "motivo=troppi consulti" in lav.nota


def test_accesso_e_errore_fino_a_bloccato(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Errore", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Errore", stato="pronto")])

    porta_err = PortaFinta(esito_lancio="errore", testo_lancio="fallimento di rete")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    # 1. Tentativo 1
    e1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_err},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert e1.esito == "errore"
    assert board.lavoro(1).stato == "pronto"
    assert "tentativi=1" in board.lavoro(1).nota

    # 2. Tentativo 2
    e2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_err},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=1),
        caso=caso,
    )
    assert e2.esito == "errore"
    assert board.lavoro(1).stato == "pronto"
    assert "tentativi=2" in board.lavoro(1).nota

    # 3. Tentativo 3 -> Bloccato
    e3 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta_err},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=2),
        caso=caso,
    )
    assert e3.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"
    assert "tentativi=3" in board.lavoro(1).nota
    assert any("bloccato dopo 3 tentativi" in c.corpo for c in forgia.commenti(1))


def test_senza_fatto_quando_torna_pronto(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief senza sezione fatto quando."
    iss = Issue(numero=1, titolo="Compito Incompleto", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Incompleto", stato="pronto")])

    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta()},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "senza_fatto_quando"
    assert board.lavoro(1).stato == "pronto"
    assert "manca fatto quando" in board.lavoro(1).nota
    assert any("manca il blocco «Fatto quando»" in c.corpo for c in forgia.commenti(1))


def test_ramo_principale_rifiutato(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    # Titolo vuoto con numero 0 genera ramo non valido
    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=0, titolo="", corpo=corpo)
    # Se ramo_principale è "bottega/0", coinciderebbe
    forgia = ForgiaFinta(issues=[iss], ramo_principale="bottega/0")
    board = BoardFinta(lavori=[Lavoro(numero=0, titolo="", stato="pronto")])

    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=0,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta()},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    assert board.lavoro(0).stato == "bloccato"


def test_pulizia_spazio_anche_con_errore(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Crash", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Crash", stato="pronto")])

    def esplodi(cartella, prompt, **kwargs):
        raise RuntimeError("eccezione imprevista")

    porta = PortaFinta(callback=esplodi)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "errore"

    # Verifica che la cartella del giro non sia rimasta
    assert not any(spazio.iterdir()) if spazio.exists() else True


def test_consigliere_senza_quota_durante_revisione(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    # Nessun consigliere nella configurazione
    progetto = Progetto(
        comandanti=("maestro",),
        adattatore=None,
        fuso="UTC",
        notte=None,
        manutenzione=(),
        project=1,
    )
    botteghe = {"principale": Bottega(id="principale", quota="abbondante", porte=("finta",))}
    candidati = {
        "esecutore": Candidato(
            id="esecutore",
            nome="Esecutore Finto",
            bottega="principale",
            porta="finta",
            modello="finto-1",
            funzioni=("eseguire",),
            runner=None,
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Senza Consigliere", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Senza Consigliere", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "file.txt"
        p.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    pr_num = esito.pr
    comms_pr = forgia.commenti(pr_num)
    assert any("compito senza rilettura" in c.corpo for c in comms_pr)


def test_cli_bottega_giro(tmp_path: Path, monkeypatch):
    from bottega.__main__ import main

    origin, clone = _crea_ambiente_git(tmp_path)
    bottega_dir = clone / ".github" / "bottega"
    bottega_dir.mkdir(parents=True)
    cfg_file = bottega_dir / "bottega.toml"
    cfg_file.write_text(
        'versione = 1\n\n'
        '[progetto]\n'
        'fuso = "UTC"\n'
        'project = 1\n\n'
        '[botteghe.principale]\n'
        'quota = "abbondante"\n'
        'porte = ["finta"]\n\n'
        '[candidati.esecutore]\n'
        'nome = "Esecutore Finto"\n'
        'bottega = "principale"\n'
        'porta = "finta"\n'
        'modello = "finto-1"\n'
        'funzioni = ["eseguire"]\n'
        'runner = "linux-x64"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(clone)
    monkeypatch.setenv("GITHUB_REPOSITORY", "bottega/test")

    # Verifica invocazione con --help
    with pytest.raises(SystemExit) as exc:
        main(["giro", "--help"])
    assert exc.value.code == 0


def test_falso_git_esecutore_non_inganna_runner_consegna(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntest -f .github/attacco.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Ingannevole", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Ingannevole", stato="pronto")])

    # Il falso git dell'esecutore sta in testa al suo PATH (attraverso il prefisso, come farebbe un modello che scrive
    # in una cartella sua del PATH): per «diff» non stampa niente, per il resto chiama il git vero. Il runner deve
    # trovare lo stesso la modifica a .github/, perché il controllo lo fa col suo git sul suo clone.
    import os
    import shutil

    falso_bin = tmp_path / "falso_bin"
    falso_bin.mkdir()
    git_vero = shutil.which("git")
    falso_git = falso_bin / "git"
    falso_git.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "diff" ]; then exit 0; fi\n'
        f'exec {git_vero} "$@"\n',
        encoding="utf-8",
    )
    falso_git.chmod(0o755)
    prefisso_falso = ("env", f"PATH={falso_bin}:{os.environ['PATH']}")

    def committa_con_falso_git(cartella, prompt, **kwargs):
        # L'esecutore scrive un file sotto .github/ e lo committa col git (falso) del suo PATH
        gh_dir = Path(cartella) / ".github"
        gh_dir.mkdir(exist_ok=True)
        (gh_dir / "attacco.txt").write_text("attacco", encoding="utf-8")
        ambiente = {**os.environ, "PATH": f"{falso_bin}:{os.environ['PATH']}"}
        subprocess.run(["git", "add", ".github/attacco.txt"], cwd=str(cartella), check=True, env=ambiente)
        subprocess.run(["git", "commit", "-m", "attacco git"], cwd=str(cartella), check=True, env=ambiente)
        vuoto = subprocess.run(["git", "diff", "HEAD~1", "HEAD"], cwd=str(cartella), capture_output=True, env=ambiente)
        assert vuoto.stdout == b""  # il falso git nasconde davvero il diff all'esecutore
        return Lancio(esito="fatto", testo="fatto con furbizia")

    porta = PortaFinta(callback=committa_con_falso_git)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=prefisso_falso,
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    # L'origine nuda non deve avere il ramo
    ramo_atteso = "bottega/1-compito-ingannevole"
    check = subprocess.run(["git", "rev-parse", "--verify", ramo_atteso], cwd=str(origin), capture_output=True)
    assert check.returncode != 0
    assert board.lavoro(1).stato == "bloccato"


def test_falso_git_esecutore_non_inganna_runner_salvataggio_quota(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Quota Ingannevole", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Quota Ingannevole", stato="pronto")])

    def committa_quota_vietato(cartella, prompt, **kwargs):
        gh_dir = Path(cartella) / ".github"
        gh_dir.mkdir(exist_ok=True)
        (gh_dir / "vietato.txt").write_text("vietato", encoding="utf-8")
        subprocess.run(["git", "add", ".github/vietato.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "salvataggio vietato"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="quota", testo="quota", conversazione="c1")

    porta = PortaFinta(callback=committa_quota_vietato)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    # Il salvataggio che tocca .github/ viene rifiutato e il lavoro bloccato
    assert esito.esito == "bloccato"
    ramo_atteso = "bottega/1-compito-quota-ingannevole"
    check = subprocess.run(["git", "rev-parse", "--verify", ramo_atteso], cwd=str(origin), capture_output=True)
    assert check.returncode != 0
    assert board.lavoro(1).stato == "bloccato"


def test_fascicolo_completo_e_prompt(tmp_path: Path, monkeypatch):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    # Crea quaderno bottega e quaderno progetto
    bottega_clone = tmp_path / "repo_bottega"
    quaderni_bottega = bottega_clone / "quaderni"
    quaderni_bottega.mkdir(parents=True)
    (quaderni_bottega / "finto-1.md").write_text("# Quaderno bottega per finto-1\n", encoding="utf-8")
    monkeypatch.setenv("BOTTEGA_CLONE", str(bottega_clone))

    quaderni_proj = clone / ".github" / "bottega" / "quaderni"
    quaderni_proj.mkdir(parents=True)
    (quaderni_proj / "finto-1.md").write_text("# Quaderno progetto per finto-1\n", encoding="utf-8")
    subprocess.run(["git", "add", ".github"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "aggiungi quaderno progetto"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)


    madre = Issue(numero=10, titolo="Madre Tappa", corpo="Corpo generale della madre")
    compito = Issue(
        numero=11,
        titolo="Compito Sotto",
        corpo="Brief compito 11\n\n## Fatto quando\n```bash\ntest -f fatto.txt\n```\n",
        stato="OPEN",
    )
    forgia = ForgiaFinta(issues=[madre, compito])
    forgia._sotto_issue[10] = [11]
    forgia.commenta(10, "Commento sulla madre da comandante", ruolo="esecutore")
    forgia.commenta(11, "Domanda o suggerimento", ruolo="consigliere")

    board = BoardFinta(lavori=[Lavoro(numero=10, titolo="Madre Tappa", stato="pronto", nota="inizio_precedente=ok")])

    fascicolo_ispezionato: dict[str, str] = {}
    prompt_ispezionato: list[str] = []

    def callback_esecutore(cartella, prompt, **kwargs):
        prompt_ispezionato.append(prompt)
        fasc_dir = Path(cartella) / ".bottega" / "fascicolo"
        for f in fasc_dir.iterdir():
            if f.is_file():
                fascicolo_ispezionato[f.name] = f.read_text(encoding="utf-8")

        p = Path(cartella) / "fatto.txt"
        p.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "fatto.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="rapporto dell'esecutore")

    porta = PortaFinta(callback=callback_esecutore)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    # File presenti nel fascicolo
    assert "brief.md" in fascicolo_ispezionato
    assert "Brief compito 11" in fascicolo_ispezionato["brief.md"]

    assert "lavoro.md" in fascicolo_ispezionato
    assert "Corpo generale della madre" in fascicolo_ispezionato["lavoro.md"]

    assert "commenti.md" in fascicolo_ispezionato
    assert "[consigliere]" in fascicolo_ispezionato["commenti.md"]

    assert "costituzione.md" in fascicolo_ispezionato
    assert "Regole del repo" in fascicolo_ispezionato["costituzione.md"]

    assert "quaderno.md" in fascicolo_ispezionato
    assert "Quaderno bottega per finto-1" in fascicolo_ispezionato["quaderno.md"]
    assert "Quaderno progetto per finto-1" in fascicolo_ispezionato["quaderno.md"]

    assert "stato.md" in fascicolo_ispezionato
    assert "Ramo:" in fascicolo_ispezionato["stato.md"]

    # Prompt contiene le istruzioni esplicite
    pr_text = prompt_ispezionato[0]
    assert "committa nel ramo corrente" in pr_text
    assert "non toccare mai .github/" in pr_text.lower() or "non toccare .github/" in pr_text.lower()
    assert "rapporto come ultimo messaggio" in pr_text
    assert "DOMANDA PER CHI DECIDE:" in pr_text


def test_pr_corpo_e_commento_secondo_compito(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    madre = Issue(numero=10, titolo="Tappa Due Passi", corpo="Descrizione tappa")
    s1 = Issue(numero=11, titolo="Passo 1", corpo="Brief 1\n\n## Fatto quando\n```bash\ntest -f p1.txt\n```\n")
    s2 = Issue(numero=12, titolo="Passo 2", corpo="Brief 2\n\n## Fatto quando\n```bash\ntest -f p2.txt\n```\n")

    forgia = ForgiaFinta(issues=[madre, s1, s2])
    forgia._sotto_issue[10] = [11, 12]
    board = BoardFinta(lavori=[Lavoro(numero=10, titolo="Tappa Due Passi", stato="pronto")])

    def committa_1(cartella, prompt, **kwargs):
        p = Path(cartella) / "p1.txt"
        p.write_text("1", encoding="utf-8")
        subprocess.run(["git", "add", "p1.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "p1"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="Rapporto primo passo")

    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito1 = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=committa_1)},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito1.esito == "consegnato"
    pr1 = esito1.pr
    assert pr1 is not None

    # Corpo PR contiene Lavoro: #10, rapporto e oracolo
    dati_pr1 = forgia._pr[pr1]
    corpo_pr1 = dati_pr1["corpo"]
    assert "Lavoro: #10" in corpo_pr1
    assert "Rapporto primo passo" in corpo_pr1
    assert "VERDE" in corpo_pr1

    # 2. Secondo passo: PR c'è già -> rapporto va in un commento sulla PR
    def committa_2(cartella, prompt, **kwargs):
        p = Path(cartella) / "p2.txt"
        p.write_text("2", encoding="utf-8")
        subprocess.run(["git", "add", "p2.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "p2"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="Rapporto secondo passo")

    esito2 = giro(
        lavoro=10,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=committa_2)},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=10),
        caso=caso,
    )
    assert esito2.esito == "consegnato"
    assert esito2.pr == pr1

    comms_pr = forgia.commenti(pr1)
    testi_pr = [c.corpo for c in comms_pr]
    assert any("Rapporto secondo passo" in t and "<!-- bottega:esecutore -->" in t for t in testi_pr)


def test_rilancio_distributore_a_fine_giro(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Rilancio", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Rilancio", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        p = Path(cartella) / "ok.txt"
        p.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "ok.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "ok"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "consegnato"
    # Rilancio avvenuto
    assert ("bottega-distributore.yml", {}) in forgia._workflow_avviati


def test_attacco_12_rapporto_con_closes_e_menzione(tmp_path: Path):
    """Attacco 12: un rapporto che contiene `Closes #1` e `@qualcuno` deve essere recintato in modo sicuro."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Iniezione", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Iniezione", stato="pronto")])

    testo_malevolo = "Ho finito!\n```python\nprint(1)\n```\nCloses #1 e avviso per @qualcuno."

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo=testo_malevolo)

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    pr_dati = list(forgia._pr.values())[0]
    corpo_pr = pr_dati["corpo"]
    # Il testo del modello deve essere racchiuso in un blocco di codice con almeno 4 backtick (perché il testo ne contiene 3)
    assert "````" in corpo_pr
    assert f"````\n{testo_malevolo}\n````" in corpo_pr



def test_attacco_13_rapporto_con_domanda_in_mezzo_al_testo(tmp_path: Path):
    """Attacco 13: un rapporto che cita `DOMANDA PER CHI DECIDE:` in mezzo al testo non deve essere trattato come consulto."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Citazione", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Citazione", stato="pronto")])

    testo_con_citazione = (
        "Ho letto la regola: se hai dubbi usa DOMANDA PER CHI DECIDE: per chiedere.\n"
        "Non ho avuto dubbi quindi ho completato tutto.\n"
        "Rapporto finale: implementazione riuscita."
    )

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo=testo_con_citazione)

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    # Non deve essere andato in attesa o in consulto
    assert esito.esito == "consegnato"
    # Nessun commento di consulto creato
    commenti_esec = [c for c in forgia._commenti.get(1, []) if "Consulto dell'esecutore:" in c.corpo]
    assert commenti_esec == []


def test_attacco_1_file_non_ascii_sotto_github(tmp_path: Path):
    """Attacco 1: un file `.github/workflows/è.yml` (nome non ASCII) deve essere rifiutato dal diff raw a NUL."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Non ASCII", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Non ASCII", stato="pronto")])

    def committa_non_ascii(cartella, prompt, **kwargs):
        wf = Path(cartella) / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "è.yml").write_text("name: malevolo\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "attacco non-ascii"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_non_ascii)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"
    assert forgia._pr == {}


def test_attacco_2_file_con_tab_sotto_github(tmp_path: Path):
    """Attacco 2: un file con un tab nel nome sotto `.github/` deve essere rifiutato."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Tab", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Tab", stato="pronto")])

    def committa_tab(cartella, prompt, **kwargs):
        gh = Path(cartella) / ".github"
        gh.mkdir(parents=True, exist_ok=True)
        (gh / "tab\tx.txt").write_text("malevolo", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "attacco tab"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_tab)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


def test_attacco_3_rinomina_da_github_a_docs(tmp_path: Path):
    """Attacco 3: una rinomina da `.github/x` a `docs/x` deve essere rifiutata (il vecchio percorso è vietato)."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    # Creiamo un file iniziale sotto .github/ nel clone
    gh_init = clone / ".github"
    gh_init.mkdir(parents=True, exist_ok=True)
    (gh_init / "x.txt").write_text("originale", encoding="utf-8")
    subprocess.run(["git", "add", ".github/x.txt"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "aggiungi .github/x.txt"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Rinomina", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Rinomina", stato="pronto")])

    def committa_rinomina(cartella, prompt, **kwargs):
        docs = Path(cartella) / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", ".github/x.txt", "docs/x.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "mv da github a docs"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_rinomina)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


def test_attacco_4_link_simbolico_costituzione_verso_environ(tmp_path: Path):
    """Attacco 4: un link simbolico (modo 120000), es. `docs/costituzione.md -> /proc/self/environ`, deve essere rifiutato."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Symlink", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Symlink", stato="pronto")])

    def committa_symlink(cartella, prompt, **kwargs):
        docs = Path(cartella) / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        link = docs / "costituzione.md"
        if link.exists():
            link.unlink()
        link.symlink_to("/proc/self/environ")
        subprocess.run(["git", "add", "docs/costituzione.md"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "symlink exploit"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_symlink)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


def test_attacco_5_submodulo_e_gitmodules(tmp_path: Path):
    """Attacco 5: un submodulo (modo 160000) e un file .gitmodules devono essere rifiutati."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Submodulo", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Submodulo", stato="pronto")])

    def committa_gitmodules(cartella, prompt, **kwargs):
        # Aggiungiamo .gitmodules
        gm = Path(cartella) / ".gitmodules"
        gm.write_text("[submodule \"sub\"]\n\tpath = sub\n\turl = https://example.com/sub.git\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitmodules"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiungi .gitmodules"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_gitmodules)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


def test_attacco_6_file_sotto_bottega(tmp_path: Path):
    """Attacco 6: un file consegnato sotto `.bottega/` deve essere rifiutato."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Bottega Dir", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Bottega Dir", stato="pronto")])

    def committa_bottega_dir(cartella, prompt, **kwargs):
        b_dir = Path(cartella) / ".bottega"
        b_dir.mkdir(parents=True, exist_ok=True)
        (b_dir / "exploit.sh").write_text("echo boom", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".bottega/exploit.sh"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "exploit in .bottega"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_bottega_dir)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


def test_attacco_7_falso_git_che_falsifica_anche_bundle(tmp_path: Path):
    """Attacco 7: un falso git sul PATH dell'esecutore che falsifica anche bundle non inganna il runner."""
    from bottega.giro import giro
    import shutil

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Fake Git Bundle", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Fake Git Bundle", stato="pronto")])

    falso_bin = tmp_path / "falso_bin"
    falso_bin.mkdir()
    git_vero = shutil.which("git")
    falso_git = falso_bin / "git"
    # Il falso git falsifica 'diff' e per 'bundle' scrive un file vuoto/corrotto
    falso_git.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "diff" ]; then exit 0; fi\n'
        'if [ "$1" = "bundle" ] && [ "$2" = "create" ]; then echo "falso bundle" > "$3"; exit 0; fi\n'
        f'exec {git_vero} "$@"\n',
        encoding="utf-8",
    )
    falso_git.chmod(0o755)
    prefisso_falso = ("env", f"PATH={falso_bin}:{os.environ['PATH']}")

    def committa_con_attacco(cartella, prompt, **kwargs):
        (Path(cartella) / ".github").mkdir(exist_ok=True)
        (Path(cartella) / ".github" / "attacco.txt").write_text("attacco", encoding="utf-8")
        ambiente = {**os.environ, "PATH": f"{falso_bin}:{os.environ['PATH']}"}
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, env=ambiente)
        subprocess.run(["git", "commit", "-m", "attacco"], cwd=str(cartella), check=True, env=ambiente)
        return Lancio(esito="fatto", testo="fatto furbo")

    porta = PortaFinta(callback=committa_con_attacco)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=prefisso_falso,
        adesso=adesso,
        caso=caso,
    )
    # Il bundle è corrotto o non verificabile, il runner non consegna e il lavoro non va consegnato
    assert esito.esito in ("bloccato", "errore")
    assert forgia._pr == {}


def test_attacco_8_commit_vuoto(tmp_path: Path):
    """Attacco 8: un commit vuoto (nessuna modifica nei file) rimette il lavoro pronto con tentativi+1 e commento."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco Commit Vuoto", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco Commit Vuoto", stato="pronto")])

    def committa_vuoto(cartella, prompt, **kwargs):
        subprocess.run(["git", "commit", "--allow-empty", "-m", "commit vuoto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="ho creato un commit vuoto")

    porta = PortaFinta(callback=committa_vuoto)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "pronto"
    assert forgia._pr == {}
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_n = nota(lav.nota)
    assert d_n.get("tentativi") == "1"
    # Rapporto in un commento
    assert any("ho creato un commit vuoto" in c.corpo for c in forgia._commenti.get(1, []))


def test_attacco_9_nessun_commit(tmp_path: Path):
    """Attacco 9: nessun commit rimette il lavoro pronto con tentativi+1 e commento del rapporto."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Nessun Commit", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Nessun Commit", stato="pronto")])

    def non_committare(cartella, prompt, **kwargs):
        # Non fa nulla
        return Lancio(esito="fatto", testo="non ho fatto alcun commit")

    porta = PortaFinta(callback=non_committare)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "pronto"
    assert forgia._pr == {}
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_n = nota(lav.nota)
    assert d_n.get("tentativi") == "1"
    assert any("non ho fatto alcun commit" in c.corpo for c in forgia._commenti.get(1, []))


def test_attacco_10_lavoro_senza_commit_poi_quota(tmp_path: Path):
    """Attacco 10: lavoro lasciato senza commit e poi quota viene committato automaticamente e salvato."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Quota Senza Commit", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Quota Senza Commit", stato="pronto")])

    def sporca_e_quota(cartella, prompt, **kwargs):
        (Path(cartella) / "incompleto.txt").write_text("lavoro parziale non committato\n", encoding="utf-8")
        return Lancio(esito="quota", testo="quota esaurita", conversazione="c10")

    porta = PortaFinta(callback=sporca_e_quota)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "quota"
    assert len(forgia._pr) == 1
    # Il file non committato è stato committato nel ramo remoto
    check = subprocess.run(
        ["git", "show", "origin/bottega/1-quota-senza-commit:incompleto.txt"],
        cwd=str(clone),
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0
    assert "lavoro parziale non committato" in check.stdout


def test_attacco_14_oracolo_timeout_rosso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Attacco 14: un oracolo che non finisce mai è ROSSO, non crasha e il gruppo processi viene terminato."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief\n\n## Fatto quando\n```bash\nsleep 100\n```\n"
    iss = Issue(numero=1, titolo="Compito Timeout Oracolo", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Timeout Oracolo", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    monkeypatch.setenv("BOTTEGA_TEMPO_ORACOLO", "0.2")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    assert esito.oracolo_ok is False
    assert any("Esito dell'oracolo: ROSSO" in c.corpo for c in forgia._commenti.get(1, []))


def test_rv2_clone_con_rebase_apply_o_superficiale(tmp_path: Path):
    """RV2: un clone del runner con un `.git/rebase-apply` lasciato da un giro precedente non ferma il giro."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    # Lasciamo un rebase-apply sporco nel clone del runner
    (clone / ".git" / "rebase-apply").mkdir(exist_ok=True)
    (clone / ".git" / "rebase-apply" / "applying").write_text("1", encoding="utf-8")

    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Rebase Sporco", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Rebase Sporco", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    assert not (clone / ".git" / "rebase-apply").exists()


def test_rv5_nessuna_eccezione_fallimento_gh_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """RV5: nessuna eccezione esce da giro() in caso di fallimento di gh finto sulla PR."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Fallimento PR", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Fallimento PR", stato="pronto")])

    # Simuliamo fallimento di gh apri_pr
    def fallisci_apri_pr(*args, **kwargs):
        raise RuntimeError("gh pr create: errore di rete simulato")
    monkeypatch.setattr(forgia, "apri_pr", fallisci_apri_pr)

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "errore"
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_n = nota(lav.nota)
    assert d_n.get("tentativi") == "1"
    # Commento del motivo inserito
    assert any("errore di rete simulato" in c.corpo for c in forgia._commenti.get(1, []))
    # Rilancio del distributore avvenuto
    assert ("bottega-distributore.yml", {}) in forgia._workflow_avviati


def test_rv5_nessuna_eccezione_bundle_rotto(tmp_path: Path):
    """RV5: nessuna eccezione esce da giro() in caso di bundle rotto."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Bundle Rotto", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Bundle Rotto", stato="pronto")])

    def committa_bundle_rotto(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        # Sovrascriviamo git bundle create con un file corrotto nello spazio
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_bundle_rotto)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    # Monkeypatch subprocess.run per simulare fallimento di git bundle verify
    orig_run = subprocess.run
    def finto_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[-2] == "verify":
            raise subprocess.CalledProcessError(1, cmd, stderr=b"fatal: not a valid bundle")
        return orig_run(cmd, *args, **kwargs)

    import unittest.mock
    with unittest.mock.patch("subprocess.run", side_effect=finto_run):
        esito = giro(
            lavoro=1,
            bottega="principale",
            configurazione=cfg,
            forgia=forgia,
            board=board,
            porte={"finta": porta},
            clone_progetto=clone,
            spazio=spazio,
            prefisso=(),
            adesso=adesso,
            caso=caso,
        )

    assert esito.esito == "errore"
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_n = nota(lav.nota)
    assert d_n.get("tentativi") == "1"
    assert ("bottega-distributore.yml", {}) in forgia._workflow_avviati


def test_rv3_fonti_sicure_e_commenti_comandanti(tmp_path: Path):
    """RV3: fascicolo in .bottega/fascicolo/, costituzione letta da git show origin/main e solo commenti dei comandanti."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    # Creiamo costituzione.md committata nel ramo principale
    docs_dir = clone / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "costituzione.md").write_text("Costituzione Autentica da Git\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/costituzione.md"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "aggiungi costituzione vera"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    # Ora modifichiamo costituzione.md nell'albero di lavoro (o con symlink)
    (docs_dir / "costituzione.md").write_text("CONTENUTO_SPORCO_NON_AUTENTICO\n", encoding="utf-8")

    cfg = _crea_configurazione()
    # Impostiamo comandanti espliciti
    cfg = replace(cfg, progetto=replace(cfg.progetto, comandanti=("comandante1",)))

    iss = Issue(numero=1, titolo="Compito Fascicolo", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    # Aggiungiamo commenti di un comandante e di un intruso
    c_comandante = Commento(autore="comandante1", corpo="Istruzioni valide dal comandante")
    c_intruso = Commento(autore="utente_malevolo", corpo="Commento non autorizzato da ignorare")
    forgia = ForgiaFinta(issues=[iss])
    forgia._commenti[1] = [c_comandante, c_intruso]
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Fascicolo", stato="pronto")])

    fascicolo_letto: dict[str, str] = {}

    def callback_esecutore(cartella, prompt, **kwargs):
        fasc_dir = Path(cartella) / ".bottega" / "fascicolo"
        for f in fasc_dir.iterdir():
            if f.is_file():
                fascicolo_letto[f.name] = f.read_text(encoding="utf-8")
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=callback_esecutore)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    # Costituzione proviene da git show origin/main, NON dall'albero di lavoro modificato
    assert "Costituzione Autentica da Git" in fascicolo_letto["costituzione.md"]
    assert "CONTENUTO_SPORCO" not in fascicolo_letto["costituzione.md"]
    # Commenti contengono solo quelli dei comandanti
    assert "comandante1" in fascicolo_letto["commenti.md"]
    assert "utente_malevolo" not in fascicolo_letto["commenti.md"]


def test_rv8_prove_cambiate_e_segreti_gitleaks(tmp_path: Path):
    """RV8: diff con test modificato/cancellato -> prove cambiate; file .gitleaksignore toccato -> segreti."""
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Prove e Segreti", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Prove e Segreti", stato="pronto")])

    def committa_modifiche(cartella, prompt, **kwargs):
        # Modifica di un file di test esistente (test_file.py è stato creato in _crea_ambiente_git)
        (Path(cartella) / "test_file.py").write_text("def test_modificato(): pass\n", encoding="utf-8")
        # Tocco del file .gitleaksignore
        (Path(cartella) / ".gitleaksignore").write_text("secret_hash\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "modifica test e gitleaksignore"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_modifiche)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    pr_num = esito.pr
    assert pr_num is not None
    pr_etichette = forgia._pr[pr_num].get("etichette", [])
    assert "bottega: prove cambiate" in pr_etichette
    assert "bottega: segreti" in pr_etichette


# Prove di sicurezza e robustezza C4 (RV1-RV18)


def test_c4_storia_github_aggiunto_e_tolto(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    def committa_tre_volte(cartella, prompt, **kwargs):
        wf = Path(cartella) / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "x.yml").write_text("name: temp\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunto workflow"], cwd=str(cartella), check=True, capture_output=True)

        (wf / "x.yml").unlink()
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "tolto workflow"], cwd=str(cartella), check=True, capture_output=True)

        docs_a = Path(cartella) / "docs" / "a.md"
        docs_a.parent.mkdir(parents=True, exist_ok=True)
        docs_a.write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunto docs/a.md"], cwd=str(cartella), check=True, capture_output=True)

        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_tre_volte)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"
    rami_origin = subprocess.run(["git", "branch"], cwd=str(origin), check=True, capture_output=True, text=True).stdout
    assert "bottega/" not in rami_origin


def test_c4_commit_di_unione_rifiutato(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    def committa_unione(cartella, prompt, **kwargs):
        ramo_corrente = subprocess.run(
            ["git", "branch", "--show-current"], cwd=str(cartella), check=True, capture_output=True, text=True
        ).stdout.strip()

        subprocess.run(["git", "checkout", "-b", "laterale"], cwd=str(cartella), check=True, capture_output=True)
        docs_b = Path(cartella) / "docs" / "b.md"
        docs_b.parent.mkdir(parents=True, exist_ok=True)
        docs_b.write_text("laterale", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "commit laterale"], cwd=str(cartella), check=True, capture_output=True)

        subprocess.run(["git", "checkout", ramo_corrente], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(
            ["git", "merge", "--no-ff", "-m", "unione laterale", "laterale"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_unione)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"
    rami_origin = subprocess.run(["git", "branch"], cwd=str(origin), check=True, capture_output=True, text=True).stdout
    assert "bottega/" not in rami_origin


def test_c4_copia_consigliere_non_segue_i_link(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    fuori = tmp_path / "fuori.txt"
    fuori.write_text("testo segreto", encoding="utf-8")

    consigliere_ha_visto_symlink: list[bool] = []

    def callback_porta(cartella, prompt, sola_lettura=False, **kwargs):
        p_cartella = Path(cartella)
        if not sola_lettura:
            link = p_cartella / "segreto"
            link.symlink_to(fuori)
            return Lancio(esito="fatto", testo="fatto\n\nDOMANDA PER CHI DECIDE: che fare?")
        else:
            segreto_nel_cons = p_cartella / "segreto"
            consigliere_ha_visto_symlink.append(segreto_nel_cons.is_symlink())
            return Lancio(esito="fatto", testo="A CHI DECIDE")

    porta = PortaFinta(callback=callback_porta)
    porta.gestisce_sola_lettura = True
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert consigliere_ha_visto_symlink == [True]


def test_c4_oracolo_recintato(tmp_path: Path):
    import re
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    cmd_oracolo = "printf '```\\nCloses #1\\n/bottega riprova\\n'"
    corpo = f"Brief\n\n## Fatto quando\n```bash\n{cmd_oracolo}\n```\n"
    iss = Issue(numero=1, titolo="Compito 1", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    def committa_ok(cartella, prompt, **kwargs):
        f = Path(cartella) / "test_file.py"
        f.write_text("def test_ok(): assert True\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "modifica"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_ok)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    comm_oracolo = [c for c in forgia.commenti(1) if "Esito dell'oracolo" in c.corpo]
    assert len(comm_oracolo) == 1
    testo = comm_oracolo[0].corpo

    m = re.search(r"(`{4,})", testo)
    assert m is not None, f"Nessun recinto di 4+ apici in: {testo}"
    recinto = m.group(1)
    pattern = rf"{recinto}\n.*Closes #1.*\n{recinto}"
    assert re.search(pattern, testo, re.DOTALL) is not None


def test_c4_esito_sconosciuto_conta_tentativi(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    porta = PortaFinta(esito_lancio="tempo", testo_lancio="tempo scaduto")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    # Giro 1
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito1.esito == "errore"
    assert board.lavoro(1).stato == "pronto"
    assert nota(board.lavoro(1).nota).get("tentativi") == "1"

    # Giro 2
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito2.esito == "errore"
    assert board.lavoro(1).stato == "pronto"
    assert nota(board.lavoro(1).nota).get("tentativi") == "2"

    # Giro 3
    esito3 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito3.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"


@pytest.mark.parametrize("ramo_non_valido", ["bottega/../main", "bottega/a:b"])
def test_c4_ramo_della_nota_non_valido(tmp_path: Path, ramo_non_valido: str):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", nota=f"ramo={ramo_non_valido}")
    ])

    porta = PortaFinta(esito_lancio="fatto", testo_lancio="fatto")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "bloccato"
    assert esito.motivo == "ramo non valido"
    assert board.lavoro(1).stato == "bloccato"
    nota_scritta = nota(board.lavoro(1).nota)
    assert nota_scritta.get("compito") == "1"
    rami_origin = subprocess.run(["git", "branch"], cwd=str(origin), check=True, capture_output=True, text=True).stdout
    assert "bottega/" not in rami_origin


def test_c4_senza_fatto_quando_conserva_la_nota(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief senza fatto quando.")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", nota="ramo=bottega/1-prova")
    ])

    porta = PortaFinta()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert board.lavoro(1).stato == "pronto"
    nota_scritta = nota(board.lavoro(1).nota)
    assert nota_scritta.get("ramo") == "bottega/1-prova"


def test_c4_errore_prima_del_giro_non_esce(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    class ForgiaCheSolleva(ForgiaFinta):
        def issue(self, n: int):
            raise RuntimeError("guasto alla forgia prima del giro")

    forgia = ForgiaCheSolleva()
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])
    porta = PortaFinta()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "errore"
    assert "guasto alla forgia" in (esito.motivo or "")
    assert board.lavoro(1).stato == "pronto"
    assert not any(op[0] == "avvia_workflow" for op in forgia.registro)


def test_c4_salvataggio_quota_con_commit_vuoto(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    def committa_vuoto(cartella, prompt, **kwargs):
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "commit vuoto"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="quota", testo="quota finita")

    porta = PortaFinta(callback=committa_vuoto)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert esito.esito == "quota"
    assert len(forgia._pr) == 0


def test_c4_domanda_e_l_ultima(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    testo_modello = (
        "Ho pensato a questa cosa:\n"
        "DOMANDA PER CHI DECIDE: vecchia\n"
        "Poi ho cambiato idea e quindi:\n\n"
        "DOMANDA PER CHI DECIDE: nuova"
    )

    porta = PortaFinta(esito_lancio="fatto", testo_lancio=testo_modello)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    comms = forgia.commenti(1)
    comm_consulto = [c for c in comms if "Consulto dell'esecutore:" in c.corpo]
    assert len(comm_consulto) == 1
    corpo = comm_consulto[0].corpo
    assert "nuova" in corpo
    assert "vecchia" not in corpo


def test_c4_gitleaks_sulla_storia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "gl_args.txt"
    gl_script = fake_bin / "gitleaks"
    gl_script.write_text(f"""#!/bin/sh
printf '%s\\n' "$@" > "{args_file}"
exit 1
""", encoding="utf-8")
    gl_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")

    def committa_normale(cartella, prompt, **kwargs):
        f = Path(cartella) / "test_file.py"
        f.write_text("def test_ok(): pass\n# commento", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "normale"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa_normale)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert args_file.is_file()
    args = args_file.read_text(encoding="utf-8").splitlines()
    assert "--pre-commit" not in args
    assert any(a.startswith("--log-opts=") for a in args)

    assert len(forgia._pr) == 1
    pr = next(iter(forgia._pr.values()))
    assert "bottega: segreti" in pr.get("etichette", [])


def test_c4_spazio_di_serie_fuori_dal_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import argparse
    from typing import Any
    from bottega.giro import comando_giro

    monkeypatch.delenv("BOTTEGA_SPAZIO", raising=False)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(temp_dir))
    monkeypatch.setenv("GITHUB_REPOSITORY", "proprietario/repo")

    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(
        'versione = 1\n\n'
        '[progetto]\n'
        'fuso = "Europe/Rome"\n'
        'adattatore = "echo"\n\n'
        '[botteghe.principale]\n'
        'quota = "scarsa"\n'
        'porte = ["claude-code"]\n\n'
        '[candidati.maestro]\n'
        'nome = "Maestro"\n'
        'bottega = "principale"\n'
        'porta = "claude-code"\n'
        'modello = "m"\n'
        'funzioni = ["decidere", "eseguire"]\n',
        encoding="utf-8",
    )

    catturato: dict[str, Any] = {}

    def finto_giro(**kwargs):
        catturato["spazio"] = kwargs.get("spazio")
        from bottega.giro import EsitoGiro
        return EsitoGiro("consegnato")

    monkeypatch.setattr("bottega.giro.giro", finto_giro)

    args = argparse.Namespace(lavoro=1, bottega="principale", configurazione=cfg_file)
    rc = comando_giro(args)
    assert rc == 0
    spazio = catturato.get("spazio")
    assert spazio == temp_dir / "bottega-spazio"
    assert not str(spazio).startswith(str(Path.cwd()))


def test_c5_clone_del_runner_resta_sul_principale(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito 1", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito 1", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        docs = Path(cartella) / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "a.md").write_text("testo modello a", encoding="utf-8")
        strum = Path(cartella) / "strumenti"
        strum.mkdir(exist_ok=True)
        (strum / "board").write_text("echo board", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunge a e board"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    res_head = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=str(clone),
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_head.stdout.strip() == "refs/heads/main"
    assert not (clone / "strumenti" / "board").exists()
    assert not (clone / "docs" / "a.md").exists()


def test_c5_orfano_non_appende_l_oracolo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import time
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief\n\n## Fatto quando\n```bash\nsetsid sleep 21.5 & echo fatto\n```\n"
    iss = Issue(numero=1, titolo="Compito Orfano", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Orfano", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    monkeypatch.setenv("BOTTEGA_TEMPO_ORACOLO", "3")

    try:
        t0 = time.monotonic()
        esito = giro(
            lavoro=1,
            bottega="principale",
            configurazione=cfg,
            forgia=forgia,
            board=board,
            porte={"finta": porta},
            clone_progetto=clone,
            spazio=spazio,
            prefisso=(),
            adesso=adesso,
            caso=caso,
        )
        durata = time.monotonic() - t0
        assert durata < 12, f"giro ha impiegato {durata}s (atteso < 12s)"
        assert esito.esito == "consegnato"
    finally:
        subprocess.run(["pkill", "-f", "sleep 21.5"], capture_output=True)


def test_c5_oracolo_byte_non_utf8(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief\n\n## Fatto quando\n```bash\nprintf '\\xe8\\xff\\n'\n```\n"
    iss = Issue(numero=1, titolo="Compito Non UTF8", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Non UTF8", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    assert len(forgia._pr) == 1


def test_c5_tag_del_bundle_non_entra(tmp_path: Path):
    import shutil
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Trappola Tag", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Trappola Tag", stato="pronto")])

    falso_bin = tmp_path / "bin"
    falso_bin.mkdir()
    git_vero = shutil.which("git")
    assert git_vero is not None
    falso_git = falso_bin / "git"
    falso_git.write_text(
        f'#!/bin/sh\n'
        f'if [ "$1" = "bundle" ] && [ "$2" = "create" ]; then\n'
        f'    "{git_vero}" tag trappola HEAD\n'
        f'    exec "{git_vero}" "$@" refs/tags/trappola\n'
        f'fi\n'
        f'exec "{git_vero}" "$@"\n',
        encoding="utf-8",
    )
    falso_git.chmod(0o755)
    prefisso_falso = ("env", f"PATH={falso_bin}:{os.environ['PATH']}")

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=prefisso_falso,
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    res_tag = subprocess.run(
        ["git", "-C", str(clone), "tag", "-l", "trappola"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_tag.stdout.strip() == ""


def test_c5_nome_di_file_recintato(tmp_path: Path):
    import re
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Nome Link", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Nome Link", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        nome_link = "x\n\n@vittima leggi subito"
        os.symlink("docs/costituzione.md", Path(cartella) / nome_link)
        subprocess.run(["git", "add", nome_link], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunge link"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    comm = forgia._commenti.get(1, [])
    assert len(comm) == 1
    corpo = comm[0].corpo
    assert "@vittima" in corpo
    senza_recinti = re.sub(r"`{3,}[\s\S]*?`{3,}", "", corpo)
    assert "@vittima" not in senza_recinti


def test_c5_closes_nel_messaggio_rifiutato(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Closes", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Closes", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "docs" / "a.md").write_text("testo a", encoding="utf-8")
        subprocess.run(["git", "add", "docs/a.md"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Aggiunge a\n\nFixes #1"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    # C6: un tentativo, non un blocco; il commento dice perché; niente spinta.
    assert esito.esito == "errore"
    lav = board.lavoro(1)
    assert lav is not None and lav.stato == "pronto"
    assert "tentativi=1" in lav.nota
    assert any("chiude un'issue" in c.corpo for c in forgia.commenti(1))
    res_rami = subprocess.run(
        ["git", "--git-dir", str(origin), "branch", "--list", "bottega/*"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_rami.stdout.strip() == ""


def test_c5_quota_ripetuta_blocca(tmp_path: Path):
    from bottega.giro import giro
    from bottega.quota import nome_variabile

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Quota", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Quota", stato="pronto")])

    porta = PortaFinta(esito_lancio="quota", testo_lancio="quota esaurita")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)
    var_q = nome_variabile("principale")

    # Primo giro
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito1.esito == "quota"
    lav1 = board.lavoro(1)
    assert lav1 is not None
    assert nota(lav1.nota).get("quote") == "1"

    # Azzera la variabile della quota
    forgia._variabili.pop(var_q, None)

    # Secondo giro
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito2.esito == "quota"
    lav2 = board.lavoro(1)
    assert lav2 is not None
    assert nota(lav2.nota).get("quote") == "2"

    # Azzera la variabile della quota
    forgia._variabili.pop(var_q, None)

    # Terzo giro
    esito3 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito3.esito == "bloccato"
    assert esito3.motivo == "quota ripetuta"
    lav3 = board.lavoro(1)
    assert lav3 is not None
    assert lav3.stato == "bloccato"
    assert nota(lav3.nota).get("quote") == "3"
    assert nota(lav3.nota).get("motivo") == "quota ripetuta"


def test_c5_conftest_nuovo_accende_prove_cambiate(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Conftest", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Conftest", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        tests_dir = Path(cartella) / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "conftest.py").write_text("# fixtures\n", encoding="utf-8")
        subprocess.run(["git", "add", "tests/conftest.py"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunge conftest"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    pr = next(iter(forgia._pr.values()))
    assert "bottega: prove cambiate" in pr.get("etichette", [])


def test_c5_gitleaks_allow_accende_segreti(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import shutil
    from bottega.giro import giro

    cur_path = os.environ.get("PATH", "")
    senza_gl = os.pathsep.join(p for p in cur_path.split(os.pathsep) if not (Path(p) / "gitleaks").exists())
    monkeypatch.setenv("PATH", senza_gl)
    assert shutil.which("gitleaks") is None

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Gitleaks Allow", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Gitleaks Allow", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "chiave.py").write_text("x = 1  # gitleaks:allow\n", encoding="utf-8")
        subprocess.run(["git", "add", "chiave.py"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aggiunge x con allow"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    pr = next(iter(forgia._pr.values()))
    assert "bottega: segreti" in pr.get("etichette", [])


def test_c5_fascicolo_scritto_dall_esecutore(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Fascicolo", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Fascicolo", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f'#!/bin/sh\n'
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f'    kill|pkill|killall)\n'
        f'        exit 0\n'
        f'        ;;\n'
        f'esac\n'
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(str(prefisso_sh),),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    righe = registro.read_text(encoding="utf-8").splitlines()
    assert any("cp -R" in r and "fascicolo" in r for r in righe)
    assert any(".git/info/exclude" in r for r in righe)


def test_c5_autore_non_comandante(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Estraneo", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="estraneo")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Estraneo", stato="pronto")])

    chiamate_porta = []

    def callback(cartella, prompt, **kwargs):
        chiamate_porta.append(prompt)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=callback)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "bloccato"
    assert esito.motivo == "autore non comandante"
    assert len(chiamate_porta) == 0
    assert len(porta.lanci) == 0


def test_c5_avviso_della_porta_recintato(tmp_path: Path):
    import re
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Avviso", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Avviso", stato="pronto")])

    porta = PortaFinta(esito_controllo=False, motivo_controllo="rotta\n@vittima")
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "porta_non_pronta"
    avvisi = [iss for iss in forgia._issues.values() if "bottega: avviso" in iss.etichette]
    assert len(avvisi) == 1
    corpo = avvisi[0].corpo
    assert "@vittima" in corpo
    senza_recinti = re.sub(r"`{3,}[\s\S]*?`{3,}", "", corpo)
    assert "@vittima" not in senza_recinti








def test_c6_chiude_issue_forme_url_e_gh():
    """C6: le forme che GitHub riconosce, e non quelle innocue."""
    from bottega.giro import _CHIUDE_ISSUE

    for testo in ("Fixes #3", "closes: #3", "Resolves o/r#3", "Closes GH-5", "fix https://github.com/o/r/issues/5"):
        assert _CHIUDE_ISSUE.search(testo), testo
    for testo in ("Fix the bug in #3 handler", "Prefix #3", "risolve #3", "Fixes nothing"):
        assert not _CHIUDE_ISSUE.search(testo), testo


def test_c6_gitleaks_allow_aggiunto_e_tolto(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito C6", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito C6", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        c = Path(cartella)

        def git(*a):
            subprocess.run(["git", *a], cwd=str(c), check=True, capture_output=True)

        (c / "k.py").write_text("x = 1  # gitleaks:allow\n", encoding="utf-8")
        git("add", "k.py")
        git("commit", "-m", "aggiunge k")
        git("rm", "-q", "k.py")
        git("commit", "-m", "toglie k")
        (c / "docs").mkdir(exist_ok=True)
        (c / "docs" / "b.md").write_text("b\n", encoding="utf-8")
        git("add", "docs/b.md")
        git("commit", "-m", "aggiunge b")
        return Lancio(esito="fatto", testo="fatto")

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
    pr = next(iter(forgia._pr.values()))
    assert "bottega: segreti" in pr.get("etichette", [])


def test_c6_pytest_ini_nascosto_accende_prove_cambiate(tmp_path: Path):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito C6", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito C6", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        c = Path(cartella)

        def git(*a):
            subprocess.run(["git", *a], cwd=str(c), check=True, capture_output=True)

        (c / ".pytest.ini").write_text("[pytest]\naddopts = -k 'not rotta'\n", encoding="utf-8")
        git("add", ".pytest.ini")
        git("commit", "-m", "configura")
        return Lancio(esito="fatto", testo="fatto")

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
    pr = next(iter(forgia._pr.values()))
    assert "bottega: prove cambiate" in pr.get("etichette", [])


def test_c6_pulizia_che_cade_non_cambia_l_esito(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from bottega.giro import giro

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito C6", corpo="Brief\n\n## Fatto quando\n```bash\ntrue\n```\n", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito C6", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        c = Path(cartella)

        def git(*a):
            subprocess.run(["git", *a], cwd=str(c), check=True, capture_output=True)

        (c / "docs").mkdir(exist_ok=True)
        (c / "docs" / "c.md").write_text("c\n", encoding="utf-8")
        git("add", "docs/c.md")
        git("commit", "-m", "aggiunge c")
        import bottega.giro as modulo_giro
        vero_rmtree = modulo_giro.shutil.rmtree

        def rmtree_che_cade(percorso, *a, **k):
            if str(percorso).startswith(str(tmp_path / "spazio")) and Path(percorso).parent == tmp_path / "spazio":
                raise RuntimeError("pulizia rotta")
            return vero_rmtree(percorso, *a, **k)

        monkeypatch.setattr(modulo_giro.shutil, "rmtree", rmtree_che_cade)
        return Lancio(esito="fatto", testo="fatto")

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
    assert lav is not None and lav.stato == "consegnato"
