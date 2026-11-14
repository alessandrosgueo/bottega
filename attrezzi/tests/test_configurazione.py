"""Prove della configurazione del progetto: `bottega.toml`, il suo esempio e il comando `bottega configurazione`."""

import tomllib
from pathlib import Path

import pytest

from bottega.__main__ import costruisci_parser, main
from bottega.configurazione import (
    FUNZIONI,
    PORTE,
    QUOTE,
    Bottega,
    Candidato,
    Configurazione,
    ErroreConfigurazione,
    Progetto,
    controlla_configurazione,
    leggi_configurazione,
    peso_del_candidato,
    variabile_della_quota,
    variabili_della_quota,
)
from bottega.pubblico import cerca

ROOT = Path(__file__).resolve().parents[2]
MODELLO = ROOT / "plugin" / "skills" / "bottega" / "modelli" / "bottega.toml"

# Una configurazione valida e minima: ogni prova ne cambia una cosa sola.
BASE = """versione = 1

[progetto]
fuso = "Europe/Rome"

[botteghe.principale]
quota = "scarsa"
porte = ["claude-code"]

[candidati.maestro]
nome = "Maestro <modello forte>"
bottega = "principale"
porta = "claude-code"
modello = "<modello forte>"
funzioni = ["decidere", "rivedere"]
"""

# Un secondo candidato con lo stesso nome del primo.
CANDIDATO_CON_NOME_RIPETUTO = """
[candidati.altro]
nome = "Maestro <modello forte>"
bottega = "principale"
porta = "claude-code"
modello = "<modello forte>"
funzioni = ["rivedere"]
"""


def _scrivi(cartella: Path, testo: str) -> Path:
    percorso = cartella / "bottega.toml"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


def _errori(cartella: Path, testo: str) -> list[str]:
    return controlla_configurazione(_scrivi(cartella, testo))


def _cambia(testo: str, vecchio: str, nuovo: str) -> str:
    assert testo.count(vecchio) == 1, vecchio
    return testo.replace(vecchio, nuovo)


def test_esempio_si_legge_per_intero():
    assert leggi_configurazione(MODELLO) == Configurazione(
        versione=1,
        progetto=Progetto(
            comandanti=("<account>",),
            adattatore="<comando>",
            fuso="Europe/Rome",
            notte="01:30",
            manutenzione=("03:00-04:30", "23:30-01:00"),
            project=1,
            liberi=("<etichetta>",),
        ),
        botteghe={
            "principale": Bottega("principale", "scarsa", ("claude-code",)),
            "secondaria": Bottega("secondaria", "abbondante", ("pi",)),
        },
        candidati={
            "maestro": Candidato(
                "maestro",
                "Maestro <modello forte>",
                "principale",
                "claude-code",
                "<modello forte>",
                ("decidere", "rivedere"),
                None,
            ),
            "lavorante": Candidato(
                "lavorante",
                "Lavorante <modello economico>",
                "secondaria",
                "pi",
                "<modello economico>",
                ("eseguire",),
                "<etichetta del runner>",
            ),
        },
    )


def test_esempio_passa_il_controllo():
    assert controlla_configurazione(MODELLO) == []


def test_esempio_ha_ogni_chiave_ammessa():
    dati = tomllib.loads(MODELLO.read_text(encoding="utf-8"))
    assert set(dati) == {"versione", "progetto", "botteghe", "candidati"}
    assert set(dati["progetto"]) == {
        "comandanti",
        "adattatore",
        "fuso",
        "notte",
        "manutenzione",
        "project",
        "liberi",
    }
    assert {chiave for voce in dati["botteghe"].values() for chiave in voce} == {"quota", "porte"}
    assert {chiave for voce in dati["candidati"].values() for chiave in voce} == {
        "nome",
        "bottega",
        "porta",
        "modello",
        "funzioni",
        "runner",
    }


def test_esempio_senza_dati_veri():
    # Il controllo pubblico con le sole regole fisse (nessuna parola vietata): l'esempio non deve trovare nulla.
    assert cerca(MODELLO.read_text(encoding="utf-8"), MODELLO.name, []) == []


