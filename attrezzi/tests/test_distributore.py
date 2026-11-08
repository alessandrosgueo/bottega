"""Prove del distributore: scelta del lavoro, scelta del candidato, manutenzione, CI rossa, quote, board."""

from datetime import datetime
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo
import pytest

from bottega.board import Lavoro
from bottega.configurazione import Candidato, Bottega, Progetto, Configurazione
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue


def _configurazione_base(
    manutenzione: tuple[str, ...] = (),
    fuso: str = "Europe/Rome",
    liberi: tuple[str, ...] = ("bug", "debito"),
) -> Configurazione:
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso=fuso,
        notte="02:00",
        manutenzione=manutenzione,
        project=1,
        liberi=liberi,
    )
    botteghe = {
        "b-claude": Bottega(id="b-claude", quota="abbondante", porte=("claude-code",)),
        "b-pi": Bottega(id="b-pi", quota="normale", porte=("pi",)),
    }
    candidati = {
        "c-claude": Candidato(
            id="c-claude",
            nome="Claude",
            bottega="b-claude",
            porta="claude-code",
            modello="claude-3-7-sonnet",
            funzioni=("eseguire", "decidere"),
            runner="linux",
        ),
        "c-pi": Candidato(
            id="c-pi",
            nome="Pi",
            bottega="b-pi",
            porta="pi",
            modello="pi-default",
            funzioni=("eseguire", "decidere"),
            runner="linux",
        ),
    }
    return Configurazione(versione=1, progetto=progetto, botteghe=botteghe, candidati=candidati)


def test_manutenzione_blocca_distribuzione() -> None:
    cfg = _configurazione_base(manutenzione=("03:00-04:30", "23:30-01:00"))
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 3, 30, tzinfo=fuso)

    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"])])
    forgia = ForgiaFinta([Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```")])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    assert any("manutenzione" in r for r in righe)
    assert len(forgia.registro) == 0
    assert len(board.registro) == 0


def test_manutenzione_a_cavallo_della_mezzanotte() -> None:
    cfg = _configurazione_base(manutenzione=("23:30-01:00",))
    fuso = ZoneInfo(cfg.progetto.fuso)

    # 23:45 -> dentro la finestra
    adesso_notte = datetime(2026, 11, 8, 23, 45, tzinfo=fuso)
    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"])])
    forgia = ForgiaFinta([Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```")])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso_notte,
        caso=random.Random(42),
        notte=False,
    )
    assert any("manutenzione" in r for r in righe)
    assert len(board.registro) == 0

    # 00:30 del giorno dopo -> dentro la finestra
    adesso_dopo = datetime(2026, 11, 9, 0, 30, tzinfo=fuso)
    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso_dopo,
        caso=random.Random(42),
        notte=False,
    )
    assert any("manutenzione" in r for r in righe)
    assert len(board.registro) == 0

    # 01:15 del giorno dopo -> fuori dalla finestra
    adesso_fuori = datetime(2026, 11, 9, 1, 15, tzinfo=fuso)
    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso_fuori,
        caso=random.Random(42),
        notte=False,
    )
    assert not any("manutenzione" in r for r in righe)
    assert len(board.registro) > 0


def test_ramo_principale_rosso_avviso_e_nessun_lavoro() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"])])
    forgia = ForgiaFinta([Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```")])
    forgia.imposta_stato_ci(forgia.ramo_principale(), "rosso")

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    assert any("rosso" in r for r in righe)
    # Nessun lavoro avviato
    assert len(board.registro) == 0
    # Un avviso creato
    avvisi = [r for r in forgia.registro if r[0] == "avviso"]
    assert len(avvisi) == 1
    assert avvisi[0][3] is not None  # motivo non nullo


def test_ramo_principale_verde_chiude_avviso() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"])])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```"),
    ])
    forgia.imposta_stato_ci(forgia.ramo_principale(), "verde")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    # L'avviso viene chiuso (motivo None)
    avvisi = [r for r in forgia.registro if r[0] == "avviso"]
    assert len(avvisi) == 1
    assert avvisi[0][3] is None  # motivo None = chiusura
    # E il lavoro pronto viene preso
    assert any(r[0] == "prendi" for r in board.registro)


