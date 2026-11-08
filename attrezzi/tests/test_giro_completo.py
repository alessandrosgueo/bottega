"""Giro finto completo e Review Focus 1-4 (Task 9, B3).

Verifica l'intero ciclo di regia del repo bottega:
- Distribuzione e assegnazione dei lavori tramite la board;
- Giro dell'esecutore con clone, fascicolo, oracolo e consegna su ramo dedicato;
- Consegna incrementale di una tappa su più compiti (stesso ramo, stessa PR);
- Assegnazione del lavoro sciolto alla stessa bottega solo a tappa ultimata;
- Review Focus 1: rifiuto di patch che toccano .github/ (nessuna spinta su origin);
- Review Focus 2: idempotenza di distribuzioni consecutive (nessun lavoro duplicato);
- Review Focus 3: gestione della quota esaurita con salvataggio parziale e ripresa della conversazione;
- Review Focus 4: gestione di porta non pronta (lavoro non toccato, avviso unico deduplicato, chiusura al ripristino);
- Presenza del segno su tutti i commenti e le PR, assenza di comandi nei commenti dei giri.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import subprocess

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import giro
from bottega.porte import Controllo, Lancio
from bottega.quota import nome_variabile
from bottega.segni import comando, ruolo, segna


class PortaFintaCompleta:
    """Porta finta configurabile per le prove del giro completo."""

    def __init__(
        self,
        callback: Callable[..., Lancio] | None = None,
        esito_controllo: bool = True,
        motivo_controllo: str | None = None,
    ) -> None:
        self.nome = "finta"
        self.eseguibile = "finta"
        self.esito_controllo = esito_controllo
        self.versione = "1.0"
        self.motivo_controllo = motivo_controllo
        self.callback = callback
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
        if sola_lettura:
            return Lancio(esito="fatto", testo="Revisione in sola lettura approvata")
        if self.callback is not None:
            return self.callback(cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura)
        return Lancio(esito="fatto", testo="Compito completato con successo")


def _costruisci_progetto_git(tmp_path: Path) -> tuple[Path, Path]:
    """Inizializza un'origine nuda e un clone locale per il runner."""
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
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "costituzione.md").write_text("# Costituzione\nRegole del repo di prova.\n", encoding="utf-8")
    (clone / "base.txt").write_text("file iniziale di prova\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "commit iniziale"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    return origin, clone


def _configurazione_due_botteghe() -> Configurazione:
    """Configura due botteghe: scarsa senza runner (decisione/consiglio), abbondante col runner (esecuzione)."""
    progetto = Progetto(
        comandanti=("maestro",),
        adattatore=None,
        fuso="UTC",
        notte=None,
        manutenzione=(),
        project=1,
        liberi=("sciolto",),
    )
    botteghe = {
        "b_scarsa": Bottega(id="b_scarsa", quota="scarsa", porte=("finta",)),
        "b_abbondante": Bottega(id="b_abbondante", quota="abbondante", porte=("finta",)),
    }
    candidati = {
        "consigliere": Candidato(
            id="consigliere",
            nome="Consigliere",
            bottega="b_scarsa",
            porta="finta",
            modello="mod-consigliere",
            funzioni=("decidere", "consigliare"),
            runner=None,
        ),
        "esecutore": Candidato(
            id="esecutore",
            nome="Esecutore",
            bottega="b_abbondante",
            porta="finta",
            modello="mod-esecutore",
            funzioni=("eseguire",),
            runner="linux",
        ),
    }
    return Configurazione(versione=1, progetto=progetto, botteghe=botteghe, candidati=candidati)


def test_giro_completo_ciclo_e_segno(tmp_path: Path) -> None:
    """Verifica il ciclo completo di regia (distributore -> giro 1 -> giro 2 -> sblocco lavoro sciolto) e il segno."""
    origin, clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione_due_botteghe()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)

    # 1. Forgia e Board: tappa madre (id 1) con due sotto-issue (id 2, id 3) e lavoro sciolto (id 4)
    madre = Issue(
        numero=1,
        titolo="Tappa Nuova Funzionalita",
        corpo="Tappa con due sotto-compiti sequenziali.",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )
    sotto1 = Issue(
        numero=2,
        titolo="Passo 1: creazione modulo",
        corpo="Crea modulo.txt.\n\n## Fatto quando\n```bash\ntest -f modulo.txt\n```\n",
        stato="OPEN",
    )
    sotto2 = Issue(
        numero=3,
        titolo="Passo 2: estensione modulo",
        corpo="Crea estensione.txt.\n\n## Fatto quando\n```bash\ntest -f estensione.txt\n```\n",
        stato="OPEN",
    )
    sciolto = Issue(
        numero=4,
        titolo="Lavoro Sciolto",
        corpo="Crea sciolto.txt.\n\n## Fatto quando\n```bash\ntest -f sciolto.txt\n```\n",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )

    forgia = ForgiaFinta(issues=[madre, sotto1, sotto2, sciolto])
    forgia._sotto_issue[1] = [2, 3]

    board = BoardFinta(lavori=[
        Lavoro(numero=1, titolo="Tappa Nuova Funzionalita", stato="pronto", etichette=["bottega: fuori"]),
        Lavoro(numero=4, titolo="Lavoro Sciolto", stato="pronto", etichette=["bottega: fuori"]),
    ])

    compito_in_corso = 2

    def callback_porta(cartella: Path | str, prompt: str, **kwargs) -> Lancio:
        nonlocal compito_in_corso
        p_cartella = Path(cartella)
        if compito_in_corso == 2:
            (p_cartella / "modulo.txt").write_text("funzionalita base\n", encoding="utf-8")
            return Lancio(esito="fatto", testo="Rapporto esecutore: modulo.txt creato")
        elif compito_in_corso == 3:
            (p_cartella / "estensione.txt").write_text("estensione modulo\n", encoding="utf-8")
            return Lancio(esito="fatto", testo="Rapporto esecutore: estensione.txt creato")
        elif compito_in_corso == 4:
            (p_cartella / "sciolto.txt").write_text("lavoro sciolto fatto\n", encoding="utf-8")
            return Lancio(esito="fatto", testo="Rapporto esecutore: sciolto.txt creato")
        return Lancio(esito="fatto", testo="completato")

    porta = PortaFintaCompleta(callback=callback_porta)
    porte = {"finta": porta}

    # Passo 1: primo distribuisci -> assegna lavoro 1 a b_abbondante; lavoro 4 saltato (bottega occupata)
    righe1 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )
    assert any("assegnato a «esecutore»" in r for r in righe1)
    assert any("lavoro 4: bottega «b_abbondante» occupata, salto" in r for r in righe1)
    wf_esec = [w for w in forgia._workflow_avviati if w[0] == "bottega-esecutore-b_abbondante.yml"]
    assert len(wf_esec) == 1
    assert wf_esec[-1][1] == {"lavoro": "1"}
    assert board.lavoro(1).stato == "in corso"

    # Passo 2: primo giro -> esegue sotto-issue 2, apre PR in bozza per la madre, chiude sotto-issue 2
    compito_in_corso = 2
    esito_giro1 = giro(
        lavoro=1,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte=porte,
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=1),
        caso=random.Random(1),
    )
    assert esito_giro1.esito == "consegnato"
    assert esito_giro1.oracolo_ok is True
    assert forgia.issue(2).stato == "CLOSED"
    assert forgia.issue(3).stato == "OPEN"
    # Madre torna pronta per il prossimo compito, la tappa continua
    assert board.lavoro(1).stato == "pronto"
    assert "precedente=esecutore" in board.lavoro(1).nota

    ramo_tappa = "bottega/1-tappa-nuova-funzionalita"
    pr_num1 = forgia.pr_del_ramo(ramo_tappa)
    assert pr_num1 is not None
    dati_pr1 = forgia._pr[pr_num1]
    assert "Lavoro: #1" in dati_pr1["corpo"]

    # Verifica rilancio del distributore registrato nella forgia
    wf_dist = [w for w in forgia._workflow_avviati if w[0] == "bottega-distributore.yml"]
    assert len(wf_dist) >= 1

    # Passo 3: secondo distribuisci -> prende secondo compito della tappa, lavoro 4 ancora in attesa
    righe2 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso + timedelta(minutes=5),
        caso=random.Random(2),
        notte=False,
    )
    assert any("assegnato a «esecutore»" in r for r in righe2)
    assert any("lavoro 4: bottega «b_abbondante» occupata, salto" in r for r in righe2)
    wf_esec2 = [w for w in forgia._workflow_avviati if w[0] == "bottega-esecutore-b_abbondante.yml"]
    assert len(wf_esec2) == 2
    assert wf_esec2[-1][1] == {"lavoro": "1"}

    # Passo 4: secondo giro -> sullo STESSO ramo e STESSA PR, chiude sotto-issue 3 e consegna la madre
    compito_in_corso = 3
    esito_giro2 = giro(
        lavoro=1,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte=porte,
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=6),
        caso=random.Random(2),
    )
    assert esito_giro2.esito == "consegnato"
    assert esito_giro2.oracolo_ok is True
    assert forgia.issue(3).stato == "CLOSED"
    assert board.lavoro(1).stato == "consegnato"

    pr_num2 = forgia.pr_del_ramo(ramo_tappa)
    assert pr_num2 == pr_num1  # Stessa PR

    # Passo 5: terzo distribuisci -> la tappa è consegnata, ora la bottega è libera e prende il lavoro sciolto
    righe3 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso + timedelta(minutes=10),
        caso=random.Random(3),
        notte=False,
    )
    assert any("lavoro 4: assegnato a «esecutore» (b_abbondante)" in r for r in righe3)
    assert board.lavoro(4).stato == "in corso"
    wf_esec3 = [w for w in forgia._workflow_avviati if w[0] == "bottega-esecutore-b_abbondante.yml"]
    assert len(wf_esec3) == 3
    assert wf_esec3[-1][1] == {"lavoro": "4"}

    # Passo 6: verifica del segno e assenza di comandi nei commenti dei giri (B3-R1, B3-R2, B3-R3)
    for num_iss, comms in forgia._commenti.items():
        for c in comms:
            assert ruolo(c.corpo) is not None, f"Commento su issue/PR {num_iss} senza segno: {c.corpo!r}"
            cmd = comando(c.corpo, autore=c.autore, comandanti=cfg.progetto.comandanti)
            assert cmd is None, f"Commento su issue/PR {num_iss} contiene un comando vietato: {c.corpo!r}"

    for num_pr, pr_info in forgia._pr.items():
        assert ruolo(pr_info["corpo"]) is not None, f"PR {num_pr} senza segno: {pr_info['corpo']!r}"