def test_base_e_valida_e_ha_i_facoltativi_di_serie(tmp_path):
    assert _errori(tmp_path, BASE) == []
    configurazione = leggi_configurazione(_scrivi(tmp_path, BASE))
    assert configurazione.progetto == Progetto(
        comandanti=(),
        adattatore=None,
        fuso="Europe/Rome",
        notte=None,
        manutenzione=(),
        project=None,
        liberi=(),
    )
    assert configurazione.candidati["maestro"].runner is None


def test_dizionari_nell_ordine_del_file(tmp_path):
    testo = _cambia(
        BASE,
        "[botteghe.principale]",
        '[botteghe.zeta]\nquota = "normale"\nporte = ["pi"]\n\n[botteghe.principale]',
    )
    testo = _cambia(
        testo,
        "[candidati.maestro]",
        '[candidati.lavorante]\nnome = "Lavorante <modello economico>"\nbottega = "zeta"\nporta = "pi"\n'
        'modello = "<modello economico>"\nfunzioni = ["eseguire"]\n\n[candidati.maestro]',
    )
    configurazione = leggi_configurazione(_scrivi(tmp_path, testo))
    assert list(configurazione.botteghe) == ["zeta", "principale"]
    assert list(configurazione.candidati) == ["lavorante", "maestro"]


