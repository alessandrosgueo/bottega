"""Prove della scelta viva: proprietà del cancello con hypothesis, costo atteso e CLI."""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.quota import valore_esaurita
from bottega.scelta import Compito, Risultati, Scelta, argomenti_scegli, comando_scegli, scegli


def _configurazione_di_base() -> Configurazione:
    progetto = Progetto(
        comandanti=("alice",),
        adattatore=None,
        fuso="Europe/Rome",
        notte="01:30",
        manutenzione=(),
    )
    botteghe = {
        "principale": Bottega("principale", "scarsa", ("claude-code",)),
        "secondaria": Bottega("secondaria", "abbondante", ("pi",)),
    }
    candidati = {
        "maestro": Candidato(
            id="maestro",
            nome="Maestro Claude",
            bottega="principale",
            porta="claude-code",
            modello="claude-3-opus",
            funzioni=("decidere", "rivedere"),
            runner=None,
        ),
        "lavorante": Candidato(
            id="lavorante",
            nome="Lavorante Pi",
            bottega="secondaria",
            porta="pi",
            modello="modello-lavorante",
            funzioni=("eseguire",),
            runner="linux-x64",
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


# --- Strategie Hypothesis per le proprietà del cancello ---

@st.composite
def strategie_scenario(draw: st.DrawFn) -> tuple[Configurazione, Compito, dict, dict, datetime]:
    fuso = timezone.utc
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=fuso)

    quote_nomi = ["scarsa", "normale", "abbondante"]
    n_botteghe = draw(st.integers(min_value=1, max_value=3))
    botteghe: dict[str, Bottega] = {}
    quote_map: dict[str, str | None] = {}

    for i in range(n_botteghe):
        b_id = f"b-{i}"
        q_tipo = draw(st.sampled_from(quote_nomi))
        botteghe[b_id] = Bottega(b_id, q_tipo, ("porta-1",))
        # Quota disponibile o esaurita
        esaurita = draw(st.booleans())
        if esaurita:
            fino_a = adesso + timedelta(hours=draw(st.integers(min_value=1, max_value=24)))
            quote_map[b_id] = valore_esaurita(fino_a)
        else:
            quote_map[b_id] = None

    tutte_funzioni = ["decidere", "eseguire", "rivedere", "consigliare"]
    n_candidati = draw(st.integers(min_value=1, max_value=5))
    candidati: dict[str, Candidato] = {}
    for i in range(n_candidati):
        c_id = f"c-{i}"
        b_scelta = draw(st.sampled_from(list(botteghe.keys())))
        fns = draw(st.lists(st.sampled_from(tutte_funzioni), min_size=1, unique=True))
        ha_runner = draw(st.booleans())
        candidati[c_id] = Candidato(
            id=c_id,
            nome=f"Nome {c_id}",
            bottega=b_scelta,
            porta="porta-1",
            modello="mod-1",
            funzioni=tuple(fns),
            runner="runner-1" if ha_runner else None,
        )

    # Assicura almeno un decisore
    if not any("decidere" in c.funzioni for c in candidati.values()):
        primo = list(candidati.keys())[0]
        candidati[primo] = Candidato(
            id=primo,
            nome=candidati[primo].nome,
            bottega=candidati[primo].bottega,
            porta=candidati[primo].porta,
            modello=candidati[primo].modello,
            funzioni=candidati[primo].funzioni + ("decidere",),
            runner=candidati[primo].runner,
        )

    cfg = Configurazione(
        versione=1,
        progetto=Progetto(("admin",), None, "UTC", None, ()),
        botteghe=botteghe,
        candidati=candidati,
    )

    funzione_compito = draw(st.sampled_from(tutte_funzioni))
    fuori = draw(st.booleans())
    etichette = draw(st.sets(st.text(min_size=1, max_size=10, alphabet="abcdef-"), max_size=3))

    compito = Compito(
        funzione=funzione_compito,
        fuori=fuori,
        etichette=frozenset(etichette),
    )

    # Risultati
    risultati: dict[tuple[str, str], Risultati] = {}
    for c_id in candidati:
        u = draw(st.integers(min_value=0, max_value=20))
        c_val = draw(st.integers(min_value=0, max_value=10))
        r = draw(st.integers(min_value=0, max_value=10))
        risultati[(c_id, "*")] = Risultati(u, c_val, r)

    return cfg, compito, risultati, quote_map, adesso


@settings(max_examples=200)
@given(dati=strategie_scenario(), seme=st.integers(min_value=0, max_value=10000), estrazione=st.data())
def test_proprieta_cancello_1_candidato_ha_sempre_quota(
    dati: tuple[Configurazione, Compito, dict, dict, datetime],
    seme: int,
    estrazione: st.DataObject,
) -> None:
    cfg, compito_base, risultati, quote_map, adesso = dati
    # Anche col precedente della tappa e coi giri d'attesa: il candidato scelto ha sempre quota.
    precedente = estrazione.draw(st.one_of(st.none(), st.sampled_from(list(cfg.candidati))), label="precedente")
    compito = Compito(
        funzione=compito_base.funzione,
        fuori=compito_base.fuori,
        etichette=compito_base.etichette,
        precedente=precedente,
        giri_in_attesa=estrazione.draw(st.integers(min_value=0, max_value=2), label="giri"),
    )
    caso = random.Random(seme)
    scelta = scegli(compito, cfg, risultati, quote_map, adesso, caso)

    if scelta.candidato is not None:
        cand = cfg.candidati[scelta.candidato]
        val_quota = quote_map.get(cand.bottega)
        # Se c'è un valore di quota, non deve essere nel futuro
        if val_quota and val_quota.startswith("esaurita fino a "):
            fino_a = datetime.fromisoformat(val_quota[len("esaurita fino a ") :])
            assert adesso >= fino_a, f"Candidato {cand.id} scelto ma quota esaurita fino a {fino_a}"


@settings(max_examples=200)
@given(
    dati=strategie_scenario(),
    seme=st.integers(min_value=0, max_value=10000),
    estrazione=st.data(),
)
def test_proprieta_cancello_2_etichetta_esegue_mai_un_altro(
    dati: tuple[Configurazione, Compito, dict, dict, datetime],
    seme: int,
    estrazione: st.DataObject,
) -> None:
    cfg, compito_base, risultati, quote_map, adesso = dati
    # Il nome dell'etichetta: quasi sempre un candidato vero (per id o per nome, in un'altra maiuscola), a volte no.
    veri = [c.id for c in cfg.candidati.values()] + [c.nome.upper() for c in cfg.candidati.values()]
    nome_esegue = estrazione.draw(
        st.one_of(st.sampled_from(veri), st.text(min_size=1, max_size=15, alphabet="abcdef-012")), label="esegue"
    )
    # Aggiungi esegue
    compito = Compito(
        funzione=compito_base.funzione,
        fuori=compito_base.fuori,
        etichette=compito_base.etichette,
        esegue=nome_esegue,
    )
    caso = random.Random(seme)
    scelta = scegli(compito, cfg, risultati, quote_map, adesso, caso)

    # La scelta può essere solo il candidato corrispondente a nome_esegue (per id o nome) oppure None
    trovato = None
    for c in cfg.candidati.values():
        if c.id.casefold() == nome_esegue.casefold() or c.nome.casefold() == nome_esegue.casefold():
            trovato = c
            break

    if scelta.candidato is not None:
        assert trovato is not None
        assert scelta.candidato == trovato.id
    else:
        # Nessun candidato scelto: aspetta o esce per candidato inesistente/incompatibile
        assert scelta.candidato is None


# --- Prove puntuali sui casi d'uso ---

def test_precedente_con_quota_scelto() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, precedente="lavorante")

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato == "lavorante"
    assert scelta.aspetta is False
    assert "precedente" in scelta.perche


