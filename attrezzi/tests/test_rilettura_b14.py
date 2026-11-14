"""Prove per il motivo del commento «compito senza rilettura» (B14-R6)."""

from __future__ import annotations

import random
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import giro
from bottega.porte import Controllo, Lancio
from bottega.quota import valore_esaurita


class _PortaFinta:
    """Porta finta minimale per le prove della rilettura."""

    nome = "finta"
    eseguibile = "finta"

    def __init__(self, callback) -> None:
        self._callback = callback

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True, versione="1.0", motivo=None)

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
        return self._callback(cartella, prompt, sola_lettura=sola_lettura)


def _crea_repo(tmp_path: Path) -> Path:
    """Crea una repo bare di origine e restituisce il clone locale."""
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
    subprocess.run(["git", "commit", "-m", "primo commit"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)
    return clone


def _configurazione(runner_consigliere: str | None) -> Configurazione:
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
        "consigliere": Candidato(
            id="consigliere",
            nome="Consigliere Finto",
            bottega="consiglio",
            porta="finta",
            modello="finto-2",
            funzioni=("consigliare",),
            runner=runner_consigliere,
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def _esegui_giro(
    tmp_path: Path,
    cfg: Configurazione,
    esito_consigliere: Lancio | None = None,
    esaurisci_quota_consigliere: bool = False,
):
    clone = _crea_repo(tmp_path)
    corpo = "Brief\n\n## Fatto quando\n```bash\ntest -f fatto.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Rilettura", corpo=corpo)
    forgia = ForgiaFinta(issues=[iss])
    adesso = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    if esaurisci_quota_consigliere:
        forgia.imposta_variabile("BOTTEGA_QUOTA_CONSIGLIO", valore_esaurita(adesso + timedelta(hours=1)))
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Rilettura", stato="pronto")])

    def callback(cartella, prompt, **kwargs):
        if kwargs.get("sola_lettura"):
            assert esito_consigliere is not None
            return esito_consigliere
        (Path(cartella) / "fatto.txt").write_text("ok", encoding="utf-8")
        subprocess.run(["git", "add", "fatto.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: fatto"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = _PortaFinta(callback=callback)
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
        adesso=adesso,
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"
    assert esito.pr is not None
    prefisso_segno = "<!-- bottega:consigliere -->\n"
    return [c.corpo[len(prefisso_segno):] for c in forgia.commenti(esito.pr) if c.corpo.startswith(prefisso_segno)]


def test_senza_rilettura_nessun_candidato_con_quota(tmp_path: Path):
    """B14-R6: senza quota disponibile sul consigliere il commento riporta il perché della scelta."""
    commenti = _esegui_giro(
        tmp_path,
        _configurazione(runner_consigliere="linux-x64"),
        esaurisci_quota_consigliere=True,
    )
    assert len(commenti) == 1
    corpo = commenti[0]
    assert "\n" not in corpo
    assert corpo.startswith("compito senza rilettura: ")
    assert "nessun candidato con quota disponibile per la funzione «consigliare»" in corpo


def test_senza_rilettura_nessun_candidato_sul_runner(tmp_path: Path):
    """B14-R6: senza consigliere sul runner dell'esecutore il commento riporta il perché della scelta."""
    commenti = _esegui_giro(
        tmp_path,
        _configurazione(runner_consigliere="altro-runner"),
    )
    assert len(commenti) == 1
    corpo = commenti[0]
    assert "\n" not in corpo
    assert corpo == "compito senza rilettura: nessun candidato per la funzione «consigliare» fuori"


def test_senza_rilettura_lancio_finito_male(tmp_path: Path):
    """B14-R6: se il lancio del consigliere fallisce il commento riporta solo l'esito, mai il testo del modello."""
    commenti = _esegui_giro(
        tmp_path,
        _configurazione(runner_consigliere="linux-x64"),
        esito_consigliere=Lancio(esito="tempo_scaduto", testo="testo riservato del modello\ncon stderr"),
    )
    assert len(commenti) == 1
    corpo = commenti[0]
    assert "\n" not in corpo
    assert corpo == "compito senza rilettura: il lancio del consigliere è finito con «tempo_scaduto»"
    assert "testo riservato" not in corpo
    assert "stderr" not in corpo
