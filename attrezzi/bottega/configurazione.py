"""La configurazione del progetto, `.github/bottega/bottega.toml`: letta con `tomllib` e controllata per intero.

Ogni errore è una riga `bottega.toml: <chiave con il suo percorso>: <motivo>`, e vengono tutti insieme, così chi
scrive il file lo corregge in un giro solo. Un file che non è TOML valido dà un errore solo. Solo libreria standard.
"""

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bottega.ci import rischi

PERCORSO_PREDEFINITO = ".github/bottega/bottega.toml"
PREFISSO = "bottega.toml"
VERSIONE_FORMATO = 1
PORTE = ("claude-code", "antigravity", "pi", "copilot-cli")
FUNZIONI = ("decidere", "eseguire", "rivedere", "consigliare")
QUOTE = ("scarsa", "normale", "abbondante")

_CHIAVI_TOP = ("versione", "progetto", "botteghe", "candidati")
_CHIAVI_PROGETTO = ("comandanti", "adattatore", "fuso", "notte", "manutenzione", "project", "liberi")
_CHIAVI_BOTTEGA = ("quota", "porte")
_CHIAVI_CANDIDATO = ("nome", "bottega", "porta", "modello", "funzioni", "runner")
_ID = re.compile(r"[a-z0-9-]+")
_ORA = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
_FINESTRA = re.compile(r"((?:[01][0-9]|2[0-3]):[0-5][0-9])-((?:[01][0-9]|2[0-3]):[0-5][0-9])")


@dataclass(frozen=True)
class Progetto:
    """La sezione `[progetto]`: il fuso è obbligatorio, il resto è facoltativo."""

    comandanti: tuple[str, ...]
    adattatore: str | None
    fuso: str
    notte: str | None
    manutenzione: tuple[str, ...]
    project: int | None = None
    liberi: tuple[str, ...] = ()


@dataclass(frozen=True)
class Bottega:
    """Un abbonamento con la sua quota e le sue porte."""

    id: str
    quota: str
    porte: tuple[str, ...]


@dataclass(frozen=True)
class Candidato:
    """Un modello di una bottega, da una porta, per le sue funzioni."""

    id: str
    nome: str
    bottega: str
    porta: str
    modello: str
    funzioni: tuple[str, ...]
    runner: str | None


@dataclass(frozen=True)
class Configurazione:
    """Il file intero, controllato. I dizionari tengono l'ordine del file."""

    versione: int
    progetto: Progetto
    botteghe: dict[str, Bottega]
    candidati: dict[str, Candidato]


class ErroreConfigurazione(ValueError):
    """La configurazione ha errori: il messaggio li elenca, uno per riga, come `bottega.toml: <chiave>: <motivo>`."""


def leggi_configurazione(percorso: Path) -> Configurazione:
    """La configurazione del file: con errori solleva ErroreConfigurazione con l'elenco.

    Un file illeggibile solleva OSError.
    """
    configurazione, errori = _esamina(percorso)
    if configurazione is None:
        raise ErroreConfigurazione("\n".join(errori))
    return configurazione


def controlla_configurazione(percorso: Path) -> list[str]:
    """Gli errori della configurazione, nell'ordine del file.

    Non solleva mai un'eccezione: un file mancante o illeggibile è un errore come gli altri.
    """
    try:
        return _esamina(percorso)[1]
    except OSError as e:
        return [f"{PREFISSO}: {percorso}: {_motivo(e)}"]


def argomenti_configurazione(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="PERCORSO",
        help=f"il file da controllare (predefinito: {PERCORSO_PREDEFINITO})",
    )