def test_precedente_senza_quota_aspetta_al_giro_0_e_sceglie_altro_al_giro_1() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    # Entrambi sanno eseguire in sessione
    candidati = dict(cfg.candidati)
    candidati["maestro"] = Candidato(
        id="maestro",
        nome="Maestro",
        bottega="principale",
        porta="claude-code",
        modello="m",
        funzioni=("decidere", "eseguire"),
        runner=None,
    )
    cfg2 = Configurazione(1, cfg.progetto, cfg.botteghe, candidati)

    # lavorante ha quota esaurita
    quote = {"secondaria": valore_esaurita(adesso + timedelta(hours=2))}

    # Giro 0: aspetta
    compito_giro_0 = Compito(funzione="eseguire", fuori=False, precedente="lavorante", giri_in_attesa=0)
    scelta_0 = scegli(compito_giro_0, cfg2, {}, quote, adesso, random.Random(1))
    assert scelta_0.candidato is None
    assert scelta_0.aspetta is True
    assert "aspetta" in scelta_0.perche

    # Giro 1: sceglie fra gli altri (maestro)
    compito_giro_1 = Compito(funzione="eseguire", fuori=False, precedente="lavorante", giri_in_attesa=1)
    scelta_1 = scegli(compito_giro_1, cfg2, {}, quote, adesso, random.Random(1))
    assert scelta_1.candidato == "maestro"
    assert scelta_1.aspetta is False


def test_etichetta_sconosciuta_dice_il_motivo_e_non_sceglie() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, esegue="inesistente")

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert "inesistente" in scelta.perche


def test_etichette_senza_risultati_usano_totale_asterisco() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, etichette=frozenset({"nuova-etichetta"}))

    risultati = {
        ("lavorante", "*"): Risultati(uniti=10, corretti=1, rifiutati=0),
    }
    scelta = scegli(compito, cfg, risultati, {}, adesso, random.Random(1))
    assert scelta.candidato == "lavorante"
    assert "11 risultati" in scelta.perche


def test_stesso_seme_stessa_scelta() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="decidere", fuori=False)

    scelta_a = scegli(compito, cfg, {}, {}, adesso, random.Random(42))
    scelta_b = scegli(compito, cfg, {}, {}, adesso, random.Random(42))
    assert scelta_a.candidato == scelta_b.candidato
    assert scelta_a.perche == scelta_b.perche


