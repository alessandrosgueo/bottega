"""Il banco di prova della skill (B5-R10).

Sottopone una selezione casuale di casi della casistica al modello tramite una porta in sola lettura
o legge le risposte da file, confronta con la Scelta attesa di ciascun caso e calcola l'accordo.
Se richiesto (--pr), commenta l'esito sulla PR col ruolo «consigliere».
Solo libreria standard.
"""

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import random
import re
import sys
import tempfile

from bottega.casi import Caso, _foglio, leggi_casistica
from bottega.forgia import Forgia, ForgiaGh
from bottega.porte import Porta, porta as porta_fabbrica

_RIGA_RISPOSTA = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*:\s*([A-Za-z])\s*$")


def scegli_casi(casi: Sequence[Caso], k: int | None, caso: random.Random) -> list[Caso]:
    """Seleziona k casi a caso dalla sequenza; se k è None o maggiore/uguale al totale, li restituisce tutti."""
    lista = list(casi)
    if k is None or k >= len(lista):
        return lista
    if k <= 0:
        return []
    return caso.sample(lista, k)


def prompt_del_banco(skill: str, foglio: str) -> str:
    """Costruisce il prompt per la porta con la skill, il foglio delle domande e le istruzioni di risposta."""
    return (
        f"{skill.strip()}\n\n"
        f"{foglio.strip()}\n\n"
        "Per ciascun caso sopra, rispondi con una sola riga nel formato:\n"
        "ID: LETTERA\n"
        "e niente altro (nessun commento, premessa o spiegazione)."
    )


def leggi_risposte(testo: str) -> dict[str, str]:
    """Estrae le risposte dalle righe «ID: LETTERA», ignorando le altre righe. Tollerante su spazi e maiuscole."""
    risposte: dict[str, str] = {}
    for riga in testo.splitlines():
        m = _RIGA_RISPOSTA.match(riga)
        if m:
            id_caso = m.group(1).upper()
            lettera = m.group(2).upper()
            risposte[id_caso] = lettera
    return risposte


def confronta(casi: Sequence[Caso], risposte: dict[str, str]) -> tuple[list[str], int, int]:
    """Confronta le risposte con le scelte attese dei casi.

    Restituisce (divergenze, accordi, totale), dove le divergenze sono nel formato
    «ID: scelta X, risposta Y» (con «risposta —» se mancante).
    """
    divergenze: list[str] = []
    accordi = 0
    totale = len(casi)

    for caso in casi:
        id_norm = caso.id.strip().upper()
        scelta_attesa = caso.scelta.strip().upper()
        risposta_data = risposte.get(id_norm)

        if risposta_data == scelta_attesa:
            accordi += 1
        else:
            risp_str = risposta_data if risposta_data is not None else "—"
            divergenze.append(f"{caso.id}: scelta {caso.scelta.strip()}, risposta {risp_str}")

    return divergenze, accordi, totale


def argomenti_banco(parser: argparse.ArgumentParser) -> None:
    """Argomenti del sottocomando banco."""
    parser.add_argument(
        "--cartella",
        default="casistica",
        metavar="PERCORSO",
        help="cartella della casistica (predefinita: casistica)",
    )
    parser.add_argument(
        "--casi",
        type=int,
        default=None,
        metavar="K",
        help="numero di casi da sottoporre (predefinito: tutti)",
    )
    parser.add_argument(
        "--seme",
        type=int,
        default=None,
        metavar="S",
        help="seme per la scelta casuale dei casi",
    )
    parser.add_argument(
        "--porta",
        metavar="P",
        help="nome della porta da usare (obbligatoria senza --risposte)",
    )
    parser.add_argument(
        "--modello",
        metavar="M",
        help="nome del modello da usare (obbligatorio senza --risposte)",
    )
    parser.add_argument(
        "--risposte",
        metavar="FILE",
        help="file con le risposte invece di lanciare la porta",
    )
    parser.add_argument(
        "--pr",
        type=int,
        metavar="N",
        help="numero della PR su cui commentare l'esito",
    )
    parser.add_argument(
        "--skill",
        default="plugin/skills/bottega/SKILL.md",
        metavar="FILE",
        help="percorso della skill (predefinito: plugin/skills/bottega/SKILL.md)",
    )
    parser.add_argument(
        "--repo",
        default="",
        metavar="REPO",
        help="il repo di GitHub (predefinito: da GITHUB_REPOSITORY)",
    )


