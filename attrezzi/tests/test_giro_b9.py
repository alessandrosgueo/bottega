"""Prove del giro B9.4: l'oracolo rosso non chiude il compito (B9-R4) e la domanda è una riga, non la coda (B9-R5)."""

from datetime import datetime, timezone
from pathlib import Path
import random
import subprocess

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega import giro as modulo_giro
from bottega.giro import domanda_del_consulto, giro
from bottega.porte import Controllo, Lancio
from bottega.segni import nota, scrivi_nota

RAMO_TAPPA = "bottega/1-tappa-con-due-compiti"
RAMO_SCIOLTO = "bottega/1-compito-sciolto"
ADESSO = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


class PortaFinta:
    """Porta finta: il callback fa il lavoro dell'esecutore; il consigliere (sola lettura) non risponde `RISPOSTA`."""

    def __init__(self, callback=None) -> None:
        self.nome = "finta"
        self.eseguibile = "finta"
        self.callback = callback
        self.lanci: list[dict] = []

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True, versione="1.0")

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
        self.lanci.append({"cartella": Path(cartella), "prompt": prompt, "sola_lettura": sola_lettura})
        if sola_lettura:
            return Lancio(esito="fatto", testo="A CHI DECIDE: serve una scelta del comandante")
        if self.callback is not None:
            return self.callback(cartella, prompt, conversazione=conversazione)
        return Lancio(esito="fatto", testo="fatto")

    def lanci_esecutore(self) -> list[dict]:
        return [lancio for lancio in self.lanci if not lancio["sola_lettura"]]