def test_giro_completo_review_focus_1_patch_github(tmp_path: Path) -> None:
    """Review Focus 1: patch che tocca .github/ -> niente spinta (l'origine non ha il ramo), lavoro bloccato."""
    origin, clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione_due_botteghe()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 11, 0, tzinfo=timezone.utc)

    iss = Issue(
        numero=10,
        titolo="Modifica CI",
        corpo="Aggiunge workflow.\n\n## Fatto quando\n```bash\ntest -f .github/workflows/test.yml\n```\n",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=10, titolo="Modifica CI", stato="pronto", etichette=["bottega: fuori"])])

    def callback_vietata(cartella: Path | str, prompt: str, **kwargs) -> Lancio:
        gh_dir = Path(cartella) / ".github" / "workflows"
        gh_dir.mkdir(parents=True, exist_ok=True)
        (gh_dir / "test.yml").write_text("name: Test\n", encoding="utf-8")
        return Lancio(esito="fatto", testo="Aggiunto file in .github")

    porta = PortaFintaCompleta(callback=callback_vietata)
    esito = giro(
        lavoro=10,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=random.Random(1),
    )

    assert esito.esito == "bloccato"
    assert esito.motivo == "modifica a .github vietata"
    assert board.lavoro(10).stato == "bloccato"

    # L'origine non ha il ramo della consegna
    res_b = subprocess.run(["git", "branch", "--list"], cwd=str(origin), capture_output=True, text=True)
    assert "bottega/10-modifica-ci" not in res_b.stdout

    # Commento dell'esecutore col motivo del rifiuto
    comms = forgia.commenti(10)
    assert any("Consegna rifiutata: la patch tocca percorsi sotto .github/" in c.corpo for c in comms)


