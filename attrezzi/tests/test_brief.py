"""Prove per il modulo bottega.brief: estrazione del «Fatto quando» e nome del ramo."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bottega.brief import fatto_quando, ramo


def test_fatto_quando_blocco_base():
    corpo = (
        "## Obiettivo\n\n"
        "Fai il compito.\n\n"
        "## Fatto quando\n\n"
        "```bash\n"
        "uv run pytest -q\n"
        "```\n\n"
        "## Rapporto finale\n"
    )
    assert fatto_quando(corpo) == "uv run pytest -q"


def test_fatto_quando_senza_etichetta_di_linguaggio():
    corpo = "## Fatto quando\n```\npytest -q\n```\n"
    assert fatto_quando(corpo) == "pytest -q"


def test_fatto_quando_rimuove_spazi_in_testa_e_in_coda():
    corpo = "## Fatto quando\n```\n  \n  uv run pytest  \n\n  \n```\n"
    assert fatto_quando(corpo) == "uv run pytest"


def test_fatto_quando_ignora_blocchi_in_altre_sezioni():
    # Blocco prima di Fatto quando
    corpo_prima = (
        "## Da leggere prima\n\n"
        "```bash\n"
        "echo non questo\n"
        "```\n\n"
        "## Fatto quando\n\n"
        "```bash\n"
        "uv run pytest\n"
        "```\n"
    )
    assert fatto_quando(corpo_prima) == "uv run pytest"

    # Blocco dopo Fatto quando, con Fatto quando privo di blocchi
    corpo_dopo = (
        "## Fatto quando\n\n"
        "Nessun blocco qui dentro.\n\n"
        "## Rapporto finale\n\n"
        "```bash\n"
        "echo nemmeno questo\n"
        "```\n"
    )
    assert fatto_quando(corpo_dopo) is None


def test_fatto_quando_prende_il_primo_blocco():
    corpo = (
        "## Fatto quando\n\n"
        "```bash\n"
        "comando-1\n"
        "```\n\n"
        "```bash\n"
        "comando-2\n"
        "```\n"
    )
    assert fatto_quando(corpo) == "comando-1"


def test_fatto_quando_sezione_mancante():
    assert fatto_quando("## Obiettivo\n\nNessuna sezione fatto quando.") is None
    assert fatto_quando("") is None


def test_fatto_quando_blocco_vuoto():
    corpo_vuoto = "## Fatto quando\n```\n```\n"
    assert fatto_quando(corpo_vuoto) is None

    corpo_spazi = "## Fatto quando\n```\n   \n\t\n```\n"
    assert fatto_quando(corpo_spazi) is None


def test_fatto_quando_con_sottotitoli_interni():
    corpo = (
        "## Fatto quando\n\n"
        "### Dettagli del controllo\n\n"
        "```bash\n"
        "uv run pytest -q attrezzi/tests/test_brief.py\n"
        "```\n\n"
        "## Sezione successiva\n"
    )
    assert fatto_quando(corpo) == "uv run pytest -q attrezzi/tests/test_brief.py"


def test_fatto_quando_con_quattro_apici():
    corpo = (
        "## Fatto quando\n\n"
        "````bash\n"
        "echo test\n"
        "````\n"
    )
    assert fatto_quando(corpo) == "echo test"


def test_fatto_quando_con_commento_cancelletto_nel_blocco():
    corpo = (
        "## Obiettivo\n\nFai il compito.\n\n"
        "## Fatto quando\n\n"
        "```bash\n"
        "# Esegui le prove\n"
        "uv run pytest -q\n"
        "```\n\n"
        "## Rapporto finale\n"
    )
    assert fatto_quando(corpo) == "# Esegui le prove\nuv run pytest -q"



# Prove per ramo(numero, titolo)


def test_ramo_semplice():
    assert ramo(12, "Un titolo semplice") == "bottega/12-un-titolo-semplice"


def test_ramo_lettere_accentate_ridotte_a_base():
    assert (
        ramo(42, "È un'ottima opportunità per il caffè")
        == "bottega/42-e-un-ottima-opportunita-per-il-caffe"
    )


def test_ramo_caratteri_non_alfanumerici_e_trattini_ripetuti():
    assert ramo(7, "Fix: bug #123 (urgente)!") == "bottega/7-fix-bug-123-urgente"
    assert ramo(1, "alpha --- beta") == "bottega/1-alpha-beta"


def test_ramo_senza_trattini_in_testa_o_in_coda():
    assert ramo(3, "--titolo con trattini--") == "bottega/3-titolo-con-trattini"


def test_ramo_limite_quaranta_caratteri():
    cinquanta_a = "a" * 50
    risultato = ramo(5, cinquanta_a)
    assert risultato == f"bottega/5-{'a' * 40}"
    # Lunghezza dello slug esattamente 40
    slug = risultato.removeprefix("bottega/5-")
    assert len(slug) == 40


def test_ramo_taglio_a_quaranta_non_lascia_trattino_in_coda():
    # 39 'a', un trattino, poi altri caratteri
    titolo = ("a" * 39) + "-extra-caratteri"
    risultato = ramo(9, titolo)
    # Se tagliato a 40 caratteri, il 40esimo sarebbe '-' ma rstrip('-') lo rimuove
    assert risultato == f"bottega/9-{'a' * 39}"
    slug = risultato.removeprefix("bottega/9-")
    assert not slug.endswith("-")
    assert len(slug) <= 40


def test_ramo_titolo_vuoto_o_solo_spazi_o_punteggiatura():
    assert ramo(10, "") == "bottega/10"
    assert ramo(10, "   ") == "bottega/10"
    assert ramo(10, "---") == "bottega/10"
    assert ramo(10, "!@#$%^&*()") == "bottega/10"


@given(
    numero=st.integers(min_value=1, max_value=99999),
    titolo=st.text(min_size=0, max_size=100),
)
def test_proprieta_ramo(numero: int, titolo: str):
    nome = ramo(numero, titolo)
    prefisso = f"bottega/{numero}"
    assert nome.startswith(prefisso)
    if nome == prefisso:
        return
    assert nome.startswith(f"{prefisso}-")
    slug = nome[len(prefisso) + 1 :]
    assert len(slug) <= 40
    assert not slug.startswith("-")
    assert not slug.endswith("-")
    assert "--" not in slug
    assert re.fullmatch(r"[a-z0-9-]+", slug) is not None