def comando_banco(
    args: argparse.Namespace,
    porta: Porta | None = None,
    forgia: Forgia | None = None,
) -> int:
    """Sottopone i casi al banco di prova: esce 0 se confrontato, 2 se non ha potuto."""
    cartella = Path(args.cartella)
    try:
        tutti_casi = leggi_casistica(cartella)
    except Exception as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        print(f"errore: casistica non leggibile: {motivo}", file=sys.stderr)
        return 2

    if not tutti_casi:
        print(f"errore: nessun caso trovato in {cartella}", file=sys.stderr)
        return 2

    seme = getattr(args, "seme", None)
    caso_rnd = random.Random(seme)
    casi_scelti = scegli_casi(tutti_casi, getattr(args, "casi", None), caso_rnd)

    if getattr(args, "risposte", None):
        percorso_risposte = Path(args.risposte)
        try:
            testo_risposte = percorso_risposte.read_text(encoding="utf-8")
        except OSError as e:
            motivo = e.strerror or str(e)
            print(f"errore: lettura file risposte {percorso_risposte}: {motivo}", file=sys.stderr)
            return 2
        risposte = leggi_risposte(testo_risposte)
    else:
        nome_porta = getattr(args, "porta", None)
        modello = getattr(args, "modello", None)
        if not nome_porta or not modello:
            print("errore: senza --risposte servono sia --porta che --modello", file=sys.stderr)
            return 2

        percorso_skill = Path(getattr(args, "skill", "plugin/skills/bottega/SKILL.md"))
        try:
            testo_skill = percorso_skill.read_text(encoding="utf-8")
        except OSError as e:
            motivo = e.strerror or str(e)
            print(f"errore: lettura skill {percorso_skill}: {motivo}", file=sys.stderr)
            return 2

        foglio = _foglio(casi_scelti)
        prompt = prompt_del_banco(testo_skill, foglio)

        p = porta
        if p is None:
            try:
                p = porta_fabbrica(nome_porta)
            except Exception as e:
                print(f"errore: porta {nome_porta}: {e}", file=sys.stderr)
                return 2

        with tempfile.TemporaryDirectory() as cartella_tmp:
            try:
                lancio = p.lancia(
                    cartella=Path(cartella_tmp),
                    prompt=prompt,
                    modello=modello,
                    sola_lettura=True,
                )
            except Exception as e:
                print(f"errore durante il lancio della porta: {e}", file=sys.stderr)
                return 2

        if lancio.esito != "fatto":
            print(f"errore: porta non risponde (esito: {lancio.esito})", file=sys.stderr)
            return 2

        risposte = leggi_risposte(lancio.testo)

    divergenze, accordi, totale = confronta(casi_scelti, risposte)

    for div in divergenze:
        print(div)
    print(f"accordo: {accordi} su {totale}")

    pr_num = getattr(args, "pr", None)
    if pr_num is not None:
        if forgia is None:
            repo = getattr(args, "repo", None) or os.environ.get("GITHUB_REPOSITORY", "")
            forgia = ForgiaGh(repo)
        righe_commento = []
        if divergenze:
            for div in divergenze:
                righe_commento.append(div)
        righe_commento.append(f"accordo: {accordi} su {totale}")
        corpo = "\n".join(righe_commento)
        try:
            forgia.commenta(pr_num, corpo, "consigliere")
        except Exception as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: commento sulla PR #{pr_num} non riuscito: {motivo}", file=sys.stderr)
            return 2

    return 0