def test_lavoro_in_corso_scaduto_oltre_7_ore_torna_pronto() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 18, 0, tzinfo=fuso)

    # In corso dalle 09:00 -> 9 ore fa (> 7 ore)
    board = BoardFinta([
        Lavoro(
            numero=10,
            titolo="Compito Scaduto",
            stato="in corso",
            esecutore="c-claude",
            nota="inizio=2026-11-08T09:00:00+01:00",
            etichette=["bottega: fuori"],
        )
    ])
    forgia = ForgiaFinta([
        Issue(numero=10, titolo="Compito Scaduto", corpo="## Fatto quando\n```\npytest\n```")
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    # Il lavoro 10 torna pronto
    assert any(r[0] == "stato" and r[1] == 10 and r[2] == "pronto" for r in board.registro)
    assert any("scaduto" in r.lower() or "pronto" in r.lower() for r in righe)


def test_bottega_occupata_e_review_focus_2() -> None:
    # Review Focus 2:
    # Due distribuisci di fila non prendono lo stesso lavoro né due lavori per la stessa bottega.
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori", "esegue: c-claude"]),
        Lavoro(numero=2, titolo="Compito 2", stato="pronto", etichette=["bottega: fuori", "esegue: c-claude"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```"),
        Issue(numero=2, titolo="Compito 2", corpo="## Fatto quando\n```\npytest\n```"),
    ])

    # Primo giro di distribuisci:
    # Prende il lavoro 1 per c-claude (bottega b-claude).
    # Il lavoro 2 per c-claude viene saltato perché la bottega b-claude è ora occupata nel giro.
    righe1 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    prendi_fatti = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi_fatti) == 1
    assert prendi_fatti[0][1] == 1  # Lavoro 1 preso
    assert any("occupata" in r for r in righe1)

    # Secondo giro di distribuisci:
    # Lavoro 1 è ora "in corso" sulla board.
    # Lavoro 2 è "pronto" ma richiede b-claude che ha lavoro 1 in corso.
    # Nessun lavoro deve essere preso!
    board.registro.clear()
    righe2 = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    assert not any(r[0] == "prendi" for r in board.registro)
    assert any("occupata" in r for r in righe2)


def test_due_botteghe_diverse_possono_partire_nello_stesso_giro() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito Claude", stato="pronto", etichette=["bottega: fuori", "esegue: c-claude"]),
        Lavoro(numero=2, titolo="Compito Pi", stato="pronto", etichette=["bottega: fuori", "esegue: c-pi"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito Claude", corpo="## Fatto quando\n```\npytest\n```"),
        Issue(numero=2, titolo="Compito Pi", corpo="## Fatto quando\n```\npytest\n```"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    prendi_fatti = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi_fatti) == 2
    numeri_presi = {r[1] for r in prendi_fatti}
    assert numeri_presi == {1, 2}

    # Due workflow avviati: uno per b-claude e uno per b-pi
    assert len(forgia._workflow_avviati) == 2
    wf_file = {w[0] for w in forgia._workflow_avviati}
    assert wf_file == {"bottega-esecutore-b-claude.yml", "bottega-esecutore-b-pi.yml"}


def test_giro_saltato_non_perde_lavori() -> None:
    # Review Focus 2: un giro saltato (es. quota esaurita) non perde niente:
    # il successivo trova gli stessi lavori pronti e li assegna.
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori", "esegue: c-claude"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```"),
    ])

    # Quota b-claude esaurita fino alle 15:00
    variabili_esaurita = {"BOTTEGA_QUOTA_B_CLAUDE": "esaurita fino a 2026-11-08T15:00:00+01:00"}

    # Primo giro: aspetta
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili_esaurita,
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    assert not any(r[0] == "prendi" for r in board.registro)

    # Secondo giro: adesso alle 15:30 (quota ripristinata)
    adesso_dopo = datetime(2026, 11, 8, 15, 30, tzinfo=fuso)
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili_esaurita,
        adesso=adesso_dopo,
        caso=random.Random(42),
        notte=False,
    )
    # Ora il lavoro viene preso!
    assert any(r[0] == "prendi" and r[1] == 1 for r in board.registro)


def test_precedente_e_attese() -> None:
    # se si aspetta, la nota guadagna attese+1 solo quando c'era un precedente.
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    # Caso 1: con precedente -> guadagna attese+1
    board1 = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Compito con precedente",
            stato="pronto",
            etichette=["bottega: fuori"],
            nota="precedente=c-claude; attese=0",
        )
    ])
    forgia1 = ForgiaFinta([
        Issue(numero=1, titolo="Compito con precedente", corpo="## Fatto quando\n```\npytest\n```")
    ])
    # Entrambi senza quota
    variabili_stop = {
        "BOTTEGA_QUOTA_B_CLAUDE": "esaurita fino a 2026-11-08T15:00:00+01:00",
        "BOTTEGA_QUOTA_B_PI": "esaurita fino a 2026-11-08T15:00:00+01:00",
    }

    distribuisci(
        configurazione=cfg,
        forgia=forgia1,
        board=board1,
        variabili=variabili_stop,
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    d1 = board1._trova_lavoro(1)
    assert d1 is not None
    assert "attese=1" in d1["nota"]

    # Caso 2: senza precedente -> NON guadagna attese
    board2 = BoardFinta([
        Lavoro(
            numero=2,
            titolo="Compito senza precedente",
            stato="pronto",
            etichette=["bottega: fuori"],
            nota="attese=0",
        )
    ])
    forgia2 = ForgiaFinta([
        Issue(numero=2, titolo="Compito senza precedente", corpo="## Fatto quando\n```\npytest\n```")
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia2,
        board=board2,
        variabili=variabili_stop,
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    d2 = board2._trova_lavoro(2)
    assert d2 is not None
    assert "attese=1" not in d2["nota"]


def test_etichetta_candidato_inesistente_blocca_lavoro() -> None:
    # se l'etichetta nomina un candidato che non esiste, bloccato col motivo
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito Fantasma", stato="pronto", etichette=["bottega: fuori", "esegue: fantasma"])
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito Fantasma", corpo="## Fatto quando\n```\npytest\n```")
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    # Il lavoro va a bloccato
    d = board._trova_lavoro(1)
    assert d is not None
    assert d["stato"] == "bloccato"
    assert "motivo=" in d["nota"]

    # Commento sul lavoro col segno distributore
    comm = forgia.commenti(1)
    assert len(comm) == 1
    assert "<!-- bottega:distributore -->" in comm[0].corpo
    assert "fantasma" in comm[0].corpo


def test_notte_e_lavori_liberi() -> None:
    cfg = _configurazione_base(liberi=("bug", "debito"))
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Lavoro Libero", stato="pronto", etichette=["bug"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Lavoro Libero", corpo="## Fatto quando\n```\npytest\n```", autore="alice")
    ])

    # Giorno (notte=False) -> non ha "bottega: fuori" né "esegue:" -> ignorato
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    assert not any(r[0] == "prendi" for r in board.registro)

    # Notte (notte=True) -> etichetta "bug" è in liberi -> preso!
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=True,
    )
    assert any(r[0] == "prendi" and r[1] == 1 for r in board.registro)