ERRORI = [
    pytest.param(
        "versione = 1\n",
        "versione = 1\nrefuso = 1\n",
        ["bottega.toml: refuso: chiave sconosciuta"],
        id="chiave-sconosciuta-in-cima",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nnotte_x = "01:30"',
        ["bottega.toml: progetto.notte_x: chiave sconosciuta"],
        id="chiave-sconosciuta-in-progetto",
    ),
    pytest.param(
        'quota = "scarsa"',
        'quota = "scarsa"\nnota = "x"',
        ["bottega.toml: botteghe.principale.nota: chiave sconosciuta"],
        id="chiave-sconosciuta-in-bottega",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        'funzione = ["decidere", "rivedere"]',
        [
            "bottega.toml: candidati.maestro.funzione: chiave sconosciuta",
            "bottega.toml: candidati.maestro.funzioni: chiave obbligatoria mancante",
            "bottega.toml: candidati: nessun candidato con la funzione «decidere»",
        ],
        id="refuso-funzione-al-posto-di-funzioni",
    ),
    pytest.param(
        "versione = 1\n",
        "",
        ["bottega.toml: versione: chiave obbligatoria mancante"],
        id="versione-mancante",
    ),
    pytest.param(
        "versione = 1\n",
        "versione = 2\n",
        ["bottega.toml: versione: 2 non supportata (serve 1)"],
        id="versione-diversa",
    ),
    pytest.param(
        "versione = 1\n",
        'versione = "1"\n',
        ["bottega.toml: versione: tipo sbagliato: serve un numero intero"],
        id="versione-stringa",
    ),
    pytest.param(
        "versione = 1\n",
        "versione = true\n",
        ["bottega.toml: versione: tipo sbagliato: serve un numero intero"],
        id="versione-booleana",
    ),
    pytest.param(
        '[progetto]\nfuso = "Europe/Rome"\n\n',
        "",
        ["bottega.toml: progetto: chiave obbligatoria mancante"],
        id="progetto-mancante",
    ),
    pytest.param(
        'fuso = "Europe/Rome"\n',
        "",
        ["bottega.toml: progetto.fuso: chiave obbligatoria mancante"],
        id="fuso-mancante",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\ncomandanti = "<account>"',
        ["bottega.toml: progetto.comandanti: tipo sbagliato: serve una lista"],
        id="comandanti-non-lista",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        "fuso = \"Europe/Rome\"\ncomandanti = [3]",
        ["bottega.toml: progetto.comandanti[0]: tipo sbagliato: serve una stringa"],
        id="comandanti-voce-non-stringa",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nnotte = 130',
        ["bottega.toml: progetto.notte: tipo sbagliato: serve una stringa"],
        id="notte-numero",
    ),
    pytest.param(
        '[botteghe.principale]\nquota = "scarsa"\nporte = ["claude-code"]\n',
        '[botteghe.principale]\nquota = "scarsa"\nporte = "claude-code"\n',
        ["bottega.toml: botteghe.principale.porte: tipo sbagliato: serve una lista"],
        id="porte-non-lista",
    ),
    pytest.param(
        'porte = ["claude-code"]',
        "porte = []",
        ["bottega.toml: botteghe.principale.porte: lista vuota: serve almeno una porta"],
        id="porte-vuote",
    ),
    pytest.param(
        'porte = ["claude-code"]',
        'porte = ["claude-code", "claude-code"]',
        ["bottega.toml: botteghe.principale.porte[1]: «claude-code» ripetuta"],
        id="porte-ripetute",
    ),
    pytest.param(
        'porte = ["claude-code"]',
        'porte = ["telegram"]',
        [
            "bottega.toml: botteghe.principale.porte[0]: «telegram» non è una porta "
            "(claude-code, antigravity, pi, copilot-cli)"
        ],
        id="porte-fuori-elenco",
    ),
    pytest.param(
        'quota = "scarsa"',
        'quota = "molta"',
        ["bottega.toml: botteghe.principale.quota: «molta» non è una quota (scarsa, normale, abbondante)"],
        id="quota-fuori-elenco",
    ),
    pytest.param(
        'quota = "scarsa"',
        "",
        ["bottega.toml: botteghe.principale: serve «quota» oppure «quote»"],
        id="quota-mancante",
    ),
    pytest.param(
        "[candidati.maestro]",
        "[candidati.Maestro]",
        ["bottega.toml: candidati.Maestro: id non valido: «Maestro» (si usano a-z, 0-9 e -)"],
        id="id-candidato-non-valido",
    ),
    pytest.param(
        'bottega = "principale"',
        'bottega = "altra"',
        ["bottega.toml: candidati.maestro.bottega: bottega inesistente: «altra»"],
        id="bottega-inesistente",
    ),
    pytest.param(
        'porta = "claude-code"',
        'porta = "telegram"',
        [
            "bottega.toml: candidati.maestro.porta: «telegram» non è una porta "
            "(claude-code, antigravity, pi, copilot-cli)"
        ],
        id="porta-inesistente",
    ),
    pytest.param(
        'porta = "claude-code"',
        'porta = "pi"',
        ["bottega.toml: candidati.maestro.porta: «pi» non è una porta della bottega «principale»"],
        id="porta-non-della-sua-bottega",
    ),
    pytest.param(
        'modello = "<modello forte>"',
        'modello = ""',
        ["bottega.toml: candidati.maestro.modello: valore vuoto"],
        id="modello-vuoto",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        'funzioni = ["decidere", "scrivere"]',
        [
            "bottega.toml: candidati.maestro.funzioni[1]: «scrivere» non è una funzione "
            "(decidere, eseguire, rivedere, consigliare)"
        ],
        id="funzione-fuori-elenco",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        "funzioni = []",
        [
            "bottega.toml: candidati.maestro.funzioni: lista vuota: serve almeno una funzione",
            "bottega.toml: candidati: nessun candidato con la funzione «decidere»",
        ],
        id="funzioni-vuote",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        'funzioni = ["rivedere"]',
        ["bottega.toml: candidati: nessun candidato con la funzione «decidere»"],
        id="nessun-candidato-decide",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        'funzioni = ["decidere", "rivedere"]\nrunner = ""',
        ["bottega.toml: candidati.maestro.runner: valore vuoto"],
        id="runner-vuoto",
    ),
    pytest.param(
        BASE[BASE.index("[candidati.maestro]") :],
        "",
        ["bottega.toml: candidati: nessun candidato con la funzione «decidere»"],
        id="nessun-candidato",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nproject = "1"',
        ["bottega.toml: progetto.project: tipo sbagliato: serve un numero intero"],
        id="project-tipo-sbagliato-stringa",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nproject = true',
        ["bottega.toml: progetto.project: tipo sbagliato: serve un numero intero"],
        id="project-tipo-sbagliato-booleano",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nproject = 0',
        ["bottega.toml: progetto.project: serve un intero positivo"],
        id="project-zero",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nproject = -5',
        ["bottega.toml: progetto.project: serve un intero positivo"],
        id="project-negativo",
    ),
    pytest.param(
        'funzioni = ["decidere", "rivedere"]',
        'funzioni = ["decidere", "rivedere"]\nrunner = "self-hosted"',
        ["bottega.toml: progetto.project: chiave obbligatoria se almeno un candidato ha «runner»"],
        id="project-mancante-con-runner",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = "bug"',
        ["bottega.toml: progetto.liberi: tipo sbagliato: serve una lista"],
        id="liberi-tipo-sbagliato",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = [1]',
        ["bottega.toml: progetto.liberi[0]: tipo sbagliato: serve una stringa"],
        id="liberi-elemento-non-stringa",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = [""]',
        ["bottega.toml: progetto.liberi[0]: valore vuoto"],
        id="liberi-elemento-vuoto",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = ["   "]',
        ["bottega.toml: progetto.liberi[0]: valore vuoto"],
        id="liberi-elemento-solo-spazi",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = ["bug", "bug"]',
        ["bottega.toml: progetto.liberi[1]: «bug» ripetuta"],
        id="liberi-ripetuta",
    ),
    pytest.param(
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nliberi = ["bug", "BUG"]',
        ["bottega.toml: progetto.liberi[1]: «BUG» ripetuta"],
        id="liberi-ripetuta-maiuscole",
    ),
]


