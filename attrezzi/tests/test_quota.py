"""Prove dello stato della quota di una bottega: variabile di Actions, formati e disponibilità."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bottega.quota import disponibile, nome_variabile, valore_esaurita


def test_nome_variabile_converte_in_maiuscolo_e_trattini_in_trattini_bassi() -> None:
    assert nome_variabile("principale") == "BOTTEGA_QUOTA_PRINCIPALE"
    assert nome_variabile("secondaria-2") == "BOTTEGA_QUOTA_SECONDARIA_2"
    assert nome_variabile("a-b-c") == "BOTTEGA_QUOTA_A_B_C"


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
