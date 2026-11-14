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
from bottega.quota import disponibile, nome_variabile, valore_esaurita
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
    cfg, compito_base, risultati_base, quote_map_base, adesso = dati

    # Quote passate sia per id della bottega sia come BOTTEGA_QUOTA_<ID>
    quote_map: dict[str, str | None] = {}
    for b_id, val in quote_map_base.items():
        stile = estrazione.draw(st.sampled_from(["id", "variabile", "entrambi"]))
        if stile in ("id", "entrambi"):
            quote_map[b_id] = val
        if stile in ("variabile", "entrambi"):
            quote_map[nome_variabile(b_id)] = val

    # Risultati anche per etichette specifiche
    risultati = dict(risultati_base)
    for c_id in cfg.candidati:
        for et in compito_base.etichette:
            u = estrazione.draw(st.integers(min_value=0, max_value=10))
            cr = estrazione.draw(st.integers(min_value=0, max_value=5))
            rf = estrazione.draw(st.integers(min_value=0, max_value=5))
            risultati[(c_id, et)] = Risultati(u, cr, rf)

    precedente = estrazione.draw(st.one_of(st.none(), st.sampled_from(list(cfg.candidati))), label="precedente")
    giri = estrazione.draw(st.integers(min_value=0, max_value=2), label="giri")

    # Genera anche esegue
    ha_esegue = estrazione.draw(st.booleans(), label="ha_esegue")
    esegue_attr: str | None = None
    etichette = set(compito_base.etichette)
    if ha_esegue:
        nomi_candidati = [c.id for c in cfg.candidati.values()] + [c.nome for c in cfg.candidati.values()]
        nome_esegue = estrazione.draw(
            st.one_of(st.sampled_from(nomi_candidati), st.text(min_size=1, max_size=10, alphabet="abcdef-"))
        )
        in_attr = estrazione.draw(st.booleans())
        if in_attr:
            esegue_attr = nome_esegue
        else:
            etichette.add(f"esegue: {nome_esegue}")

    compito = Compito(
        funzione=compito_base.funzione,
        fuori=compito_base.fuori,
        etichette=frozenset(etichette),
        esegue=esegue_attr,
        precedente=precedente,
        giri_in_attesa=giri,
    )
    caso = random.Random(seme)
    scelta = scegli(compito, cfg, risultati, quote_map, adesso, caso)

    if scelta.candidato is not None:
        cand = cfg.candidati[scelta.candidato]
        val_quota = quote_map.get(cand.bottega)
        if val_quota is None:
            val_quota = quote_map.get(nome_variabile(cand.bottega))
        ha_q, _ = disponibile(val_quota, adesso)
        assert ha_q is True, f"Candidato {cand.id} scelto ma quota non disponibile (valore: {val_quota})"


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
    # Il nome dell'etichetta: candidato vero (per id o nome, maiuscole/minuscole), o inesistente
    veri = [c.id for c in cfg.candidati.values()] + [c.nome.upper() for c in cfg.candidati.values()]
    nome_esegue = estrazione.draw(
        st.one_of(st.sampled_from(veri), st.text(min_size=1, max_size=15, alphabet="abcdef-012")), label="esegue"
    )

    in_campo = estrazione.draw(st.booleans(), label="in_campo")
    etichette = set(compito_base.etichette)
    # Rimuovi eventuali altre etichette esegue: generate in precedenza
    etichette = {e for e in etichette if not e.lower().startswith("esegue:")}
    if in_campo:
        compito = Compito(
            funzione=compito_base.funzione,
            fuori=compito_base.fuori,
            etichette=frozenset(etichette),
            esegue=nome_esegue,
        )
    else:
        etichette.add(f"esegue: {nome_esegue}")
        compito = Compito(
            funzione=compito_base.funzione,
            fuori=compito_base.fuori,
            etichette=frozenset(etichette),
            esegue=None,
        )

    caso = random.Random(seme)
    scelta = scegli(compito, cfg, risultati, quote_map, adesso, caso)

    # Ricerca attesa: prima per id (senza maiuscole), poi per nome (senza maiuscole)
    nome_cf = nome_esegue.casefold()
    trovato = next((c for c in cfg.candidati.values() if c.id.casefold() == nome_cf), None)
    if trovato is None:
        trovato = next((c for c in cfg.candidati.values() if c.nome.casefold() == nome_cf), None)

    idoneo = (
        trovato is not None and compito.funzione in trovato.funzioni and (not compito.fuori or bool(trovato.runner))
    )

    if trovato is not None and idoneo:
        val_q = quote_map.get(trovato.bottega)
        if val_q is None:
            val_q = quote_map.get(nome_variabile(trovato.bottega))
        ha_q, _ = disponibile(val_q, adesso)
        if ha_q:
            # 1. trovato, idoneo e con quota
            assert scelta.candidato == trovato.id
            assert scelta.aspetta is False
        else:
            # 2. trovato e idoneo ma senza quota
            assert scelta.candidato is None
            assert scelta.aspetta is True
    else:
        # 3. assente o non idoneo
        assert scelta.candidato is None
        assert scelta.aspetta is False


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

    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--fuori",
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
            "--seme",
            "1",
        ]
    )
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

    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--esegue",
            "persona-misteriosa",
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 1
    catturato = capsys.readouterr()
    riga = catturato.out.strip()
    assert "\t" in riga
    primo, perche = riga.split("\t", 1)
    assert primo == "nessuno"
    assert "persona-misteriosa" in perche