def _crea_ambiente_git(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    clone = tmp_path / "progetto"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"], cwd=str(clone), check=True, capture_output=True
    )
    (clone / "docs").mkdir()
    (clone / "docs" / "costituzione.md").write_text("# Costituzione\nRegole del repo.\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "primo commit"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)
    return origin, clone


def _crea_configurazione() -> Configurazione:
    progetto = Progetto(
        comandanti=("maestro",), adattatore=None, fuso="UTC", notte=None, manutenzione=(), project=1
    )
    botteghe = {"principale": Bottega(id="principale", quota="abbondante", porte=("finta",))}
    candidati = {
        "esecutore": Candidato(
            id="esecutore", nome="Esecutore Finto", bottega="principale", porta="finta", modello="finto-1",
            funzioni=("eseguire",), runner="linux-x64",
        ),
        "consigliere": Candidato(
            id="consigliere", nome="Consigliere Finto", bottega="principale", porta="finta",
            modello="finto-consigliere", funzioni=("consigliare",), runner="linux-x64",
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def _committa(cartella: Path | str, nome_file: str, contenuto: str = "x\n") -> None:
    (Path(cartella) / nome_file).write_text(contenuto, encoding="utf-8")
    subprocess.run(["git", "add", nome_file], cwd=str(cartella), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"aggiunge {nome_file}"], cwd=str(cartella), check=True, capture_output=True)


def _brief(comando: str) -> str:
    return f"Brief del compito.\n\n## Fatto quando\n```bash\n{comando}\n```\n"


def _tappa_con_due_compiti() -> tuple[ForgiaFinta, BoardFinta]:
    """Una tappa (madre 1) con due sotto-issue: l'oracolo del primo è `test -f corretto.txt`."""
    madre = Issue(numero=1, titolo="Tappa con due compiti", corpo="Descrizione della tappa.", stato="OPEN")
    primo = Issue(numero=2, titolo="Primo compito", corpo=_brief("test -f corretto.txt"), stato="OPEN")
    secondo = Issue(numero=3, titolo="Secondo compito", corpo=_brief("test -f secondo.txt"), stato="OPEN")
    forgia = ForgiaFinta(issues=[madre, primo, secondo])
    forgia._sotto_issue[1] = [2, 3]
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Tappa con due compiti", stato="pronto")])
    return forgia, board


def _lavoro_sciolto(comando: str) -> tuple[ForgiaFinta, BoardFinta]:
    iss = Issue(numero=1, titolo="Compito sciolto", corpo=_brief(comando), stato="OPEN")
    return ForgiaFinta(issues=[iss]), BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito sciolto", stato="pronto")])


def _giro(tmp_path: Path, clone: Path, forgia: ForgiaFinta, board: BoardFinta, porta: PortaFinta, minuti: int = 0):
    return giro(
        lavoro=1,
        bottega="principale",
        configurazione=_crea_configurazione(),
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=ADESSO.replace(minute=minuti),
        caso=random.Random(7),
    )


def _rilanci_distributore(forgia: ForgiaFinta) -> int:
    return sum(1 for file, _ in forgia._workflow_avviati if file == "bottega-distributore.yml")


def _consegne_in_board(board: BoardFinta) -> list[tuple]:
    return [r for r in board.registro if r[0] == "consegna"]


# --- B9-R4: l'oracolo rosso ---------------------------------------------------------------------------------------


def test_oracolo_rosso_al_primo_tentativo_non_chiude_il_compito(tmp_path: Path) -> None:
    """RED sul codice di oggi: il compito 2 risulta CLOSED e il lavoro è `pronto` senza `tentativi`."""
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _tappa_con_due_compiti()
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])

    esito = _giro(tmp_path, clone, forgia, board, porta)

    assert (esito.esito, esito.motivo, esito.oracolo_ok) == ("errore", "oracolo rosso", False)
    assert esito.pr is not None
    # La PR esiste, il commento col suo esito pure: la consegna resta visibile.
    assert forgia.pr_del_ramo(RAMO_TAPPA) == esito.pr
    assert "ROSSO" in forgia._pr[esito.pr]["corpo"]
    assert any("Esito dell'oracolo: ROSSO" in c.corpo for c in forgia.commenti(2))
    # Il compito resta aperto, il secondo non parte, il lavoro non è consegnato.
    assert forgia.issue(2).stato == "OPEN"
    assert forgia.issue(3).stato == "OPEN"
    assert len(porta.lanci_esecutore()) == 1
    assert _consegne_in_board(board) == []
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_nota = nota(lav.nota)
    assert d_nota["tentativi"] == "1"
    assert d_nota["motivo"] == "oracolo rosso"
    assert "consegnato" not in d_nota
    # Il distributore è rilanciato.
    assert _rilanci_distributore(forgia) == 1
    # La consegna rossa è sul ramo remoto: il giro dopo parte da lì.
    sul_ramo = subprocess.run(
        ["git", "show", f"{RAMO_TAPPA}:file.txt"], cwd=str(_origin), capture_output=True, text=True, check=False
    )
    assert sul_ramo.returncode == 0


def test_oracolo_rosso_al_terzo_tentativo_blocca(tmp_path: Path) -> None:
    """RED sul codice di oggi: il compito si chiude e il lavoro non è `bloccato`."""
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _tappa_con_due_compiti()
    board.stato(1, "pronto", nota=scrivi_nota({"ramo": RAMO_TAPPA, "compito": "2", "tentativi": "2"}))
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])

    esito = _giro(tmp_path, clone, forgia, board, porta)

    assert (esito.esito, esito.oracolo_ok) == ("bloccato", False)
    assert forgia.issue(2).stato == "OPEN"
    assert _consegne_in_board(board) == []
    assert board.lavoro(1).stato == "bloccato"
    d_nota = nota(board.lavoro(1).nota)
    assert d_nota["tentativi"] == "3"
    assert d_nota["motivo"] == "oracolo rosso"
    assert "consegnato" not in d_nota
    testi = [c.corpo for c in forgia.commenti(2)]
    assert any("oracolo rosso tre volte" in t and "serve chi decide" in t for t in testi)
    assert _rilanci_distributore(forgia) == 1  # come gli altri lavori bloccati


