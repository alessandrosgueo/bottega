import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bottega.__main__ import main
from bottega.casi import Caso, ErroreCasi, controlla_casistica, leggi

ROOT = Path(__file__).resolve().parents[2]
ATTREZZI = Path(__file__).resolve().parents[1]
CAMPI = ["Scenario", "Domanda", "Opzioni", "Scelta", "Perché", "Esito", "Fonte"]

CASO = """### CICLO-1. Un difetto del compito prima

**Scenario:** chi esegue il compito 2 scopre un difetto piccolo nel compito 1.
**Domanda:** che cosa fa chi esegue?
**Opzioni:**
- A) lo corregge con una prova che lo fissa
- B) si ferma e chiede a chi decide
- C) lo lascia stare
**Scelta:** A
**Perché:** è una modifica sensata, non irreversibile.
**Esito:** tenuta.
**Fonte:** dal vivo 2026-11-08
"""


def _scrivi(cartella: Path, nome: str, testo: str) -> Path:
    percorso = cartella / nome
    percorso.write_text(testo, encoding="utf-8")
    return percorso


def _riga(testo: str, inizio: str) -> int:
    """Il numero (da 1) della prima riga che comincia con `inizio`."""
    return next(n for n, r in enumerate(testo.split("\n"), 1) if r.startswith(inizio))


def _senza(testo: str, inizio: str) -> str:
    return "\n".join(r for r in testo.split("\n") if not r.startswith(inizio))


def _cambia(testo: str, vecchio: str, nuovo: str) -> str:
    assert testo.count(vecchio) == 1, vecchio
    return testo.replace(vecchio, nuovo)


def _errori(cartella: Path) -> list[str]:
    return controlla_casistica(cartella)


def test_caso_valido_si_legge_per_intero(tmp_path):
    p = _scrivi(tmp_path, "ciclo.md", CASO)
    assert leggi(p) == [
        Caso(
            id="CICLO-1",
            titolo="Un difetto del compito prima",
            scenario="chi esegue il compito 2 scopre un difetto piccolo nel compito 1.",
            domanda="che cosa fa chi esegue?",
            opzioni={
                "A": "lo corregge con una prova che lo fissa",
                "B": "si ferma e chiede a chi decide",
                "C": "lo lascia stare",
            },
            scelta="A",
            perche="è una modifica sensata, non irreversibile.",
            esito="tenuta.",
            fonte="dal vivo 2026-11-08",
            percorso=str(p),
            riga=1,
        )
    ]


def test_campo_e_opzione_che_vanno_a_capo(tmp_path):
    testo = _cambia(
        CASO, "**Scenario:** chi esegue il compito 2 scopre", "**Scenario:** chi esegue il compito 2\nscopre"
    )
    testo = _cambia(
        testo, "- A) lo corregge con una prova che lo fissa", "- A) lo corregge con una prova\n  che lo fissa"
    )
    caso = leggi(_scrivi(tmp_path, "ciclo.md", testo))[0]
    assert caso.scenario == "chi esegue il compito 2 scopre un difetto piccolo nel compito 1."
    assert caso.opzioni["A"] == "lo corregge con una prova che lo fissa"


@pytest.mark.parametrize("campo", CAMPI)
def test_campo_mancante_si_segnala_per_nome_alla_riga_del_titolo(tmp_path, campo):
    p = _scrivi(tmp_path, "ciclo.md", _senza(CASO, f"**{campo}:**"))
    assert _errori(tmp_path) == [f"{p}:1: campo mancante: **{campo}:**"]


def test_campi_fuori_ordine(tmp_path):
    righe = CASO.split("\n")
    righe[2], righe[3] = righe[3], righe[2]  # Domanda prima di Scenario
    testo = "\n".join(righe)
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Scenario:**')}: campo fuori ordine: **Scenario:**"]


def test_campo_ripetuto(tmp_path):
    testo = _cambia(CASO, "**Esito:** tenuta.\n", "**Esito:** tenuta.\n**Esito:** di nuovo.\n")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Esito:** di nuovo')}: campo ripetuto: **Esito:**"]


def test_campo_vuoto(tmp_path):
    testo = _cambia(CASO, "**Esito:** tenuta.", "**Esito:**")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Esito:**')}: campo vuoto: **Esito:**"]


