"""La casistica: i casi di decisione, il loro formato e il foglio del banco di prova.

Un file per area, `casistica/<area>.md` (area in minuscolo). Ogni caso è una sezione `### <ID>. <titolo>` con i campi in
quest'ordine, uno per riga che comincia col nome in grassetto; il testo di un campo può andare a capo. Le opzioni sono
righe `- <LETTERA>) <testo>`: una riga rientrata sotto un'opzione ne continua il testo.
"""

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CAMPI = ("Scenario", "Domanda", "Opzioni", "Scelta", "Perché", "Esito", "Fonte")
# Campi di testo che non possono restare vuoti; Opzioni, Scelta e Fonte hanno regole loro.
_NON_VUOTI = ("Scenario", "Domanda", "Perché", "Esito")
_FONTI_FISSE = ("deciso dall'utente", "di chi decide")
_ETICHETTA = re.compile(r"\*\*([^*:]+):\*\*(.*)")
_INTESTAZIONE = re.compile(r"###\s+(\S+?)\.\s+(\S.*)")
_OPZIONE = re.compile(r"- ([A-Z])\) (\S.*)")
_DAL_VIVO = re.compile(r"dal vivo ([0-9]{4}-[0-9]{2}-[0-9]{2})")


class ErroreCasi(ValueError):
    """La casistica ha errori di formato: il messaggio li elenca come `file:riga: motivo`, uno per riga."""


@dataclass(frozen=True)
class Caso:
    """Un caso letto per intero; `riga` è la riga del titolo nel file."""

    id: str
    titolo: str
    scenario: str
    domanda: str
    opzioni: dict[str, str]
    scelta: str
    perche: str
    esito: str
    fonte: str
    percorso: str
    riga: int


@dataclass
class _Campo:
    """Un campo com'è nel file: il nome (None se non è un campo valido), la riga dell'etichetta, le sue righe."""

    nome: str | None
    riga: int
    righe: list[tuple[int, str]]

    def testo(self) -> str:
        return " ".join(r.strip() for _, r in self.righe)


def leggi(percorso: Path) -> list[Caso]:
    """I casi di un file di area; con errori di formato solleva ErroreCasi con l'elenco."""
    casi, errori = _analizza(percorso, {})
    if errori:
        raise ErroreCasi("\n".join(errori))
    return casi


def controlla_casistica(cartella: Path) -> list[str]:
    """Gli errori di formato della casistica, come `file:riga: motivo`, nell'ordine dei file e delle righe."""
    return _esamina(cartella)[1]


def argomenti_casi(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cartella", default="casistica", metavar="PERCORSO", help="cartella della casistica (predefinita: casistica)"
    )
    parser.add_argument(
        "--domande",
        action="store_true",
        help="stampa il foglio del banco di prova: casi senza scelta, perché, esito e fonte",
    )


def comando_casi(args: argparse.Namespace) -> int:
    """Controlla la casistica; con --domande, il foglio.

    Senza opzioni esce 1 con gli errori di formato, 0 con una riga di conteggio. Con --domande stampa il foglio del
    banco di prova, o esce 1 con gli errori su stderr. Esce 2 se la cartella non si legge.
    """
    try:
        casi, errori = _esamina(Path(args.cartella))
    except OSError as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
    if args.domande:
        if errori:
            print("\n".join(errori), file=sys.stderr)
            return 1
        print(_foglio(casi), end="")
        return 0
    if errori:
        print("\n".join(errori))
        return 1
    print(f"casi: {len(casi)}, nessun errore")
    return 0


def _file_di_area(cartella: Path) -> list[Path]:
    """I file di area della cartella in ordine di nome: i .md, tranne LEGGIMI.md, che descrive e non è un'area."""
    if not cartella.is_dir():
        raise FileNotFoundError(f"cartella della casistica non trovata: {cartella}")
    file = [p for p in cartella.glob("*.md") if p.is_file() and p.name.casefold() != "leggimi.md"]
    return sorted(file, key=lambda p: p.name)


