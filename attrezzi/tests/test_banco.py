"""Prove per il banco di prova della skill (bottega.banco)."""

from argparse import Namespace
from pathlib import Path
import random

from bottega.banco import (
    argomenti_banco,
    comando_banco,
    confronta,
    leggi_risposte,
    prompt_del_banco,
    scegli_casi,
)
from bottega.casi import Caso
from bottega.finta import ForgiaFinta
from bottega.forgia import Issue
from bottega.porte import Controllo, Lancio


class PortaFinta:
    """Porta finta per simulare le risposte della porta nelle prove."""

    def __init__(
        self,
        esito: str = "fatto",
        testo: str = "",
        conversazione: str | None = None,
    ) -> None:
        self.esito = esito
        self.testo = testo
        self.conversazione = conversazione
        self.chiamate: list[dict] = []

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


CASO_1 = """### CICLO-1. Primo caso

**Scenario:** scenario uno.
**Domanda:** domanda uno?
**Opzioni:**
- A) opzione a
- B) opzione b
**Scelta:** A
**Perché:** perché sì.
**Esito:** positivo.
**Fonte:** deciso dall'utente
"""

CASO_2 = """### CICLO-2. Secondo caso

**Scenario:** scenario due.
**Domanda:** domanda due?
**Opzioni:**
- A) opzione a
- B) opzione b
**Scelta:** B
**Perché:** perché no.
**Esito:** positivo.
**Fonte:** deciso dall'utente
"""


def _crea_caso(id_: str, scelta: str = "A") -> Caso:
    return Caso(
        id=id_,
        titolo=f"Titolo {id_}",
        scenario="scenario",
        domanda="domanda?",
        opzioni={"A": "opt A", "B": "opt B"},
        scelta=scelta,
        perche="perché",
        esito="esito",
        fonte="deciso dall'utente",
        percorso="test.md",
        riga=1,
    )


def test_scegli_casi_tutti_se_meno():
    casi = [_crea_caso("C1"), _crea_caso("C2"), _crea_caso("C3")]
    rnd = random.Random(0)
    assert len(scegli_casi(casi, 5, rnd)) == 3
    assert len(scegli_casi(casi, 3, rnd)) == 3
    assert len(scegli_casi(casi, None, rnd)) == 3


def test_scegli_casi_seme():
    casi = [_crea_caso(f"C{i}") for i in range(10)]
    s1 = scegli_casi(casi, 4, random.Random(42))
    s2 = scegli_casi(casi, 4, random.Random(42))
    assert [c.id for c in s1] == [c.id for c in s2]
    assert len(s1) == 4


def test_leggi_risposte_tollerante():
    testo = """
    Ecco le risposte elaborate:
    CICLO-1: A
      CICLO-2 :  b  
    Una riga descrittiva qualsiasi
    CICLO-3: c
    Altro commento finale.
    """
    risposte = leggi_risposte(testo)
    assert risposte == {
        "CICLO-1": "A",
        "CICLO-2": "B",
        "CICLO-3": "C",
    }


def test_confronta_divergenze_e_mancanti():
    casi = [
        _crea_caso("C1", scelta="A"),
        _crea_caso("C2", scelta="B"),
        _crea_caso("C3", scelta="C"),
    ]
    risposte = {
        "C1": "A",
        "C2": "A",
        # C3 mancante
    }
    divergenze, accordi, totale = confronta(casi, risposte)
    assert accordi == 1
    assert totale == 3
    assert divergenze == [
        "C2: scelta B, risposta A",
        "C3: scelta C, risposta —",
    ]


def test_banco_da_file(tmp_path, capsys):
    cartella = tmp_path / "casistica"
    cartella.mkdir()
    (cartella / "ciclo.md").write_text(CASO_1 + "\n" + CASO_2, encoding="utf-8")

    risposte_file = tmp_path / "risposte.txt"
    risposte_file.write_text("CICLO-1: A\nCICLO-2: B\n", encoding="utf-8")

    args = Namespace(
        cartella=str(cartella),
        casi=None,
        seme=None,
        porta=None,
        modello=None,
        risposte=str(risposte_file),
        pr=None,
    )
    codice = comando_banco(args)
    assert codice == 0
    catturato = capsys.readouterr()
    assert "accordo: 2 su 2" in catturato.out


def test_banco_con_porta_finta(tmp_path, capsys):
    cartella = tmp_path / "casistica"
    cartella.mkdir()
    (cartella / "ciclo.md").write_text(CASO_1 + "\n" + CASO_2, encoding="utf-8")

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("Testo skill segreto.", encoding="utf-8")

    porta = PortaFinta(testo="CICLO-1: A\nCICLO-2: B\n")
    args = Namespace(
        cartella=str(cartella),
        casi=None,
        seme=None,
        porta="pi",
        modello="modello-test",
        risposte=None,
        pr=None,
        skill=str(skill_file),
    )
    codice = comando_banco(args, porta=porta)
    assert codice == 0

    assert len(porta.chiamate) == 1
    chiamata = porta.chiamate[0]
    assert chiamata["sola_lettura"] is True
    assert "Testo skill segreto." in chiamata["prompt"]
    assert "CICLO-1" in chiamata["prompt"]
    assert "Scelta:" not in chiamata["prompt"]
    assert "**Scelta:**" not in chiamata["prompt"]

    catturato = capsys.readouterr()
    assert "accordo: 2 su 2" in catturato.out


def test_banco_porta_che_non_risponde(tmp_path):
    cartella = tmp_path / "casistica"
    cartella.mkdir()
    (cartella / "ciclo.md").write_text(CASO_1, encoding="utf-8")

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("Skill.", encoding="utf-8")

    porta = PortaFinta(esito="errore", testo="")
    args = Namespace(
        cartella=str(cartella),
        casi=None,
        seme=None,
        porta="pi",
        modello="modello-test",
        risposte=None,
        pr=None,
        skill=str(skill_file),
    )
    codice = comando_banco(args, porta=porta)
    assert codice == 2


def test_banco_commenta_la_pr(tmp_path):
    cartella = tmp_path / "casistica"
    cartella.mkdir()
    (cartella / "ciclo.md").write_text(CASO_1 + "\n" + CASO_2, encoding="utf-8")

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("Skill.", encoding="utf-8")

    porta = PortaFinta(testo="CICLO-1: A\nCICLO-2: A\n")  # CICLO-2 diverge
    forgia = ForgiaFinta(issues=[Issue(numero=10, titolo="PR 10")])

    args = Namespace(
        cartella=str(cartella),
        casi=None,
        seme=None,
        porta="pi",
        modello="modello-test",
        risposte=None,
        pr=10,
        skill=str(skill_file),
    )
    codice = comando_banco(args, porta=porta, forgia=forgia)
    assert codice == 0

    commenti = [entry for entry in forgia.registro if entry[0] == "commenta"]
    assert len(commenti) == 1
    _, pr_num, corpo, ruolo = commenti[0]
    assert pr_num == 10
    assert ruolo == "consigliere"
    assert "CICLO-2: scelta B, risposta A" in corpo
    assert "accordo: 1 su 2" in corpo