def test_cli_scegli_file_non_trovato_esce_2(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--file",
            "file-che-non-esiste.toml",
        ]
    )
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
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--fuori",
            "--quote",
            str(f_quote),
            "--risultati",
            str(f_risultati),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 0
    catturato = capsys.readouterr()
    riga = catturato.out.strip()
    primo, perche = riga.split("\t", 1)
    assert primo == "aspetta"
    assert "aspetta" in perche


# --- Nuove prove sulle correzioni della revisione finale ---


def test_mutante_etichetta_esegue_con_quota_sceglie_davvero() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito_attr = Compito(funzione="eseguire", fuori=False, esegue="lavorante")
    scelta_attr = scegli(compito_attr, cfg, {}, {}, adesso, random.Random(1))
    assert scelta_attr.candidato == "lavorante"
    assert scelta_attr.aspetta is False

    compito_et = Compito(funzione="eseguire", fuori=False, etichette=frozenset({"esegue: lavorante"}))
    scelta_et = scegli(compito_et, cfg, {}, {}, adesso, random.Random(1))
    assert scelta_et.candidato == "lavorante"
    assert scelta_et.aspetta is False


def test_nessun_candidato_ha_la_funzione_restituisce_aspetta_false() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="consigliare", fuori=False)
    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert "nessun candidato per la funzione «consigliare»" in scelta.perche


def test_nessun_candidato_ha_runner_per_compito_fuori_restituisce_aspetta_false() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    # maestro sa decidere ma non ha runner
    compito = Compito(funzione="decidere", fuori=True)
    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert "nessun candidato per la funzione «decidere» fuori" in scelta.perche


def test_cli_scegli_nessun_candidato_idoneo_esce_1(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    codice = main(
        [
            "scegli",
            "--funzione",
            "consigliare",
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 1
    catturato = capsys.readouterr()
    primo, perche = catturato.out.strip().split("\t", 1)
    assert primo == "nessuno"
    assert "nessun candidato per la funzione «consigliare»" in perche


def test_due_etichette_esegue_diverse_in_conflitto() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, etichette=frozenset({"esegue: maestro", "esegue: lavorante"}))
    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert scelta.perche == "etichette esegue in conflitto: lavorante, maestro"


def test_conflitto_fra_attributo_esegue_ed_etichetta() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, esegue="lavorante", etichette=frozenset({"esegue: maestro"}))
    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert scelta.perche == "etichette esegue in conflitto: lavorante, maestro"


def test_conflitto_esegue_non_dipende_dall_ordine_del_frozenset() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    c1 = Compito(funzione="eseguire", fuori=False, etichette=frozenset({"esegue: zorro", "esegue: alfa"}))
    c2 = Compito(funzione="eseguire", fuori=False, etichette=frozenset({"esegue: alfa", "esegue: zorro"}))
    s1 = scegli(c1, cfg, {}, {}, adesso, random.Random(1))
    s2 = scegli(c2, cfg, {}, {}, adesso, random.Random(1))
    assert s1.perche == s2.perche == "etichette esegue in conflitto: alfa, zorro"


def test_etichette_esegue_stesso_candidato_non_conflitto() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=False, esegue="lavorante", etichette=frozenset({"esegue: LAVORANTE"}))
    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato == "lavorante"
    assert scelta.aspetta is False