def test_senza_fatto_quando_non_e_pronto() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Senza Fatto Quando", stato="pronto", etichette=["bottega: fuori"])
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Senza Fatto Quando", corpo="Brief generico senza blocco di prova")
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )
    assert not any(r[0] == "prendi" for r in board.registro)


def test_tappa_con_sotto_issue() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    # Madre sulla board (numero 10)
    board = BoardFinta([
        Lavoro(numero=10, titolo="Tappa B3", stato="pronto", etichette=["bottega: fuori"])
    ])
    # Madre ha due sotto-issue: 11 (chiusa) e 12 (aperta, con Fatto quando)
    forgia = ForgiaFinta([
        Issue(numero=10, titolo="Tappa B3", corpo="Descrizione tappa"),
        Issue(numero=11, titolo="Task 1", corpo="Fatto", stato="CLOSED"),
        Issue(numero=12, titolo="Task 2", corpo="## Fatto quando\n```\npytest -q\n```", stato="OPEN"),
    ])
    forgia._sotto_issue[10] = [11, 12]

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    # Il lavoro preso sulla board è la madre 10
    prendi = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi) == 1
    assert prendi[0][1] == 10
    # Workflow lanciato per la madre 10
    assert len(forgia._workflow_avviati) == 1
    assert forgia._workflow_avviati[0][1] == {"lavoro": "10"}
    # Commento sul lavoro 10 con il ruolo distributore
    comm = forgia.commenti(10)
    assert len(comm) == 1
    assert "<!-- bottega:distributore -->" in comm[0].corpo


def test_cli_distribuisci_argomenti() -> None:
    from bottega.__main__ import costruisci_parser

    parser = costruisci_parser()
    args = parser.parse_args(["distribuisci", "--notte", "--file", "custom.toml"])
    assert args.comando == "distribuisci"
    assert args.notte is True
    assert args.file == "custom.toml"