def test_giro_completo_review_focus_2_due_distribuisci_consecutivi(tmp_path: Path) -> None:
    """Review Focus 2: due distribuisci di fila -> nessun lavoro preso due volte, nessun workflow duplicato."""
    _origin, _clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione_due_botteghe()
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    iss = Issue(
        numero=20,
        titolo="Compito Unico",
        corpo="Brief.\n\n## Fatto quando\n```bash\ntest -f ok.txt\n```\n",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=20, titolo="Compito Unico", stato="pronto", etichette=["bottega: fuori"])])

    righe_1 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )
    righe_2 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso + timedelta(seconds=5),
        caso=random.Random(1),
        notte=False,
    )

    assert any("assegnato a «esecutore»" in r for r in righe_1)
    assert len(righe_2) == 0  # Nessun lavoro assegnato nel secondo giro

    wf = [w for w in forgia._workflow_avviati if w[0] == "bottega-esecutore-b_abbondante.yml"]
    assert len(wf) == 1
    assert wf[0][1] == {"lavoro": "20"}
    assert board.lavoro(20).stato == "in corso"


def test_giro_completo_review_focus_3_quota_esaurita_e_ripresa(tmp_path: Path) -> None:
    """Review Focus 3: quota esaurita a metà tappa -> variabile scritta, salvataggio spinto, ripresa con conversazione."""
    origin, clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione_due_botteghe()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 13, 0, tzinfo=timezone.utc)

    madre = Issue(numero=30, titolo="Tappa Quota", corpo="Descrizione tappa.", stato="OPEN", etichette=["bottega: fuori"])
    sotto1 = Issue(
        numero=31,
        titolo="Compito Parziale",
        corpo="Crea finale.txt.\n\n## Fatto quando\n```bash\ntest -f finale.txt\n```\n",
        stato="OPEN",
    )
    forgia = ForgiaFinta(issues=[madre, sotto1])
    forgia._sotto_issue[30] = [31]
    board = BoardFinta(lavori=[Lavoro(numero=30, titolo="Tappa Quota", stato="pronto", etichette=["bottega: fuori"])])

    id_conversazione = "conv-quota-30"
    rinnovo_previsto = adesso + timedelta(hours=2)

    # 1. Giro interrotto da quota esaurita: committa lavoro parziale prima di esaurire la quota
    def callback_quota(cartella: Path | str, prompt: str, conversazione: str | None = None, **kwargs) -> Lancio:
        p_cartella = Path(cartella)
        (p_cartella / "parziale.txt").write_text("lavoro preliminare salvato\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "salvataggio intermedio"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(
            esito="quota",
            testo="Quota consumata",
            conversazione=id_conversazione,
            rinnovo=rinnovo_previsto,
        )

    porta = PortaFintaCompleta(callback=callback_quota)
    esito_quota = giro(
        lavoro=30,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=random.Random(1),
    )

    assert esito_quota.esito == "quota"

    # Variabile di quota impostata
    var_nome = nome_variabile("b_abbondante")
    assert var_nome in forgia._variabili
    assert forgia._variabili[var_nome].startswith("esaurita fino a ")

    # Salvataggio spinto su origin e PR aperta
    ramo_quota = "bottega/30-tappa-quota"
    res_b = subprocess.run(["git", "branch", "--list"], cwd=str(origin), capture_output=True, text=True)
    assert ramo_quota in res_b.stdout

    pr_num = forgia.pr_del_ramo(ramo_quota)
    assert pr_num is not None
    assert "Salvataggio parziale per quota esaurita" in forgia._pr[pr_num]["corpo"]

    # Stato della board torna a pronto con conversazione (RV8: attese la cresce solo il distributore)
    lav = board.lavoro(30)
    assert lav.stato == "pronto"
    assert f"conversazione={id_conversazione}" in lav.nota

    # 2. Giro di ripresa: dopo il rinnovo della quota, passa la conversazione memorizzata
    conversazione_ricevuta = False

    def callback_ripresa(cartella: Path | str, prompt: str, conversazione: str | None = None, **kwargs) -> Lancio:
        nonlocal conversazione_ricevuta
        if conversazione == id_conversazione:
            conversazione_ricevuta = True
        p_cartella = Path(cartella)
        (p_cartella / "finale.txt").write_text("tutto completato\n", encoding="utf-8")
        return Lancio(esito="fatto", testo="Completato dopo ripresa")

    porta.callback = callback_ripresa
    esito_ripresa = giro(
        lavoro=30,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(hours=3),
        caso=random.Random(1),
    )

    assert esito_ripresa.esito == "consegnato"
    assert conversazione_ricevuta is True
    assert board.lavoro(30).stato == "consegnato"