def test_scelta_etichetta_cerca_prima_per_id_poi_per_nome() -> None:
    # Candidato 1 ha id="c1" e nome="c2"
    # Candidato 2 ha id="c2" e nome="c3"
    progetto = Progetto(("admin",), None, "Europe/Rome", None, ())
    botteghe = {"b": Bottega("b", "abbondante", ("porta",))}
    candidati = {
        "c1": Candidato("c1", "c2", "b", "porta", "mod", ("eseguire",), None),
        "c2": Candidato("c2", "c3", "b", "porta", "mod", ("eseguire",), None),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)

    # Ricerca per "c2" (o "C2"): deve trovare il candidato con id="c2", non quello con nome="c2" (c1)
    compito_id = Compito(funzione="eseguire", fuori=False, esegue="C2")
    scelta_id = scegli(compito_id, cfg, {}, {}, adesso, random.Random(1))
    assert scelta_id.candidato == "c2"

    # Ricerca per "c3": nessun candidato ha id="c3", trova per nome (c2)
    compito_nome = Compito(funzione="eseguire", fuori=False, esegue="c3")
    scelta_nome = scegli(compito_nome, cfg, {}, {}, adesso, random.Random(1))
    assert scelta_nome.candidato == "c2"


def test_cli_scegli_json_risultati_non_oggetto_esce_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    f = tmp_path / "risultati.json"
    f.write_text("[1, 2, 3]")
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--risultati",
            str(f),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_cli_scegli_json_risultati_sotto_oggetti_non_oggetti_esce_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f = tmp_path / "risultati.json"
    f.write_text(json.dumps({"lavorante": [1, 2]}))
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--risultati",
            str(f),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_cli_scegli_json_risultati_conteggi_booleani_esce_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    f = tmp_path / "risultati.json"
    f.write_text(json.dumps({"lavorante": {"*": {"uniti": True}}}))
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--risultati",
            str(f),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_cli_scegli_json_risultati_conteggi_negativi_esce_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    f = tmp_path / "risultati.json"
    f.write_text(json.dumps({"lavorante": {"*": {"uniti": -1}}}))
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--risultati",
            str(f),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_cli_scegli_json_quote_non_oggetto_esce_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    f = tmp_path / "quote.json"
    f.write_text('"non un dizionario"')
    codice = main(
        ["scegli", "--funzione", "eseguire", "--quote", str(f), "--file", "plugin/skills/bottega/modelli/bottega.toml"]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_cli_scegli_json_quote_valori_non_stringa_o_null_esce_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f = tmp_path / "quote.json"
    f.write_text(json.dumps({"secondaria": 123}))
    codice = main(
        ["scegli", "--funzione", "eseguire", "--quote", str(f), "--file", "plugin/skills/bottega/modelli/bottega.toml"]
    )
    assert codice == 2
    catturato = capsys.readouterr()
    assert "errore" in catturato.err.lower()


def test_avvisi_quota_in_fondo_al_perche_separati() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    # Valore malformato per la bottega secondaria
    quote = {"secondaria": "valore non riconosciuto"}
    compito = Compito(funzione="eseguire", fuori=False)
    scelta = scegli(compito, cfg, {}, quote, adesso, random.Random(1))
    assert "; avviso: " in scelta.perche
    assert "valore della quota non riconosciuto: «valore non riconosciuto»" in scelta.perche


def test_cli_scegli_stampa_avvisi_quota_su_stderr_uno_per_bottega(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f = tmp_path / "quote.json"
    f.write_text(json.dumps({"secondaria": "quota corrotta"}))
    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--quote",
            str(f),
            "--file",
            "plugin/skills/bottega/modelli/bottega.toml",
        ]
    )
    assert codice == 0
    catturato = capsys.readouterr()
    assert "avviso: secondaria:" in catturato.err or "avviso:" in catturato.err
    assert "quota corrotta" in catturato.err
    assert "; avviso: " in catturato.out
    assert "quota corrotta" in catturato.out


