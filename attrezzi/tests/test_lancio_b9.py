"""Prove per il comando bottega lancia e bottega segui (Compito B9.5).

Solo finti in memoria, nessun comando esterno reale, nessuna attesa reale.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from bottega.__main__ import main
from bottega.board import Lavoro
from bottega.lancio import (
    Giro,
    comando_lancia,
    comando_segui,
    esito_del_lavoro,
    giri_rossi_nuovi,
    verdetto,
)


class FintoEsecutore:
    """Esecutore finto che risponde in base agli argomenti del comando."""

    def __init__(self, risposte: Mapping[str, tuple[int, str]] | None = None) -> None:
        self.risposte = dict(risposte or {})
        self.chiamate: list[tuple[Sequence[str], Mapping[str, str] | None]] = []

    def __call__(
        self, comando: Sequence[str], ambiente: Mapping[str, str] | None = None
    ) -> tuple[int, str]:
        self.chiamate.append((list(comando), ambiente))
        cmd_str = " ".join(comando)
        if cmd_str in self.risposte:
            return self.risposte[cmd_str]
        for prefisso, esito in self.risposte.items():
            if cmd_str.startswith(prefisso):
                return esito
        return 0, ""


class FintaBoard:
    """Board finta con dizionario dei lavori in memoria."""

    def __init__(self, lavori: Mapping[int, Lavoro] | None = None) -> None:
        self.lavori = dict(lavori or {})

    def lavoro(self, numero: int) -> Lavoro | None:
        return self.lavori.get(numero)


class FintoOrologio:
    """Orologio finto che avanza quando si dorme."""

    def __init__(self, istante: datetime) -> None:
        self.adesso_dt = istante

    def adesso(self) -> datetime:
        return self.adesso_dt

    def dormi(self, secondi: float) -> None:
        self.adesso_dt += timedelta(seconds=secondi)


# 1. esito_del_lavoro
def test_esito_del_lavoro_casi():
    reg_avviato = (
        "distributore\tUNKNOWN STEP\t2026-11-12T05:20:00.1234567Z "
        "lavoro 563: assegnato a «x» (b), workflow f.yml avviato\n"
    )
    esito, riga = esito_del_lavoro(reg_avviato, 563)
    assert esito == "avviato"
    assert riga == "lavoro 563: assegnato a «x» (b), workflow f.yml avviato"

    # lavoro 56 cercato nello stesso registro non prende lavoro 563
    esito_56, riga_56 = esito_del_lavoro(reg_avviato, 56)
    assert esito_56 == "assente"
    assert riga_56 == "nessuna riga per il lavoro 56"

    # finestra di manutenzione
    reg_manutenzione = (
        "distributore\tUNKNOWN STEP\t2026-11-12T05:20:00.1234567Z "
        "finestra di manutenzione «06:00-07:00»: nessun lavoro avviato\n"
    )
    esito_m, riga_m = esito_del_lavoro(reg_manutenzione, 563)
    assert esito_m == "manutenzione"
    assert riga_m == "finestra di manutenzione «06:00-07:00»: nessun lavoro avviato"

    # ramo principale rosso
    reg_rosso = (
        "distributore\tUNKNOWN STEP\t2026-11-12T05:20:00.1234567Z "
        "ramo principale «main» rosso: nessun lavoro avviato\n"
    )
    esito_r, riga_r = esito_del_lavoro(reg_rosso, 563)
    assert esito_r == "rosso"
    assert riga_r == "ramo principale «main» rosso: nessun lavoro avviato"

    # bottega occupata
    reg_occupata = (
        "distributore\tUNKNOWN STEP\t2026-11-12T05:20:00.1234567Z "
        "lavoro 563: bottega «b» occupata, salto\n"
    )
    esito_o, riga_o = esito_del_lavoro(reg_occupata, 563)
    assert esito_o == "occupata"
    assert riga_o == "lavoro 563: bottega «b» occupata, salto"


# 2. verdetto
def test_verdetto_regole_e_bordi():
    inizio = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)

    # 1. stato consegnato
    assert verdetto(
        stato="consegnato",
        figli=[],
        giri=[],
        inizio=inizio,
        adesso=inizio,
        fermo_s=1200.0,
    ) == (0, "finito")

    # 1b. figli non vuoto e tutti falsi (chiusi)
    assert verdetto(
        stato="in corso",
        figli=[False, False],
        giri=[],
        inizio=inizio,
        adesso=inizio,
        fermo_s=1200.0,
    ) == (0, "finito")

    # 2. in attesa
    assert verdetto(
        stato="in attesa",
        figli=[True],
        giri=[],
        inizio=inizio,
        adesso=inizio,
        fermo_s=1200.0,
    ) == (2, "in attesa: una domanda per chi decide")

    # 3. bloccato
    assert verdetto(
        stato="bloccato",
        figli=[True],
        giri=[],
        inizio=inizio,
        adesso=inizio,
        fermo_s=1200.0,
    ) == (3, "bloccato")

    # 4. bordi del fermo (1199 s: None; 1201 s: 4)
    giro_comp = Giro(
        id=1,
        stato="completed",
        conclusione="success",
        creato=inizio,
        aggiornato=inizio,
    )
    v_1199 = verdetto(
        stato="pronto",
        figli=[True],
        giri=[giro_comp],
        inizio=inizio,
        adesso=inizio + timedelta(seconds=1199),
        fermo_s=1200.0,
    )
    assert v_1199 is None

    v_1201 = verdetto(
        stato="pronto",
        figli=[True],
        giri=[giro_comp],
        inizio=inizio,
        adesso=inizio + timedelta(seconds=1201),
        fermo_s=1200.0,
    )
    assert v_1201 == (4, f"fermo dal {inizio.isoformat(timespec='minutes')}")

    # giro in_progress che impedisce il fermo
    giro_in_corso = Giro(
        id=2,
        stato="in_progress",
        conclusione=None,
        creato=inizio,
        aggiornato=inizio,
    )
    v_in_progress = verdetto(
        stato="pronto",
        figli=[True],
        giri=[giro_in_corso],
        inizio=inizio,
        adesso=inizio + timedelta(seconds=1500),
        fermo_s=1200.0,
    )
    assert v_in_progress is None

    # giro aggiornato prima di inizio che conta come inizio
    giro_vecchio = Giro(
        id=3,
        stato="completed",
        conclusione="success",
        creato=inizio - timedelta(seconds=600),
        aggiornato=inizio - timedelta(seconds=600),
    )
    v_vecchio_1199 = verdetto(
        stato="pronto",
        figli=[True],
        giri=[giro_vecchio],
        inizio=inizio,
        adesso=inizio + timedelta(seconds=1199),
        fermo_s=1200.0,
    )
    assert v_vecchio_1199 is None

    v_vecchio_1201 = verdetto(
        stato="pronto",
        figli=[True],
        giri=[giro_vecchio],
        inizio=inizio,
        adesso=inizio + timedelta(seconds=1201),
        fermo_s=1200.0,
    )
    assert v_vecchio_1201 == (4, f"fermo dal {inizio.isoformat(timespec='minutes')}")


# 3. giri_rossi_nuovi
def test_giri_rossi_nuovi_casi():
    inizio = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
    g_vecchio = Giro(
        id=10,
        stato="completed",
        conclusione="failure",
        creato=inizio - timedelta(seconds=10),
        aggiornato=inizio,
    )
    g_visto = Giro(
        id=20,
        stato="completed",
        conclusione="failure",
        creato=inizio + timedelta(seconds=10),
        aggiornato=inizio + timedelta(seconds=20),
    )
    g_verde = Giro(
        id=30,
        stato="completed",
        conclusione="success",
        creato=inizio + timedelta(seconds=30),
        aggiornato=inizio + timedelta(seconds=40),
    )
    g_nuovo1 = Giro(
        id=40,
        stato="completed",
        conclusione="failure",
        creato=inizio + timedelta(seconds=50),
        aggiornato=inizio + timedelta(seconds=60),
    )
    g_nuovo2 = Giro(
        id=50,
        stato="completed",
        conclusione="failure",
        creato=inizio + timedelta(seconds=70),
        aggiornato=inizio + timedelta(seconds=80),
    )

    tutti = [g_nuovo2, g_verde, g_nuovo1, g_visto, g_vecchio]
    visti = {20}
    rossi = giri_rossi_nuovi(tutti, inizio, visti)
    assert rossi == [40, 50]


# 4. comando_lancia
def test_comando_lancia_casi(capsys: pytest.CaptureFixture[str]):
    orologio = FintoOrologio(datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC))

    class Args:
        numero = 42
        repo = None
        attesa = 180
        tetto = 900

    # 4a. etichetta già presente -> gh workflow run
    esecutore_gia_fuori = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (
                0,
                json.dumps({"labels": [{"name": "bottega: fuori"}]}),
            ),
            "gh workflow run bottega-distributore.yml": (0, ""),
            "gh run list --workflow bottega-distributore.yml --limit 10 --json databaseId,createdAt": (
                0,
                json.dumps([{"databaseId": 101, "createdAt": "2026-11-12T10:00:05Z"}]),
            ),
            "gh run view 101 --json status": (0, json.dumps({"status": "completed"})),
            "gh run view 101 --log": (
                0,
                "lavoro 42: assegnato a «x» (b), workflow f.yml avviato\n",
            ),
        }
    )
    rc = comando_lancia(
        Args(), esegui=esecutore_gia_fuori, dormi=orologio.dormi, adesso=orologio.adesso
    )
    assert rc == 0
    chiamate_str = [" ".join(c[0]) for c in esecutore_gia_fuori.chiamate]
    assert "gh workflow run bottega-distributore.yml" in chiamate_str
    assert "gh issue edit 42 --add-label bottega: fuori" not in chiamate_str
    out, _ = capsys.readouterr()
    assert "giro 101: lavoro 42: assegnato a «x» (b), workflow f.yml avviato" in out

    # 4b. etichetta assente -> gh issue edit --add-label
    esecutore_senza_etichetta = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (0, json.dumps({"labels": []})),
            'gh issue edit 42 --add-label "bottega: fuori"': (0, ""),
            "gh issue edit 42 --add-label bottega: fuori": (0, ""),
            "gh run list --workflow bottega-distributore.yml --limit 10 --json databaseId,createdAt": (
                0,
                json.dumps([{"databaseId": 102, "createdAt": "2026-11-12T10:00:05Z"}]),
            ),
            "gh run view 102 --json status": (0, json.dumps({"status": "completed"})),
            "gh run view 102 --log": (
                0,
                "lavoro 42: assegnato a «x» (b), workflow f.yml avviato\n",
            ),
        }
    )
    rc = comando_lancia(
        Args(),
        esegui=esecutore_senza_etichetta,
        dormi=orologio.dormi,
        adesso=orologio.adesso,
    )
    assert rc == 0
    chiamate_str = [" ".join(c[0]) for c in esecutore_senza_etichetta.chiamate]
    assert any("gh issue edit 42 --add-label" in c for c in chiamate_str)
    assert "gh workflow run bottega-distributore.yml" not in chiamate_str

    # 4c. registro con manutenzione -> esce 2
    esecutore_manutenzione = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (
                0,
                json.dumps({"labels": [{"name": "bottega: fuori"}]}),
            ),
            "gh workflow run bottega-distributore.yml": (0, ""),
            "gh run list --workflow bottega-distributore.yml --limit 10 --json databaseId,createdAt": (
                0,
                json.dumps([{"databaseId": 103, "createdAt": "2026-11-12T10:00:05Z"}]),
            ),
            "gh run view 103 --json status": (0, json.dumps({"status": "completed"})),
            "gh run view 103 --log": (
                0,
                "finestra di manutenzione «06:00-07:00»: nessun lavoro avviato\n",
            ),
        }
    )
    rc = comando_lancia(
        Args(),
        esegui=esecutore_manutenzione,
        dormi=orologio.dormi,
        adesso=orologio.adesso,
    )
    assert rc == 2
    out, _ = capsys.readouterr()
    assert (
        "giro 103: finestra di manutenzione «06:00-07:00»: nessun lavoro avviato" in out
    )

    # 4d. nessun giro entro attesa -> 1
    orologio_timeout = FintoOrologio(datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC))
    esecutore_vuoto = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (
                0,
                json.dumps({"labels": [{"name": "bottega: fuori"}]}),
            ),
            "gh workflow run bottega-distributore.yml": (0, ""),
            "gh run list --workflow bottega-distributore.yml --limit 10 --json databaseId,createdAt": (
                0,
                "[]",
            ),
        }
    )
    rc = comando_lancia(
        Args(),
        esegui=esecutore_vuoto,
        dormi=orologio_timeout.dormi,
        adesso=orologio_timeout.adesso,
    )
    assert rc == 1
    _, err = capsys.readouterr()
    assert "nessun giro del distributore entro 180 s" in err

    # 4e. tutti assente -> stampa ultima riga su stderr, esce 1
    esecutore_assente = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (
                0,
                json.dumps({"labels": [{"name": "bottega: fuori"}]}),
            ),
            "gh workflow run bottega-distributore.yml": (0, ""),
            "gh run list --workflow bottega-distributore.yml --limit 10 --json databaseId,createdAt": (
                0,
                json.dumps([{"databaseId": 104, "createdAt": "2026-11-12T10:00:05Z"}]),
            ),
            "gh run view 104 --json status": (0, json.dumps({"status": "completed"})),
            "gh run view 104 --log": (0, "lavoro 42: senza «Fatto quando», salto\n"),
        }
    )
    rc = comando_lancia(
        Args(), esegui=esecutore_assente, dormi=orologio.dormi, adesso=orologio.adesso
    )
    assert rc == 1
    _, err = capsys.readouterr()
    assert "lavoro 42: senza «Fatto quando», salto" in err

    # 4f. errore di gh (codice != 0) -> stderr lancio non verificato: ..., esce 1
    esecutore_errore = FintoEsecutore(
        {
            "gh issue view 42 --json labels": (1, "connessione fallita\n"),
        }
    )
    rc = comando_lancia(
        Args(), esegui=esecutore_errore, dormi=orologio.dormi, adesso=orologio.adesso
    )
    assert rc == 1
    _, err = capsys.readouterr()
    assert "lancio non verificato: connessione fallita" in err


# 5. comando_segui
def test_comando_segui_casi(capsys: pytest.CaptureFixture[str]):
    class Args:
        numero = 42
        repo = None
        intervallo = 300
        fermo = 1200.0
        tetto = 18000.0
        configurazione = Path("bottega.toml")

    # 5a. tutte le sotto-issue chiuse -> 0
    board_chiuse = FintaBoard({42: Lavoro(numero=42, titolo="Madre", stato="in corso")})
    esecutore_chiuse = FintoEsecutore(
        {
            "gh api repos/{owner}/{repo}/issues/42/sub_issues": (
                0,
                json.dumps(
                    [
                        {"number": 43, "state": "closed"},
                        {"number": 44, "state": "closed"},
                    ]
                ),
            ),
            "gh workflow list --all --json name,path": (
                0,
                "[]",
            ),
        }
    )
    rc = comando_segui(Args(), esegui=esecutore_chiuse, board=board_chiuse)
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "finito" in out

    # 5b. stato in attesa -> 2
    board_attesa = FintaBoard(
        {42: Lavoro(numero=42, titolo="Madre", stato="in attesa")}
    )
    esecutore_attesa = FintoEsecutore(
        {
            "gh api repos/{owner}/{repo}/issues/42/sub_issues": (
                0,
                json.dumps([{"state": "open"}]),
            ),
            "gh workflow list --all --json name,path": (
                0,
                "[]",
            ),
        }
    )
    rc = comando_segui(Args(), esegui=esecutore_attesa, board=board_attesa)
    assert rc == 2
    out, _ = capsys.readouterr()
    assert "in attesa: una domanda per chi decide" in out

    # 5c. giro rosso nuovo stampa avviso e non esce
    passi = [0]
    orologio = FintoOrologio(datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC))
    board_rosso = FintaBoard({42: Lavoro(numero=42, titolo="Madre", stato="pronto")})

    def esegui_rosso(cmd: Sequence[str], _=None) -> tuple[int, str]:
        cmd_str = " ".join(cmd)
        if "sub_issues" in cmd_str:
            if passi[0] == 0:
                return 0, json.dumps([{"state": "open"}])
            return 0, json.dumps([{"state": "closed"}])
        if "workflow list" in cmd_str:
            return 0, json.dumps(
                [
                    {
                        "name": "bottega-esecutore-test",
                        "path": ".github/workflows/bottega-esecutore-test.yml",
                    }
                ]
            )
        if "run list" in cmd_str:
            return 0, json.dumps(
                [
                    {
                        "databaseId": 999,
                        "workflowName": "bottega-esecutore-test",
                        "status": "completed",
                        "conclusion": "failure",
                        "createdAt": "2026-11-12T10:01:00Z",
                        "updatedAt": "2026-11-12T10:02:00Z",
                    }
                ]
            )
        return 0, ""

    def dormi_rosso(sec: float):
        passi[0] += 1
        orologio.dormi(sec)

    rc = comando_segui(
        Args(),
        esegui=esegui_rosso,
        dormi=dormi_rosso,
        adesso=orologio.adesso,
        board=board_rosso,
    )
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "avviso: giro 999 finito male" in out
    assert "finito" in out

    # 5d. senza giri attivi da più di --fermo -> 4
    orologio_fermo = FintoOrologio(datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC))
    board_fermo = FintaBoard({42: Lavoro(numero=42, titolo="Madre", stato="pronto")})
    # Avanti l'orologio oltre il fermo
    orologio_fermo.dormi(1205.0)
    esecutore_fermo = FintoEsecutore(
        {
            "gh api repos/{owner}/{repo}/issues/42/sub_issues": (
                0,
                json.dumps([{"state": "open"}]),
            ),
            "gh workflow list --all --json name,path": (
                0,
                json.dumps(
                    [
                        {
                            "name": "bottega-esecutore-test",
                            "path": ".github/workflows/bottega-esecutore-test.yml",
                        }
                    ]
                ),
            ),
            "gh run list --workflow .github/workflows/bottega-esecutore-test.yml --limit 10 --json databaseId,status,conclusion,createdAt,updatedAt": (
                0,
                json.dumps(
                    [
                        {
                            "databaseId": 501,
                            "workflowName": "bottega-esecutore-test",
                            "status": "completed",
                            "conclusion": "success",
                            "createdAt": "2026-11-12T09:50:00Z",
                            "updatedAt": "2026-11-12T09:55:00Z",
                        }
                    ]
                ),
            ),
        }
    )
    rc = comando_segui(
        Args(),
        esegui=esecutore_fermo,
        dormi=orologio_fermo.dormi,
        adesso=orologio_fermo.adesso,
        board=board_fermo,
    )
    assert rc == 4
    out, _ = capsys.readouterr()
    assert "fermo dal " in out

    # 5e. oltre --tetto -> 6
    orologio_tetto = FintoOrologio(datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC))
    board_in_corso = FintaBoard(
        {42: Lavoro(numero=42, titolo="Madre", stato="in corso")}
    )
    esecutore_in_corso = FintoEsecutore(
        {
            "gh api repos/{owner}/{repo}/issues/42/sub_issues": (
                0,
                json.dumps([{"state": "open"}]),
            ),
            "gh workflow list --all --json name,path": (
                0,
                json.dumps(
                    [
                        {
                            "name": "bottega-esecutore-test",
                            "path": ".github/workflows/bottega-esecutore-test.yml",
                        }
                    ]
                ),
            ),
            "gh run list --workflow .github/workflows/bottega-esecutore-test.yml --limit 10 --json databaseId,status,conclusion,createdAt,updatedAt": (
                0,
                json.dumps(
                    [
                        {
                            "databaseId": 601,
                            "workflowName": "bottega-esecutore-test",
                            "status": "in_progress",
                            "conclusion": None,
                            "createdAt": "2026-11-12T10:00:00Z",
                            "updatedAt": "2026-11-12T10:00:00Z",
                        }
                    ]
                ),
            ),
        }
    )

    def dormi_tetto(sec: float):
        orologio_tetto.dormi(18005.0)

    rc = comando_segui(
        Args(),
        esegui=esecutore_in_corso,
        dormi=dormi_tetto,
        adesso=orologio_tetto.adesso,
        board=board_in_corso,
    )
    assert rc == 6
    out, _ = capsys.readouterr()
    assert "tempo scaduto" in out

    # 5f. errore di gh o della board in un passo: stderr avviso: ... e si va avanti
    passo_err = [0]

    class BoardCheSbaglia:
        def lavoro(self, numero: int):
            if passo_err[0] == 0:
                raise RuntimeError("rete non raggiungibile")
            return Lavoro(numero=numero, titolo="Madre", stato="consegnato")

    def esegui_errore_passo(cmd: Sequence[str], _=None) -> tuple[int, str]:
        if passo_err[0] == 0:
            return 1, "errore temporaneo api"
        return 0, "[]"

    def dormi_err(sec: float):
        passo_err[0] += 1

    rc = comando_segui(
        Args(),
        esegui=esegui_errore_passo,
        dormi=dormi_err,
        adesso=orologio_tetto.adesso,
        board=BoardCheSbaglia(),
    )
    assert rc == 0
    out, err = capsys.readouterr()
    assert "avviso: board #42: rete non raggiungibile" in err
    assert "avviso: errore temporaneo api" in err
    assert "finito" in out


# 6. help di bottega lancia e bottega segui
def test_help_lancia_e_segui(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as e:
        main(["lancia", "--help"])
    assert e.value.code == 0
    out_lancia = capsys.readouterr().out
    assert "lancia" in out_lancia
    assert "--attesa" in out_lancia
    assert "--tetto" in out_lancia

    with pytest.raises(SystemExit) as e:
        main(["segui", "--help"])
    assert e.value.code == 0
    out_segui = capsys.readouterr().out
    assert "segui" in out_segui
    assert "--intervallo" in out_segui
    assert "--fermo" in out_segui
    assert "--tetto" in out_segui


def test_esecutore_gh_tiene_solo_lo_stdout_se_riesce(tmp_path: Path) -> None:
    """Un avviso di `gh` su stderr non rompe il JSON dello stdout; un errore porta stderr e stdout."""
    from bottega.lancio import esecutore_gh

    script = tmp_path / "finto.sh"
    script.write_text('#!/bin/sh\necho \'{"a": 1}\'\necho "A new release of gh is available" >&2\nexit "$1"\n')
    script.chmod(0o755)
    codice, uscita = esecutore_gh([str(script), "0"])
    assert codice == 0 and json.loads(uscita) == {"a": 1}
    codice, uscita = esecutore_gh([str(script), "3"])
    assert codice == 3 and "A new release" in uscita


def test_segui_falso_fermo_con_venti_giri_di_altri_workflow() -> None:
    """Un giro dell'esecutore in corso da ore, ma fuori dai 20 giri più recenti del repo (commenti, CI)."""
    import argparse
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    orologio = FintoOrologio(t0)
    board = FintaBoard({42: Lavoro(numero=42, titolo="L", stato="in corso")})
    altri = [
        {
            "databaseId": 100 + i,
            "workflowName": "bottega-distributore",
            "status": "completed",
            "conclusion": "skipped",
            "createdAt": f"2026-11-12T09:{30 + i}:00Z",
            "updatedAt": f"2026-11-12T09:{30 + i}:05Z",
        }
        for i in range(20)
    ]

    def esegui(cmd: Sequence[str], _=None) -> tuple[int, str]:
        s = " ".join(cmd)
        if "sub_issues" in s:
            return 0, json.dumps([{"state": "open"}])
        if "workflow list" in s:
            return 0, json.dumps([{"name": "bottega-esecutore-test", "path": ".github/workflows/esecutore.yml"}])
        if "run list" in s and "--workflow" in s:
            return 0, json.dumps(
                [
                    {
                        "databaseId": 999,
                        "status": "in_progress",
                        "conclusion": None,
                        "createdAt": "2026-11-12T08:00:00Z",
                        "updatedAt": "2026-11-12T08:00:00Z",
                    }
                ]
            )
        if "run list" in s:
            return 0, json.dumps(altri)
        return 0, ""

    args = argparse.Namespace(numero=42, repo="o/r", intervallo=300, fermo=1200.0, tetto=18000.0)
    rc = comando_segui(args, esegui=esegui, dormi=orologio.dormi, adesso=orologio.adesso, board=board)
    assert rc != 4, "fermo dichiarato con un giro dell'esecutore ancora in corso"