def comando_configurazione(args: argparse.Namespace) -> int:
    """Controlla la configurazione: esce 1 con gli errori, 0 con il conteggio, 2 se il file non si legge.

    Gli errori vanno tutti su stdout; un file che non si legge dà il suo errore su stderr.
    Se c'è .github/workflows/ controlla i rischi della CI sui rami bottega/* e se ce ne sono esce 1.
    """
    percorso = Path(args.file)
    try:
        configurazione, errori = _esamina(percorso)
    except OSError as e:
        print(f"errore: {percorso}: {_motivo(e)}", file=sys.stderr)
        return 2
    if configurazione is None:
        print("\n".join(errori))
        return 1

    cartella_wf: Path | None = None
    if percorso == Path(PERCORSO_PREDEFINITO):
        possibile = Path(".github/workflows")
        if possibile.is_dir():
            cartella_wf = possibile
    elif (percorso.parent / ".github" / "workflows").is_dir():
        cartella_wf = percorso.parent / ".github" / "workflows"
    elif (
        percorso.parent.name == "bottega"
        and percorso.parent.parent.name == ".github"
        and (percorso.parent.parent / "workflows").is_dir()
    ):
        cartella_wf = percorso.parent.parent / "workflows"

    if cartella_wf is not None:
        testi: dict[str, str] = {}
        for p in sorted(cartella_wf.iterdir()):
            if p.is_file() and p.suffix in (".yml", ".yaml"):
                try:
                    nome = str(p.relative_to(Path.cwd()))
                except ValueError:
                    nome = str(p)
                try:
                    testi[nome] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
        avvisi = rischi(testi)
        if avvisi:
            for r in avvisi:
                print(f"avviso: {r.file}: {r.motivo}")
            return 1

    print(
        f"{PREFISSO}: botteghe {len(configurazione.botteghe)}, "
        f"candidati {len(configurazione.candidati)}, nessun errore"
    )
    return 0


def _esamina(percorso: Path) -> tuple[Configurazione | None, list[str]]:
    """La configurazione e i suoi errori: senza errori c'è la configurazione, con errori è None.

    Un file illeggibile solleva OSError; un file che non è TOML valido (o non è UTF-8) dà un errore solo.
    """
    try:
        with percorso.open("rb") as file:
            dati = tomllib.load(file)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, [f"{PREFISSO}: TOML non valido: {e}"]
    return _valida(dati)


def _motivo(e: OSError) -> str:
    return "file non trovato" if isinstance(e, FileNotFoundError) else (e.strerror or str(e))


def _valida(dati: dict) -> tuple[Configurazione | None, list[str]]:
    errori: list[str] = []
    _sconosciute(dati, _CHIAVI_TOP, "", errori)
    versione = _versione(dati, errori)
    progetto = _progetto(dati, errori, ha_runner=_ha_runner(dati))
    botteghe = _botteghe(dati, errori)
    grezze = dati.get("botteghe", {})
    ids = set(grezze) if isinstance(grezze, dict) else None  # senza tabella valida, niente controllo dei riferimenti
    candidati = _candidati(dati, ids, botteghe, errori)
    if errori or versione is None or progetto is None:
        return None, errori
    return Configurazione(versione, progetto, botteghe, candidati), []


def _ha_runner(dati: dict) -> bool:
    """Vero se almeno un candidato dichiara un runner non vuoto."""
    grezze = dati.get("candidati")
    if not isinstance(grezze, dict):
        return False
    return any(
        isinstance(voce, dict) and isinstance(voce.get("runner"), str) and bool(voce["runner"].strip())
        for voce in grezze.values()
    )


def _versione(dati: dict, errori: list[str]) -> int | None:
    if "versione" not in dati:
        _errore(errori, "versione", "chiave obbligatoria mancante")
        return None
    valore = dati["versione"]
    if type(valore) is not int:  # bool è un int per Python: qui no
        _errore(errori, "versione", "tipo sbagliato: serve un numero intero")
        return None
    if valore != VERSIONE_FORMATO:
        _errore(errori, "versione", f"{valore} non supportata (serve {VERSIONE_FORMATO})")
        return None
    return valore