def _esamina(cartella: Path) -> tuple[list[Caso], list[str]]:
    visti: dict[str, tuple[str, int]] = {}  # id -> (file, riga): per trovare i doppi anche fra file diversi
    casi: list[Caso] = []
    errori: list[str] = []
    for percorso in _file_di_area(cartella):
        nuovi, nuovi_errori = _analizza(percorso, visti)
        casi += nuovi
        errori += nuovi_errori
    return casi, errori


def _analizza(percorso: Path, visti: dict[str, tuple[str, int]]) -> tuple[list[Caso], list[str]]:
    """I casi del file e i suoi errori, in ordine di riga. `visti` ricorda gli id già letti in tutta la casistica."""
    try:
        testo = percorso.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return [], [_errore(percorso, 1, "file non leggibile come UTF-8")]
    area = percorso.stem.upper()
    errori: list[tuple[int, str]] = []
    sezioni: list[tuple[int, str, list[tuple[int, str]]]] = []  # riga del titolo, titolo, righe del corpo
    corpo: list[tuple[int, str]] | None = None
    for numero, riga in enumerate(testo.split("\n"), 1):
        if riga.startswith("### "):
            corpo = []
            sezioni.append((numero, riga.strip(), corpo))
        elif corpo is not None:
            corpo.append((numero, riga))
        elif etichetta := _ETICHETTA.match(riga.strip()):
            errori.append((numero, f"campo fuori da un caso: **{etichetta.group(1)}:**"))
    casi: list[Caso] = []
    for numero, intestazione, righe in sezioni:
        caso, errori_caso = _caso(percorso, area, numero, intestazione, righe, visti)
        errori += errori_caso
        if caso is not None:
            casi.append(caso)
    errori.sort(key=lambda e: e[0])  # stabile: a parità di riga, resta l'ordine di trovazione
    return casi, [_errore(percorso, numero, motivo) for numero, motivo in errori]


def _caso(
    percorso: Path,
    area: str,
    numero: int,
    intestazione: str,
    righe: list[tuple[int, str]],
    visti: dict[str, tuple[str, int]],
) -> tuple[Caso | None, list[tuple[int, str]]]:
    """Il caso di una sezione, o None con i suoi errori. `numero` è la riga del titolo."""
    trovata = _INTESTAZIONE.fullmatch(intestazione)
    if trovata is None:
        return None, [(numero, "intestazione malformata: serve «### <id>. <titolo>»")]
    id_, titolo = trovata.groups()
    errori: list[tuple[int, str]] = []
    if not re.fullmatch(re.escape(area) + r"-[0-9]+", id_):
        errori.append((numero, f"id «{id_}» deve cominciare con {area}- e un numero"))
    elif id_ in visti:
        altro_percorso, altro_riga = visti[id_]
        errori.append((numero, f"id ripetuto: {id_} (già a {altro_percorso}:{altro_riga})"))
    else:
        visti[id_] = (str(percorso), numero)
    campi, errori_campi = _campi(righe)
    errori += errori_campi
    for nome in CAMPI:
        if nome not in campi:
            errori.append((numero, f"campo mancante: **{nome}:**"))
    for nome in _NON_VUOTI:
        if nome in campi and not campi[nome].testo():
            errori.append((campi[nome].riga, f"campo vuoto: **{nome}:**"))
    opzioni: dict[str, str] = {}
    if "Opzioni" in campi:
        opzioni, errori_opzioni = _opzioni(campi["Opzioni"].righe)
        errori += errori_opzioni
        if len(opzioni) < 2:
            errori.append((campi["Opzioni"].riga, "meno di due opzioni"))
    if "Scelta" in campi and "Opzioni" in campi:
        scelta = campi["Scelta"]
        if scelta.testo() not in opzioni:
            elenco = ", ".join(opzioni) or "nessuna"
            errori.append((scelta.riga, f"scelta «{scelta.testo()}» non è una delle opzioni ({elenco})"))
    if "Fonte" in campi and not _fonte_valida(campi["Fonte"].testo()):
        errori.append(
            (
                campi["Fonte"].riga,
                f"fonte «{campi['Fonte'].testo()}» non è una delle tre forme: "
                "deciso dall'utente, dal vivo AAAA-MM-GG (data vera), di chi decide",
            )
        )
    if errori:
        return None, errori
    return (
        Caso(
            id=id_,
            titolo=titolo,
            scenario=campi["Scenario"].testo(),
            domanda=campi["Domanda"].testo(),
            opzioni=opzioni,
            scelta=campi["Scelta"].testo(),
            perche=campi["Perché"].testo(),
            esito=campi["Esito"].testo(),
            fonte=campi["Fonte"].testo(),
            percorso=str(percorso),
            riga=numero,
        ),
        [],
    )