def test_rosso_poi_verde_il_secondo_giro_riparte_dalla_consegna_rossa(tmp_path: Path) -> None:
    """RED sul codice di oggi: il compito 2 è già chiuso dopo il primo giro, il secondo giro prende il compito 3."""
    origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _tappa_con_due_compiti()
    visto_dal_secondo: dict[str, object] = {}

    def primo_giro(cartella, prompt, **kw):
        _committa(cartella, "file.txt", "consegna rossa\n")
        return Lancio("fatto", "primo rapporto")

    porta = PortaFinta(callback=primo_giro)
    esito1 = _giro(tmp_path, clone, forgia, board, porta, minuti=0)
    assert (esito1.esito, esito1.oracolo_ok) == ("errore", False)
    assert board.lavoro(1).stato == "pronto"

    def secondo_giro(cartella, prompt, **kw):
        radice = Path(cartella)
        visto_dal_secondo["file_di_prima"] = (radice / "file.txt").read_text(encoding="utf-8")
        visto_dal_secondo["commenti"] = (radice / ".bottega" / "fascicolo" / "commenti.md").read_text(encoding="utf-8")
        visto_dal_secondo["brief"] = (radice / ".bottega" / "fascicolo" / "brief.md").read_text(encoding="utf-8")
        _committa(cartella, "corretto.txt")
        return Lancio("fatto", "correzione fatta")

    porta.callback = secondo_giro
    esito2 = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    # L'esecutore ha trovato la consegna rossa sul ramo e l'esito dell'oracolo fra i commenti del fascicolo.
    assert visto_dal_secondo["file_di_prima"] == "consegna rossa\n"
    assert "Esito dell'oracolo: ROSSO" in str(visto_dal_secondo["commenti"])
    assert "corretto.txt" in str(visto_dal_secondo["brief"])
    # Il secondo giro è verde: il compito si chiude, i tentativi si azzerano, la tappa va avanti.
    assert (esito2.esito, esito2.oracolo_ok) == ("consegnato", True)
    assert forgia.issue(2).stato == "CLOSED"
    assert forgia.issue(3).stato == "OPEN"
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_nota = nota(lav.nota)
    assert "tentativi" not in d_nota
    assert "consegnato" not in d_nota
    assert _consegne_in_board(board) == []
    # Stessa PR, con l'esito verde commentato.
    assert len(forgia._pr) == 1
    assert any("VERDE" in c.corpo for c in forgia.commenti(esito2.pr))
    # Il ramo remoto ha tutte e due le consegne.
    for nome_file in ("file.txt", "corretto.txt"):
        assert subprocess.run(
            ["git", "show", f"{RAMO_TAPPA}:{nome_file}"], cwd=str(origin), capture_output=True, check=False
        ).returncode == 0


def test_rosso_senza_commit_nel_giro_dopo_non_riprende_dall_oracolo(tmp_path: Path) -> None:
    """Dopo un rosso la chiave `consegnato` non c'è: un giro dopo senza commit nuovi conta «nessun commit» (non
    riprende dall'oracolo e non chiude un compito rosso). Al terzo tentativo complessivo il lavoro è bloccato."""
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _tappa_con_due_compiti()
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])
    _giro(tmp_path, clone, forgia, board, porta, minuti=0)

    porta.callback = lambda cartella, prompt, **kw: Lancio("fatto", "non so che correggere")
    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    assert (esito.esito, esito.motivo) == ("pronto", "nessun commit")
    assert forgia.issue(2).stato == "OPEN"
    assert nota(board.lavoro(1).nota)["tentativi"] == "2"
    assert _consegne_in_board(board) == []


def test_oracolo_rosso_senza_sotto_issue_non_consegna(tmp_path: Path) -> None:
    """RED sul codice di oggi: `board.consegna` è chiamato e il lavoro risulta `consegnato`."""
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _lavoro_sciolto("false")
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])

    esito = _giro(tmp_path, clone, forgia, board, porta)

    assert (esito.esito, esito.motivo, esito.oracolo_ok) == ("errore", "oracolo rosso", False)
    assert esito.pr is not None
    assert _consegne_in_board(board) == []
    lav = board.lavoro(1)
    assert lav.stato == "pronto"
    d_nota = nota(lav.nota)
    assert d_nota["tentativi"] == "1"
    assert d_nota["motivo"] == "oracolo rosso"
    assert "consegnato" not in d_nota
    assert _rilanci_distributore(forgia) == 1