def test_giro_completo_review_focus_4_porta_non_risponde(tmp_path: Path) -> None:
    """Review Focus 4: porta che non risponde -> lavoro non toccato, avviso unico dopo due giri, chiuso al ripristino."""
    _origin, clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione_due_botteghe()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)

    iss = Issue(
        numero=40,
        titolo="Compito con Porta Giu",
        corpo="Brief.\n\n## Fatto quando\n```bash\ntest -f fine.txt\n```\n",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=40, titolo="Compito con Porta Giu", stato="pronto", etichette=["bottega: fuori"])])

    porta = PortaFintaCompleta(esito_controllo=False, motivo_controllo="CLI assente o servizio irraggiungibile")

    # Primo giro: porta fallisce il controllo
    esito_1 = giro(
        lavoro=40,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=random.Random(1),
    )
    assert esito_1.esito == "porta_non_pronta"
    assert board.lavoro(40).stato == "pronto"

    avvisi_1 = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi_1) == 1
    num_avviso = avvisi_1[0].numero
    assert "CLI assente o servizio irraggiungibile" in avvisi_1[0].corpo

    # Secondo giro: porta ancora non pronta con lo stesso motivo -> un solo avviso, nessun commento duplicato
    esito_2 = giro(
        lavoro=40,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=10),
        caso=random.Random(1),
    )
    assert esito_2.esito == "porta_non_pronta"
    assert board.lavoro(40).stato == "pronto"

    avvisi_2 = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi_2) == 1
    assert avvisi_2[0].numero == num_avviso
    assert len(forgia.commenti(num_avviso)) == 0  # Nessun commento ridondante

    # Terzo giro: porta ripristinata e controllo ok -> lavoro consegnato e avviso chiuso
    porta.esito_controllo = True
    porta.motivo_controllo = None

    def callback_ok(cartella: Path | str, prompt: str, **kwargs) -> Lancio:
        (Path(cartella) / "fine.txt").write_text("fatto\n", encoding="utf-8")
        return Lancio(esito="fatto", testo="Consegna eseguita")

    porta.callback = callback_ok

    esito_3 = giro(
        lavoro=40,
        bottega="b_abbondante",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso + timedelta(minutes=20),
        caso=random.Random(1),
    )
    assert esito_3.esito == "consegnato"
    assert board.lavoro(40).stato == "consegnato"
    # L'avviso della porta è chiuso al primo controllo buono
    assert forgia.issue(num_avviso).stato == "CLOSED"
