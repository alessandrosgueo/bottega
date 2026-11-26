"""Prove del distributore per B15: scala sui fallimenti, ritmo dei riempitivi e bozze di piano di notte."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo

from bottega.board import Lavoro
from bottega.configurazione import (
    Bottega,
    Candidato,
    Configurazione,
    Progetto,
    Ritmo,
    variabile_della_quota,
)
from bottega.distributore import distribuisci
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.quota import PuntoQuota, formatta_punti, nome_variabile_punti, valore_esaurita


def _cfg_b15(
    *,
    scala: tuple[str, ...] = ("c-med", "c-high", "c-spec"),
    aree_non_delicate: tuple[str, ...] = ("debito", "prove", "docs"),
    bozze_piano: int = 3,
    con_pianificatore: bool = True,
) -> Configurazione:
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso="Europe/Rome",
        notte="02:00",
        manutenzione=(),
        project=1,
        liberi=("bug", "debito"),
        scala=scala,
        aree_non_delicate=aree_non_delicate,
        bozze_piano=bozze_piano,
    )
    botteghe = {
        "google": Bottega(id="google", quota="abbondante", porte=("antigravity",)),
        "b-claude": Bottega(id="b-claude", quota="scarsa", porte=("claude-code",)),
    }
    candidati: dict[str, Candidato] = {
        "c-med": Candidato(
            id="c-med",
            nome="Esecutore Medio",
            bottega="google",
            porta="antigravity",
            modello="modello-medio",
            funzioni=("eseguire",),
            runner="linux",
        ),
        "c-high": Candidato(
            id="c-high",
            nome="Esecutore Forte",
            bottega="google",
            porta="antigravity",
            modello="modello-forte",
            funzioni=("eseguire",),
            runner="linux",
            riserva=True,
        ),
        "c-spec": Candidato(
            id="c-spec",
            nome="Esecutore Speciale",
            bottega="google",
            porta="antigravity",
            modello="modello-speciale",
            funzioni=("eseguire",),
            runner="linux",
            su_richiesta=True,
        ),
        "c-claude": Candidato(
            id="c-claude",
            nome="Claude",
            bottega="b-claude",
            porta="claude-code",
            modello="claude-3-7-sonnet",
            funzioni=("eseguire", "decidere"),
            runner="linux",
            riserva=True,
        ),
    }
    if con_pianificatore:
        candidati["c-plan"] = Candidato(
            id="c-plan",
            nome="Pianificatore",
            bottega="google",
            porta="antigravity",
            modello="modello-pianificatore",
            funzioni=("pianificare",),
            runner="linux",
        )
    return Configurazione(
        versione=1,
        progetto=progetto,
        botteghe=botteghe,
        candidati=candidati,
        ritmo=Ritmo(gruppo="Gemini Models", ritardo=15, riserva_5h=30, riserva_settimana=15),
    )


def test_distributore_usa_prossimo_gradino_dopo_salita() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))

    # Gradino 1 -> prende c-high (riserva=True)
    board1 = BoardFinta([
        Lavoro(numero=1, titolo="Compito", stato="pronto", etichette=["bottega: fuori"], nota="gradino=1"),
    ])
    forgia1 = ForgiaFinta([
        Issue(numero=1, titolo="Compito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia1,
        board=board1,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )
    lav1 = board1.lavoro(1)
    assert lav1 is not None
    assert lav1.esecutore == "Esecutore Forte"
    assert "gradino=1" in lav1.nota

    # Gradino 2 -> prende c-spec (su_richiesta=True)
    board2 = BoardFinta([
        Lavoro(numero=2, titolo="Compito 2", stato="pronto", etichette=["bottega: fuori"], nota="gradino=2"),
    ])
    forgia2 = ForgiaFinta([
        Issue(numero=2, titolo="Compito 2", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia2,
        board=board2,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )
    lav2 = board2.lavoro(2)
    assert lav2 is not None
    assert lav2.esecutore == "Esecutore Speciale"
    assert "gradino=2" in lav2.nota

    # Gradino len(scala) -> scala esaurita -> bloccato
    board3 = BoardFinta([
        Lavoro(numero=3, titolo="Compito 3", stato="pronto", etichette=["bottega: fuori"], nota="gradino=3"),
    ])
    forgia3 = ForgiaFinta([
        Issue(numero=3, titolo="Compito 3", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia3,
        board=board3,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )
    lav3 = board3.lavoro(3)
    assert lav3 is not None
    assert lav3.stato == "bloccato"
    assert "scala esaurita" in lav3.nota
    assert any("scala esaurita" in c.corpo for c in forgia3.commenti(3))


def test_distributore_esegue_vince_su_gradino() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Forzato",
            stato="pronto",
            etichette=["bottega: fuori", "esegue: c-claude"],
            nota="gradino=1",
        ),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Forzato", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
    )

    lav = board.lavoro(1)
    assert lav is not None
    assert lav.esecutore == "Claude"
    assert ("avvia_workflow", "bottega-esecutore-b-claude.yml", {"lavoro": "1"}) in forgia.registro


def test_riprova_azzera_gradino_e_modo(tmp_path: Path) -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    board = BoardFinta([
        Lavoro(
            numero=1,
            titolo="Bloccato",
            stato="bloccato",
            etichette=["bottega: fuori"],
            nota="tentativi=2; gradino=2; modo=pianifica; motivo=fallito",
        ),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Bloccato", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    evento_file = tmp_path / "evento.json"
    evento_file.write_text(
        json.dumps({
            "action": "created",
            "issue": {"number": 1},
            "comment": {"body": "/bottega riprova", "user": {"login": "alice"}},
        }),
        encoding="utf-8",
    )

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        percorso_evento=evento_file,
    )

    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "pronto"
    assert "gradino=" not in lav.nota
    assert "modo=" not in lav.nota
    assert "tentativi=" not in lav.nota
    assert "motivo=" not in lav.nota


def _variabile_punti(adesso: datetime, *, settimana: int, cinque_ore: int) -> dict[str, str]:
    adesso_utc = adesso.astimezone(timezone.utc)
    # 3.5 giorni passati su 7 -> atteso_speso = 50.0%
    rinnovo_settimana = adesso_utc + timedelta(days=3, hours=12)
    rinnovo_5h = adesso_utc + timedelta(hours=2)
    punti = {
        "Gemini Models": PuntoQuota(
            gruppo="Gemini Models",
            settimana=settimana,
            rinnovo_settimana=rinnovo_settimana,
            cinque_ore=cinque_ore,
            rinnovo_cinque_ore=rinnovo_5h,
        )
    }
    return {nome_variabile_punti("google"): formatta_punti(punti, adesso_utc)}


def test_distributore_riempitivo_quando_ritmo_indietro() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    # settimana residua 75% (speso 25% vs 50% atteso -> ritardo 25 >= 15), 5h al 60%
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=60)

    board = BoardFinta([
        Lavoro(numero=10, titolo="Aggiorna guida", stato="pronto", etichette=["docs"]),
        Lavoro(numero=11, titolo="Aggiungi test", stato="pronto", etichette=["prove"]),
        Lavoro(numero=12, titolo="Sistema debito", stato="pronto", etichette=["debito"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=10, titolo="Aggiorna guida", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
        Issue(numero=11, titolo="Aggiungi test", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
        Issue(numero=12, titolo="Sistema debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    prendi = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi) == 1
    assert prendi[0][1] == 12
    lav12 = board.lavoro(12)
    assert lav12 is not None
    assert lav12.esecutore == "Esecutore Medio"
    assert "riempitivo=1" in lav12.nota
    assert "gradino=0" in lav12.nota
    assert ("avvia_workflow", "bottega-esecutore-google.yml", {"lavoro": "12"}) in forgia.registro
    assert any("fascia 0" in c.corpo and "25" in c.corpo for c in forgia.commenti(12))


def test_distributore_riempitivo_fermo_sotto_riserva_5h() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=20)

    board = BoardFinta([
        Lavoro(numero=12, titolo="Sistema debito", stato="pronto", etichette=["debito"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=12, titolo="Sistema debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    assert not any(r[0] == "prendi" for r in board.registro)
    assert forgia._workflow_avviati == []


def test_distributore_riempitivo_non_scavalca_lavoro_ordinario() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=60)

    board = BoardFinta([
        Lavoro(numero=1, titolo="Lavoro ordinario", stato="pronto", etichette=["bottega: fuori"]),
        Lavoro(numero=2, titolo="Debito riempitivo", stato="pronto", etichette=["debito"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Lavoro ordinario", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
        Issue(numero=2, titolo="Debito riempitivo", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    prendi = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi) == 1
    assert prendi[0][1] == 1
    assert forgia._workflow_avviati == [("bottega-esecutore-google.yml", {"lavoro": "1"})]


def test_distributore_bozza_di_piano_di_notte_anche_nel_delicato() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 2, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))

    board = BoardFinta([
        Lavoro(numero=1, titolo="Nuova funzione cuore", stato="pronto", etichette=["cuore", "bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Nuova funzione cuore", corpo="Idea di modifica al cuore senza piano.", autore="alice"),
    ])

    # Di giorno resta saltata
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )
    assert not any(r[0] == "prendi" for r in board.registro)

    # Di notte viene presa dal candidato pianificare anche nel delicato
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=True,
    )
    prendi = [r for r in board.registro if r[0] == "prendi"]
    assert len(prendi) == 1
    assert prendi[0][1] == 1
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.esecutore == "Pianificatore"
    assert "modo=pianifica" in lav.nota
    assert ("avvia_workflow", "bottega-esecutore-google.yml", {"lavoro": "1"}) in forgia.registro



def test_distributore_niente_bozza_di_piano_senza_etichetta() -> None:
    # B15-R8: la bottega pianifica di notte solo i lavori che le sono stati affidati («bottega: fuori» o `liberi`).
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 2, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    board = BoardFinta([
        Lavoro(numero=1, titolo="Idea non affidata", stato="pronto", etichette=["cuore"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Idea non affidata", corpo="Idea senza piano.", autore="alice"),
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=True,
    )
    assert not any(r[0] == "prendi" for r in board.registro)
    assert forgia._workflow_avviati == []

def test_distributore_tetto_tre_bozze_di_piano() -> None:
    cfg = _cfg_b15(bozze_piano=3)
    adesso = datetime(2026, 11, 26, 2, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))

    board = BoardFinta([
        Lavoro(numero=1, titolo="Bozza 1", stato="consegnato", etichette=["bottega: bozza di piano"]),
        Lavoro(numero=2, titolo="Bozza 2", stato="in attesa", etichette=["Bottega: Bozza di Piano"]),
        Lavoro(numero=3, titolo="Bozza 3", stato="in corso", esecutore="Pianificatore", nota="modo=pianifica"),
        Lavoro(numero=4, titolo="Quarta idea", stato="pronto", etichette=["cuore", "bottega: fuori"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=1, titolo="Bozza 1", corpo="Idea 1", autore="alice"),
        Issue(numero=2, titolo="Bozza 2", corpo="Idea 2", autore="alice"),
        Issue(numero=3, titolo="Bozza 3", corpo="Idea 3", autore="alice"),
        Issue(numero=4, titolo="Quarta idea", corpo="Idea 4 senza piano", autore="alice"),
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili={},
        adesso=adesso,
        caso=random.Random(1),
        notte=True,
    )

    assert not any(r[0] == "prendi" for r in board.registro)
    assert forgia._workflow_avviati == []
    assert any("bozze di piano al tetto (3/3)" in r for r in righe)


def test_riempitivo_fallito_riparte_dal_suo_gradino() -> None:
    cfg = _cfg_b15()
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=60)

    board = BoardFinta([
        Lavoro(
            numero=12,
            titolo="Sistema debito",
            stato="pronto",
            etichette=["debito"],
            nota="riempitivo=1; gradino=1",
        ),
        Lavoro(
            numero=13,
            titolo="Altro debito",
            stato="pronto",
            etichette=["debito"],
            nota="gradino=non_intero",
        ),
    ])
    forgia = ForgiaFinta([
        Issue(numero=12, titolo="Sistema debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
        Issue(numero=13, titolo="Altro debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    lav12 = board.lavoro(12)
    assert lav12 is not None
    assert lav12.esecutore == "Esecutore Forte"
    assert "gradino=1" in lav12.nota

    # Con gradino non intero riparte da 0
    board2 = BoardFinta([
        Lavoro(
            numero=13,
            titolo="Altro debito",
            stato="pronto",
            etichette=["debito"],
            nota="gradino=boh",
        ),
    ])
    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board2,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )
    lav13 = board2.lavoro(13)
    assert lav13 is not None
    assert lav13.esecutore == "Esecutore Medio"
    assert "gradino=0" in lav13.nota


def test_riempitivo_con_scala_senza_quota_non_ripiega() -> None:
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo("Europe/Rome"))
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso="Europe/Rome",
        notte="02:00",
        manutenzione=(),
        project=1,
        liberi=("bug", "debito"),
        scala=("c-med", "c-high"),
        aree_non_delicate=("debito",),
    )
    botteghe = {
        "google": Bottega(
            id="google",
            quota="",
            quote=(("gemini", "abbondante"), ("altro", "abbondante")),
            porte=("antigravity",),
        ),
        "altra": Bottega(id="altra", quota="abbondante", porte=("claude-code",)),
    }
    c_med = Candidato(
        id="c-med",
        nome="Esecutore Medio",
        bottega="google",
        porta="antigravity",
        modello="modello-medio",
        funzioni=("eseguire",),
        runner="linux",
        quota="gemini",
    )
    c_high = Candidato(
        id="c-high",
        nome="Esecutore Forte",
        bottega="google",
        porta="antigravity",
        modello="modello-forte",
        funzioni=("eseguire",),
        runner="linux",
        riserva=True,
        quota="gemini",
    )
    c_alt = Candidato(
        id="c-alt",
        nome="Altro Google",
        bottega="google",
        porta="antigravity",
        modello="modello-alt",
        funzioni=("eseguire",),
        runner="linux",
        quota="altro",
    )
    cfg = Configurazione(
        versione=1,
        progetto=progetto,
        botteghe=botteghe,
        candidati={"c-med": c_med, "c-high": c_high, "c-alt": c_alt},
        ritmo=Ritmo(gruppo="Gemini Models", ritardo=15, riserva_5h=30, riserva_settimana=15),
    )
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=60)
    variabili[variabile_della_quota(c_med)] = valore_esaurita(adesso + timedelta(hours=1))

    board = BoardFinta([
        Lavoro(numero=12, titolo="Sistema debito", stato="pronto", etichette=["debito"]),
    ])
    forgia = ForgiaFinta([
        Issue(numero=12, titolo="Sistema debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    assert not any(r[0] == "prendi" for r in board.registro)
    assert forgia._workflow_avviati == []


def test_riempitivo_a_scala_esaurita_va_a_chi_decide() -> None:
    cfg = _cfg_b15(scala=("c-med", "c-high"))
    adesso = datetime(2026, 11, 26, 12, 0, tzinfo=ZoneInfo(cfg.progetto.fuso))
    variabili = _variabile_punti(adesso, settimana=75, cinque_ore=60)

    board = BoardFinta([
        Lavoro(
            numero=12,
            titolo="Sistema debito",
            stato="pronto",
            etichette=["debito"],
            nota="riempitivo=1; gradino=2",
        ),
    ])
    forgia = ForgiaFinta([
        Issue(numero=12, titolo="Sistema debito", corpo="## Fatto quando\n```\npytest\n```", autore="alice"),
    ])

    righe = distribuisci(
        configurazione=cfg,
        forgia=forgia,
        board=board,
        variabili=variabili,
        adesso=adesso,
        caso=random.Random(1),
        notte=False,
    )

    assert not any(r[0] == "prendi" for r in board.registro)
    assert forgia._workflow_avviati == []
    lav12 = board.lavoro(12)
    assert lav12 is not None
    assert lav12.stato == "bloccato"
    assert "scala esaurita" in lav12.nota
    assert "lavoro 12: scala esaurita, a chi decide" in righe