def _progetto(dati: dict, errori: list[str], ha_runner: bool = False) -> Progetto | None:
    if "progetto" not in dati:
        _errore(errori, "progetto", "chiave obbligatoria mancante")
        return None
    tabella = _tabella(dati["progetto"], "progetto", errori)
    if tabella is None:
        return None
    _sconosciute(tabella, _CHIAVI_PROGETTO, "progetto", errori)
    fuso = _testo(tabella, "fuso", "progetto", errori, obbligatoria=True)
    if fuso is not None and not _fuso_noto(fuso):
        _errore(errori, "progetto.fuso", f"«{fuso}» non è un fuso orario noto (per esempio Europe/Rome)")
        fuso = None
    notte = _ora(tabella, "notte", "progetto", errori)
    adattatore = _testo(tabella, "adattatore", "progetto", errori, obbligatoria=False)
    comandanti = _comandanti(tabella, "progetto", errori)
    manutenzione = _manutenzione(tabella, "progetto", errori)
    project = _project(tabella, "progetto", errori, obbligatorio=ha_runner)
    liberi = _liberi(tabella, "progetto", errori)
    if fuso is None:
        return None
    return Progetto(
        comandanti=comandanti,
        adattatore=adattatore,
        fuso=fuso,
        notte=notte,
        manutenzione=manutenzione,
        project=project,
        liberi=liberi,
    )


def _botteghe(dati: dict, errori: list[str]) -> dict[str, Bottega]:
    valide: dict[str, Bottega] = {}
    tabella = _tabella(dati.get("botteghe", {}), "botteghe", errori)
    for id_, voce in (tabella or {}).items():
        percorso = f"botteghe.{id_}"
        n = len(errori)
        _id(id_, percorso, errori)
        corpo = _tabella(voce, percorso, errori)
        if corpo is None:
            continue
        _sconosciute(corpo, _CHIAVI_BOTTEGA, percorso, errori)
        quota = _scelta(corpo, "quota", percorso, QUOTE, "quota", errori)
        porte = _scelte(corpo, "porte", percorso, PORTE, "porta", errori)
        if len(errori) == n and quota is not None and porte is not None:
            valide[id_] = Bottega(id_, quota, porte)
    return valide


def _candidati(
    dati: dict,
    ids: set[str] | None,
    botteghe: dict[str, Bottega],
    errori: list[str],
) -> dict[str, Candidato]:
    valide: dict[str, Candidato] = {}
    grezze = _tabella(dati.get("candidati", {}), "candidati", errori)
    if grezze is None:
        return valide
    nomi: dict[str, str] = {}  # nome -> id del candidato che lo ha
    for id_, voce in grezze.items():
        percorso = f"candidati.{id_}"
        n = len(errori)
        _id(id_, percorso, errori)
        tabella = _tabella(voce, percorso, errori)
        if tabella is None:
            continue
        _sconosciute(tabella, _CHIAVI_CANDIDATO, percorso, errori)
        nome = _testo(tabella, "nome", percorso, errori, obbligatoria=True)
        if nome is not None:
            chiave = nome.casefold()
            if chiave in nomi:
                _errore(errori, f"{percorso}.nome", f"nome ripetuto: «{nome}» (già in candidati.{nomi[chiave]})")
            else:
                nomi[chiave] = id_
        bottega = _testo(tabella, "bottega", percorso, errori, obbligatoria=True)
        if bottega is not None and ids is not None and bottega not in ids:
            _errore(errori, f"{percorso}.bottega", f"bottega inesistente: «{bottega}»")
        porta = _scelta(tabella, "porta", percorso, PORTE, "porta", errori)
        if porta is not None and bottega in botteghe and porta not in botteghe[bottega].porte:
            _errore(errori, f"{percorso}.porta", f"«{porta}» non è una porta della bottega «{bottega}»")
        modello = _testo(tabella, "modello", percorso, errori, obbligatoria=True)
        funzioni = _scelte(tabella, "funzioni", percorso, FUNZIONI, "funzione", errori)
        runner = _testo(tabella, "runner", percorso, errori, obbligatoria=False)
        if len(errori) == n and None not in (nome, bottega, porta, modello, funzioni):
            valide[id_] = Candidato(id_, nome, bottega, porta, modello, funzioni, runner)
    if not any(_decide(voce) for voce in grezze.values()):
        _errore(errori, "candidati", "nessun candidato con la funzione «decidere»")
    return valide


