"""Configurazione e fixture globali per le prove di attrezzi."""

import bottega.giro
import pytest


@pytest.fixture(autouse=True)
def _spegni_sentinella_rete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spegne la sentinella di rete dell'esecutore per tutte le prove di serie."""
    monkeypatch.setattr(bottega.giro, "SENTINELLA_RETE", False, raising=False)