def test_oracolo_rosso_senza_sotto_issue_al_terzo_blocca(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _lavoro_sciolto("false")
    board.stato(1, "pronto", nota=scrivi_nota({"ramo": RAMO_SCIOLTO, "compito": "1", "tentativi": "2"}))
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])

    esito = _giro(tmp_path, clone, forgia, board, porta)

    assert esito.esito == "bloccato"
    assert board.lavoro(1).stato == "bloccato"
    assert any("oracolo rosso tre volte" in c.corpo for c in forgia.commenti(1))
    assert _consegne_in_board(board) == []
    assert _rilanci_distributore(forgia) == 1  # come gli altri lavori bloccati


def test_ripresa_dopo_caduta_nell_oracolo_rosso_non_si_perde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B7-2 e B9-R4: un giro caduto dopo la consegna (nota `consegnato`) riprende dall'oracolo; se è rosso il compito
    non si chiude e il lavoro torna all'esecutore con un tentativo in più."""
    origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _lavoro_sciolto("test -f corretto.txt")
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "fatto"))[1])
    # Primo giro: l'oracolo si simula caduto prima dell'esito, lasciando la nota `consegnato` e il ramo spinto.
    originale = modulo_giro.esegui_oracolo

    def oracolo_caduto(*args, **kwargs):
        raise RuntimeError("giro caduto nell'oracolo")

    monkeypatch.setattr(modulo_giro, "esegui_oracolo", oracolo_caduto)
    esito_caduto = _giro(tmp_path, clone, forgia, board, porta, minuti=0)
    monkeypatch.setattr(modulo_giro, "esegui_oracolo", originale)
    assert "consegnato" in nota(board.lavoro(1).nota)
    assert esito_caduto.esito == "errore"

    # Secondo giro: nessun commit nuovo, la ripresa va all'oracolo, che è rosso.
    porta.callback = lambda cartella, prompt, **kw: Lancio("fatto", "niente da aggiungere")
    esito = _giro(tmp_path, clone, forgia, board, porta, minuti=10)

    assert (esito.esito, esito.motivo, esito.oracolo_ok) == ("errore", "oracolo rosso", False)
    assert _consegne_in_board(board) == []
    d_nota = nota(board.lavoro(1).nota)
    assert "consegnato" not in d_nota
    assert board.lavoro(1).stato == "pronto"
    assert subprocess.run(
        ["git", "show", f"{RAMO_SCIOLTO}:file.txt"], cwd=str(origin), capture_output=True, check=False
    ).returncode == 0


# --- B9-R5: la domanda è una riga --------------------------------------------------------------------------------

DOMANDA_IN_TESTA = (
    "DOMANDA PER CHI DECIDE: quale dei due file devo toccare?\n"
    "\n"
    "Il brief dice di aggiungere la funzione, ma il modulo esiste già in due posti e non so quale sia quello giusto.\n"
    "\n"
    "Ho provato a leggere la costituzione e non lo dice.\n"
    "\n"
    "Opzioni:\n"
    "- A: modifico il modulo vecchio\n"
    "- B: modifico il modulo nuovo\n"
)


def _giro_con_rapporto(tmp_path: Path, testo: str, *, commit: bool = False):
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _lavoro_sciolto("true")

    def callback(cartella, prompt, **kw):
        if commit:
            _committa(cartella, "file.txt")
        return Lancio("fatto", testo)

    porta = PortaFinta(callback=callback)
    esito = _giro(tmp_path, clone, forgia, board, porta)
    return esito, forgia, board, porta