def _decide(voce: object) -> bool:
    """Vero se una voce di candidato, anche malformata, dichiara la funzione `decidere`."""
    return isinstance(voce, dict) and isinstance(voce.get("funzioni"), list) and "decidere" in voce["funzioni"]


def _comandanti(tabella: dict, percorso: str, errori: list[str]) -> tuple[str, ...]:
    completa = _completa(percorso, "comandanti")
    if "comandanti" not in tabella:
        return ()
    lista = _come_lista(tabella["comandanti"], completa, errori)
    if lista is None:
        return ()
    voci = [_come_testo(voce, f"{completa}[{i}]", errori) for i, voce in enumerate(lista)]
    return tuple(voce for voce in voci if voce is not None)


def _manutenzione(tabella: dict, percorso: str, errori: list[str]) -> tuple[str, ...]:
    completa = _completa(percorso, "manutenzione")
    if "manutenzione" not in tabella:
        return ()
    lista = _come_lista(tabella["manutenzione"], completa, errori)
    if lista is None:
        return ()
    finestre: list[str] = []
    for i, voce in enumerate(lista):
        voce_completa = f"{completa}[{i}]"
        finestra = _come_testo(voce, voce_completa, errori)
        if finestra is None:
            continue
        trovata = _FINESTRA.fullmatch(finestra)
        if trovata is None:
            _errore(errori, voce_completa, f"«{finestra}» non è una finestra HH:MM-HH:MM")
        elif trovata.group(1) == trovata.group(2):
            _errore(errori, voce_completa, f"inizio uguale alla fine: «{finestra}»")
        else:
            finestre.append(finestra)
    return tuple(finestre)


def _ora(tabella: dict, chiave: str, percorso: str, errori: list[str]) -> str | None:
    valore = _testo(tabella, chiave, percorso, errori, obbligatoria=False)
    if valore is not None and not _ORA.fullmatch(valore):
        _errore(errori, _completa(percorso, chiave), f"«{valore}» non è un'ora HH:MM")
        return None
    return valore


def _project(tabella: dict, percorso: str, errori: list[str], obbligatorio: bool) -> int | None:
    completa = _completa(percorso, "project")
    if "project" not in tabella:
        if obbligatorio:
            _errore(errori, completa, "chiave obbligatoria se almeno un candidato ha «runner»")
        return None
    valore = tabella["project"]
    if type(valore) is not int:  # bool è un int per Python: qui no
        _errore(errori, completa, "tipo sbagliato: serve un numero intero")
        return None
    if valore <= 0:
        _errore(errori, completa, "serve un intero positivo")
        return None
    return valore


def _liberi(tabella: dict, percorso: str, errori: list[str]) -> tuple[str, ...]:
    completa = _completa(percorso, "liberi")
    if "liberi" not in tabella:
        return ()
    lista = _come_lista(tabella["liberi"], completa, errori)
    if lista is None:
        return ()
    valori: list[str] = []
    viste: set[str] = set()
    for i, voce in enumerate(lista):
        voce_completa = f"{completa}[{i}]"
        valore = _come_testo(voce, voce_completa, errori)
        if valore is None:
            continue
        chiave = valore.casefold()
        if chiave in viste:
            _errore(errori, voce_completa, f"«{valore}» ripetuta")
        else:
            viste.add(chiave)
            valori.append(valore)
    return tuple(valori)