def _campi(righe: list[tuple[int, str]]) -> tuple[dict[str, _Campo], list[tuple[int, str]]]:
    """I campi di un caso per nome; segnala righe fuori campo, nomi sconosciuti, ripetuti o fuori ordine."""
    campi: dict[str, _Campo] = {}
    errori: list[tuple[int, str]] = []
    ultimo = -1  # posizione in CAMPI del campo più avanzato visto finora
    attuale: _Campo | None = None
    for numero, riga in righe:
        testo = riga.strip()
        if not testo:
            continue
        etichetta = _ETICHETTA.match(testo)
        if etichetta is None:
            if attuale is None:
                errori.append((numero, "riga fuori da un campo"))
            else:
                attuale.righe.append((numero, riga))
            continue
        nome = etichetta.group(1)
        resto = etichetta.group(2).strip()
        if nome not in CAMPI:
            errori.append((numero, f"campo sconosciuto: **{nome}:**"))
            attuale = _Campo(None, numero, [])
        elif nome in campi:
            errori.append((numero, f"campo ripetuto: **{nome}:**"))
            attuale = _Campo(None, numero, [])
        else:
            posizione = CAMPI.index(nome)
            if posizione < ultimo:
                errori.append((numero, f"campo fuori ordine: **{nome}:**"))
            ultimo = max(ultimo, posizione)
            attuale = campi[nome] = _Campo(nome, numero, [])
            if resto:
                attuale.righe.append((numero, resto))
    return campi, errori


def _opzioni(righe: list[tuple[int, str]]) -> tuple[dict[str, str], list[tuple[int, str]]]:
    """Le opzioni di un campo: `- A) testo`. Una riga rientrata sotto un'opzione ne continua il testo."""
    opzioni: dict[str, str] = {}
    errori: list[tuple[int, str]] = []
    lettera: str | None = None  # l'ultima opzione letta
    for numero, riga in righe:
        testo = riga.strip()
        trovata = _OPZIONE.fullmatch(testo)
        if trovata is not None:
            lettera = trovata.group(1)
            if lettera in opzioni:
                errori.append((numero, f"opzione «{lettera}» ripetuta"))
                lettera = None
            else:
                opzioni[lettera] = trovata.group(2)
        elif lettera is not None and riga[:1] in (" ", "\t"):
            opzioni[lettera] += " " + testo
        else:
            errori.append((numero, "opzione non valida: serve «- A) testo»"))
    return opzioni, errori


def _fonte_valida(fonte: str) -> bool:
    """Vero per le due forme fisse e per `dal vivo AAAA-MM-GG` con una data del calendario."""
    if fonte in _FONTI_FISSE:
        return True
    trovata = _DAL_VIVO.fullmatch(fonte)
    if trovata is None:
        return False
    try:
        datetime.date.fromisoformat(trovata.group(1))
    except ValueError:
        return False
    return True


def _foglio(casi: list[Caso]) -> str:
    """Il foglio del banco di prova: id, titolo, scenario, domanda e opzioni. Mai scelta, perché, esito o fonte."""
    blocchi = []
    for caso in casi:
        righe = [
            f"### {caso.id}. {caso.titolo}",
            f"**Scenario:** {caso.scenario}",
            f"**Domanda:** {caso.domanda}",
            "**Opzioni:**",
            *(f"- {lettera}) {testo}" for lettera, testo in caso.opzioni.items()),
        ]
        blocchi.append("\n".join(righe) + "\n")
    return "\n".join(blocchi)


def _errore(percorso: Path, riga: int, motivo: str) -> str:
    return f"{percorso}:{riga}: {motivo}"