def test_campo_sconosciuto(tmp_path):
    testo = _cambia(CASO, "**Esito:** tenuta.\n", "**Esito:** tenuta.\n**Nota:** di troppo.\n")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Nota:**')}: campo sconosciuto: **Nota:**"]


def test_riga_prima_del_primo_campo(tmp_path):
    testo = _cambia(CASO, "\n\n**Scenario:**", "\nTesto libero.\n\n**Scenario:**")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, 'Testo libero.')}: riga fuori da un campo"]


def test_campo_fuori_da_un_caso(tmp_path):
    testo = _cambia(CASO, "### CICLO-1.", "## CICLO-1.")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:{_riga(testo, '**' + c + ':**')}: campo fuori da un caso: **{c}:**" for c in CAMPI
    ]


def test_intestazione_senza_punto_e_malformata(tmp_path):
    testo = _cambia(CASO, "### CICLO-1. Un difetto", "### CICLO-1 Un difetto")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:1: intestazione malformata: serve «### <id>. <titolo>»"]


@pytest.mark.parametrize("id_", ["RICORSO-1", "CICLO-", "CICLO1", "ciclo-1", "CICLO-1a"])
def test_id_che_non_e_dell_area_con_un_numero(tmp_path, id_):
    testo = _cambia(CASO, "### CICLO-1.", f"### {id_}.")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:1: id «{id_}» deve cominciare con CICLO- e un numero"]


def test_id_ripetuto_nello_stesso_file(tmp_path):
    testo = CASO + "\n" + CASO
    p = _scrivi(tmp_path, "ciclo.md", testo)
    secondo = [n for n, r in enumerate(testo.split("\n"), 1) if r.startswith("### CICLO-1.")][1]
    assert _errori(tmp_path) == [f"{p}:{secondo}: id ripetuto: CICLO-1 (già a {p}:1)"]


def test_id_ripetuto_fra_file_diversi(tmp_path):
    altro = _scrivi(tmp_path, "CICLO.md", CASO)
    p = _scrivi(tmp_path, "ciclo.md", CASO)
    assert _errori(tmp_path) == [f"{p}:1: id ripetuto: CICLO-1 (già a {altro}:1)"]


@pytest.mark.parametrize("scelta", ["D", "b", "A)", ""])
def test_scelta_deve_essere_una_lettera_delle_opzioni(tmp_path, scelta):
    testo = _cambia(CASO, "**Scelta:** A", f"**Scelta:** {scelta}")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:{_riga(testo, '**Scelta:**')}: scelta «{scelta}» non è una delle opzioni (A, B, C)"
    ]


def test_meno_di_due_opzioni(tmp_path):
    testo = _senza(_senza(CASO, "- B)"), "- C)")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Opzioni:**')}: meno di due opzioni"]


@pytest.mark.parametrize("riga", ["- b) minuscola", "-  B) doppio spazio", "- B minuta", "B) senza trattino"])
def test_opzione_non_valida(tmp_path, riga):
    testo = _cambia(CASO, "- B) si ferma e chiede a chi decide", riga)
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, riga)}: opzione non valida: serve «- A) testo»"]


def test_opzione_ripetuta(tmp_path):
    testo = _cambia(CASO, "- B) si ferma e chiede a chi decide", "- A) si ferma e chiede a chi decide")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '- A) si ferma')}: opzione «A» ripetuta"]


@pytest.mark.parametrize("fonte", ["deciso dall'utente", "dal vivo 2026-11-08", "dal vivo 2024-02-29", "di chi decide"])
def test_fonte_nelle_tre_forme(tmp_path, fonte):
    _scrivi(tmp_path, "ciclo.md", _cambia(CASO, "**Fonte:** dal vivo 2026-11-08", f"**Fonte:** {fonte}"))
    assert _errori(tmp_path) == []


@pytest.mark.parametrize(
    "fonte", ["deciso da lui", "dal vivo 2026-02-30", "dal vivo 26-11-08", "dal vivo 2026-11-8", "di chi decide.", ""]
)
def test_fonte_fuori_dalle_tre_forme(tmp_path, fonte):
    testo = _cambia(CASO, "**Fonte:** dal vivo 2026-11-08", f"**Fonte:** {fonte}")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:{_riga(testo, '**Fonte:**')}: fonte «{fonte}» non è una delle tre forme: "
        "deciso dall'utente, dal vivo AAAA-MM-GG (data vera), di chi decide"
    ]


