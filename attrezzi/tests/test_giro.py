"""Prove per bottega.giro (Task 5, B3)."""

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

    def controlla(self) -> Controllo:
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
            runner=None,
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

    # Lavoro tornato pronto con conversazione e attese=1
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    assert "attese=1" in lav.nota
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
    assert "precedente=11" in lav_madre.nota

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

    with pytest.raises(RuntimeError):
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
        fasc_dir = Path(cartella).parent / "fascicolo"
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
