"""Cancello della tappa B5: una tappa finta misurata dall'inizio alla fine (Compito B5.5).

Verifica l'intero ciclo delle misure:
1. Inizio e fine del segno di chi decide con calcolo dei token da trascrizione finta di Claude Code;
2. Scrittura delle misure del compito al termine del giro dell'esecutore fuori;
3. Revisione del compito con bottega misura (esito e rilievi);
4. Compito con segno dimenticato (inizio senza fine): nessun token di chi decide e segno aperto;
5. Resoconto aggregato con bottega conti (statistiche per candidato, per dove e spia);
6. Scelta viva del distributore che riceve i risultati storici della board.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import subprocess
import time

import pytest

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.conti import conti
import bottega.distributore
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.giro import giro
from bottega.misura import argomenti_misura, comando_misura
import bottega.misure as misure
from bottega.porte import Controllo, Lancio
from bottega.scelta import Risultati
import bottega.segno
from bottega.segno import argomenti_segno, comando_segno


class PortaFintaCompleta:
    """Porta finta configurabile per le prove del cancello."""

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
        return Lancio(esito="fatto", testo="Compito completato con successo", contatori={"total_tokens": 1000})


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


def _configurazione() -> Configurazione:
    """Configura una bottega e un candidato che esegue fuori."""
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
            nome="Esecutore",
            bottega="principale",
            porta="finta",
            modello="mod-esecutore",
            funzioni=("eseguire",),
            runner="linux",
        ),
    }
    return Configurazione(versione=1, progetto=progetto, botteghe=botteghe, candidati=candidati)


def test_tappa_finta_misurata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancello B5.5: una tappa finta con due compiti, misurata dall'inizio alla fine."""
    casa = tmp_path / "casa"
    casa.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(casa))
    for var in (
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_SESSION_ID",
        "ANTIGRAVITY_APP_DATA_DIR",
        "ANTIGRAVITY_CONVERSATION_ID",
        "PI_CODING_AGENT_SESSION_DIR",
        "PI_SESSION_FILE",
        "COPILOT_HOME",
        "COPILOT_AGENT_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)

    sessione_claude = "sessione-cancello-claude-1"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sessione_claude)

    t_inizio = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)
    t_fine = t_inizio + timedelta(minutes=10)

    class FintoDatetime(datetime):
        adesso_finto = t_inizio

        @classmethod
        def now(cls, tz=None):
            return cls.adesso_finto

    monkeypatch.setattr(bottega.segno, "datetime", FintoDatetime)

    # Trascrizione finta in HOME/.claude/projects/qualsiasi/<id>.jsonl
    # Due messaggi assistant dopo l'inizio (uno ripetuto con lo stesso id), uno prima dell'inizio.
    proj_dir = casa / ".claude" / "projects" / "qualsiasi"
    proj_dir.mkdir(parents=True, exist_ok=True)
    f_jsonl = proj_dir / f"{sessione_claude}.jsonl"

    rec_prima = {
        "type": "assistant",
        "timestamp": (t_inizio - timedelta(minutes=2)).isoformat(),
        "message": {
            "id": "msg_pre",
            "usage": {
                "input_tokens": 5000,
                "output_tokens": 1000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }
    rec_1a = {
        "type": "assistant",
        "timestamp": (t_inizio + timedelta(minutes=1)).isoformat(),
        "message": {
            "id": "msg_1",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 1000,  # pesa 0.1 -> 100; subtotale = 250
            },
        },
    }
    rec_1b = {
        "type": "assistant",
        "timestamp": (t_inizio + timedelta(minutes=2)).isoformat(),
        "message": {
            "id": "msg_1",  # stesso id: sostituisce il precedente senza raddoppiare
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 1000,
            },
        },
    }
    rec_2 = {
        "type": "assistant",
        "timestamp": (t_inizio + timedelta(minutes=3)).isoformat(),
        "message": {
            "id": "msg_2",
            "usage": {
                "input_tokens": 200,
                "output_tokens": 40,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 2000,  # pesa 0.1 -> 200; subtotale = 440
            },
        },
    }
    righe_jsonl = [json.dumps(r) for r in (rec_prima, rec_1a, rec_1b, rec_2)]
    f_jsonl.write_text("\n".join(righe_jsonl) + "\n", encoding="utf-8")

    # 1. Progetto finto: origine nuda, clone, configurazione, ForgiaFinta e BoardFinta
    origin, clone = _costruisci_progetto_git(tmp_path)
    cfg = _configurazione()
    spazio = tmp_path / "spazio"

    madre = Issue(
        numero=1,
        titolo="Tappa Madre Misure",
        corpo="Tappa con due sotto-issue sequenziali.\n",
        autore="maestro",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )
    sotto1 = Issue(
        numero=2,
        titolo="Compito 1: modulo",
        corpo="Crea modulo.txt.\n\n## Fatto quando\n```bash\ntest -f modulo.txt\n```\n",
        autore="maestro",
        stato="OPEN",
    )
    sotto2 = Issue(
        numero=3,
        titolo="Compito 2: estensione",
        corpo="Crea estensione.txt.\n\n## Fatto quando\n```bash\ntest -f estensione.txt\n```\n",
        autore="maestro",
        stato="OPEN",
    )
    terzo = Issue(
        numero=4,
        titolo="Terzo lavoro pronto",
        corpo="Crea terzo.txt.\n\n## Fatto quando\n```bash\ntrue\n```\n",
        autore="maestro",
        stato="OPEN",
        etichette=["bottega: fuori"],
    )

    forgia = ForgiaFinta(issues=[madre, sotto1, sotto2, terzo])
    forgia._sotto_issue[1] = [2, 3]

    board = BoardFinta(lavori=[
        Lavoro(numero=1, titolo="Tappa Madre Misure", stato="pronto", etichette=["bottega: fuori"]),
        Lavoro(numero=2, titolo="Compito 1: modulo", stato="pronto"),
        Lavoro(numero=3, titolo="Compito 2: estensione", stato="pronto"),
    ])

    parser_segno = argparse.ArgumentParser()
    argomenti_segno(parser_segno)

    # 2. Compito 1: bottega segno inizio 2
    res_inizio1 = comando_segno(parser_segno.parse_args(["inizio", "2"]), board=board)
    assert res_inizio1 == 0
    lav1 = board.lavoro(2)
    assert lav1 is not None
    assert lav1.campi.get("Segno") is not None

    # Compito 1: bottega segno fine 2 (somma pesata dei due messaggi: 250 + 440 = 690)
    FintoDatetime.adesso_finto = t_fine
    res_fine1 = comando_segno(parser_segno.parse_args(["fine", "2"]), board=board)
    assert res_fine1 == 0
    lav1 = board.lavoro(2)
    assert lav1 is not None
    assert lav1.campi.get("Token di chi decide") == "690"
    assert lav1.campi.get("Segno") is None

    # Compito 1: giro dell'esecutore che consegna
    def callback_porta(cartella: Path | str, prompt: str, **kwargs) -> Lancio:
        p = Path(cartella)
        if kwargs.get("sola_lettura"):
            return Lancio(esito="fatto", testo="Revisione consigliere approvata")
        if not (p / "modulo.txt").exists():
            (p / "modulo.txt").write_text("modulo base creato\n", encoding="utf-8")
            return Lancio(esito="fatto", testo="modulo.txt completato", contatori={"total_tokens": 1500})
        if not (p / "estensione.txt").exists():
            (p / "estensione.txt").write_text("estensione modulo creata\n", encoding="utf-8")
            return Lancio(esito="fatto", testo="estensione.txt completata", contatori={"total_tokens": 1800})
        return Lancio(esito="fatto", testo="operazione completata", contatori={"total_tokens": 500})

    porta = PortaFintaCompleta(callback=callback_porta)
    porte = {"finta": porta}

    tempo_mono = 100.0

    def finto_monotonic() -> float:
        nonlocal tempo_mono
        tempo_mono += 8.0
        return tempo_mono

    monkeypatch.setattr(time, "monotonic", finto_monotonic)

    adesso_giro = datetime(2026, 11, 8, 14, 15, tzinfo=timezone.utc)
    esito_giro1 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte=porte,
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso_giro,
        caso=random.Random(1),
    )
    assert esito_giro1.esito == "consegnato"
    assert esito_giro1.oracolo_ok is True

    # Verifica misure scritte dal giro sul compito 1
    lav1 = board.lavoro(2)
    assert lav1 is not None
    assert lav1.campi.get("Esecutore") == "Esecutore"
    assert lav1.campi.get("Porta") == "finta"
    assert lav1.campi.get("Dove") == "fuori"
    assert int(lav1.campi.get("Durata", 0)) > 0
    assert lav1.campi.get("Giri") == "1"
    assert lav1.campi.get("Token esecutore") == "1500"

    # Compito 1: bottega misura 2 --esito corretto --rilievi-brief 1
    parser_misura = argparse.ArgumentParser()
    argomenti_misura(parser_misura)
    res_misura1 = comando_misura(
        parser_misura.parse_args(["2", "--esito", "corretto", "--rilievi-brief", "1"]),
        board=board,
    )
    assert res_misura1 == 0
    lav1 = board.lavoro(2)
    assert lav1.campi.get("Esito del compito") == "corretto"
    assert lav1.campi.get("Rilievi del brief") == "1"

    # 3. Compito 2: segno inizio senza segno fine (segno dimenticato)
    FintoDatetime.adesso_finto = t_fine + timedelta(minutes=5)
    res_inizio2 = comando_segno(parser_segno.parse_args(["inizio", "3"]), board=board)
    assert res_inizio2 == 0
    lav2 = board.lavoro(3)
    assert lav2 is not None
    assert lav2.campi.get("Segno") is not None

    # Compito 2: giro dell'esecutore che consegna
    esito_giro2 = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte=porte,
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso_giro + timedelta(minutes=10),
        caso=random.Random(2),
    )
    assert esito_giro2.esito == "consegnato"
    assert esito_giro2.oracolo_ok is True

    # Compito 2: bottega misura 3 --esito unito
    res_misura2 = comando_misura(
        parser_misura.parse_args(["3", "--esito", "unito"]),
        board=board,
    )
    assert res_misura2 == 0

    # Compito 2 resta SENZA Token di chi decide e con Segno aperto
    lav2 = board.lavoro(3)
    assert lav2 is not None
    assert "Token di chi decide" not in lav2.campi
    assert lav2.campi.get("Segno") is not None
    assert lav2.campi.get("Esito del compito") == "unito com'era"
    assert lav2.campi.get("Esecutore") == "Esecutore"
    assert lav2.campi.get("Porta") == "finta"
    assert lav2.campi.get("Dove") == "fuori"
    assert int(lav2.campi.get("Durata", 0)) > 0
    assert lav2.campi.get("Giri") == "1"
    assert lav2.campi.get("Token esecutore") == "1800"

    # 4. conti sull'elenco() della board
    elenco_board = board.elenco()
    statistiche = conti(elenco_board)
    stats_candidato = statistiche["per_candidato"]["Esecutore"]
    assert stats_candidato["compiti"] == 2
    assert stats_candidato["senza_numero"] == 1
    assert stats_candidato["esiti"]["corretto"] == 1
    assert stats_candidato["esiti"]["unito com'era"] == 1
    assert stats_candidato["rilievi"]["brief"] == 1
    assert statistiche["spia"]["fuori"] == 690.0

    # 5. misure.risultati sul totale '*'
    risultati_misure = misure.risultati(board.elenco(), cfg)
    assert ("esecutore", "*") in risultati_misure
    r = risultati_misure[("esecutore", "*")]
    assert r.uniti == 1
    assert r.corretti == 1
    assert r.rifiutati == 0

    # distribuisci su un terzo lavoro pronto passa a scegli quei risultati
    board.aggiungi(Lavoro(numero=4, titolo="Terzo lavoro pronto", stato="pronto", etichette=["bottega: fuori"]))

    chiamate_scegli: list[dict] = []
    vero_scegli = bottega.distributore.scegli

    def mock_scegli(**kwargs):
        chiamate_scegli.append(kwargs)
        return vero_scegli(**kwargs)

    monkeypatch.setattr(bottega.distributore, "scegli", mock_scegli)

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso_giro + timedelta(hours=1),
        caso=random.Random(42),
    )

    assert len(chiamate_scegli) >= 1
    risultati_passati = chiamate_scegli[0]["risultati"]
    assert risultati_passati.get(("esecutore", "*")) == Risultati(uniti=1, corretti=1, rifiutati=0)