def test_cli_comando_distribuisci_file_mancante(capsys) -> None:
    from bottega.__main__ import main

    codice = main(["distribuisci", "--file", "inesistente.toml"])
    assert codice == 1
    catturato = capsys.readouterr()
    assert "errore:" in catturato.err


def test_rv14_liberi_solo_se_autore_comandante() -> None:
    """RV14: Con liberi di notte, vengono presi solo issue il cui autore è un comandante."""
    cfg = _configurazione_base(liberi=("bug",))
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Bug da non-comandante", stato="pronto", etichette=["bug"]),
        Lavoro(numero=2, titolo="Bug da comandante", stato="pronto", etichette=["bug"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Bug da non-comandante", corpo="## Fatto quando\n```\npytest\n```", autore="sconosciuto"),
        Issue(numero=2, titolo="Bug da comandante", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=True,
    )

    presi = [r[1] for r in board.registro if r[0] == "prendi"]
    assert 1 not in presi
    assert 2 in presi


def test_rv13_evento_riprova(tmp_path: Path) -> None:
    """RV13 e C5: `/bottega riprova` di un comandante rimette a pronto e rilancia il distributore, senza prendere
    lavori in linea (l'evento di commento gira in un gruppo di concorrenza suo)."""
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="in attesa", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega riprova", "user": {"login": "alice"}},
    }), encoding="utf-8")

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
        percorso_evento=evento_file,
    )

    # 1. Deve aver commentato il riprova col segno
    comms = forgia.commenti(1)
    assert any("<!-- bottega:distributore -->" in c.corpo and "pronto" in c.corpo.lower() for c in comms)
    # 2. Deve aver rimesso a pronto, rilanciato il distributore e non preso niente in linea
    stati = [r for r in board.registro if r[0] == "stato"]
    assert any(s[1] == 1 and s[2] == "pronto" for s in stati)
    assert not any(r[0] == "prendi" for r in board.registro)
    assert ("avvia_workflow", "bottega-distributore.yml", {}) in forgia.registro


def test_rv13_evento_riprova_gia_in_corso(tmp_path: Path) -> None:
    """RV13: Se il lavoro è già in corso, riprova viene ignorato con commento col segno."""
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="in corso", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega riprova", "user": {"login": "alice"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
    )

    comms = forgia.commenti(1)
    assert any("<!-- bottega:distributore -->" in c.corpo and "in corso" in c.corpo.lower() for c in comms)
    # Non deve essere stato reimpostato a pronto
    stati = [r for r in board.registro if r[0] == "stato"]
    assert not any(s[1] == 1 and s[2] == "pronto" for s in stati)


def test_rv13_evento_sospendi(tmp_path: Path) -> None:
    """RV13: `/bottega sospendi <motivo>` mette il lavoro in attesa con nota e commento col segno."""
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega sospendi necessita chiarimenti", "user": {"login": "alice"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
    )

    # Stato impostato a "in attesa"
    stati = [r for r in board.registro if r[0] == "stato"]
    assert any(s[1] == 1 and s[2] == "in attesa" for s in stati)
    # Commento col segno presente
    comms = forgia.commenti(1)
    assert any("<!-- bottega:distributore -->" in c.corpo and "necessita chiarimenti" in c.corpo for c in comms)


