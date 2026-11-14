"""Prove di B14-R10: il fascicolo e i file del brief entrano nel prompt entro 96 KiB UTF-8 e senza uscire dalla copia."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import random
import subprocess

import pytest

from bottega.board import Lavoro
from bottega.brief import file_del_brief
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import componi_prompt_con_fascicolo, giro
from bottega.porte import Lancio

from test_giro_b9 import PortaFinta, _committa, _crea_ambiente_git, _crea_configurazione

TETTO_PROMPT = 96 * 1024


class _PortaConConsulto(PortaFinta):
    """Porta finta che inoltra anche i lanci in sola lettura al callback."""

    gestisce_sola_lettura = True

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
        if self.callback is not None:
            return self.callback(cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura)
        return Lancio(esito="fatto", testo="fatto")


def _giro_con_brief(
    tmp_path: Path,
    clone: Path,
    corpo_brief: str,
    *,
    titolo: str = "Compito Fascicolo",
    madre: Issue | None = None,
    commenti_madre: list[str] | None = None,
    commenti_compito: list[str] | None = None,
    callback_porta=None,
    bottega_clone: Path | None = None,
    monkeypatch=None,
) -> tuple[list[dict], Path]:
    cfg = _crea_configurazione()
    if bottega_clone is not None and monkeypatch is not None:
        monkeypatch.setenv("BOTTEGA_CLONE", str(bottega_clone))

    if madre is None:
        iss = Issue(numero=1, titolo=titolo, corpo=corpo_brief, autore="maestro")
        forgia = ForgiaFinta(issues=[iss])
        lavoro_num = 1
    else:
        iss = Issue(numero=2, titolo=titolo, corpo=corpo_brief, autore="maestro")
        forgia = ForgiaFinta(issues=[madre, iss])
        forgia._sotto_issue[madre.numero] = [iss.numero]
        lavoro_num = madre.numero

    for testo in commenti_madre or ():
        forgia.commenta(lavoro_num, testo, ruolo="esecutore")
    for testo in commenti_compito or ():
        forgia.commenta(iss.numero, testo, ruolo="consigliere")

    board = BoardFinta(lavori=[Lavoro(numero=lavoro_num, titolo=titolo, stato="pronto")])
    spazio = tmp_path / "spazio"

    def default_cb(cartella, prompt, **kwargs):
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="nessun rilievo")
        _committa(cartella, "fatto.txt")
        return Lancio(esito="fatto", testo="rapporto finale")

    porta = _PortaConConsulto(callback=callback_porta or default_cb)
    esito = giro(
        lavoro=lavoro_num,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"
    return porta.lanci_esecutore(), spazio


# --- Lettura della sezione ## File dal brief -----------------------------------------------------------------------


def test_file_del_brief_estrae_elenco_puntato_e_ignora_recinti() -> None:
    corpo = (
        "## Obiettivo\n\n"
        "- `non/questo.py`\n\n"
        "```markdown\n"
        "## File\n"
        "- `finto/nel_recinto.py`\n"
        "```\n\n"
        "## File\n\n"
        "- `attrezzi/bottega/giro.py`: da modificare\n"
        "  * `attrezzi/bottega/brief.py` (da imitare)\n"
        "+ `docs/costituzione.md`\n"
        "- `attrezzi/bottega/giro.py` duplicato\n"
        "- senza apici inversi\n\n"
        "## Fatto quando\n\n"
        "```bash\n"
        "true\n"
        "```\n"
    )
    assert file_del_brief(corpo) == [
        "attrezzi/bottega/giro.py",
        "attrezzi/bottega/brief.py",
        "docs/costituzione.md",
    ]


def test_file_del_brief_assente_o_vuota() -> None:
    assert file_del_brief("Solo testo.\n\n## Fatto quando\n```\ntrue\n```\n") == []
    assert file_del_brief("## File\n\nNessun elenco.\n\n## Fatto quando\n```\ntrue\n```\n") == []


# --- Fascicolo completo nel prompt e file invariati su disco --------------------------------------------------------


def test_fascicolo_entra_nel_prompt_in_ordine_e_resta_su_disco(tmp_path: Path, monkeypatch) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    bottega_clone = tmp_path / "bottega_clone"
    (bottega_clone / "quaderni").mkdir(parents=True)
    (bottega_clone / "quaderni" / "finto-1.md").write_text("Lezione comune finto-1.\n", encoding="utf-8")

    madre = Issue(numero=1, titolo="Tappa Madre", corpo="Corpo della madre della tappa.", autore="maestro")
    corpo = "Corpo del brief 2.\n\n## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    fascicolo_su_disco: dict[str, str] = {}

    def cb(cartella, prompt, **kwargs):
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="nessun rilievo")
        f_dir = Path(cartella) / ".bottega" / "fascicolo"
        for f in f_dir.iterdir():
            if f.is_file():
                fascicolo_su_disco[f.name] = f.read_text(encoding="utf-8")
        _committa(cartella, "fatto.txt")
        return Lancio(esito="fatto", testo="ok")

    lanci, _spazio = _giro_con_brief(
        tmp_path,
        clone,
        corpo,
        titolo="Sotto Compito",
        madre=madre,
        commenti_madre=["Nota sulla madre"],
        commenti_compito=["Consiglio sul compito"],
        callback_porta=cb,
        bottega_clone=bottega_clone,
        monkeypatch=monkeypatch,
    )
    prompt = lanci[0]["prompt"]

    # I sei file su disco restano invariati
    assert set(fascicolo_su_disco) == {
        "brief.md",
        "stato.md",
        "costituzione.md",
        "quaderno.md",
        "lavoro.md",
        "commenti.md",
    }

    # Istruzioni 1-6 e Fatto quando restano invariati
    assert "Fatto quando:\ntest -f fatto.txt" in prompt
    assert "Istruzioni:\n1. Lavora in questa cartella e committa nel ramo corrente" in prompt
    assert "6. Lavora in pochi passi:" in prompt

    # I sei pezzi appaiono dopo le istruzioni, nell'ordine esatto di R10
    pos_istruzioni = prompt.index("6. Lavora in pochi passi:")
    ordine = ["brief.md", "stato.md", "costituzione.md", "quaderno.md", "lavoro.md", "commenti.md"]
    posizioni = [prompt.index(f"### {nome}") for nome in ordine]
    assert posizioni[0] > pos_istruzioni
    assert posizioni == sorted(posizioni)

    assert "Corpo del brief 2." in prompt
    assert "Ramo: bottega/1-tappa-madre" in prompt
    assert "Regole del repo." in prompt
    assert "Lezione comune finto-1." in prompt
    assert "Corpo della madre della tappa." in prompt
    assert "Consiglio sul compito" in prompt


def test_recinto_sicuro_con_apici_nel_brief(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    blocco_interno = "````python\nprint('ciao')\n````"
    corpo = (
        f"Testo prima.\n\n{blocco_interno}\n\nTesto dopo apici.\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo)
    prompt = lanci[0]["prompt"]

    sez_brief = prompt.split("### brief.md\n\n", 1)[1].split("\n\n### stato.md", 1)[0]
    prima_riga = sez_brief.splitlines()[0]
    ultima_riga = sez_brief.splitlines()[-1]
    assert prima_riga == ultima_riga
    assert prima_riga.startswith("`````")  # almeno 5 apici perché il brief ne ha 4 consecutivi
    assert "Testo dopo apici." in sez_brief


# --- File del brief validi, mancanti, binari e > 40 KiB -------------------------------------------------------------


def test_file_del_brief_inclusi_e_scartati_per_formato_o_dimensione(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    (clone / "src").mkdir()
    (clone / "src" / "buono.py").write_text("VALORE_BUONO = 123\n", encoding="utf-8")
    (clone / "src" / "binario.dat").write_bytes(b"\xff\xfe\x00\x80BINARIO_SEGRETO")
    (clone / "src" / "enorme.txt").write_text("X" * (40 * 1024 + 1), encoding="utf-8")
    subprocess.run(["git", "add", "src"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "aggiungi file"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    corpo = (
        "Leggi questi file.\n\n"
        "## File\n\n"
        "- `src/buono.py`\n"
        "- `src/binario.dat`\n"
        "- `src/enorme.txt`\n"
        "- `src/manca.txt`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo)
    prompt = lanci[0]["prompt"]

    assert "### src/buono.py" in prompt
    assert "VALORE_BUONO = 123" in prompt
    assert prompt.index("### src/buono.py") > prompt.index("### commenti.md")

    assert "BINARIO_SEGRETO" not in prompt
    assert "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in prompt
    righe = prompt.splitlines()
    assert any(r.startswith("saltato src/binario.dat:") for r in righe)
    assert any(r.startswith("saltato src/enorme.txt:") for r in righe)
    assert any(r.startswith("saltato src/manca.txt:") for r in righe)


# --- Sei attacchi di sicurezza sui percorsi in ## File --------------------------------------------------------------


def _esegui_attacco(tmp_path: Path, percorso_attacco: str, segreto: str, prepara_clone=None) -> str:
    _origin, clone = _crea_ambiente_git(tmp_path)
    if prepara_clone is not None:
        prepara_clone(clone)
        subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "prepara attacco"], cwd=str(clone), check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    corpo = (
        "Compito con attacco.\n\n"
        "## File\n\n"
        f"- `{percorso_attacco}`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo)
    prompt = lanci[0]["prompt"]
    if segreto:
        assert segreto not in prompt
    assert any(r.startswith(f"saltato {percorso_attacco}:") for r in prompt.splitlines())
    return prompt


def test_attacco_a_risalita_fuori_dalla_copia(tmp_path: Path) -> None:
    # 1. Prova diretta su componi_prompt_con_fascicolo con ../fuori.txt esistente proprio fuori da lavoro_dir
    lavoro_dir = tmp_path / "esecutore" / "lavoro"
    lavoro_dir.mkdir(parents=True)
    fasc_runner = tmp_path / "fascicolo"
    fasc_runner.mkdir()
    (fasc_runner / "brief.md").write_text("Brief\n", encoding="utf-8")
    (lavoro_dir.parent / "fuori.txt").write_text("SEGRETO_ATTACCO_A_DIRETTO", encoding="utf-8")

    prompt_diretto = componi_prompt_con_fascicolo(
        intestazione="Testa",
        fascicolo_runner=fasc_runner,
        fascicolo_dir=lavoro_dir / ".bottega" / "fascicolo",
        lavoro_dir=lavoro_dir,
        brief_testo="## File\n\n- `../fuori.txt`\n",
    )
    assert "SEGRETO_ATTACCO_A_DIRETTO" not in prompt_diretto
    assert any(r.startswith("saltato ../fuori.txt:") for r in prompt_diretto.splitlines())

    # 2. Prova nel giro completo con risalita fino a spazio/fuori.txt
    _origin, clone = _crea_ambiente_git(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    def cb(cartella, prompt, **kwargs):
        _committa(cartella, "fatto.txt")
        return Lancio(esito="fatto", testo="ok")

    (spazio / "fuori.txt").write_text("SEGRETO_ATTACCO_A_SPAZIO", encoding="utf-8")
    corpo = (
        "Attacco A.\n\n## File\n\n- `../fuori.txt`\n- `../../../fuori.txt`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Attacco A", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Attacco A", stato="pronto")])
    porta = PortaFinta(callback=cb)
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
        adesso=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    prompt = porta.lanci_esecutore()[0]["prompt"]
    assert "SEGRETO_ATTACCO_A_SPAZIO" not in prompt
    assert any(r.startswith("saltato ../fuori.txt:") for r in prompt.splitlines())
    assert any(r.startswith("saltato ../../../fuori.txt:") for r in prompt.splitlines())


def test_attacco_b_percorso_assoluto(tmp_path: Path) -> None:
    segreto = tmp_path / "chiavi_runner.txt"
    segreto.write_text("SEGRETO_ATTACCO_B", encoding="utf-8")
    _esegui_attacco(tmp_path, str(segreto), "SEGRETO_ATTACCO_B")


def test_attacco_c_symlink_a_file_fuori(tmp_path: Path) -> None:
    fuori = tmp_path / "segreto_c.txt"
    fuori.write_text("SEGRETO_ATTACCO_C", encoding="utf-8")

    def prepara(clone: Path) -> None:
        (clone / "link_file.txt").symlink_to(fuori)

    _esegui_attacco(tmp_path, "link_file.txt", "SEGRETO_ATTACCO_C", prepara_clone=prepara)


def test_attacco_d_symlink_a_cartella_fuori_con_file_sotto(tmp_path: Path) -> None:
    fuori_dir = tmp_path / "cartella_segreta"
    fuori_dir.mkdir()
    (fuori_dir / "segreto.txt").write_text("SEGRETO_ATTACCO_D", encoding="utf-8")

    def prepara(clone: Path) -> None:
        (clone / "link_dir").symlink_to(fuori_dir)

    _esegui_attacco(tmp_path, "link_dir/segreto.txt", "SEGRETO_ATTACCO_D", prepara_clone=prepara)


def test_attacco_e_git_config_e_bottega(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    corpo = (
        "Attacco E.\n\n## File\n\n"
        "- `.git/config`\n"
        "- `.bottega/fascicolo/stato.md`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo)
    prompt = lanci[0]["prompt"]
    assert "[remote \"origin\"]" not in prompt
    assert any(r.startswith("saltato .git/config:") for r in prompt.splitlines())
    assert any(r.startswith("saltato .bottega/fascicolo/stato.md:") for r in prompt.splitlines())


def test_attacco_f_cartella_al_posto_di_file(tmp_path: Path) -> None:
    _esegui_attacco(tmp_path, "docs", "")


# --- Tetto di 96 KiB in byte UTF-8 (non in caratteri) ----------------------------------------------------------------


def test_tetto_96_kib_in_byte_utf8_con_accenti_e_da_leggere(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    # 55.000 lettere accentate 'à' = 55.000 caratteri (< 96 KiB se contati a caratteri) ma 110.000 byte UTF-8 (> 96 KiB)
    testo_accentato = "à" * 55000
    (clone / "docs" / "costituzione.md").write_text(testo_accentato, encoding="utf-8")
    subprocess.run(["git", "add", "docs"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "costituzione accentata"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    # Anche due file nel repo validi (< 40 KiB ciascuno) dove il secondo sfora i 96 KiB insieme al resto
    (clone / "f1.txt").write_text("é" * 18000, encoding="utf-8")  # 36.000 byte (< 40 KiB)
    (clone / "f2.txt").write_text("ò" * 18000, encoding="utf-8")  # 36.000 byte (< 40 KiB)
    (clone / "f3.txt").write_text("ù" * 18000, encoding="utf-8")  # 36.000 byte (< 40 KiB)
    subprocess.run(["git", "add", "f1.txt", "f2.txt", "f3.txt"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "file accentati"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    corpo = (
        "Brief con file accentati.\n\n"
        "## File\n\n"
        "- `f1.txt`\n"
        "- `f2.txt`\n"
        "- `f3.txt`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo)
    prompt = lanci[0]["prompt"]

    assert len(prompt.encode("utf-8")) <= TETTO_PROMPT
    assert "àààà" not in prompt
    assert "### costituzione.md" not in prompt
    assert "Da leggere nel fascicolo" in prompt
    assert "costituzione.md" in prompt.split("Da leggere nel fascicolo", 1)[1]

    # f1.txt e f2.txt (36 KB + 36 KB = 72 KB + brief/stato/commenti < 96 KB) entrano per intero, f3.txt resta fuori
    assert "### f1.txt" in prompt
    assert "### f2.txt" in prompt
    assert "### f3.txt" not in prompt
    assert "ùùùù" not in prompt
    assert "Da leggere nel repo" in prompt
    assert "f3.txt" in prompt.split("Da leggere nel repo", 1)[1]


# --- Ripresa dopo consulto usa la stessa composizione ----------------------------------------------------------------


def test_ripresa_dopo_consulto_include_fascicolo(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    (clone / "modulo.py").write_text("CODICE_MODULO = 'ok'\n", encoding="utf-8")
    subprocess.run(["git", "add", "modulo.py"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "aggiungi modulo"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

    passo = 0

    def cb(cartella, prompt, **kwargs):
        nonlocal passo
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="RISPOSTA usa CODICE_MODULO")
        if passo == 0:
            passo += 1
            return Lancio(
                esito="fatto",
                testo="DOMANDA PER CHI DECIDE: posso procedere?",
                conversazione="conv-1",
            )
        _committa(cartella, "fatto.txt")
        return Lancio(esito="fatto", testo="fatto dopo risposta")

    corpo = (
        "Compito con consulto.\n\n"
        "## File\n\n"
        "- `modulo.py`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    lanci, _spazio = _giro_con_brief(tmp_path, clone, corpo, callback_porta=cb)

    assert len(lanci) == 2
    prompt_ripresa = lanci[1]["prompt"]
    assert len(prompt_ripresa.encode("utf-8")) <= TETTO_PROMPT
    assert "Risposta del consigliere:\nRISPOSTA usa CODICE_MODULO" in prompt_ripresa
    assert "### brief.md" in prompt_ripresa
    assert "### stato.md" in prompt_ripresa
    assert "### modulo.py" in prompt_ripresa
    assert "CODICE_MODULO = 'ok'" in prompt_ripresa


def test_ripresa_dopo_consulto_blocca_symlink_piantato(tmp_path: Path) -> None:
    _origin, clone = _crea_ambiente_git(tmp_path)
    fuori_ripresa = tmp_path / "segreto_ripresa.txt"
    fuori_ripresa.write_text("SEGRETO_POST_CONSULTO", encoding="utf-8")

    passo = 0

    def cb(cartella, prompt, **kwargs):
        nonlocal passo
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="RISPOSTA procedi")
        if passo == 0:
            passo += 1
            (Path(cartella) / "trappola.txt").symlink_to(fuori_ripresa)
            return Lancio(
                esito="fatto",
                testo="DOMANDA PER CHI DECIDE: posso procedere?",
                conversazione="conv-1",
            )
        _committa(cartella, "fatto.txt")
        return Lancio(esito="fatto", testo="fatto dopo risposta")

    corpo = (
        "Compito con symlink in ripresa.\n\n"
        "## File\n\n"
        "- `trappola.txt`\n\n"
        "## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    )
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Symlink ripresa", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Symlink ripresa", stato="pronto")])
    porta = _PortaConConsulto(callback=cb)
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
        adesso=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    lanci = porta.lanci_esecutore()
    assert len(lanci) == 2
    prompt_ripresa = lanci[1]["prompt"]
    assert "SEGRETO_POST_CONSULTO" not in prompt_ripresa
    assert any(r.startswith("saltato trappola.txt:") for r in prompt_ripresa.splitlines())
    assert esito.esito == "bloccato"


def test_attacco_g_scambio_fra_il_controllo_e_l_apertura(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fra `resolve` e `open` un processo rimasto dell'esecutore scambia il file con uno di fuori: il controllo sul
    file aperto lo ferma. Qui lo scambio lo fa un `os.open` finto, che apre il file di fuori al posto di quello chiesto."""
    import bottega.giro as modulo_giro

    lavoro_dir = tmp_path / "esecutore" / "lavoro"
    lavoro_dir.mkdir(parents=True)
    (lavoro_dir / "buono.txt").write_text("CONTENUTO_BUONO", encoding="utf-8")
    fuori = tmp_path / "runner" / "segreto.txt"
    fuori.parent.mkdir()
    fuori.write_text("SEGRETO_ATTACCO_G", encoding="utf-8")
    fasc_runner = tmp_path / "fascicolo"
    fasc_runner.mkdir()
    (fasc_runner / "brief.md").write_text("Brief\n", encoding="utf-8")

    apri_vero = modulo_giro.os.open

    def apri_scambiato(percorso, flag, *resto):  # type: ignore[no-untyped-def]
        if Path(percorso).name == "buono.txt":
            return apri_vero(fuori, flag, *resto)
        return apri_vero(percorso, flag, *resto)

    monkeypatch.setattr(modulo_giro.os, "open", apri_scambiato)
    prompt = componi_prompt_con_fascicolo(
        intestazione="Testa",
        fascicolo_runner=fasc_runner,
        fascicolo_dir=lavoro_dir / ".bottega" / "fascicolo",
        lavoro_dir=lavoro_dir,
        brief_testo="## File\n\n- `buono.txt`\n",
    )

    assert "SEGRETO_ATTACCO_G" not in prompt
    assert any(r.startswith("saltato buono.txt:") for r in prompt.splitlines())