# --- B12.2: secchi di quota e candidati di riserva ---


def _cfg_con_secchi(
    secchi: tuple[tuple[str, str], ...] = (("a", "normale"), ("b", "normale")),
    riserva_b: bool = False,
) -> Configurazione:
    progetto = Progetto(("admin",), None, "UTC", None, ())
    botteghe = {"google": Bottega("google", "", ("porta",), quote=secchi)}
    candidati = {
        "c-a": Candidato("c-a", "Cand A", "google", "porta", "mod-a", ("eseguire",), "linux-x64", quota="a"),
        "c-b": Candidato(
            "c-b",
            "Cand B",
            "google",
            "porta",
            "mod-b",
            ("eseguire",),
            "linux-x64",
            quota="b",
            riserva=riserva_b,
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def test_secchio_esaurito_ferma_solo_i_suoi() -> None:
    cfg = _cfg_con_secchi()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    # Il secchio "a" è esaurito: si ferma solo il suo candidato (la bottega intera: B12-R5bis, prove sotto)
    quote = {nome_variabile("google", "a"): valore_esaurita(adesso + timedelta(hours=1))}
    compito = Compito(funzione="eseguire", fuori=True)
    for seme in range(20):
        scelta = scegli(compito, cfg, {}, quote, adesso, random.Random(seme))
        assert scelta.candidato == "c-b"
        assert scelta.aspetta is False


def test_peso_del_secchio_nel_costo() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "google": Bottega("google", "", ("porta",), quote=(("a", "abbondante"), ("b", "scarsa"))),
    }
    candidati = {
        "c-abbondante": Candidato("c-abbondante", "A", "google", "porta", "m", ("eseguire",), None, quota="a"),
        "c-scarsa": Candidato("c-scarsa", "S", "google", "porta", "m", ("eseguire",), None, quota="b"),
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
    assert percentuale > 0.70, f"Percentuale abbondante {percentuale} <= 70%"


def test_vecchia_variabile_blocca_ancora() -> None:
    cfg = _configurazione_di_base()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    quote = {nome_variabile("secondaria"): valore_esaurita(adesso + timedelta(hours=1))}
    compito = Compito(funzione="eseguire", fuori=True)

    scelta = scegli(compito, cfg, {}, quote, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is True
    assert "aspetta" in scelta.perche


def test_riserva_mai_scelta_coi_normali() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "google": Bottega("google", "", ("porta",), quote=(("a", "scarsa"), ("b", "abbondante"))),
    }
    candidati = {
        "normale": Candidato("normale", "Normale", "google", "porta", "m1", ("eseguire",), "r", quota="a"),
        "riserva": Candidato(
            "riserva",
            "Riserva",
            "google",
            "porta",
            "m2",
            ("eseguire",),
            "r",
            quota="b",
            riserva=True,
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=True)
    # Anche con storia ottima e quota abbondante, la riserva non viene mai scelta coi normali
    risultati = {("riserva", "*"): Risultati(uniti=20, corretti=0, rifiutati=0)}

    for seme in range(100):
        scelta = scegli(compito, cfg, risultati, {}, adesso, random.Random(seme))
        assert scelta.candidato == "normale"
        assert scelta.aspetta is False
        assert not scelta.perche.startswith("di riserva: ")


def test_riserva_scelta_senza_normali() -> None:
    cfg = _cfg_con_secchi(riserva_b=True)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    quote = {nome_variabile("google", "a"): valore_esaurita(adesso + timedelta(hours=1))}
    compito = Compito(funzione="eseguire", fuori=True)

    scelta = scegli(compito, cfg, {}, quote, adesso, random.Random(1))
    assert scelta.candidato == "c-b"
    assert scelta.aspetta is False
    assert scelta.perche.startswith("di riserva: ")


def test_tutti_di_riserva() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {"b": Bottega("b", "normale", ("porta",))}
    candidati = {
        "r1": Candidato("r1", "R1", "b", "porta", "m1", ("eseguire",), "r", riserva=True),
        "r2": Candidato("r2", "R2", "b", "porta", "m2", ("eseguire",), "r", riserva=True),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=True)

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato in ("r1", "r2")
    assert scelta.aspetta is False
    assert scelta.perche.startswith("di riserva: ")


def test_esegue_sceglie_la_riserva() -> None:
    cfg = _cfg_con_secchi(riserva_b=True)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)

    scelta_attr = scegli(
        Compito(funzione="eseguire", fuori=True, esegue="c-b"),
        cfg,
        {},
        {},
        adesso,
        random.Random(1),
    )
    assert scelta_attr.candidato == "c-b"
    assert scelta_attr.aspetta is False

    scelta_et = scegli(
        Compito(funzione="eseguire", fuori=True, etichette=frozenset({"esegue: Cand B"})),
        cfg,
        {},
        {},
        adesso,
        random.Random(1),
    )
    assert scelta_et.candidato == "c-b"
    assert scelta_et.aspetta is False


def test_precedente_di_riserva_torna_ai_normali() -> None:
    cfg = _cfg_con_secchi(riserva_b=True)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    # Il precedente è di riserva ("c-b"), ma "c-a" (normale) ha di nuovo quota
    compito = Compito(funzione="eseguire", fuori=True, precedente="c-b", giri_in_attesa=0)

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato == "c-a"
    assert scelta.aspetta is False
    assert not scelta.perche.startswith("di riserva: ")

    # Se invece il normale non ha ancora quota nemmeno dopo un'attesa, la riserva resta eleggibile
    quote_a_esaurita = {nome_variabile("google", "a"): valore_esaurita(adesso + timedelta(hours=1))}
    compito_atteso = Compito(funzione="eseguire", fuori=True, precedente="c-b", giri_in_attesa=1)
    scelta_atteso = scegli(compito_atteso, cfg, {}, quote_a_esaurita, adesso, random.Random(1))
    assert scelta_atteso.candidato == "c-b"
    assert scelta_atteso.aspetta is False
    assert scelta_atteso.perche.startswith("di riserva: ")


def test_avvisi_quote_sui_secchi_nominano_la_variabile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(
        """versione = 1

[progetto]
fuso = "UTC"

[botteghe.google]
quote = { argon = "scarsa", gemini = "abbondante" }
porte = ["antigravity"]

[candidati.maestro]
nome = "Maestro"
bottega = "google"
porta = "antigravity"
modello = "m-argon"
quota = "argon"
funzioni = ["decidere"]

[candidati.lavorante]
nome = "Lavorante"
bottega = "google"
porta = "antigravity"
modello = "m-gemini"
quota = "gemini"
funzioni = ["eseguire"]
""",
        encoding="utf-8",
    )
    f_quote = tmp_path / "quote.json"
    f_quote.write_text(json.dumps({"BOTTEGA_QUOTA_GOOGLE__ARGON": "valore rotto"}), encoding="utf-8")

    codice = main(
        [
            "scegli",
            "--funzione",
            "eseguire",
            "--quote",
            str(f_quote),
            "--file",
            str(cfg_file),
            "--seme",
            "1",
        ]
    )
    assert codice == 0
    catturato = capsys.readouterr()
    assert "avviso: BOTTEGA_QUOTA_GOOGLE__ARGON:" in catturato.err
    assert "valore rotto" in catturato.err
    assert "; avviso: BOTTEGA_QUOTA_GOOGLE__ARGON:" in catturato.out
    assert "valore rotto" in catturato.out


@settings(max_examples=200)
@given(seme=st.integers(min_value=0, max_value=10000), estrazione=st.data())
def test_proprieta_cancello_riserva_e_secchi(seme: int, estrazione: st.DataObject) -> None:
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    secchi = (("a", "abbondante"), ("b", "scarsa"))
    botteghe = {"google": Bottega("google", "", ("porta",), quote=secchi)}
    quote_map: dict[str, str | None] = {}
    for s, _ in secchi:
        var = nome_variabile("google", s)
        if estrazione.draw(st.booleans()):
            quote_map[var] = valore_esaurita(adesso + timedelta(hours=1))
        else:
            quote_map[var] = None

    candidati: dict[str, Candidato] = {}
    n_cand = estrazione.draw(st.integers(min_value=1, max_value=5))
    for i in range(n_cand):
        cid = f"c-{i}"
        secchio = estrazione.draw(st.sampled_from(["a", "b"]))
        riserva = estrazione.draw(st.booleans())
        fn = estrazione.draw(st.sampled_from(["eseguire", "consigliare"]))
        candidati[cid] = Candidato(
            cid,
            f"Cand {i}",
            "google",
            "porta",
            "mod",
            (fn, "decidere") if i == 0 else (fn,),
            "runner-1",
            quota=secchio,
            riserva=riserva,
        )

    cfg = Configurazione(1, Progetto(("admin",), None, "UTC", None, ()), botteghe, candidati)
    esegue = estrazione.draw(st.one_of(st.none(), st.sampled_from(list(candidati))))
    precedente = estrazione.draw(st.one_of(st.none(), st.sampled_from(list(candidati))))
    giri = estrazione.draw(st.integers(min_value=0, max_value=2))
    compito = Compito(
        funzione="eseguire",
        fuori=True,
        esegue=esegue,
        precedente=precedente,
        giri_in_attesa=giri,
    )

    scelta = scegli(compito, cfg, {}, quote_map, adesso, random.Random(seme))
    if scelta.candidato is not None:
        scelto = cfg.candidati[scelta.candidato]
        ha_q, _ = disponibile(quote_map.get(nome_variabile(scelto.bottega, scelto.quota)), adesso)
        assert ha_q is True
        if esegue is None:
            normali_con_quota = [
                c
                for c in cfg.candidati.values()
                if "eseguire" in c.funzioni
                and not c.riserva
                and disponibile(quote_map.get(nome_variabile(c.bottega, c.quota)), adesso)[0]
                and not (precedente == c.id and giri >= 1)
            ]
            # Se un normale non escluso ha quota, non si sceglie una riserva
            if normali_con_quota:
                assert scelto.riserva is False
                assert not scelta.perche.startswith("di riserva: ")


def test_bottega_intera_esaurita_ferma_i_secchi() -> None:
    cfg = _cfg_con_secchi()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    quote = {nome_variabile("google"): valore_esaurita(adesso + timedelta(hours=1))}
    scelta = scegli(Compito(funzione="eseguire", fuori=False), cfg, {}, quote, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is True


def test_chiave_della_bottega_ferma_i_secchi() -> None:
    cfg = _cfg_con_secchi()
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    quote = {"google": valore_esaurita(adesso + timedelta(hours=1))}
    scelta = scegli(Compito(funzione="eseguire", fuori=False), cfg, {}, quote, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is True


def test_su_richiesta_mai_scelto_dalla_scelta_viva() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "google": Bottega("google", "", ("porta",), quote=(("a", "scarsa"), ("b", "abbondante"))),
    }
    candidati = {
        "normale": Candidato("normale", "Normale", "google", "porta", "m1", ("eseguire",), "r", quota="a"),
        "riserva": Candidato(
            "riserva", "Riserva", "google", "porta", "m2", ("eseguire",), "r", quota="a", riserva=True
        ),
        "richiesta": Candidato(
            "richiesta",
            "Orchestratore",
            "google",
            "porta",
            "m3",
            ("eseguire",),
            "r",
            quota="b",
            su_richiesta=True,
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=True)
    risultati = {("richiesta", "*"): Risultati(uniti=20, corretti=0, rifiutati=0)}

    for seme in range(100):
        scelta = scegli(compito, cfg, risultati, {}, adesso, random.Random(seme))
        assert scelta.candidato == "normale"
        assert scelta.aspetta is False

    # Anche quando normale e riserva sono esauriti e richiesta è l'unico con quota, non viene scelto
    quote_a_esaurita = {nome_variabile("google", "a"): valore_esaurita(adesso + timedelta(hours=1))}
    for seme in range(100):
        scelta = scegli(compito, cfg, risultati, quote_a_esaurita, adesso, random.Random(seme))
        assert scelta.candidato is None
        assert scelta.aspetta is True


def test_su_richiesta_scelto_con_esegue() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "google": Bottega("google", "", ("porta",), quote=(("a", "scarsa"), ("b", "abbondante"))),
    }
    candidati = {
        "normale": Candidato("normale", "Normale", "google", "porta", "m1", ("eseguire",), "r", quota="a"),
        "richiesta": Candidato(
            "richiesta",
            "Orchestratore",
            "google",
            "porta",
            "m3",
            ("eseguire",),
            "r",
            quota="b",
            su_richiesta=True,
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)

    scelta_attr = scegli(
        Compito(funzione="eseguire", fuori=True, esegue="richiesta"), cfg, {}, {}, adesso, random.Random(1)
    )
    assert scelta_attr.candidato == "richiesta"
    assert scelta_attr.aspetta is False

    scelta_et = scegli(
        Compito(funzione="eseguire", fuori=True, etichette=frozenset({"esegue: Orchestratore"})),
        cfg,
        {},
        {},
        adesso,
        random.Random(1),
    )
    assert scelta_et.candidato == "richiesta"
    assert scelta_et.aspetta is False

    quote_b_esaurita = {nome_variabile("google", "b"): valore_esaurita(adesso + timedelta(hours=1))}
    scelta_attesa = scegli(
        Compito(funzione="eseguire", fuori=True, esegue="richiesta"),
        cfg,
        {},
        quote_b_esaurita,
        adesso,
        random.Random(1),
    )
    assert scelta_attesa.candidato is None
    assert scelta_attesa.aspetta is True


def test_solo_su_richiesta_nessun_candidato() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {"google": Bottega("google", "normale", ("porta",))}
    candidati = {
        "richiesta": Candidato(
            "richiesta", "Orchestratore", "google", "porta", "m3", ("eseguire",), "r", su_richiesta=True
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)

    scelta = scegli(Compito(funzione="eseguire", fuori=True), cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato is None
    assert scelta.aspetta is False
    assert "nessun candidato per la funzione «eseguire»" in scelta.perche


def test_precedente_su_richiesta_non_ereditato() -> None:
    progetto = Progetto(("a",), None, "UTC", None, ())
    botteghe = {
        "google": Bottega("google", "", ("porta",), quote=(("a", "normale"), ("b", "normale"))),
    }
    candidati = {
        "normale": Candidato("normale", "Normale", "google", "porta", "m1", ("eseguire",), "r", quota="a"),
        "richiesta": Candidato(
            "richiesta",
            "Orchestratore",
            "google",
            "porta",
            "m3",
            ("eseguire",),
            "r",
            quota="b",
            su_richiesta=True,
        ),
    }
    cfg = Configurazione(1, progetto, botteghe, candidati)
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    compito = Compito(funzione="eseguire", fuori=True, precedente="richiesta", giri_in_attesa=0)

    scelta = scegli(compito, cfg, {}, {}, adesso, random.Random(1))
    assert scelta.candidato == "normale"
    assert scelta.aspetta is False

    # Anche con il secchio del precedente su_richiesta esaurito, non aspetta e sceglie subito il normale
    quote_b_esaurita = {nome_variabile("google", "b"): valore_esaurita(adesso + timedelta(hours=1))}
    scelta_subito = scegli(compito, cfg, {}, quote_b_esaurita, adesso, random.Random(1))
    assert scelta_subito.candidato == "normale"
    assert scelta_subito.aspetta is False


