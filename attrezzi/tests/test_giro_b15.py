"""Prove B15 del giro: scala, bozze di piano, passo finale, punti quota e misure gradino."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import subprocess

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto, Ritmo
from bottega.conti import conti
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import giro
import bottega.misure as misure
from bottega.porte import Controllo, Lancio
from bottega.quota import PuntoQuota, leggi_punti, nome_variabile_punti
from bottega.segni import nota, scrivi_nota

ADESSO = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


class _PortaFinta:
    """Porta finta configurabile con supporto opzionale a `leggi_quota`."""

    nome = "finta"
    eseguibile = "finta"

    def __init__(self, callback, *, quote_sequenza: list[dict[str, PuntoQuota]] | None = None) -> None:
        self._callback = callback
        self._quote_sequenza = list(quote_sequenza or [])
        self.lanci: list[dict] = []

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True, versione="1.0")

    def leggi_quota(self, prefisso=(), tempo: int | float = 60) -> dict[str, PuntoQuota] | None:
        if not self._quote_sequenza:
            return None
        if len(self._quote_sequenza) > 1:
            return self._quote_sequenza.pop(0)
        return self._quote_sequenza[0]

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
        })
        return self._callback(
            cartella,
            prompt,
            modello=modello,
            conversazione=conversazione,
            sola_lettura=sola_lettura,
        )


def _crea_repo(tmp_path: Path) -> tuple[Path, Path]:
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
    (clone / "docs").mkdir()
    (clone / "docs" / "costituzione.md").write_text("# Costituzione\n", encoding="utf-8")
    (clone / "test_base.py").write_text("def test_base(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "primo commit"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)
    return origin, clone


def _committa(cartella: Path | str, nome_file: str, contenuto: str = "ok\n", msg: str | None = None) -> None:
    p = Path(cartella) / nome_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenuto, encoding="utf-8")
    subprocess.run(["git", "add", nome_file], cwd=str(cartella), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", msg or f"aggiunge {nome_file}"],
        cwd=str(cartella),
        check=True,
        capture_output=True,
    )


def _cfg(
    *,
    scala: tuple[str, ...] = (),
    categorie: dict[str, tuple[str, ...]] | None = None,
    con_consigliere: bool = False,
    con_revisore: bool = False,
    revisore_anche_consigliere: bool = False,
    con_pianificatore: bool = False,
) -> Configurazione:
    progetto = Progetto(
        comandanti=("maestro",),
        adattatore=None,
        fuso="UTC",
        notte=None,
        manutenzione=(),
        project=1,
        scala=scala,
    )
    botteghe = {"principale": Bottega(id="principale", quota="abbondante", porte=("finta",))}
    candidati: dict[str, Candidato] = {
        "c1": Candidato(
            id="c1",
            nome="Cand 1",
            bottega="principale",
            porta="finta",
            modello="modello-1",
            funzioni=("eseguire",),
            runner="linux",
        ),
        "c2": Candidato(
            id="c2",
            nome="Cand 2",
            bottega="principale",
            porta="finta",
            modello="modello-2",
            funzioni=("eseguire",),
            runner="linux",
            riserva=True,
        ),
    }
    if con_consigliere and not revisore_anche_consigliere:
        candidati["consigliere"] = Candidato(
            id="consigliere",
            nome="Consigliere",
            bottega="principale",
            porta="finta",
            modello="modello-cons",
            funzioni=("consigliare",),
            runner="linux",
        )
    if con_revisore:
        funz = ("consigliare", "rivedere") if revisore_anche_consigliere else ("rivedere",)
        candidati["revisore"] = Candidato(
            id="revisore",
            nome="Revisore",
            bottega="principale",
            porta="finta",
            modello="modello-rev",
            funzioni=funz,
            runner="linux",
        )
    if con_pianificatore:
        candidati["pianificatore"] = Candidato(
            id="pianificatore",
            nome="Pianificatore",
            bottega="principale",
            porta="finta",
            modello="modello-plan",
            funzioni=("pianificare",),
            runner="linux",
        )
    return Configurazione(
        versione=1,
        progetto=progetto,
        botteghe=botteghe,
        candidati=candidati,
        categorie=categorie or {},
        ritmo=Ritmo(gruppo="Gemini Models"),
    )


def test_oracolo_rosso_sale_di_gradino_e_poi_blocca_a_scala_esaurita(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"))
    iss = Issue(numero=1, titolo="Compito Scala", corpo="Brief\n\n## Fatto quando\n```\ntest -f giusto.txt\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Compito Scala",
            stato="pronto",
            nota="gradino=0; precedente=c1; conversazione=conv-1",
        )
    ])
    board.prendi(1, "Cand 1", board.lavoro(1).nota)

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, "sbagliato.txt")
        return Lancio(esito="fatto", testo="tentativo 1", conversazione="conv-1")

    porta = _PortaFinta(cb)
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp1",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito1.oracolo_ok is False
    lav1 = board.lavoro(1)
    assert lav1 is not None
    assert lav1.stato == "pronto"
    d1 = nota(lav1.nota)
    assert d1.get("gradino") == "1"
    assert "precedente" not in d1
    assert "conversazione" not in d1
    assert "rosso" in d1

    # Secondo giro al gradino 1 (c2) fallisce ancora l'oracolo -> scala esaurita -> bloccato
    assert board.prendi(1, "Cand 2", lav1.nota)
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp2",
        prefisso=(),
        adesso=ADESSO + timedelta(minutes=10),
        caso=random.Random(1),
    )
    assert esito2.esito == "bloccato"
    lav2 = board.lavoro(1)
    assert lav2 is not None
    assert lav2.stato == "bloccato"
    assert "scala esaurita" in nota(lav2.nota).get("motivo", "")


def test_rilettura_con_rilievi_gravi_blocca_compito_e_sale_di_gradino(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"), con_consigliere=True)
    madre = Issue(numero=1, titolo="Tappa", corpo="Madre")
    s1 = Issue(numero=2, titolo="Sotto 1", corpo="Brief\n\n## Fatto quando\n```\ntest -f ok.txt\n```\n")
    s2 = Issue(numero=3, titolo="Sotto 2", corpo="Brief\n\n## Fatto quando\n```\ntest -f s2.txt\n```\n")
    forgia = ForgiaFinta([madre, s1, s2])
    forgia._sotto_issue[1] = [2, 3]
    board = BoardFinta([Lavoro(numero=1, titolo="Tappa", stato="pronto", nota="gradino=0")])

    def cb(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: RILIEVI_GRAVI\nGRAVI: 1\nMINORI: 0\n\nManca una guardia.")
        _committa(cartella, "ok.txt")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito != "consegnato"
    assert forgia.issue(2).stato == "OPEN"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "pronto"
    d = nota(lav.nota)
    assert d.get("gradino") == "1"
    assert "consegnato" not in d


def test_quota_esaurita_non_sale_di_gradino(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"))
    iss = Issue(numero=1, titolo="Compito Quota", corpo="Brief\n\n## Fatto quando\n```\ntrue\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Compito Quota", stato="pronto", nota="gradino=0")])

    porta = _PortaFinta(lambda cartella, prompt, **kw: Lancio(esito="quota", testo="429"))
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "quota"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "pronto"
    assert nota(lav.nota).get("gradino") == "0"


def test_esegue_non_usa_scala(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"))
    iss = Issue(
        numero=1,
        titolo="Compito Forzato",
        corpo="Brief\n\n## Fatto quando\n```\nfalse\n```\n",
        etichette=["esegue: c1"],
    )
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Compito Forzato", stato="pronto", etichette=["esegue: c1"])])

    n = 0

    def cb(cartella, prompt, **kwargs):
        nonlocal n
        n += 1
        _committa(cartella, f"f{n}.txt")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    for i in range(1, 4):
        esito = giro(
            lavoro=1,
            bottega="principale",
            configurazione=cfg,
            forgia=forgia,
            board=board,
            porte={"finta": porta},
            clone_progetto=clone,
            spazio=tmp_path / f"sp{i}",
            prefisso=(),
            adesso=ADESSO + timedelta(minutes=i),
            caso=random.Random(1),
        )
        lav = board.lavoro(1)
        assert lav is not None
        assert "gradino" not in nota(lav.nota)
        if i < 3:
            assert esito.esito == "errore"
            assert lav.stato == "pronto"
        else:
            assert esito.esito == "bloccato"
            assert lav.stato == "bloccato"


def test_bozza_di_piano_valida_apre_pr_in_bozza_senza_oracolo(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(con_pianificatore=True)
    iss = Issue(numero=1, titolo="Nuova feature", corpo="Descrizione senza Fatto quando.")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Nuova feature",
            stato="in corso",
            esecutore="Pianificatore",
            nota="modo=pianifica",
        )
    ])

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, "docs/plans/2026-11-26-issue-1-bozza.md", "# Bozza\n\n## Scopo\nTest.\n")
        return Lancio(esito="fatto", testo="bozza pronta")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "consegnato"
    assert esito.oracolo_ok is None
    assert esito.pr is not None
    assert forgia._pr[esito.pr]["titolo"].startswith("Bozza di piano: ")
    assert "bottega: bozza di piano" in forgia.etichette_pr(esito.pr)
    assert "bottega: bozza di piano" in forgia.issue(1).etichette
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "consegnato"
    assert not lav.esito
    assert not any("Esito dell'oracolo" in c.corpo for c in forgia.commenti(1))


def test_bozza_di_piano_con_codice_rifiutata(tmp_path: Path) -> None:
    origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(con_pianificatore=True)
    iss = Issue(numero=1, titolo="Feature codice", corpo="Idea senza Fatto quando.")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Feature codice",
            stato="in corso",
            esecutore="Pianificatore",
            nota="modo=pianifica",
        )
    ])

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, "app.py", "print('x')\n", msg="aggiunge app")
        subprocess.run(["git", "rm", "app.py"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "rimuove app"], cwd=str(cartella), check=True, capture_output=True)
        _committa(cartella, "docs/plans/2026-11-26-issue-1-bozza.md", "# Bozza\n")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "bloccato"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "bloccato"
    assert "bozza di piano fuori da docs/plans/" in nota(lav.nota).get("motivo", "")
    # Nessun ramo spinto su origin
    refs = subprocess.run(["git", "show-ref"], cwd=str(origin), capture_output=True, text=True, check=True).stdout
    assert "bottega/" not in refs


def test_passo_finale_pronta_non_delicata(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(categorie={"documenti": ("docs/**",)}, con_revisore=True)
    iss = Issue(numero=1, titolo="Aggiorna guida", corpo="Brief\n\n## Fatto quando\n```\ntest -f docs/guida.md\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Aggiorna guida", stato="pronto")])

    def cb(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 0\n\nOttimo.")
        _committa(cartella, "docs/guida.md", "# Guida\n")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "consegnato"
    assert esito.pr is not None
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.campi.get("Esito") == "pronta per l'unione"
    assert nota(lav.nota).get("categoria") == "non-delicata"
    assert "bottega: non delicata" in forgia.etichette_pr(esito.pr)
    assert any("<!-- bottega:revisore -->" in c.corpo for c in forgia.commenti(esito.pr))


def test_passo_finale_riuso_verdetto_stesso_candidato_compito_singolo(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(categorie={"documenti": ("docs/**",)}, con_revisore=True, revisore_anche_consigliere=True)
    iss = Issue(numero=1, titolo="Riuso", corpo="Brief\n\n## Fatto quando\n```\ntest -f docs/guida.md\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Riuso", stato="pronto")])

    def cb(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 0\n")
        _committa(cartella, "docs/guida.md", "# Guida\n")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "consegnato"
    sola_lettura_lanci = [l for l in porta.lanci if l["sola_lettura"]]
    assert len(sola_lettura_lanci) == 1
    assert board.lavoro(1).campi.get("Esito") == "pronta per l'unione"


def test_passo_finale_delicata_per_file_o_etichetta_o_sicurezza(tmp_path: Path) -> None:
    cfg = _cfg(categorie={"documenti": ("docs/**",)}, con_revisore=True)

    # Caso 1: file fuori [categorie]
    sub1 = tmp_path / "c1"
    sub1.mkdir()
    _origin1, clone1 = _crea_repo(sub1)
    forgia1 = ForgiaFinta([
        Issue(numero=1, titolo="Fuori cat", corpo="Brief\n\n## Fatto quando\n```\ntest -f src/app.py\n```\n")
    ])
    board1 = BoardFinta([Lavoro(numero=1, titolo="Fuori cat", stato="pronto")])

    def cb_fuori(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 0\n")
        _committa(cartella, "src/app.py", "x = 1\n")
        return Lancio(esito="fatto", testo="fatto")

    esito1 = giro(
        lavoro=1, bottega="principale", configurazione=cfg, forgia=forgia1, board=board1,
        porte={"finta": _PortaFinta(cb_fuori)}, clone_progetto=clone1, spazio=sub1 / "sp",
        prefisso=(), adesso=ADESSO, caso=random.Random(1),
    )
    assert esito1.pr is not None
    assert nota(board1.lavoro(1).nota).get("categoria") == "delicata"
    assert "bottega: delicata" in forgia1.etichette_pr(esito1.pr)

    # Caso 2: bottega: prove cambiate (test_base.py modificato anche con categoria prove)
    cfg2 = _cfg(categorie={"documenti": ("docs/**",), "prove": ("test_*.py",)}, con_revisore=True)
    sub2 = tmp_path / "c2"
    sub2.mkdir()
    _origin2, clone2 = _crea_repo(sub2)
    forgia2 = ForgiaFinta([
        Issue(numero=1, titolo="Prove cambiate", corpo="Brief\n\n## Fatto quando\n```\ntest -f test_base.py\n```\n")
    ])
    board2 = BoardFinta([Lavoro(numero=1, titolo="Prove cambiate", stato="pronto")])

    def cb_prove(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: APPROVATO\nGRAVI: 0\nMINORI: 0\n")
        _committa(cartella, "test_base.py", "def test_base(): assert True\n")
        return Lancio(esito="fatto", testo="fatto")

    esito2 = giro(
        lavoro=1, bottega="principale", configurazione=cfg2, forgia=forgia2, board=board2,
        porte={"finta": _PortaFinta(cb_prove)}, clone_progetto=clone2, spazio=sub2 / "sp",
        prefisso=(), adesso=ADESSO, caso=random.Random(1),
    )
    assert esito2.pr is not None
    assert "bottega: prove cambiate" in forgia2.etichette_pr(esito2.pr)
    assert nota(board2.lavoro(1).nota).get("categoria") == "delicata"
    assert "bottega: delicata" in forgia2.etichette_pr(esito2.pr)

    # Caso 3: VERDETTO: SICUREZZA -> delicata ed Esito vuoto
    sub3 = tmp_path / "c3"
    sub3.mkdir()
    _origin3, clone3 = _crea_repo(sub3)
    forgia3 = ForgiaFinta([
        Issue(numero=1, titolo="Sicurezza", corpo="Brief\n\n## Fatto quando\n```\ntest -f docs/guida.md\n```\n")
    ])
    board3 = BoardFinta([Lavoro(numero=1, titolo="Sicurezza", stato="pronto")])

    def cb_sic(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="VERDETTO: SICUREZZA\nGRAVI: 1\nMINORI: 0\n\nSegreto esposto.")
        _committa(cartella, "docs/guida.md", "# Guida\n")
        return Lancio(esito="fatto", testo="fatto")

    esito3 = giro(
        lavoro=1, bottega="principale", configurazione=cfg, forgia=forgia3, board=board3,
        porte={"finta": _PortaFinta(cb_sic)}, clone_progetto=clone3, spazio=sub3 / "sp",
        prefisso=(), adesso=ADESSO, caso=random.Random(1),
    )
    assert esito3.pr is not None
    assert nota(board3.lavoro(1).nota).get("categoria") == "delicata"
    assert "bottega: delicata" in forgia3.etichette_pr(esito3.pr)
    assert not board3.lavoro(1).campi.get("Esito")


def test_passo_finale_verdetto_non_valido_fail_closed(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(categorie={"documenti": ("docs/**",)}, con_revisore=True)
    iss = Issue(numero=1, titolo="Verdetto rotto", corpo="Brief\n\n## Fatto quando\n```\ntest -f docs/guida.md\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Verdetto rotto", stato="pronto")])

    def cb(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="Tutto ok ma senza intestazione richiesta.")
        _committa(cartella, "docs/guida.md", "# Guida\n")
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": _PortaFinta(cb)},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "consegnato"
    assert esito.pr is not None
    assert not board.lavoro(1).campi.get("Esito")
    assert any("verdetto non leggibile" in c.corpo for c in forgia.commenti(esito.pr))


def test_punti_quota_salvati_in_variabile_e_misura_gradino_registrata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"))
    iss = Issue(numero=1, titolo="Punti quota", corpo="Brief\n\n## Fatto quando\n```\ntest -f ok.txt\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Punti quota", stato="pronto", nota="gradino=0")])

    p_prima = {
        "Gemini Models": PuntoQuota(
            gruppo="Gemini Models",
            settimana=90,
            rinnovo_settimana=ADESSO + timedelta(days=3),
            cinque_ore=80,
            rinnovo_cinque_ore=ADESSO + timedelta(hours=2),
        )
    }
    p_dopo = {
        "Gemini Models": PuntoQuota(
            gruppo="Gemini Models",
            settimana=88,
            rinnovo_settimana=ADESSO + timedelta(days=3),
            cinque_ore=75,
            rinnovo_cinque_ore=ADESSO + timedelta(hours=2),
        )
    }

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, "ok.txt")
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 500})

    porta = _PortaFinta(cb, quote_sequenza=[p_prima, p_dopo])
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "consegnato"
    val_var = forgia.variabile(nome_variabile_punti("principale"))
    assert val_var is not None
    _ril, letti = leggi_punti(val_var)
    assert letti["Gemini Models"].settimana == 88
    assert letti["Gemini Models"].cinque_ore == 75

    lav = board.lavoro(1)
    assert lav is not None
    mp = lav.campi.get("Misure parziali", "")
    assert "gradino:c1:ok:500:" in mp
    assert "più esecutori" not in mp

    out = capsys.readouterr().out
    assert "misura gradino: candidato=c1; gradino=1/2;" in out
    assert "punti_settimana=2; punti_5h=5;" in out
    assert "oracolo=ok;" in out


def test_dopo_la_bozza_il_lavoro_col_fatto_quando_parte_normale(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(con_pianificatore=True)
    iss = Issue(numero=1, titolo="Feature", corpo="Descrizione senza Fatto quando.", autore="maestro")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Feature",
            stato="in corso",
            esecutore="Pianificatore",
            nota="modo=pianifica",
        )
    ])

    def cb(cartella, prompt, **kwargs):
        if "Sei il pianificatore" in prompt:
            _committa(cartella, "docs/plans/2026-11-26-issue-1-bozza.md", "# Bozza\n")
            return Lancio(esito="fatto", testo="bozza pronta")
        _committa(cartella, "ok.txt", "fatto\n")
        return Lancio(esito="fatto", testo="eseguito")

    porta = _PortaFinta(cb)
    esito_bozza = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp_bozza",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito_bozza.esito == "consegnato"
    lav_dopo_bozza = board.lavoro(1)
    assert lav_dopo_bozza is not None
    assert "modo" not in nota(lav_dopo_bozza.nota)

    # Anche con nota sporca lasciata a modo=pianifica, il distributore la ripulisce quando il lavoro ha Fatto quando.
    forgia._issues[2] = Issue(
        numero=2,
        titolo="Feature 2",
        corpo="Brief\n\n## Fatto quando\n```\ntest -f ok.txt\n```\n",
        etichette=["bottega: fuori"],
        autore="maestro",
    )
    board2 = BoardFinta([
        Lavoro(
            numero=2,
            titolo="Feature 2",
            stato="pronto",
            etichette=["bottega: fuori"],
            nota="modo=pianifica",
        )
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board2,
        variabili={},
        adesso=ADESSO,
        caso=random.Random(1),
    )
    lav_avviato = board2.lavoro(2)
    assert lav_avviato is not None
    assert lav_avviato.esecutore != "Pianificatore"
    assert "modo" not in nota(lav_avviato.nota)

    esito_normale = giro(
        lavoro=2,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board2,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp_normale",
        prefisso=(),
        adesso=ADESSO + timedelta(minutes=5),
        caso=random.Random(1),
    )
    assert esito_normale.esito == "consegnato"
    assert esito_normale.oracolo_ok is True


def test_un_attesa_poi_ok_dello_stesso_gradino_conta_una_volta(tmp_path: Path) -> None:
    _origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(scala=("c1", "c2"), con_consigliere=True)
    iss = Issue(numero=1, titolo="Consulto poi ok", corpo="Brief\n\n## Fatto quando\n```\ntest -f ok.txt\n```\n")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([Lavoro(numero=1, titolo="Consulto poi ok", stato="pronto", nota="gradino=0")])

    fase = {"turno": 1}

    def cb(cartella, prompt, sola_lettura=False, **kwargs):
        if sola_lettura:
            return Lancio(esito="fatto", testo="A CHI DECIDE\nServe scelta umana.")
        if fase["turno"] == 1:
            return Lancio(esito="fatto", testo="DOMANDA PER CHI DECIDE: Quale formato usare?")
        _committa(cartella, "ok.txt", "ok\n")
        return Lancio(esito="fatto", testo="fatto", contatori={"total_tokens": 250})

    porta = _PortaFinta(cb)
    esito1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp1",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito1.esito == "in_attesa"
    lav1 = board.lavoro(1)
    assert lav1 is not None
    assert nota(lav1.nota).get("gradino") == "0"
    assert "fallito" not in (lav1.campi.get("Misure parziali") or "")

    fase["turno"] = 2
    board.stato(1, "pronto", nota=lav1.nota)
    esito2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp2",
        prefisso=(),
        adesso=ADESSO + timedelta(minutes=10),
        caso=random.Random(1),
    )
    assert esito2.esito == "consegnato"
    board.campo(1, "Esito del compito", "unito com'era")
    lav2 = board.lavoro(1)
    assert lav2 is not None

    res = misure.risultati([lav2], cfg)[("c1", "*")]
    c_esiti = conti([lav2])["per_candidato"]["c1"]["esiti"]
    assert res == misure.Risultati(uniti=1, corretti=0, rifiutati=0)
    assert c_esiti == {"unito com'era": 1, "corretto": 0, "rifiutato": 0}


def test_bozza_con_percorso_con_spazio_rifiutata(tmp_path: Path) -> None:
    origin, clone = _crea_repo(tmp_path)
    cfg = _cfg(con_pianificatore=True)
    iss = Issue(numero=1, titolo="Bozza spazio", corpo="Idea senza Fatto quando.")
    forgia = ForgiaFinta([iss])
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Bozza spazio",
            stato="in corso",
            esecutore="Pianificatore",
            nota="modo=pianifica",
        )
    ])

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, " docs/plans/x.md", "# Bozza con spazio\n")
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(cb)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "sp",
        prefisso=(),
        adesso=ADESSO,
        caso=random.Random(1),
    )
    assert esito.esito == "bloccato"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "bloccato"
    assert "bozza di piano fuori da docs/plans/" in nota(lav.nota).get("motivo", "")
    refs = subprocess.run(["git", "show-ref"], cwd=str(origin), capture_output=True, text=True, check=True).stdout
    assert "bottega/" not in refs