@pytest.mark.parametrize("vecchio, nuovo, atteso", ERRORI)
def test_ogni_motivo_da_il_suo_errore(tmp_path, vecchio, nuovo, atteso):
    assert _errori(tmp_path, _cambia(BASE, vecchio, nuovo)) == atteso


def test_botteghe_non_tabella_e_un_errore(tmp_path):
    testo = BASE.replace('[botteghe.principale]\nquota = "scarsa"\nporte = ["claude-code"]\n', "")
    testo = _cambia(testo, "versione = 1\n", "versione = 1\nbotteghe = 3\n")
    assert _errori(tmp_path, testo) == ["bottega.toml: botteghe: tipo sbagliato: serve una tabella"]


def test_nome_ripetuto_e_un_errore(tmp_path):
    assert _errori(tmp_path, BASE + CANDIDATO_CON_NOME_RIPETUTO) == [
        "bottega.toml: candidati.altro.nome: nome ripetuto: «Maestro <modello forte>» (già in candidati.maestro)"
    ]


def test_nome_ripetuto_senza_badare_alle_maiuscole_e_un_errore(tmp_path):
    candidato_maiuscolo = CANDIDATO_CON_NOME_RIPETUTO.replace(
        'nome = "Maestro <modello forte>"', 'nome = "MAESTRO <MODELLO FORTE>"'
    )
    assert _errori(tmp_path, BASE + candidato_maiuscolo) == [
        "bottega.toml: candidati.altro.nome: nome ripetuto: «MAESTRO <MODELLO FORTE>» (già in candidati.maestro)"
    ]



@pytest.mark.parametrize("valore", ["1:30", "24:00", "23:60", "0130", "01:30:00", "01.30"])
def test_notte_non_hh_mm_e_un_errore(tmp_path, valore):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', f'fuso = "Europe/Rome"\nnotte = "{valore}"')
    assert _errori(tmp_path, testo) == [f"bottega.toml: progetto.notte: «{valore}» non è un'ora HH:MM"]


@pytest.mark.parametrize("valore", ["00:00", "01:30", "23:59"])
def test_notte_hh_mm_e_valida(tmp_path, valore):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', f'fuso = "Europe/Rome"\nnotte = "{valore}"')
    assert leggi_configurazione(_scrivi(tmp_path, testo)).progetto.notte == valore


