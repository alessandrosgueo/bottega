"""Prove per la divisione di un piano in issue (bottega.dividi)."""

import json
from pathlib import Path
from typing import Any

import pytest

from bottega.finta import ForgiaFinta
from bottega.forgia import Issue
from bottega.porte import Controllo, Lancio


class PortaFinta:
    """Porta finta per simulare le risposte del consigliere nelle prove."""

    def __init__(
        self,
        esito: str = "fatto",
        testo: str = "",
        conversazione: str | None = None,
    ) -> None:
        self.esito = esito
        self.testo = testo
        self.conversazione = conversazione
        self.chiamate: list[dict[str, Any]] = []

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True)

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
        self.chiamate.append({
            "cartella": Path(cartella),
            "prompt": prompt,
            "modello": modello,
            "conversazione": conversazione,
            "sola_lettura": sola_lettura,
            "prefisso": tuple(prefisso),
            "tempo": tempo,
        })
        return Lancio(
            esito=self.esito,
            testo=self.testo,
            conversazione=self.conversazione,
        )


def _configurazione_con_consigliere(tmp_path: Path) -> Path:
    """Crea una configurazione minima con un candidato consigliere e uno che decide."""
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(
        """versione = 1

[progetto]
fuso = "Europe/Rome"

[botteghe.principale]
quota = "abbondante"
porte = ["pi"]

[candidati.maestro]
nome = "Maestro che decide"
bottega = "principale"
porta = "pi"
modello = "modello-forte"
funzioni = ["decidere"]

[candidati.consigliere]
nome = "Consigliere di prova"
bottega = "principale"
porta = "pi"
modello = "modello-consigliere"
funzioni = ["consigliare"]
""",
        encoding="utf-8",
    )
    return cfg_file


def _json_valido() -> dict[str, Any]:
    return {
        "madre": {
            "titolo": "Tappa 1: Fondamenta",
            "corpo": "Descrizione della tappa madre.",
        },
        "compiti": [
            {
                "titolo": "Compito 1: Setup",
                "corpo": (
                    "Sei l'esecutore del compito 1.\n\n"
                    "## Fatto quando\n\n"
                    "```bash\n"
                    "uv run pytest -q tests/test_uno.py\n"
                    "```\n"
                ),
            },
            {
                "titolo": "Compito 2: Funzionalità",
                "corpo": (
                    "Sei l'esecutore del compito 2.\n\n"
                    "## Fatto quando\n\n"
                    "```bash\n"
                    "uv run pytest -q tests/test_due.py\n"
                    "```\n"
                ),
            },
        ],
    }


# --- Prove unità su dividi() con --dal-json ---


def test_dividi_dal_json_valido_crea_madre_e_sotto_issue(tmp_path: Path) -> None:
    from bottega.dividi import dividi

    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(_json_valido()), encoding="utf-8")

    forgia = ForgiaFinta()
    creati = dividi(dal_json=f_json, forgia=forgia)

    # Madre prima, poi compiti nell'ordine
    assert creati == [1, 2, 3]

    madre = forgia.issue(1)
    assert madre.titolo == "Tappa 1: Fondamenta"
    assert "bottega: fuori" not in madre.etichette

    sotto = forgia.sotto_issue(1)
    assert len(sotto) == 2
    assert sotto[0].numero == 2
    assert sotto[0].titolo == "Compito 1: Setup"
    assert "bottega: fuori" not in sotto[0].etichette

    assert sotto[1].numero == 3
    assert sotto[1].titolo == "Compito 2: Funzionalità"
    assert "bottega: fuori" not in sotto[1].etichette


def test_dividi_dal_json_compito_senza_fatto_quando_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    dati = _json_valido()
    dati["compiti"][1]["corpo"] = "Brief senza la sezione di fatto quando."
    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(dati), encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(dal_json=f_json, forgia=forgia)

    assert "compito 2" in str(exc_info.value).lower()
    assert "fatto quando" in str(exc_info.value).lower()
    # Niente si crea se una parte non va
    assert len(forgia.registro) == 0


