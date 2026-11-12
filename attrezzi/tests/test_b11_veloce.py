"""Prove di B11: il giro chiede all'esecutore pochi passi, e il distributore dice dove manca il «Fatto quando».

Le misure dal vivo (Jarvis, 2026-11-12): il tempo di un giro va quasi tutto nei passi del modello (circa 5 secondi
l'uno, ognuno rilegge il contesto), non nelle prove; e un compito di correzione aggiunto a mano senza il suo
«Fatto quando» fermava il lavoro con un messaggio che non diceva quale compito.
"""

from datetime import datetime
from pathlib import Path
import random
from zoneinfo import ZoneInfo

from bottega.board import Lavoro
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.porte import Lancio

from test_distributore import _configurazione_base
from test_giro_b9 import PortaFinta, _committa, _crea_ambiente_git, _giro, _lavoro_sciolto


# --- Il prompt dell'esecutore: pochi passi ------------------------------------------------------------------------


def _prompt_del_giro(tmp_path: Path) -> str:
    _origin, clone = _crea_ambiente_git(tmp_path)
    forgia, board = _lavoro_sciolto("true")
    porta = PortaFinta(callback=lambda cartella, prompt, **kw: (_committa(cartella, "file.txt"), Lancio("fatto", "ok"))[1])
    _giro(tmp_path, clone, forgia, board, porta)
    return porta.lanci_esecutore()[0]["prompt"]


def test_il_prompt_chiede_pochi_passi(tmp_path: Path) -> None:
    prompt = _prompt_del_giro(tmp_path)
    assert "Lavora in pochi passi" in prompt
    assert "blocchi grandi" in prompt
    assert "un solo comando" in prompt
    assert "riscrivere" in prompt


def test_il_prompt_chiede_le_prove_in_primo_piano_e_il_fatto_quando_una_volta(tmp_path: Path) -> None:
    prompt = _prompt_del_giro(tmp_path)
    assert "in primo piano" in prompt
    assert "una volta sola, alla fine" in prompt


# --- Il distributore dice quale compito non ha il «Fatto quando» ---------------------------------------------------


def _distribuisci(forgia: ForgiaFinta) -> tuple[list[str], BoardFinta]:
    cfg = _configurazione_base()
    adesso = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    board = BoardFinta([Lavoro(numero=1, titolo="Lavoro", stato="pronto", etichette=["bottega: fuori"])])
    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    return righe, board


def test_un_compito_senza_fatto_quando_si_nomina() -> None:
    madre = Issue(numero=1, titolo="Lavoro", corpo="La tappa.")
    chiuso = Issue(numero=2, titolo="Fatto", corpo="Brief.\n\n## Fatto quando\n```bash\ntrue\n```\n", stato="CLOSED")
    aggiunto = Issue(numero=3, titolo="Correzione aggiunta a mano", corpo="Correggi la cosa.")
    forgia = ForgiaFinta([madre, chiuso, aggiunto])
    forgia._sotto_issue[1] = [2, 3]

    righe, board = _distribuisci(forgia)

    attesa = (
        "lavoro 1: senza «Fatto quando» nel compito #3 (serve la sezione «## Fatto quando» con il comando in un "
        "blocco recintato), salto"
    )
    assert attesa in righe
    assert not any(r[0] == "prendi" for r in board.registro)


def test_un_lavoro_senza_compiti_e_senza_fatto_quando_lo_dice_del_lavoro() -> None:
    righe, _board = _distribuisci(ForgiaFinta([Issue(numero=1, titolo="Lavoro", corpo="Brief senza prova")]))
    attesa = (
        "lavoro 1: senza «Fatto quando» nel corpo del lavoro (serve la sezione «## Fatto quando» con il comando in "
        "un blocco recintato), salto"
    )
    assert attesa in righe