@pytest.mark.parametrize("finestra", ["3:00-04:30", "03:00 04:30", "03:00-", "03:00-24:00", "03:00-04:60"])
def test_finestra_non_hh_mm_hh_mm_e_un_errore(tmp_path, finestra):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', f'fuso = "Europe/Rome"\nmanutenzione = ["{finestra}"]')
    assert _errori(tmp_path, testo) == [
        f"bottega.toml: progetto.manutenzione[0]: «{finestra}» non è una finestra HH:MM-HH:MM"
    ]


def test_finestra_con_inizio_uguale_alla_fine_e_un_errore(tmp_path):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', 'fuso = "Europe/Rome"\nmanutenzione = ["03:00-03:00"]')
    assert _errori(tmp_path, testo) == [
        "bottega.toml: progetto.manutenzione[0]: inizio uguale alla fine: «03:00-03:00»"
    ]


def test_finestra_che_passa_la_mezzanotte_e_valida(tmp_path):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', 'fuso = "Europe/Rome"\nmanutenzione = ["23:30-01:00"]')
    assert leggi_configurazione(_scrivi(tmp_path, testo)).progetto.manutenzione == ("23:30-01:00",)


@pytest.mark.parametrize("fuso", ["Europe/Roma", "Europa/Roma", "../Europe/Rome", "Europe"])
def test_fuso_sconosciuto_e_un_errore_e_non_un_eccezione(tmp_path, fuso):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', f'fuso = "{fuso}"')
    assert _errori(tmp_path, testo) == [
        f"bottega.toml: progetto.fuso: «{fuso}» non è un fuso orario noto (per esempio Europe/Rome)"
    ]


def test_tutti_gli_errori_insieme(tmp_path):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', 'fuso = "Europe/Roma"\nnotte = "25:00"')
    testo = _cambia(testo, 'quota = "scarsa"', 'quota = "molta"')
    assert _errori(tmp_path, testo) == [
        "bottega.toml: progetto.fuso: «Europe/Roma» non è un fuso orario noto (per esempio Europe/Rome)",
        "bottega.toml: progetto.notte: «25:00» non è un'ora HH:MM",
        "bottega.toml: botteghe.principale.quota: «molta» non è una quota (scarsa, normale, abbondante)",
    ]


def test_toml_non_valido_da_un_errore_solo_con_la_riga(tmp_path):
    errori = _errori(tmp_path, 'versione = 1\n[progetto\nfuso = "Europe/Rome"\n')
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: TOML non valido: ")
    assert "line 2" in errori[0]


def test_file_non_utf8_da_un_errore_solo(tmp_path):
    percorso = tmp_path / "bottega.toml"
    percorso.write_bytes(b'versione = 1\nx = "\xff"\n')
    errori = controlla_configurazione(percorso)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: TOML non valido: ")


def test_file_mancante_e_un_errore_come_gli_altri(tmp_path):
    percorso = tmp_path / "manca.toml"
    assert controlla_configurazione(percorso) == [f"bottega.toml: {percorso}: file non trovato"]


def test_file_mancante_leggi_solleva_oserror(tmp_path):
    with pytest.raises(OSError):
        leggi_configurazione(tmp_path / "manca.toml")


def test_leggi_con_errori_solleva_con_l_elenco(tmp_path):
    percorso = _scrivi(tmp_path, _cambia(BASE, 'quota = "scarsa"', 'quota = "molta"'))
    with pytest.raises(ErroreConfigurazione) as e:
        leggi_configurazione(percorso)
    assert str(e.value) == (
        "bottega.toml: botteghe.principale.quota: «molta» non è una quota (scarsa, normale, abbondante)"
    )


def test_elenchi_del_formato():
    assert PORTE == ("claude-code", "antigravity", "pi", "copilot-cli")
    assert FUNZIONI == ("decidere", "eseguire", "rivedere", "consigliare")
    assert QUOTE == ("scarsa", "normale", "abbondante")


def test_comando_esempio_esce_0_con_il_conteggio(capsys):
    assert main(["configurazione", "--file", str(MODELLO)]) == 0
    assert capsys.readouterr().out == "bottega.toml: botteghe 2, candidati 2, nessun errore\n"


