"""Prove del ritmo della quota, scelta dei riempitivi e lettura quota Antigravity."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat

import pytest

from bottega.board import Lavoro
from bottega.porte.antigravity import Antigravity
from bottega.quota import PuntoQuota
from bottega.ritmo import (
    argomenti_ritmo,
    comando_ritmo,
    fascia_riempitivo,
    scegli_riempitivo,
    valuta_ritmo,
)


def _punto(
    *,
    settimana: int = 80,
    rinnovo_settimana: datetime | None = None,
    cinque_ore: int = 60,
    rinnovo_cinque_ore: datetime | None = None,
    gruppo: str = "Gemini Models",
) -> PuntoQuota:
    base = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    return PuntoQuota(
        gruppo=gruppo,
        settimana=settimana,
        rinnovo_settimana=rinnovo_settimana or base,
        cinque_ore=cinque_ore,
        rinnovo_cinque_ore=rinnovo_cinque_ore or (base - timedelta(days=3)),
    )


def test_valuta_ritmo_indietro_lancia() -> None:
    rinnovo_sett = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    adesso = rinnovo_sett - timedelta(days=3, hours=12)  # 3.5 giorni passati -> 50% atteso
    punto = _punto(
        settimana=80,  # 20% speso -> ritardo 30.0
        rinnovo_settimana=rinnovo_sett,
        cinque_ore=60,
        rinnovo_cinque_ore=adesso + timedelta(hours=2),
    )
    esito = valuta_ritmo(punto, adesso)
    assert esito.lancia is True
    assert esito.atteso_speso == pytest.approx(50.0)
    assert esito.speso == 20
    assert esito.ritardo == pytest.approx(30.0)
    assert esito.cinque_ore_effettiva == 60


def test_valuta_ritmo_in_passo_non_lancia() -> None:
    rinnovo_sett = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    # 34.9% di settimana passata -> atteso 34.9, speso 20 -> ritardo 14.9 (< 15)
    inizio_sett = rinnovo_sett - timedelta(days=7)
    adesso = inizio_sett + timedelta(seconds=0.349 * 7 * 24 * 3600)
    punto = _punto(
        settimana=80,
        rinnovo_settimana=rinnovo_sett,
        cinque_ore=60,
        rinnovo_cinque_ore=adesso + timedelta(hours=2),
    )
    esito = valuta_ritmo(punto, adesso)
    assert esito.lancia is False
    assert esito.ritardo == pytest.approx(14.9)
    assert "quota in passo" in esito.motivo


def test_valuta_ritmo_riserva_5h_ferma() -> None:
    rinnovo_sett = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    adesso = rinnovo_sett - timedelta(days=3, hours=12)  # ritardo 30
    punto = _punto(
        settimana=80,
        rinnovo_settimana=rinnovo_sett,
        cinque_ore=29,
        rinnovo_cinque_ore=adesso + timedelta(hours=2),
    )
    esito = valuta_ritmo(punto, adesso)
    assert esito.lancia is False
    assert "riserva cinque ore" in esito.motivo


def test_valuta_ritmo_5h_rinnovata_dopo_rilevazione() -> None:
    rinnovo_sett = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    adesso = rinnovo_sett - timedelta(days=3, hours=12)
    punto = _punto(
        settimana=80,
        rinnovo_settimana=rinnovo_sett,
        cinque_ore=10,
        rinnovo_cinque_ore=adesso - timedelta(minutes=5),
    )
    esito = valuta_ritmo(punto, adesso)
    assert esito.cinque_ore_effettiva == 100
    assert esito.lancia is True


def test_valuta_ritmo_riserva_settimanale_ferma() -> None:
    rinnovo_sett = datetime(2026, 12, 8, 12, 0, 0, tzinfo=timezone.utc)
    # 102% impossibile, usiamo 2% residuo mancante -> passato ~7.14% non basta:
    # settimana=14 -> speso=86. Se passato=102% -> no, usiamo adesso vicino a fine settimana:
    # 1 giorno prima del rinnovo -> passato 6/7 = 85.7%, ma serve ritardo >= 15 => atteso >= 101%?
    # No: se speso = 86 (settimana = 14) e passato = 99% -> ritardo 13.
    # Con soglia_ritardo=10 o controllo diretto:
    adesso = rinnovo_sett - timedelta(minutes=1)  # ~100% passato -> atteso ~100, speso 86 -> ritardo ~14
    punto = _punto(
        settimana=14,
        rinnovo_settimana=rinnovo_sett,
        cinque_ore=80,
        rinnovo_cinque_ore=adesso + timedelta(hours=2),
    )
    esito = valuta_ritmo(punto, adesso, soglia_ritardo=10)
    assert esito.lancia is False
    assert "riserva settimanale" in esito.motivo


def test_valuta_ritmo_epoch_zero_e_scaduta() -> None:
    epoch = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    adesso = datetime(2026, 12, 5, 12, 0, 0, tzinfo=timezone.utc)
    esito_epoch = valuta_ritmo(_punto(settimana=100, rinnovo_settimana=epoch), adesso)
    assert esito_epoch.lancia is False
    assert "non ancora avviata" in esito_epoch.motivo

    rinnovo_passato = adesso - timedelta(minutes=1)
    esito_scaduta = valuta_ritmo(_punto(settimana=50, rinnovo_settimana=rinnovo_passato), adesso)
    assert esito_scaduta.lancia is False
    assert "rilevazione scaduta" in esito_scaduta.motivo


def test_fascia_e_scegli_riempitivo_ordine() -> None:
    assert fascia_riempitivo(["debito"]) == 0
    assert fascia_riempitivo(["bug"]) == 0
    assert fascia_riempitivo(["prove"]) == 1
    assert fascia_riempitivo(["docs"]) == 2
    assert fascia_riempitivo(["pulizia"]) == 3

    aree = ("debito", "bug", "prove", "docs", "pulizia")
    lavori = [
        Lavoro(numero=10, titolo="Pulizia", etichette=["pulizia"], stato="pronto"),
        Lavoro(numero=11, titolo="Docs", etichette=["docs"], stato="pronto"),
        Lavoro(numero=12, titolo="Prove", etichette=["prove"], stato="pronto"),
        Lavoro(numero=15, titolo="Debito alto", etichette=["debito"], stato="pronto"),
        Lavoro(numero=13, titolo="Debito basso", etichette=["bug"], stato="pronto"),
        Lavoro(numero=1, titolo="Escluso attesa", etichette=["bug", "attesa utente"], stato="pronto"),
        Lavoro(numero=2, titolo="Escluso design", etichette=["bug", "design"], stato="pronto"),
        Lavoro(numero=3, titolo="Escluso delicato", etichette=["bug", "delicato"], stato="pronto"),
        Lavoro(numero=4, titolo="Escluso fuori", etichette=["bug", "bottega: fuori"], stato="pronto"),
        Lavoro(numero=5, titolo="Escluso esegue", etichette=["bug", "esegue: g-pro"], stato="pronto"),
        Lavoro(numero=6, titolo="Senza FQ", etichette=["bug"], stato="pronto"),
        Lavoro(numero=7, titolo="Autore esterno", etichette=["bug"], stato="pronto"),
    ]
    senza_fq = {6}
    autori_esterni = {7}
    scelto = scegli_riempitivo(
        lavori,
        aree_non_delicate=aree,
        ha_fatto_quando=lambda n: n not in senza_fq,
        autore_valido=lambda n: n not in autori_esterni,
    )
    assert scelto is not None
    lav, fascia = scelto
    assert lav.numero == 13
    assert fascia == 0

    # Se escludo i due debiti restano prove (12), poi docs (11), poi pulizia (10)
    scelto_prove = scegli_riempitivo(
        [x for x in lavori if x.numero not in (13, 15)],
        aree_non_delicate=aree,
        ha_fatto_quando=lambda n: n not in senza_fq,
        autore_valido=lambda n: n not in autori_esterni,
    )
    assert scelto_prove is not None
    assert scelto_prove[0].numero == 12
    assert scelto_prove[1] == 1

    # Nessuna area non delicata -> sempre None
    assert (
        scegli_riempitivo(
            lavori,
            aree_non_delicate=(),
            ha_fatto_quando=lambda _: True,
            autore_valido=lambda _: True,
        )
        is None
    )


def test_antigravity_leggi_quota_con_finto_eseguibile(tmp_path: Path) -> None:
    script_ok = tmp_path / "finto_agy_ok.py"
    script_ok.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['-p', '/quota']:\n"
        "    print('Gemini Models\\tWeekly Limit Remaining\\t86%\\t2026-12-02T15:21:03Z')\n"
        "    print('Gemini Models\\tFive Hour Limit Remaining\\t47%\\t2026-12-01T18:00:00Z')\n"
        "    sys.exit(0)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    script_ok.chmod(script_ok.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR)

    porta_ok = Antigravity(eseguibile=str(script_ok))
    punti = porta_ok.leggi_quota()
    assert punti is not None
    assert punti["Gemini Models"].settimana == 86
    assert punti["Gemini Models"].cinque_ore == 47

    script_ko = tmp_path / "finto_agy_ko.py"
    script_ko.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n", encoding="utf-8")
    script_ko.chmod(script_ko.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR)

    porta_ko = Antigravity(eseguibile=str(script_ko))
    assert porta_ko.leggi_quota() is None
    assert Antigravity(eseguibile=str(tmp_path / "non_esiste")).leggi_quota() is None


def test_comando_ritmo_da_file_e_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toml_path = tmp_path / "bottega.toml"
    toml_path.write_text(
        """versione = 1