def test_domanda_in_testa_al_rapporto_e_un_consulto(tmp_path: Path) -> None:
    """RED sul codice di oggi: l'ultima riga è un'opzione, il giro conta «nessun commit» e nessuna domanda parte."""
    esito, forgia, board, porta = _giro_con_rapporto(tmp_path, DOMANDA_IN_TESTA)

    assert esito.esito == "in_attesa"
    consulti = [c for c in forgia.commenti(1) if "Consulto dell'esecutore:" in c.corpo]
    assert len(consulti) == 1
    consigliere = next(lancio for lancio in porta.lanci if lancio["sola_lettura"])
    domanda = consigliere["prompt"].split("\n\n", 1)[1]
    assert domanda.startswith("DOMANDA PER CHI DECIDE: quale dei due file devo toccare?")
    assert "- A: modifico il modulo vecchio" in domanda
    assert "- B: modifico il modulo nuovo" in domanda
    assert board.lavoro(1).stato == "in attesa"
    assert "tentativi" not in nota(board.lavoro(1).nota)


def test_domanda_in_grassetto_e_un_consulto(tmp_path: Path) -> None:
    """RED sul codice di oggi: la riga comincia con `**`, non col segno."""
    testo = "**DOMANDA PER CHI DECIDE:** posso cambiare il formato?\n\nPer ora non ho toccato niente.\n- A: sì\n- B: no\n"
    esito, forgia, _board, porta = _giro_con_rapporto(tmp_path, testo)

    assert esito.esito == "in_attesa"
    assert len([c for c in forgia.commenti(1) if "Consulto dell'esecutore:" in c.corpo]) == 1
    consigliere = next(lancio for lancio in porta.lanci if lancio["sola_lettura"])
    domanda = consigliere["prompt"].split("\n\n", 1)[1]
    assert domanda.startswith("DOMANDA PER CHI DECIDE: posso cambiare il formato?")
    assert "- B: no" in domanda


def test_segno_citato_a_meta_riga_non_e_un_consulto(tmp_path: Path) -> None:
    """Guardia (verde anche sul codice di oggi: il vecchio giro non riconosceva il segno a metà riga): impedisce che
    B9-R5 lo cerchi ovunque nel testo."""
    testo = (
        "Ho letto il fascicolo: se serve, chiudi con `DOMANDA PER CHI DECIDE:` e una domanda precisa.\n"
        "Non serviva, ho fatto tutto.\n"
        "Rapporto: file.txt aggiunto, oracolo verde."
    )
    esito, forgia, _board, porta = _giro_con_rapporto(tmp_path, testo, commit=True)

    assert esito.esito == "consegnato"
    assert [c for c in forgia.commenti(1) if "Consulto dell'esecutore:" in c.corpo] == []
    assert [lancio for lancio in porta.lanci if lancio["sola_lettura"] and "Rispondi al consulto" in lancio["prompt"]] == []


@pytest.mark.parametrize(
    ("testo", "atteso"),
    [
        ("DOMANDA PER CHI DECIDE: una\n\ndue\n", "DOMANDA PER CHI DECIDE: una\n\ndue"),
        ("  ** DOMANDA PER CHI DECIDE: indentata", "DOMANDA PER CHI DECIDE: indentata"),
        ("**DOMANDA PER CHI DECIDE:** in grassetto", "DOMANDA PER CHI DECIDE: in grassetto"),
        ("Prima.\nDOMANDA PER CHI DECIDE: vecchia\nPoi.\nDOMANDA PER CHI DECIDE: nuova\nfine", "DOMANDA PER CHI DECIDE: nuova\nfine"),
        ("Cito `DOMANDA PER CHI DECIDE:` a metà riga.", None),
        ("domanda per chi decide: minuscolo", None),
        ("Nessuna domanda.\n", None),
        ("", None),
    ],
)
def test_domanda_del_consulto(testo: str, atteso: str | None) -> None:
    assert domanda_del_consulto(testo) == atteso