def test_dividi_dal_json_madre_invalida_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    dati = _json_valido()
    dati["madre"]["titolo"] = ""
    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(dati), encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(dal_json=f_json, forgia=forgia)

    assert "madre" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_dal_json_senza_compiti_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    dati = _json_valido()
    dati["compiti"] = []
    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(dati), encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(dal_json=f_json, forgia=forgia)

    assert "compit" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_dal_json_sintassi_non_valida_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    f_json = tmp_path / "rotto.json"
    f_json.write_text("{ non e un json valido", encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(dal_json=f_json, forgia=forgia)

    assert "json" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_dal_json_file_non_trovato(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi):
        dividi(dal_json=tmp_path / "inesistente.json", forgia=forgia)


# --- Prove unità su dividi() con --piano e consigliere ---


def test_dividi_piano_con_consigliere_valido(tmp_path: Path) -> None:
    from bottega.dividi import dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano di prova\n\nTesto del piano.", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    risposta = "Ecco la divisione richiesta:\n```json\n" + json.dumps(_json_valido()) + "\n```\nBuon lavoro!"
    porta = PortaFinta(esito="fatto", testo=risposta)
    forgia = ForgiaFinta()

    creati = dividi(
        piano=f_piano,
        forgia=forgia,
        percorso_configurazione=cfg_file,
        porta=porta,
    )

    assert creati == [1, 2, 3]
    assert len(porta.chiamate) == 1
    chiamata = porta.chiamate[0]
    assert chiamata["cartella"] == tmp_path.resolve()
    assert chiamata["sola_lettura"] is True
    assert chiamata["modello"] == "modello-consigliere"
    assert "piano.md" in chiamata["prompt"]
    assert "Fatto quando" in chiamata["prompt"]

    # Le issue sono create correttamente
    assert forgia.issue(1).titolo == "Tappa 1: Fondamenta"
    assert len(forgia.sotto_issue(1)) == 2


def test_dividi_piano_risposta_non_json_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    porta = PortaFinta(esito="fatto", testo="Non so dividere questo piano mi dispiace.")
    forgia = ForgiaFinta()

    with pytest.raises(ErroreDividi) as exc_info:
        dividi(
            piano=f_piano,
            forgia=forgia,
            percorso_configurazione=cfg_file,
            porta=porta,
        )

    assert "json" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_piano_compito_senza_fatto_quando_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    dati = _json_valido()
    dati["compiti"][0]["corpo"] = "Senza sezione fatto quando"
    porta = PortaFinta(esito="fatto", testo=json.dumps(dati))
    forgia = ForgiaFinta()

    with pytest.raises(ErroreDividi) as exc_info:
        dividi(
            piano=f_piano,
            forgia=forgia,
            percorso_configurazione=cfg_file,
            porta=porta,
        )

    assert "compito 1" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_piano_consigliere_fallito_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    porta = PortaFinta(esito="errore", testo="connessione fallita")
    forgia = ForgiaFinta()

    with pytest.raises(ErroreDividi) as exc_info:
        dividi(
            piano=f_piano,
            forgia=forgia,
            percorso_configurazione=cfg_file,
            porta=porta,
        )

    assert "errore" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_senza_consigliere_disponibile_esce_errore(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")

    # Configurazione senza consiglieri
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text(
        """versione = 1
[progetto]
fuso = "Europe/Rome"
[botteghe.principale]
quota = "abbondante"
porte = ["pi"]
[candidati.esecutore]
nome = "Esecutore"
bottega = "principale"
porta = "pi"
modello = "mod"
funzioni = ["decidere", "eseguire"]
""",
        encoding="utf-8",
    )

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(
            piano=f_piano,
            forgia=forgia,
            percorso_configurazione=cfg_file,
        )

    assert "consigliere" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


# --- Prove CLI (main) ---


def test_cli_dividi_dal_json_stampa_numeri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(_json_valido()), encoding="utf-8")

    forgia = ForgiaFinta()
    monkeypatch.setattr("bottega.dividi.crea_forgia", lambda repo=None: forgia)

    esito = main(["dividi", "--dal-json", str(f_json)])
    assert esito == 0

    catturato = capsys.readouterr()
    righe = [r.strip() for r in catturato.out.strip().splitlines() if r.strip()]
    assert righe == ["1", "2", "3"]


def test_cli_dividi_dal_json_errore_esce_1_e_stampa_su_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    dati = _json_valido()
    dati["compiti"][1]["corpo"] = "Senza fatto quando"
    f_json = tmp_path / "invalido.json"
    f_json.write_text(json.dumps(dati), encoding="utf-8")

    forgia = ForgiaFinta()
    monkeypatch.setattr("bottega.dividi.crea_forgia", lambda repo=None: forgia)

    esito = main(["dividi", "--dal-json", str(f_json)])
    assert esito == 1

    catturato = capsys.readouterr()
    assert "compito 2" in catturato.err.lower()
    assert len(forgia.registro) == 0


def test_cli_dividi_piano_consigliere_valido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    risposta = json.dumps(_json_valido())
    porta = PortaFinta(esito="fatto", testo=risposta)
    forgia = ForgiaFinta()

    monkeypatch.setattr("bottega.dividi.crea_forgia", lambda repo=None: forgia)
    monkeypatch.setattr("bottega.dividi.ottieni_porta", lambda nome, eseguibile=None: porta)

    esito = main(["dividi", "--piano", str(f_piano), "--file", str(cfg_file)])
    assert esito == 0

    catturato = capsys.readouterr()
    righe = [r.strip() for r in catturato.out.strip().splitlines() if r.strip()]
    assert righe == ["1", "2", "3"]


def test_cli_dividi_piano_non_json_esce_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bottega.__main__ import main

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    porta = PortaFinta(esito="fatto", testo="non e un json")
    forgia = ForgiaFinta()

    monkeypatch.setattr("bottega.dividi.crea_forgia", lambda repo=None: forgia)
    monkeypatch.setattr("bottega.dividi.ottieni_porta", lambda nome, eseguibile=None: porta)

    esito = main(["dividi", "--piano", str(f_piano), "--file", str(cfg_file)])
    assert esito == 1

    catturato = capsys.readouterr()
    assert "json" in catturato.err.lower()
    assert len(forgia.registro) == 0


def test_cli_dividi_senza_piano_e_senza_dal_json_esce_2(capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    esito = main(["dividi"])
    assert esito == 2
    catturato = capsys.readouterr()
    assert "errore:" in catturato.err or "uso:" in catturato.err


def test_cli_dividi_piano_inesistente_esce_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from bottega.__main__ import main

    esito = main(["dividi", "--piano", str(tmp_path / "inesistente.md")])
    assert esito == 1
    catturato = capsys.readouterr()
    assert "non trovato" in catturato.err.lower()


def test_rv17_dividi_entrambi_piano_e_dal_json_si_escludono(tmp_path: Path) -> None:
    """RV17: --piano e --dal-json si escludono a vicenda sia nella funzione che nella CLI."""
    from bottega.__main__ import main
    from bottega.dividi import ErroreDividi, dividi

    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(_json_valido()), encoding="utf-8")
    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi, match="escludono|oppure"):
        dividi(piano=f_piano, dal_json=f_json, forgia=forgia)

    # CLI esce 2 perché il gruppo è mutualmente esclusivo
    with pytest.raises(SystemExit) as exc:
        main(["dividi", "--piano", str(f_piano), "--dal-json", str(f_json)])
    assert exc.value.code == 2