def test_perche_contiene_id_scelto_e_decimali_con_virgola() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False)

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato == "lavorante"
    assert "lavorante" in scelta.perche
    assert "," in scelta.perche
    assert "\n" not in scelta.perche


def test_quota_abbondante_vince_su_scarsa_nella_maggioranza_dei_semi() -> None:
    # Review Focus 3: Senza dati, la quota abbondante vince su quella scarsa nella grande maggioranza dei semi
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "b-scarsa": Bottega("b-scarsa", "scarsa", ("porta",)),
        "b-abbondante": Bottega("b-abbondante", "abbondante", ("porta",)),
    }
    candidati = {
        "c-scarsa": Candidato("c-scarsa", "S", "b-scarsa", "porta", "m", ("eseguire",), None),
        "c-abbondante": Candidato("c-abbondante", "A", "b-abbondante", "porta", "m", ("eseguire",), None),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False)

    vittorie_abbondante = 0
    semi_totali = 500
    for s in range(semi_totali):
        scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(s))
        if scelta.candidato == "c-abbondante":
            vittorie_abbondante += 1

    percentuale = vittorie_abbondante / semi_totali
    # Teorico ~ 75%
    assert percentuale > 0.70, f"Percentuale abbondante {percentuale} <= 70%"


def test_candidato_con_20_uniti_batte_uno_con_20_rifiutati_piu_del_95_percento() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "b": Bottega("b", "normale", ("porta",)),
    }
    candidati = {
        "bravo": Candidato("bravo", "Bravo", "b", "porta", "m", ("eseguire",), None),
        "scarso": Candidato("scarso", "Scarso", "b", "porta", "m", ("eseguire",), None),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False)

    risultati = {
        ("bravo", "*"): Risultati(uniti=20, corretti=0, rifiutati=0),
        ("scarso", "*"): Risultati(uniti=0, corretti=0, rifiutati=20),
    }

    vittorie_bravo = 0
    semi_totali = 200
    for s in range(semi_totali):
        scelta = scegli(compito, cfg, risultati, {}, adesso, random.Random(s))
        if scelta.candidato == "bravo":
            vittorie_bravo += 1

    percentuale = vittorie_bravo / semi_totali
    assert percentuale > 0.95, f"Percentuale bravo {percentuale} <= 95%"


def test_nessun_candidato_con_quota_aspetta() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    quote = {
        "secondaria": valore_esaurita(adesso + timedelta(hours=1)),
    }
    compito = Compito(funzione="eseguire", fuori=False)
    scelta = scegli(compito, cfg, {}, quote, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is True
    assert "aspetta" in scelta.perche


# --- Prove CLI scegli ---

def test_cli_scegli_fatto_quando(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    codice = main([
        "scegli",
        "--funzione", "eseguire",
        "--fuori",
        "--file", "plugin/skills/bottega/modelli/bottega.toml",
        "--seme", "1",
    ])
    assert codice == 0
    catturato = capsys.readouterr()
    riga = catturato.out.strip()
    assert "\t" in riga
    id_scelto, perche = riga.split("\t", 1)
    assert id_scelto == "lavorante"
    assert "lavorante" in perche
    assert "," in perche


def test_cli_scegli_etichetta_inesistente_esce_1(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    codice = main([
        "scegli",
        "--funzione", "eseguire",
        "--esegue", "persona-misteriosa",
        "--file", "plugin/skills/bottega/modelli/bottega.toml",
    ])
    assert codice == 1
    catturato = capsys.readouterr()
    riga = catturato.out.strip()
    assert "\t" in riga
    primo, perche = riga.split("\t", 1)
    assert primo == "nessuno"
    assert "persona-misteriosa" in perche


def test_cli_scegli_file_non_trovato_esce_2(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    codice = main([
        "scegli",
        "--funzione", "eseguire",
        "--file", "file-che-non-esiste.toml",
    ])
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower() or "file non trovato" in catturato.err.lower()


def test_cli_scegli_con_json_quote_e_risultati(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    f_quote = tmp_path / "quote.json"
    adesso = datetime.now(timezone.utc)
    # secondaria esaurita
    f_quote.write_text(json.dumps({"secondaria": valore_esaurita(adesso + timedelta(hours=1))}))

    f_risultati = tmp_path / "risultati.json"
    f_risultati.write_text(json.dumps({"lavorante": {"*": {"uniti": 5, "corretti": 0, "rifiutati": 0}}}))

    # Con secondaria esaurita, lavorante non ha quota -> aspetta
    codice = main([
        "scegli",
        "--funzione", "eseguire",
        "--fuori",
        "--quote", str(f_quote),
        "--risultati", str(f_risultati),
        "--file", "plugin/skills/bottega/modelli/bottega.toml",
    ])
    assert codice == 0
    catturato = capsys.readouterr()
    riga = catturato.out.strip()
    primo, perche = riga.split("\t", 1)
    assert primo == "aspetta"
    assert "aspetta" in perche

