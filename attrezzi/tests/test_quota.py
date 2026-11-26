"""Prove dello stato della quota di una bottega: variabile di Actions, formati e disponibilità."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bottega.quota import (
    PREFISSO_PUNTI,
    PuntoQuota,
    analizza_uscita_quota,
    differenza_punti,
    disponibile,
    formatta_punti,
    leggi_punti,
    nome_variabile,
    nome_variabile_punti,
    valore_esaurita,
)


def test_nome_variabile_converte_in_maiuscolo_e_trattini_in_trattini_bassi() -> None:
    assert nome_variabile("principale") == "BOTTEGA_QUOTA_PRINCIPALE"
    assert nome_variabile("secondaria-2") == "BOTTEGA_QUOTA_SECONDARIA_2"
    assert nome_variabile("a-b-c") == "BOTTEGA_QUOTA_A_B_C"


def test_nome_variabile_col_secchio() -> None:
    assert nome_variabile("google", "argon") == "BOTTEGA_QUOTA_GOOGLE__ARGON"
    assert nome_variabile("a-b", "c-d") == "BOTTEGA_QUOTA_A_B__C_D"
    assert nome_variabile("google") == "BOTTEGA_QUOTA_GOOGLE"


def test_secchio_e_bottega_omonimi_non_si_scontrano() -> None:
    assert nome_variabile("google-argon") != nome_variabile("google", "argon")


def test_valore_esaurita_richiede_fuso_orario() -> None:
    ingenuo = datetime(2026, 11, 8, 18, 0, 0)
    with pytest.raises(ValueError, match="fuso orario"):
        valore_esaurita(ingenuo)


def test_disponibile_richiede_fuso_in_adesso() -> None:
    ingenuo = datetime(2026, 11, 8, 18, 0, 0)
    with pytest.raises(ValueError, match="fuso orario"):
        disponibile("esaurita fino a 2026-11-08T19:00:00+01:00", ingenuo)


def test_disponibile_con_valore_assente_o_vuoto() -> None:
    adesso = datetime.now(timezone.utc)
    assert disponibile(None, adesso) == (True, None)
    assert disponibile("", adesso) == (True, None)
    assert disponibile("   ", adesso) == (True, None)


def test_disponibile_valore_esaurita_inversa() -> None:
    fuso = ZoneInfo("Europe/Rome")
    adesso = datetime(2026, 11, 8, 14, 0, 0, tzinfo=fuso)

    nel_futuro = adesso + timedelta(hours=2)
    valore_futuro = valore_esaurita(nel_futuro)
    assert disponibile(valore_futuro, adesso) == (False, None)

    nel_passato = adesso - timedelta(minutes=10)
    valore_passato = valore_esaurita(nel_passato)
    assert disponibile(valore_passato, adesso) == (True, None)

    stesso_istante = adesso
    valore_uguale = valore_esaurita(stesso_istante)
    assert disponibile(valore_uguale, adesso) == (True, None)


def test_disponibile_valore_scritto_male_non_ferma_la_bottega() -> None:
    # Review Focus 5: un valore che non si capisce vale «disponibile» con avviso
    adesso = datetime(2026, 11, 8, 14, 0, 0, tzinfo=timezone.utc)

    # Data senza fuso
    ok, avviso = disponibile("esaurita fino a 2026-11-08T15:00:00", adesso)
    assert ok is True
    assert avviso is not None
    assert "senza fuso" in avviso.lower() or "fuso" in avviso.lower()

    # Testo non comprensibile
    ok, avviso = disponibile("bloccata fino a domani", adesso)
    assert ok is True
    assert avviso is not None

    # Formato data errato
    ok, avviso = disponibile("esaurita fino a data_sbagliata", adesso)
    assert ok is True
    assert avviso is not None

    # Valore che non è una stringa (numero, booleano, lista)
    ok, avviso = disponibile(123, adesso)  # type: ignore[arg-type]
    assert ok is True
    assert avviso is not None
    assert "non è una stringa" in avviso.lower() or "stringa" in avviso.lower()

    ok, avviso = disponibile(True, adesso)  # type: ignore[arg-type]
    assert ok is True
    assert avviso is not None



@given(
    delta_secondi=st.integers(min_value=-86400, max_value=86400),
    offset_minuti=st.integers(min_value=-720, max_value=720),
)
def test_proprieta_inversa_valore_esaurita_e_disponibile(delta_secondi: int, offset_minuti: int) -> None:
    fuso = timezone(timedelta(minutes=offset_minuti))
    adesso = datetime(2026, 11, 8, 12, 0, 0, tzinfo=fuso)
    fino_a = adesso + timedelta(seconds=delta_secondi)

    valore = valore_esaurita(fino_a)
    ok, avviso = disponibile(valore, adesso)
    assert avviso is None
    if delta_secondi > 0:
        assert ok is False
    else:
        assert ok is True


def test_nome_variabile_punti() -> None:
    assert PREFISSO_PUNTI == "BOTTEGA_PUNTI_"
    assert nome_variabile_punti("google") == "BOTTEGA_PUNTI_GOOGLE"
    assert nome_variabile_punti("google-pro") == "BOTTEGA_PUNTI_GOOGLE_PRO"


def test_analizza_uscita_quota_tsv() -> None:
    uscita = (
        "Quota:\n"
        "Gemini Models\tWeekly Limit Remaining\t86%\t2026-12-02T15:21:03Z\n"
        "Gemini Models\tFive Hour Limit Remaining\t47%\t2026-12-01T18:00:00Z\n"
        "Claude and GPT models\tWeekly Limit Remaining\t100%\t1970-01-01T00:00:00Z\n"
        "Claude and GPT models\tFive Hour Limit Remaining\t100%\t1970-01-01T00:00:00Z\n"
    )
    punti = analizza_uscita_quota(uscita)
    assert set(punti) == {"Gemini Models", "Claude and GPT models"}

    gem = punti["Gemini Models"]
    assert gem.gruppo == "Gemini Models"
    assert gem.settimana == 86
    assert gem.rinnovo_settimana == datetime(2026, 12, 2, 15, 21, 3, tzinfo=timezone.utc)
    assert gem.cinque_ore == 47
    assert gem.rinnovo_cinque_ore == datetime(2026, 12, 1, 18, 0, 0, tzinfo=timezone.utc)
    assert gem.rinnovo_settimana.tzinfo is timezone.utc
    assert gem.rinnovo_cinque_ore.tzinfo is timezone.utc

    cg = punti["Claude and GPT models"]
    assert cg.settimana == 100
    assert cg.cinque_ore == 100
    assert cg.rinnovo_settimana == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_formatta_e_leggi_punti_roundtrip() -> None:
    rilevato = datetime(2026, 12, 1, 12, 0, 0, tzinfo=timezone.utc)
    punti = {
        "Gemini Models": PuntoQuota(
            gruppo="Gemini Models",
            settimana=86,
            rinnovo_settimana=datetime(2026, 12, 2, 15, 21, 3, tzinfo=timezone.utc),
            cinque_ore=47,
            rinnovo_cinque_ore=datetime(2026, 12, 1, 18, 0, 0, tzinfo=timezone.utc),
        ),
    }
    testo = formatta_punti(punti, rilevato)
    ril_letto, punti_letti = leggi_punti(testo)
    assert ril_letto == rilevato
    assert punti_letti == punti

    assert leggi_punti(None) == (None, {})
    assert leggi_punti("") == (None, {})
    assert leggi_punti("{non valido") == (None, {})
    assert leggi_punti("[]") == (None, {})


def test_differenza_punti() -> None:
    t1 = datetime(2026, 12, 2, 15, 21, 3, tzinfo=timezone.utc)
    t2 = datetime(2026, 12, 1, 18, 0, 0, tzinfo=timezone.utc)
    prima = {
        "Gemini Models": PuntoQuota("Gemini Models", 86, t1, 47, t2),
        "Invariato": PuntoQuota("Invariato", 100, t1, 100, t2),
        "SoloPrima": PuntoQuota("SoloPrima", 90, t1, 80, t2),
    }
    dopo = {
        "Gemini Models": PuntoQuota("Gemini Models", 80, t1, 40, t2),
        "Invariato": PuntoQuota("Invariato", 100, t1, 100, t2),
        "SoloDopo": PuntoQuota("SoloDopo", 50, t1, 50, t2),
    }
    diff = differenza_punti(prima, dopo)
    assert diff == {"Gemini Models": (6, 7)}
    assert differenza_punti(None, dopo) == {}
    assert differenza_punti(prima, None) == {}