def test_lancia_legge_solo_il_primo_giro_visto() -> None:
    """Al primo `run list` c'è solo un giro nato da un altro evento; il nostro nasce 5 s dopo e avvia il lavoro."""
    import argparse
    t0 = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
    orologio = FintoOrologio(t0)
    polls = [0]

    def esegui(cmd: Sequence[str], _=None) -> tuple[int, str]:
        s = " ".join(cmd)
        if "issue view" in s:
            return 0, json.dumps({"labels": []})
        if "issue edit" in s:
            return 0, ""
        if "run list" in s:
            polls[0] += 1
            giri = [{"databaseId": 1, "createdAt": "2026-11-12T10:00:01Z"}]
            if polls[0] > 1:
                giri.insert(0, {"databaseId": 2, "createdAt": "2026-11-12T10:00:03Z"})
                giri.insert(0, {"databaseId": 3, "createdAt": "2026-11-12T10:00:06Z"})
            return 0, json.dumps(giri)
        if "run view 1" in s and "--json" in s:
            return 0, json.dumps({"status": "completed", "conclusion": "success"})
        if "run view 2" in s and "--json" in s:
            return 0, json.dumps({"status": "completed", "conclusion": "cancelled"})
        if "run view 3" in s and "--json" in s:
            return 0, json.dumps({"status": "completed", "conclusion": "success"})
        if "run view 1 --log" in s:
            return 0, "distributore\tpasso\tlavoro 7: assegnato a «X» (b), workflow f avviato\n"
        if "run view 2 --log" in s:
            return 0, "giro annullato\n"
        if "run view 3 --log" in s:
            return 0, "distributore\tpasso\tlavoro 42: assegnato a «X» (b), workflow f avviato\n"
        return 1, "inatteso " + s

    args = argparse.Namespace(numero=42, repo="o/r", attesa=180, tetto=900)
    rc = comando_lancia(args, esegui=esegui, dormi=orologio.dormi, adesso=orologio.adesso)
    assert rc == 0


def test_esito_prima_riga_non_decisiva() -> None:
    registro = (
        "lavoro 42: in corso da oltre 7 ore, reimpostato a pronto\n"
        "lavoro 42: assegnato a «X» (b), workflow f avviato\n"
    )
    assert esito_del_lavoro(registro, 42)[0] == "avviato"