def test_comando_con_errori_esce_1_e_li_stampa(tmp_path, capsys):
    percorso = _scrivi(tmp_path, _cambia(BASE, 'quota = "scarsa"', 'quota = "molta"'))
    assert main(["configurazione", "--file", str(percorso)]) == 1
    assert capsys.readouterr().out == (
        "bottega.toml: botteghe.principale.quota: «molta» non è una quota (scarsa, normale, abbondante)\n"
    )


def test_comando_file_mancante_esce_2(tmp_path, capsys):
    assert main(["configurazione", "--file", str(tmp_path / "manca.toml")]) == 2
    assert capsys.readouterr().err.startswith("errore: ")


def test_comando_predefinisce_il_file_del_progetto():
    assert costruisci_parser().parse_args(["configurazione"]).file == ".github/bottega/bottega.toml"


def test_project_e_liberi_validi(tmp_path):
    testo = _cambia(
        BASE,
        'fuso = "Europe/Rome"',
        'fuso = "Europe/Rome"\nproject = 42\nliberi = ["bug", "debito"]',
    )
    assert _errori(tmp_path, testo) == []
    configurazione = leggi_configurazione(_scrivi(tmp_path, testo))
    assert configurazione.progetto.project == 42
    assert configurazione.progetto.liberi == ("bug", "debito")


def test_liberi_vuota_e_valida(tmp_path):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', 'fuso = "Europe/Rome"\nliberi = []')
    assert _errori(tmp_path, testo) == []
    configurazione = leggi_configurazione(_scrivi(tmp_path, testo))
    assert configurazione.progetto.liberi == ()


def test_project_obbligatorio_con_runner_valido(tmp_path):
    testo = _cambia(BASE, 'fuso = "Europe/Rome"', 'fuso = "Europe/Rome"\nproject = 5')
    testo = _cambia(
        testo,
        'funzioni = ["decidere", "rivedere"]',
        'funzioni = ["decidere", "rivedere"]\nrunner = "self-hosted"',
    )
    assert _errori(tmp_path, testo) == []
    configurazione = leggi_configurazione(_scrivi(tmp_path, testo))
    assert configurazione.progetto.project == 5
    assert configurazione.candidati["maestro"].runner == "self-hosted"


SECCHI_BASE = """versione = 1

[progetto]
fuso = "Europe/Rome"

[botteghe.google]
quote = { gemini = "abbondante", argon = "scarsa", claude = "scarsa" }
porte = ["antigravity"]

[candidati.maestro]
nome = "Maestro <modello>"
bottega = "google"
porta = "antigravity"
modello = "<modello>"
quota = "argon"
funzioni = ["decidere"]
"""


def test_bottega_coi_secchi_valida(tmp_path):
    assert _errori(tmp_path, SECCHI_BASE) == []
    cfg = leggi_configurazione(_scrivi(tmp_path, SECCHI_BASE))
    bottega = cfg.botteghe["google"]
    assert bottega.quota == ""
    assert bottega.quote == (("argon", "scarsa"), ("claude", "scarsa"), ("gemini", "abbondante"))
    assert cfg.candidati["maestro"].quota == "argon"


def test_quota_e_quote_insieme_errore(tmp_path):
    testo = _cambia(
        BASE,
        'quota = "scarsa"',
        'quota = "scarsa"\nquote = { gemini = "abbondante" }',
    )
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: botteghe.principale: ")


def test_ne_quota_ne_quote_errore(tmp_path):
    testo = _cambia(BASE, 'quota = "scarsa"\n', "")
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: botteghe.principale: ")


def test_secchio_con_peso_sbagliato_errore(tmp_path):
    testo = _cambia(SECCHI_BASE, 'gemini = "abbondante"', 'gemini = "infinita"')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: botteghe.google.quote.gemini: ")


def test_secchio_con_nome_sbagliato_errore(tmp_path):
    testo = _cambia(SECCHI_BASE, 'gemini = "abbondante"', 'Gemini = "abbondante"')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: botteghe.google.quote.Gemini: ")