[progetto]
fuso = "UTC"
comandanti = ["alice"]

[botteghe.google]
quota = "abbondante"
porte = ["antigravity"]

[candidati.g-flash]
nome = "Gemini Flash"
bottega = "google"
porta = "antigravity"
modello = "gemini-3-flash"
funzioni = ["decidere", "eseguire"]

[ritmo]
gruppo = "Gemini Models"
ritardo = 15
riserva_5h = 30
riserva_settimana = 15
""",
        encoding="utf-8",
    )

    adesso = datetime(2026, 12, 5, 0, 0, 0, tzinfo=timezone.utc)
    rinnovo_sett = (adesso + timedelta(days=3, hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rinnovo_5h = (adesso + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    quota_ok = tmp_path / "quota_ok.tsv"
    quota_ok.write_text(
        f"Gemini Models\tWeekly Limit Remaining\t80%\t{rinnovo_sett}\n"
        f"Gemini Models\tFive Hour Limit Remaining\t60%\t{rinnovo_5h}\n",
        encoding="utf-8",
    )

    quota_ferma = tmp_path / "quota_ferma.tsv"
    quota_ferma.write_text(
        f"Gemini Models\tWeekly Limit Remaining\t80%\t{rinnovo_sett}\n"
        f"Gemini Models\tFive Hour Limit Remaining\t20%\t{rinnovo_5h}\n",
        encoding="utf-8",
    )

    quota_rotta = tmp_path / "quota_rotta.tsv"
    quota_rotta.write_text("testo non interpretabile\n", encoding="utf-8")

    # Blocca l'orologio di ritmo su `adesso`
    import bottega.ritmo as mod_ritmo

    monkeypatch.setattr(mod_ritmo, "_adesso_utc", lambda: adesso)

    parser = argparse.ArgumentParser()
    argomenti_ritmo(parser)

    args_ok = parser.parse_args(["--file", str(toml_path), "--da-quota", str(quota_ok), "--json"])
    assert comando_ritmo(args_ok) == 0
    dati_ok = json.loads(capsys.readouterr().out)
    assert dati_ok["lancia"] is True
    assert dati_ok["gruppo"] == "Gemini Models"

    args_ferma = parser.parse_args(["--file", str(toml_path), "--da-quota", str(quota_ferma), "--json"])
    assert comando_ritmo(args_ferma) == 1
    dati_ferma = json.loads(capsys.readouterr().out)
    assert dati_ferma["lancia"] is False

    args_rotta = parser.parse_args(["--file", str(toml_path), "--da-quota", str(quota_rotta)])
    assert comando_ritmo(args_rotta) == 2
    capsys.readouterr()

    args_assente = parser.parse_args(["--file", str(toml_path), "--da-quota", str(tmp_path / "manca.tsv")])
    assert comando_ritmo(args_assente) == 2
    capsys.readouterr()