def test_leggi_con_errori_solleva_l_elenco(tmp_path):
    p = _scrivi(tmp_path, "ciclo.md", _senza(CASO, "**Esito:**"))
    with pytest.raises(ErroreCasi, match="campo mancante: \\*\\*Esito:\\*\\*"):
        leggi(p)


def test_leggimi_non_e_un_area(tmp_path):
    _scrivi(tmp_path, "LEGGIMI.md", "**Scenario:** non è un caso.\nNulla di più.\n")
    _scrivi(tmp_path, "ciclo.md", CASO)
    assert _errori(tmp_path) == []


def test_testo_prima_del_primo_caso_si_ignora(tmp_path):
    _scrivi(tmp_path, "ciclo.md", "# Casistica del ciclo\n\nUna premessa.\n\n" + CASO)
    assert _errori(tmp_path) == []


def test_errori_in_ordine_di_file(tmp_path):
    p = _scrivi(tmp_path, "ciclo.md", _senza(CASO, "**Esito:**"))
    altro = _scrivi(tmp_path, "altro.md", _senza(CASO.replace("CICLO-1", "ALTRO-1"), "**Esito:**"))
    assert _errori(tmp_path) == [f"{altro}:1: campo mancante: **Esito:**", f"{p}:1: campo mancante: **Esito:**"]


