"""Prove per il modulo bottega.segni: ruoli, segni, comandi e nota del giro."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bottega.segni import (
    RUOLI,
    Comando,
    comando,
    nota,
    ruolo,
    scrivi_nota,
    segna,
)


def test_ruoli_ammessi():
    assert set(RUOLI) == {"distributore", "esecutore", "consigliere", "revisore", "avviso"}


def test_segna_aggiunge_segno_in_prima_riga():
    testo = "Questo è il corpo del commento."
    risultato = segna(testo, "esecutore")
    assert risultato == "<!-- bottega:esecutore -->\nQuesto è il corpo del commento."


def test_segna_con_testo_vuoto():
    assert segna("", "distributore") == "<!-- bottega:distributore -->"


def test_segna_ruolo_non_valido_solleva_errore():
    with pytest.raises(ValueError, match="Ruolo non valido"):
        segna("ciao", "sconosciuto")


def test_ruolo_riconosce_segno_all_inizio():
    corpo = "<!-- bottega:esecutore -->\nContenuto del lavoro."
    assert ruolo(corpo) == "esecutore"


def test_ruolo_riconosce_segno_in_mezzo_o_alla_fine():
    corpo_mezzo = "Prima riga\n<!-- bottega:consigliere -->\nSeconda riga"
    assert ruolo(corpo_mezzo) == "consigliere"

    corpo_fine = "Nota di chiusura <!-- bottega:avviso -->"
    assert ruolo(corpo_fine) == "avviso"


def test_ruolo_con_spazi_nel_commento():
    corpo = "<!--   bottega:revisore   -->"
    assert ruolo(corpo) == "revisore"


def test_ruolo_senza_segno_restituisce_none():
    assert ruolo("Commento normale senza segni.") is None
    assert ruolo("") is None


def test_ruolo_con_ruolo_sconosciuto_restituisce_none():
    assert ruolo("<!-- bottega:alieno -->") is None


# Prove per comando


def test_comando_valido_da_comandante():
    corpo = "/bottega riprova"
    assert comando(corpo, "alice", ["alice", "bob"]) == Comando("riprova", "")


def test_comando_confronto_autore_senza_badare_alle_maiuscole():
    assert comando("/bottega riprova", "ALICE", ["alice"]) == Comando("riprova", "")
    assert comando("/bottega riprova", "alice", ["ALICE"]) == Comando("riprova", "")
    assert comando("/bottega riprova", "  Alice  ", ["alice"]) == Comando("riprova", "")


def test_comando_autore_non_comandante_restituisce_none():
    assert comando("/bottega riprova", "eve", ["alice", "bob"]) is None
    assert comando("/bottega riprova", "alice", []) is None


def test_comando_salta_righe_vuote_in_testa():
    corpo = "\n  \n\t\n/bottega riprova"
    assert comando(corpo, "alice", ["alice"]) == Comando("riprova", "")


def test_comando_con_segno_non_e_mai_un_comando():
    # Segno all'inizio
    corpo_inizio = "<!-- bottega:esecutore -->\n/bottega riprova"
    assert comando(corpo_inizio, "alice", ["alice"]) is None

    # Segno in mezzo
    corpo_mezzo = "/bottega riprova\n<!-- bottega:avviso -->"
    assert comando(corpo_mezzo, "alice", ["alice"]) is None

    # Segno sconosciuto
    corpo_sconosciuto = "<!-- bottega:alieno -->\n/bottega riprova"
    assert comando(corpo_sconosciuto, "alice", ["alice"]) is None


def test_comando_manca_prefisso_bottega():
    assert comando("riprova", "alice", ["alice"]) is None
    assert comando("ciao /bottega riprova", "alice", ["alice"]) is None


def test_comando_nome_non_ammesso():
    assert comando("/bottega ciao", "alice", ["alice"]) is None
    assert comando("/bottega", "alice", ["alice"]) is None
    assert comando("/bottega aiuto", "alice", ["alice"]) is None


def test_comando_sospendi():
    assert comando("/bottega sospendi", "alice", ["alice"]) == Comando("sospendi", "")
    assert comando("/bottega sospendi manutenzione", "alice", ["alice"]) == Comando(
        "sospendi", "manutenzione"
    )


def test_comando_consulta_con_domanda_stessa_riga():
    assert comando("/bottega consulta Come procedere?", "alice", ["alice"]) == Comando(
        "consulta", "Come procedere?"
    )


def test_comando_consulta_con_domanda_su_piu_righe():
    corpo = "/bottega consulta\nQuale delle due opzioni preferisci?"
    assert comando(corpo, "alice", ["alice"]) == Comando(
        "consulta", "Quale delle due opzioni preferisci?"
    )

    corpo_multiplo = (
        "/bottega consulta Domanda principale:\n"
        "- Opzione A\n"
        "- Opzione B"
    )
    assert comando(corpo_multiplo, "alice", ["alice"]) == Comando(
        "consulta", "Domanda principale:\n- Opzione A\n- Opzione B"
    )


def test_comando_consulta_senza_domanda_restituisce_none():
    assert comando("/bottega consulta", "alice", ["alice"]) is None
    assert comando("/bottega consulta   ", "alice", ["alice"]) is None
    assert comando("/bottega consulta\n  \n\t\n", "alice", ["alice"]) is None


# Prove per nota e scrivi_nota


def test_nota_e_scrivi_nota_base():
    d = {"attese": "1", "inizio": "2026-11-08T18:00:00"}
    testo = scrivi_nota(d)
    assert testo == "attese=1; inizio=2026-11-08T18:00:00"
    assert nota(testo) == d


def test_scrivi_nota_chiavi_in_ordine_alfabetico():
    d = {"z": "3", "a": "1", "m": "2"}
    assert scrivi_nota(d) == "a=1; m=2; z=3"


def test_scrivi_nota_sostituisce_punto_e_virgola_uguale_e_a_capo():
    d = {"motivo": "errore; codice=429\nriprova"}
    risultato = scrivi_nota(d)
    assert ";" not in risultato.removeprefix("motivo=")
    assert "=" not in risultato.removeprefix("motivo=")
    assert "\n" not in risultato
    assert risultato == "motivo=errore  codice 429 riprova"


def test_nota_vuota_o_none():
    assert nota(None) == {}
    assert nota("") == {}
    assert nota("   ") == {}
    assert scrivi_nota({}) == ""


def test_nota_con_spazi_extra_e_punti_e_virgola_ripetuti():
    testo = "  inizio = 2026-11-08T18:00:00 ; ; attese = 2 ; "
    assert nota(testo) == {"inizio": "2026-11-08T18:00:00", "attese": "2"}


@given(
    d=st.dictionaries(
        keys=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20
        ),
        values=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",), blacklist_characters=";=\r\n"
            ),
            min_size=0,
            max_size=50,
        ).map(str.strip),
        min_size=0,
        max_size=10,
    )
)
def test_proprieta_inversa_nota_e_scrivi_nota(d: dict[str, str]):
    assert nota(scrivi_nota(d)) == d