def _scelta(
    tabella: dict,
    chiave: str,
    percorso: str,
    elenco: tuple[str, ...],
    nome: str,
    errori: list[str],
) -> str | None:
    """Un valore di `elenco`, obbligatorio: con l'errore se manca, è di tipo sbagliato o non c'è nell'elenco."""
    valore = _testo(tabella, chiave, percorso, errori, obbligatoria=True)
    if valore is not None and valore not in elenco:
        _errore(errori, _completa(percorso, chiave), _fuori_elenco(valore, nome, elenco))
        return None
    return valore


def _scelte(
    tabella: dict,
    chiave: str,
    percorso: str,
    elenco: tuple[str, ...],
    nome: str,
    errori: list[str],
) -> tuple[str, ...] | None:
    """Una lista di valori di `elenco`, obbligatoria, non vuota e senza ripetizioni."""
    completa = _completa(percorso, chiave)
    if chiave not in tabella:
        _errore(errori, completa, "chiave obbligatoria mancante")
        return None
    lista = _come_lista(tabella[chiave], completa, errori)
    if lista is None:
        return None
    if not lista:
        _errore(errori, completa, f"lista vuota: serve almeno una {nome}")
        return None
    valori: list[str] = []
    for i, voce in enumerate(lista):
        voce_completa = f"{completa}[{i}]"
        valore = _come_testo(voce, voce_completa, errori)
        if valore is None:
            continue
        if valore not in elenco:
            _errore(errori, voce_completa, _fuori_elenco(valore, nome, elenco))
        elif valore in valori:
            _errore(errori, voce_completa, f"«{valore}» ripetuta")
        else:
            valori.append(valore)
    return tuple(valori)


def _testo(tabella: dict, chiave: str, percorso: str, errori: list[str], obbligatoria: bool) -> str | None:
    """Il testo non vuoto di una chiave. None se manca (con l'errore, se è obbligatoria) o se è sbagliato."""
    if chiave not in tabella:
        if obbligatoria:
            _errore(errori, _completa(percorso, chiave), "chiave obbligatoria mancante")
        return None
    return _come_testo(tabella[chiave], _completa(percorso, chiave), errori)


def _come_testo(valore: object, percorso: str, errori: list[str]) -> str | None:
    if not isinstance(valore, str):
        _errore(errori, percorso, "tipo sbagliato: serve una stringa")
        return None
    if not valore.strip():
        _errore(errori, percorso, "valore vuoto")
        return None
    return valore


def _come_lista(valore: object, percorso: str, errori: list[str]) -> list | None:
    if isinstance(valore, list):
        return valore
    _errore(errori, percorso, "tipo sbagliato: serve una lista")
    return None


def _tabella(valore: object, percorso: str, errori: list[str]) -> dict | None:
    if isinstance(valore, dict):
        return valore
    _errore(errori, percorso, "tipo sbagliato: serve una tabella")
    return None


def _id(id_: str, percorso: str, errori: list[str]) -> None:
    if not _ID.fullmatch(id_):
        _errore(errori, percorso, f"id non valido: «{id_}» (si usano a-z, 0-9 e -)")


def _sconosciute(tabella: dict, ammesse: tuple[str, ...], percorso: str, errori: list[str]) -> None:
    for chiave in tabella:
        if chiave not in ammesse:
            _errore(errori, _completa(percorso, chiave), "chiave sconosciuta")


def _fuso_noto(fuso: str) -> bool:
    try:
        ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _fuori_elenco(valore: str, nome: str, elenco: tuple[str, ...]) -> str:
    return f"«{valore}» non è una {nome} ({', '.join(elenco)})"


def _completa(percorso: str, chiave: str) -> str:
    return f"{percorso}.{chiave}" if percorso else chiave


def _errore(errori: list[str], percorso: str, motivo: str) -> None:
    errori.append(f"{PREFISSO}: {percorso}: {motivo}")