def test_senza_errori_conta_i_casi(tmp_path, capsys):
    _scrivi(tmp_path, "ciclo.md", CASO)
    _scrivi(tmp_path, "altro.md", CASO.replace("CICLO-1", "ALTRO-1"))
    assert main(["casi", "--cartella", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "casi: 2, nessun errore\n"


def test_con_errori_stampa_l_elenco_ed_esce_1(tmp_path, capsys):
    p = _scrivi(tmp_path, "ciclo.md", _senza(CASO, "**Esito:**"))
    assert main(["casi", "--cartella", str(tmp_path)]) == 1
    assert capsys.readouterr().out == f"{p}:1: campo mancante: **Esito:**\n"


def test_cartella_predefinita_e_casistica(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "casistica").mkdir()
    _scrivi(tmp_path / "casistica", "ciclo.md", CASO)
    assert main(["casi"]) == 0
    assert capsys.readouterr().out == "casi: 1, nessun errore\n"


def test_cartella_che_non_c_e_esce_2(tmp_path, capsys):
    assert main(["casi", "--cartella", str(tmp_path / "manca")]) == 2
    assert capsys.readouterr().err.startswith("errore:")


def test_domande_non_lascia_trapelare_la_risposta(tmp_path, capsys):
    testo = _cambia(CASO, "**Perché:** è una modifica sensata, non irreversibile.", "**Perché:** PERCHE_SEGRETO.")
    testo = _cambia(testo, "**Esito:** tenuta.", "**Esito:** ESITO_SEGRETO.")
    _scrivi(tmp_path, "ciclo.md", testo)
    assert main(["casi", "--cartella", str(tmp_path), "--domande"]) == 0
    out = capsys.readouterr().out
    for segreto in ("**Scelta:**", "**Perché:**", "**Esito:**", "**Fonte:**", "Scelta", "dal vivo"):
        assert segreto not in out
    assert "PERCHE_SEGRETO" not in out and "ESITO_SEGRETO" not in out
    assert "### CICLO-1. Un difetto del compito prima\n" in out
    assert "- B) si ferma e chiede a chi decide\n" in out


def test_domande_segue_ordine_di_file_e_di_caso(tmp_path, capsys):
    _scrivi(tmp_path, "ciclo.md", CASO + "\n" + CASO.replace("CICLO-1.", "CICLO-2."))
    _scrivi(tmp_path, "altro.md", CASO.replace("CICLO-1", "ALTRO-1"))
    assert main(["casi", "--cartella", str(tmp_path), "--domande"]) == 0
    righe = capsys.readouterr().out.split("\n")
    assert [r.split(".")[0] for r in righe if r.startswith("### ")] == ["### ALTRO-1", "### CICLO-1", "### CICLO-2"]


def test_domande_con_errori_esce_1_senza_foglio(tmp_path, capsys):
    p = _scrivi(tmp_path, "ciclo.md", _senza(CASO, "**Esito:**"))
    assert main(["casi", "--cartella", str(tmp_path), "--domande"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"{p}:1: campo mancante: **Esito:**\n"


def test_casi_nell_elenco_dei_comandi_e_nel_proprio_aiuto(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0 and "Controlla la casistica" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["casi", "--help"])
    aiuto = capsys.readouterr().out
    assert aiuto.startswith("uso: bottega casi ") and "--cartella" in aiuto and "--domande" in aiuto


def test_comando_vero_da_terminale(tmp_path):
    _scrivi(tmp_path, "ciclo.md", CASO)
    ambiente = {**os.environ, "PYTHONPATH": str(ATTREZZI)}
    esito = subprocess.run(
        [sys.executable, "-m", "bottega", "casi", "--cartella", str(tmp_path)],
        env=ambiente,
        capture_output=True,
        text=True,
    )
    assert esito.returncode == 0 and esito.stdout == "casi: 1, nessun errore\n"


def test_casistica_vera_passa_il_controllo(capsys):
    assert main(["casi", "--cartella", str(ROOT / "casistica")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("casi: ") and out.endswith(", nessun errore\n")


# Una riga del foglio che comincia con un'etichetta di risposta. «Scelta del formato» non ci cade: manca i due punti.
RISPOSTA_A_INIZIO_RIGA = re.compile(
    r"^\s*(\*\*(Scelta|Perché|Esito|Fonte)(:\*\*|\*\*:)|(Scelta|Perché|Esito|Fonte):)", re.MULTILINE
)


@pytest.mark.parametrize("etichetta", ["**Scelta:** A", "**Scelta**: A"])
def test_etichetta_in_linea_nello_scenario(tmp_path, etichetta):
    scenario = "**Scenario:** chi esegue il compito 2 scopre un difetto piccolo nel compito 1."
    testo = _cambia(CASO, scenario, f"{scenario} {etichetta}")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Scenario:**')}: etichetta non a inizio riga: **Scelta:**"]


def test_etichetta_in_linea_nella_domanda(tmp_path):
    testo = _cambia(CASO, "**Domanda:** che cosa fa chi esegue?", "**Domanda:** che cosa fa chi esegue? **Esito:** X")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '**Domanda:**')}: etichetta non a inizio riga: **Esito:**"]


def test_etichetta_in_linea_nell_opzione(tmp_path):
    testo = _cambia(CASO, "- A) lo corregge con una prova che lo fissa", "- A) uno **Perché:** X")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '- A) uno')}: etichetta non a inizio riga: **Perché:**"]


def test_etichetta_in_linea_nel_titolo(tmp_path):
    testo = _cambia(CASO, "### CICLO-1. Un difetto del compito prima", "### CICLO-1. Un **Esito:** difetto")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:1: etichetta non a inizio riga: **Esito:**"]


def test_etichetta_in_grassetto_rientrata_non_apre_il_campo(tmp_path):
    testo = _cambia(CASO, "**Esito:** tenuta.", "  **Esito:** tenuta.")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:1: campo mancante: **Esito:**",
        f"{p}:{_riga(testo, '  **Esito:**')}: etichetta non a inizio riga: **Esito:**",
    ]


def test_etichetta_con_i_due_punti_fuori_dal_grassetto(tmp_path):
    testo = _cambia(CASO, "**Scelta:** A", "**Scelta**: A")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:1: campo mancante: **Scelta:**",
        f"{p}:{_riga(testo, '**Scelta**: A')}: i due punti vanno dentro il grassetto: **Scelta:**",
    ]


def test_scelta_senza_grassetto_al_posto_della_sua_riga(tmp_path):
    testo = _cambia(CASO, "**Scelta:** A", "Scelta: A")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [
        f"{p}:1: campo mancante: **Scelta:**",
        f"{p}:{_riga(testo, 'Scelta: A')}: etichetta senza grassetto: serve **Scelta:**",
    ]