def test_rv13_evento_consulta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RV13: `/bottega consulta <domanda>` lancia un consigliere sul runner e pubblica la risposta recintata."""
    # Candidato con runner e funzione consigliare
    cfg = _configurazione_base()
    candidati = dict(cfg.candidati)
    candidati["c-cons"] = Candidato(
        id="c-cons",
        nome="Consigliere",
        bottega="b-claude",
        porta="claude-code",
        modello="sonnet",
        funzioni=("consigliare",),
        runner="linux-runner",
    )
    from dataclasses import replace
    cfg = replace(cfg, candidati=candidati)

    monkeypatch.setenv("BOTTEGA_RUNNER", "linux-runner")

    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="Brief del compito 1", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega consulta Come procediamo con il test?", "user": {"login": "alice"}},
    }), encoding="utf-8")

    from bottega.porte import Controllo, Lancio

    chiamate_porta: list[dict] = []

    class PortaFinta:
        nome = "claude-code"
        eseguibile = "claude"
        def controlla(self): return Controllo(ok=True)
        def lancia(self, cartella, prompt, modello, *, conversazione=None, sola_lettura=False, prefisso=(), tempo=3600):
            # Verifica che il fascicolo minimo sia stato scritto nella cartella temporanea
            p_cartella = Path(cartella)
            assert (p_cartella / "fascicolo.md").is_file()
            chiamate_porta.append({"cartella": cartella, "prompt": prompt, "sola_lettura": sola_lettura})
            return Lancio(esito="fatto", testo="Suggerisco di usare pytest con un mock.", conversazione=None, rinnovo=None, contatori={})

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
        porte={"claude-code": PortaFinta()},
    )

    assert len(chiamate_porta) == 1
    assert chiamate_porta[0]["sola_lettura"] is True

    comms = forgia.commenti(1)
    assert len(comms) == 1
    assert "<!-- bottega:consigliere -->" in comms[0].corpo
    # RV6: risposta racchiusa in blocco recintato
    assert "```" in comms[0].corpo
    assert "Suggerisco di usare pytest con un mock." in comms[0].corpo


def test_rv13_evento_consulta_senza_consigliere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RV13: `/bottega consulta` senza consigliere sul runner lascia un commento che lo dice."""
    cfg = _configurazione_base()
    monkeypatch.setenv("BOTTEGA_RUNNER", "diverso-runner")

    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="Brief del compito 1", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega consulta Come procediamo?", "user": {"login": "alice"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
    )

    comms = forgia.commenti(1)
    assert len(comms) == 1
    assert "<!-- bottega:distributore -->" in comms[0].corpo
    assert "nessun consigliere" in comms[0].corpo.lower()


def test_rv13_evento_commento_da_non_comandante_o_col_segno(tmp_path: Path) -> None:
    """RV13: Commenti da non comandanti o con il segno della bottega non eseguono comandi."""
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="in attesa", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    # Commento con comando ma da autore non comandante (bob)
    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega riprova", "user": {"login": "bob"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
    )

    # Nessun commento lasciato sul compito da parte del distributore
    assert len(forgia.commenti(1)) == 0


def test_rv18_comando_distribuisci_shlex_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RV18: comando_distribuisci usa shlex.split per l'adattatore."""
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text("""versione = 1
[progetto]
fuso = "Europe/Rome"
project = 1
adattatore = "mio_comando --opzione valore"
[botteghe.b1]
quota = "normale"
porte = ["pi"]
[candidati.c1]
nome = "C1"
bottega = "b1"
porta = "pi"
modello = "m1"
funzioni = ["decidere", "eseguire"]
runner = "linux"
""", encoding="utf-8")

    chiamate_board: list[list[str]] = []
    from bottega.board import BoardComando
    orig_init = BoardComando.__init__
    def mock_init(self, comando):
        chiamate_board.append(list(comando))
        orig_init(self, comando)

    monkeypatch.setattr(BoardComando, "__init__", mock_init)
    from bottega.__main__ import main
    main(["distribuisci", "--file", str(cfg_file)])
    assert len(chiamate_board) >= 1
    assert chiamate_board[0] == ["mio_comando", "--opzione", "valore"]


def test_rv18_distribuisci_errore_senza_traccia(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """RV18: Nessun comando esce con una traccia (ErroreBoard -> messaggio ed esito 1)."""
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text("""versione = 1
[progetto]
fuso = "Europe/Rome"
project = 1
adattatore = "cmd"
[botteghe.b1]
quota = "normale"
porte = ["pi"]
[candidati.c1]
nome = "C1"
bottega = "b1"
porta = "pi"
modello = "m1"
funzioni = ["decidere", "eseguire"]
runner = "linux"
""", encoding="utf-8")

    from bottega import distributore as dist_module
    from bottega.board import ErroreBoard
    def mock_distribuisci(*args, **kwargs):
        raise ErroreBoard("GitHub Project non raggiungibile")

    monkeypatch.setattr(dist_module, "distribuisci", mock_distribuisci)
    from bottega.__main__ import main
    codice = main(["distribuisci", "--file", str(cfg_file)])
    assert codice == 1
    catturato = capsys.readouterr()
    assert "errore: GitHub Project non raggiungibile" in catturato.err
    assert "Traceback" not in catturato.err


def test_c4_riprova_azzera_i_contatori(tmp_path: Path) -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    nota_iniziale = "ramo=bottega/1-x;tentativi=3;attese=2;motivo=errore"
    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="in attesa", etichette=["bottega: fuori"], nota=nota_iniziale),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])
    forgia.imposta_stato_ci(forgia.ramo_principale(), "rosso")

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega riprova", "user": {"login": "alice"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
        percorso_evento=evento_file,
    )

    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "pronto"
    assert lav.nota == "ramo=bottega/1-x"