def test_rv17_dividi_aggiunge_madre_e_compiti_alla_board(tmp_path: Path) -> None:
    """RV17: dividi aggiunge madre e compiti al Project tramite board.aggiungi."""
    from bottega.dividi import dividi
    from bottega.finta import BoardFinta

    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(_json_valido()), encoding="utf-8")

    forgia = ForgiaFinta()
    board = BoardFinta()

    creati = dividi(dal_json=f_json, forgia=forgia, board=board)
    assert creati == [1, 2, 3]

    aggiunti = [r[1] for r in board.registro if r[0] == "aggiungi"]
    assert aggiunti == [1, 2, 3]


def test_dividi_blocco_fatto_quando_vuoto_non_crea_nulla(tmp_path: Path) -> None:
    from bottega.dividi import ErroreDividi, dividi

    dati = _json_valido()
    dati["compiti"][0]["corpo"] = "## Fatto quando\n```\n\n```\n"
    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(dati), encoding="utf-8")

    forgia = ForgiaFinta()
    with pytest.raises(ErroreDividi) as exc_info:
        dividi(dal_json=f_json, forgia=forgia)

    assert "compito 1" in str(exc_info.value).lower()
    assert len(forgia.registro) == 0


def test_dividi_blocco_senza_tag_json(tmp_path: Path) -> None:
    from bottega.dividi import dividi

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")
    cfg_file = _configurazione_con_consigliere(tmp_path)

    risposta = "```\n" + json.dumps(_json_valido()) + "\n```"
    porta = PortaFinta(esito="fatto", testo=risposta)
    forgia = ForgiaFinta()

    creati = dividi(
        piano=f_piano,
        forgia=forgia,
        percorso_configurazione=cfg_file,
        porta=porta,
    )
    assert creati == [1, 2, 3]