def test_quote_vuota_errore(tmp_path):
    testo = _cambia(
        SECCHI_BASE,
        'quote = { gemini = "abbondante", argon = "scarsa", claude = "scarsa" }',
        "quote = {}",
    )
    errori = _errori(tmp_path, testo)
    assert any(e.startswith("bottega.toml: botteghe.google.quote: ") for e in errori)


def test_candidato_senza_secchio_errore(tmp_path):
    testo = _cambia(SECCHI_BASE, 'quota = "argon"\n', "")
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: candidati.maestro.quota: ")


def test_candidato_con_secchio_sconosciuto_errore(tmp_path):
    testo = _cambia(SECCHI_BASE, 'quota = "argon"', 'quota = "ignoto"')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: candidati.maestro.quota: ")


def test_secchio_in_bottega_semplice_errore(tmp_path):
    testo = _cambia(BASE, 'porta = "claude-code"', 'porta = "claude-code"\nquota = "gemini"')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: candidati.maestro.quota: ")


@pytest.mark.parametrize("valore", ["1", "0", '"true"'])
def test_riserva_non_booleana_errore(tmp_path, valore):
    testo = _cambia(BASE, 'porta = "claude-code"', f'porta = "claude-code"\nriserva = {valore}')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: candidati.maestro.riserva: ")


@pytest.mark.parametrize("valore", ['""', '"   "'])
def test_quaderno_vuoto_errore(tmp_path, valore):
    testo = _cambia(BASE, 'porta = "claude-code"', f'porta = "claude-code"\nquaderno = {valore}')
    errori = _errori(tmp_path, testo)
    assert len(errori) == 1
    assert errori[0].startswith("bottega.toml: candidati.maestro.quaderno: ")


def test_riserva_e_quaderno_letti(tmp_path):
    testo = _cambia(
        BASE,
        'porta = "claude-code"',
        'porta = "claude-code"\nriserva = true\nquaderno = "modello-comune"',
    )
    assert _errori(tmp_path, testo) == []
    cand = leggi_configurazione(_scrivi(tmp_path, testo)).candidati["maestro"]
    assert cand.riserva is True
    assert cand.quaderno == "modello-comune"
    assert cand.quota is None


def test_peso_del_candidato(tmp_path):
    cfg_semplice = leggi_configurazione(_scrivi(tmp_path, BASE))
    assert peso_del_candidato(cfg_semplice, cfg_semplice.candidati["maestro"]) == "scarsa"

    testo_secchi = SECCHI_BASE + """
[candidati.lavorante]
nome = "Lavorante <modello>"
bottega = "google"
porta = "antigravity"
modello = "<modello>"
quota = "gemini"
funzioni = ["eseguire"]
"""
    cfg_secchi = leggi_configurazione(_scrivi(tmp_path, testo_secchi))
    assert peso_del_candidato(cfg_secchi, cfg_secchi.candidati["maestro"]) == "scarsa"
    assert peso_del_candidato(cfg_secchi, cfg_secchi.candidati["lavorante"]) == "abbondante"


def test_variabili_della_quota(tmp_path):
    testo = SECCHI_BASE + """
[botteghe.anthropic]
quota = "normale"
porte = ["claude-code"]
"""
    cfg = leggi_configurazione(_scrivi(tmp_path, testo))
    assert variabili_della_quota(cfg) == [
        "BOTTEGA_QUOTA_ANTHROPIC",
        "BOTTEGA_QUOTA_GOOGLE__ARGON",
        "BOTTEGA_QUOTA_GOOGLE__CLAUDE",
        "BOTTEGA_QUOTA_GOOGLE__GEMINI",
    ]
    assert variabile_della_quota(cfg.candidati["maestro"]) == "BOTTEGA_QUOTA_GOOGLE__ARGON"

    cfg_semplice = leggi_configurazione(_scrivi(tmp_path, BASE))
    assert variabile_della_quota(cfg_semplice.candidati["maestro"]) == "BOTTEGA_QUOTA_PRINCIPALE"