def test_c4_consulta_col_prefisso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace
    from bottega.porte import Controllo, Lancio

    cfg = _configurazione_base()
    candidati = dict(cfg.candidati)
    candidati["c-cons"] = Candidato(
        id="c-cons",
        nome="Consigliere",
        bottega="b-claude",
        porta="claude-code",
        modello="sonnet",
        funzioni=("consigliare",),
        runner="linux-runner",
    )
    cfg = replace(cfg, candidati=candidati)

    monkeypatch.setenv("BOTTEGA_RUNNER", "linux-runner")

    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="Brief del compito 1", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega consulta Come procediamo?", "user": {"login": "alice"}},
    }), encoding="utf-8")

    chiamate_porta: list[dict[str, Any]] = []

    class PortaFintaCons:
        nome = "claude-code"
        eseguibile = "claude"
        def controlla(self, prefisso=()): return Controllo(ok=True)
        def lancia(self, cartella, prompt, modello, *, conversazione=None, sola_lettura=False, prefisso=(), tempo=3600):
            chiamate_porta.append({"prefisso": prefisso, "sola_lettura": sola_lettura})
            return Lancio(esito="fatto", testo="Risposta consiglio")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        percorso_evento=evento_file,
        porte={"claude-code": PortaFintaCons()},
        prefisso=("env",),
    )

    assert len(chiamate_porta) == 1
    assert chiamate_porta[0]["prefisso"] == ("env",)


def test_c5_autore_estraneo_anche_con_etichetta() -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Compito Estraneo Etichettato",
            stato="pronto",
            etichette=["bottega: fuori"],
        )
    ])
    forgia = ForgiaFinta([
        Issue(
            numero=1,
            titolo="Compito Estraneo Etichettato",
            corpo="## Fatto quando\n```\ntrue\n```",
            autore="estraneo",
        )
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    assert not any(r[0] == "prendi" and r[1] == 1 for r in board.registro)


def test_c5_scadenza_conta_tentativi() -> None:
    from bottega.segni import nota

    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 18, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(
            numero=10,
            titolo="Compito Scaduto Tentativi",
            stato="in corso",
            esecutore="c-claude",
            nota="inizio=2026-11-08T10:00:00+01:00;tentativi=2",
            etichette=["bottega: fuori"],
        )
    ])
    forgia = ForgiaFinta([
        Issue(numero=10, titolo="Compito Scaduto Tentativi", corpo="## Fatto quando\n```\npytest\n```")
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
    )

    lav = board.lavoro(10)
    assert lav is not None
    assert lav.stato == "bloccato"
    valori = nota(lav.nota)
    assert valori.get("tentativi") == "3"


def test_c5_commento_senza_comando_non_distribuisce(tmp_path: Path) -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=fuso)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="pronto", etichette=["bottega: fuori"]),
        Lavoro(numero=2, titolo="Compito 2", stato="pronto", etichette=["bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
        Issue(numero=2, titolo="Compito 2", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "grazie", "user": {"login": "alice"}},
    }), encoding="utf-8")

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(42),
        notte=False,
        percorso_evento=evento_file,
    )

    assert not any(r[0] == "prendi" for r in board.registro)









def test_c6_riprova_azzera_anche_le_quote(tmp_path: Path) -> None:
    cfg = _configurazione_base()
    fuso = ZoneInfo(cfg.progetto.fuso)
    board = BoardFinta([
        Lavoro(numero=1, titolo="Compito 1", stato="bloccato", etichette=["bottega: fuori"],
               nota="ramo=bottega/1-x;quote=3;motivo=quota ripetuta"),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Compito 1", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])
    evento_file = tmp_path / "evento.json"
    evento_file.write_text(json.dumps({
        "action": "created",
        "issue": {"number": 1},
        "comment": {"body": "/bottega riprova", "user": {"login": "alice"}},
    }), encoding="utf-8")
    distribuisci(
        configurazione=cfg, forgia=forgia, board=board, variabili={},
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=fuso), caso=random.Random(42), notte=False,
        percorso_evento=evento_file,
    )
    lav = board.lavoro(1)
    assert lav is not None and lav.stato == "pronto"
    assert lav.nota == "ramo=bottega/1-x"