def test_rv18_dividi_errore_senza_traccia(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """RV18: ErroreBoard, ErroreForgia, FileNotFoundError non mostrano traccia ed escono 1."""
    from bottega.__main__ import main
    from bottega.board import ErroreBoard

    f_json = tmp_path / "divisione.json"
    f_json.write_text(json.dumps(_json_valido()), encoding="utf-8")
    cfg_file = tmp_path / "bottega.toml"
    cfg_file.write_text("""versione = 1
[progetto]
fuso = "Europe/Rome"
project = 1
adattatore = "cmd_inesistente"
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

    from bottega import dividi as dividi_module
    def mock_dividi(*args, **kwargs):
        raise ErroreBoard("Connessione alla board fallita")

    monkeypatch.setattr(dividi_module, "dividi", mock_dividi)

    esito = main(["dividi", "--dal-json", str(f_json), "--file", str(cfg_file)])
    assert esito == 1
    catturato = capsys.readouterr()
    assert "errore: Connessione alla board fallita" in catturato.err
    assert "Traceback" not in catturato.err


def test_dividi_legge_le_quote_dei_secchi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timedelta, timezone
    import random

    from bottega.dividi import ErroreDividi, dividi
    from bottega.quota import valore_esaurita

    f_piano = tmp_path / "piano.md"
    f_piano.write_text("# Piano\n", encoding="utf-8")

    cfg_un_cons = tmp_path / "bottega_uno.toml"
    cfg_un_cons.write_text(
        """versione = 1

[progetto]
fuso = "UTC"

[botteghe.google]
quote = { argon = "abbondante", gemini = "scarsa" }
porte = ["pi"]

[candidati.maestro]
nome = "Maestro"
bottega = "google"
porta = "pi"
modello = "modello-decisore"
quota = "argon"
funzioni = ["decidere"]

[candidati.cons-argon]
nome = "Consigliere Argon"
bottega = "google"
porta = "pi"
modello = "modello-argon"
quota = "argon"
funzioni = ["consigliare"]
""",
        encoding="utf-8",
    )

    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    forgia = ForgiaFinta()
    forgia.imposta_variabile("BOTTEGA_QUOTA_GOOGLE__ARGON", valore_esaurita(adesso + timedelta(hours=1)))

    # 1. Con il solo consigliere del secchio argon esaurito nella forgia, dividi non può sceglierlo
    with pytest.raises(ErroreDividi, match="nessun consigliere disponibile"):
        dividi(
            piano=f_piano,
            forgia=forgia,
            percorso_configurazione=cfg_un_cons,
            porta=PortaFinta(esito="fatto", testo=json.dumps(_json_valido())),
            adesso=adesso,
            caso=random.Random(1),
        )

    # 2. Con ripiego su os.environ e un secondo consigliere su gemini, sceglie gemini
    cfg_due_cons = tmp_path / "bottega_due.toml"
    cfg_due_cons.write_text(
        cfg_un_cons.read_text(encoding="utf-8")
        + """
[candidati.cons-gemini]
nome = "Consigliere Gemini"
bottega = "google"
porta = "pi"
modello = "modello-gemini"
quota = "gemini"
funzioni = ["consigliare"]
""",
        encoding="utf-8",
    )
    forgia_vuota = ForgiaFinta()
    monkeypatch.setenv("BOTTEGA_QUOTA_GOOGLE__ARGON", valore_esaurita(adesso + timedelta(hours=1)))
    porta = PortaFinta(esito="fatto", testo=json.dumps(_json_valido()))
    creati = dividi(
        piano=f_piano,
        forgia=forgia_vuota,
        percorso_configurazione=cfg_due_cons,
        porta=porta,
        adesso=adesso,
        caso=random.Random(1),
    )
    assert creati == [1, 2, 3]
    assert porta.chiamate[0]["modello"] == "modello-gemini"