@pytest.mark.parametrize("nome", ["Scelta", "Perché", "Esito", "Fonte"])
def test_etichetta_senza_grassetto_a_inizio_riga_non_apre_il_campo(tmp_path, nome):
    riga = f"{nome}: testo"
    testo = _cambia(
        CASO,
        "**Perché:** è una modifica sensata, non irreversibile.\n",
        f"**Perché:** è una modifica sensata, non irreversibile.\n{riga}\n",
    )
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, riga)}: etichetta senza grassetto: serve **{nome}:**"]


def test_etichetta_senza_grassetto_rientrata_sotto_un_opzione(tmp_path):
    testo = _cambia(CASO, "- C) lo lascia stare\n", "- C) lo lascia stare\n  Esito: tenuta.\n")
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:{_riga(testo, '  Esito:')}: etichetta senza grassetto: serve **Esito:**"]


def test_titolo_con_tab_si_riconosce(tmp_path):
    p = _scrivi(tmp_path, "ciclo.md", _cambia(CASO, "### CICLO-1.", "###\tCICLO-1."))
    assert [caso.id for caso in leggi(p)] == ["CICLO-1"]


@pytest.mark.parametrize("intestazione", ["###\tCICLO-1 Un difetto del compito prima", "###"])
def test_titolo_malformato_con_tab_o_vuoto_da_l_errore_giusto(tmp_path, intestazione):
    testo = _cambia(CASO, "### CICLO-1. Un difetto del compito prima", intestazione)
    p = _scrivi(tmp_path, "ciclo.md", testo)
    assert _errori(tmp_path) == [f"{p}:1: intestazione malformata: serve «### <id>. <titolo>»"]


def test_file_d_area_con_estensione_maiuscola_si_segnala(tmp_path):
    p = _scrivi(tmp_path, "ciclo.MD", CASO)
    assert _errori(tmp_path) == [f"{p}:1: estensione «.MD»: serve «.md» minuscolo"]


@pytest.mark.parametrize(
    "nome, testo", [("LEGGIMI.md", "Nessun caso qui.\n"), ("ciclo.md", "# Premessa\n\nSolo testo.\n")]
)
def test_cartella_senza_casi_e_un_errore(tmp_path, capsys, nome, testo):
    _scrivi(tmp_path, nome, testo)
    assert _errori(tmp_path) == [f"{tmp_path}: nessun caso"]
    assert main(["casi", "--cartella", str(tmp_path)]) == 1
    assert capsys.readouterr().out == f"{tmp_path}: nessun caso\n"
    assert main(["casi", "--cartella", str(tmp_path), "--domande"]) == 1
    uscita = capsys.readouterr()
    assert uscita.out == "" and uscita.err == f"{tmp_path}: nessun caso\n"


def test_controlla_casistica_con_cartella_mancante_restituisce_l_errore(tmp_path):
    manca = tmp_path / "manca"
    assert controlla_casistica(manca) == [f"{manca}: cartella non trovata"]


@pytest.mark.parametrize(
    "riga", ["**Scelta:** A", "**Esito**: X", "Scelta: A", "  Perché: X", "**Fonte:** di chi decide"]
)
def test_la_prova_del_foglio_vede_le_risposte_a_inizio_riga(riga):
    assert RISPOSTA_A_INIZIO_RIGA.search(riga)


@pytest.mark.parametrize("riga", ["### FORMATO-1. Scelta del formato", "Scelta del formato", "Esito positivo"])
def test_la_prova_del_foglio_non_scambia_la_prosa_per_una_risposta(riga):
    assert not RISPOSTA_A_INIZIO_RIGA.search(riga)


def test_foglio_della_casistica_vera_non_ha_righe_con_le_risposte(capsys):
    assert main(["casi", "--cartella", str(ROOT / "casistica"), "--domande"]) == 0
    out = capsys.readouterr().out
    assert "### CICLO-1." in out
    assert not RISPOSTA_A_INIZIO_RIGA.search(out)


def test_titolo_con_scelta_del_formato_non_da_allarme(tmp_path, capsys):
    testo = CASO.replace("### CICLO-1. Un difetto del compito prima", "### FORMATO-1. Scelta del formato")
    _scrivi(tmp_path, "formato.md", testo)
    assert main(["casi", "--cartella", str(tmp_path), "--domande"]) == 0
    assert "### FORMATO-1. Scelta del formato\n" in capsys.readouterr().out
