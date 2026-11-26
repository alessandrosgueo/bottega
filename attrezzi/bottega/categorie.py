"""Categorie del diff, formato del verdetto del revisore e comando `bottega categoria` (B15-R2, R5, R7)."""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from bottega.configurazione import PERCORSO_PREDEFINITO, ErroreConfigurazione, leggi_configurazione
from bottega.giro import analizza_diff_raw

ETICHETTE_DELICATE: frozenset[str] = frozenset({"bottega: prove cambiate", "bottega: segreti"})
_SEGMENTI_PROTETTI: frozenset[str] = frozenset({".github", ".bottega", ".gitleaksignore", ".gitleaks.toml"})


@dataclass(frozen=True)
class Verdetto:
    """Esito strutturato estratto dall'intestazione della risposta del revisore."""

    stato: str  # "APPROVATO", "RILIEVI_GRAVI", "SICUREZZA", "non_valido"
    gravi: int
    minori: int
    sicurezza: bool
    valido: bool

    @property
    def approvato(self) -> bool:
        """Vero solo se il verdetto è valido, APPROVATO, senza rilievi gravi né sicurezza."""
        return self.valido and self.stato == "APPROVATO" and self.gravi == 0 and not self.sicurezza

    @property
    def bloccante(self) -> bool:
        """Vero se il verdetto valido segnala rilievi gravi o problemi di sicurezza."""
        return self.valido and (self.stato in ("RILIEVI_GRAVI", "SICUREZZA") or self.gravi > 0)


@dataclass(frozen=True)
class EsitoCategoria:
    """Risultato della classificazione di un diff rispetto a `[categorie]` e ai vincoli di sicurezza."""

    delicata: bool
    categorie_toccate: tuple[str, ...]
    fuori_elenco: tuple[str, ...]
    motivi: tuple[str, ...]


def _normalizza_percorso(percorso: str) -> str:
    """Normalizza separatori e prefissi `./` o `/` iniziali."""
    p = percorso.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


@lru_cache(maxsize=512)
def _compila_glob(modello: str) -> re.Pattern[str]:
    """Converte un modello glob POSIX in espressione regolare ancorata."""
    parti: list[str] = ["^"]
    i = 0
    n = len(modello)
    while i < n:
        if modello.startswith("/**/", i):
            parti.append(r"(?:/.*)?/")
            i += 4
        elif i == 0 and modello.startswith("**/"):
            parti.append(r"(?:[^/]+/)*")
            i += 3
        elif modello[i:] == "/**":
            parti.append(r"/.*")
            i += 3
        elif modello.startswith("**", i):
            parti.append(r".*")
            i += 2
        elif modello[i] == "*":
            parti.append(r"[^/]*")
            i += 1
        elif modello[i] == "?":
            parti.append(r"[^/]")
            i += 1
        else:
            parti.append(re.escape(modello[i]))
            i += 1
    parti.append("$")
    return re.compile("".join(parti))


def corrisponde_glob(percorso: str, modello: str) -> bool:
    """Verifica se `percorso` corrisponde al `modello` glob POSIX."""
    p = _normalizza_percorso(percorso)
    m = _normalizza_percorso(modello)
    if not p or not m:
        return False
    return _compila_glob(m).match(p) is not None


def percorso_protetto(percorso: str) -> bool:
    """Vero se il percorso tocca il pavimento protetto (.github, .bottega, .gitleaksignore, .gitleaks.toml)."""
    p = _normalizza_percorso(percorso).lower()
    if not p:
        return False
    return any(seg in _SEGMENTI_PROTETTI for seg in p.split("/") if seg)


def analizza_verdetto(testo: str) -> Verdetto:
    """Estrae `VERDETTO`, `GRAVI` e `MINORI` ignorando blocchi recintati; fail-closed su anomalie."""
    stato_letto: str | None = None
    gravi_letto: int | None = None
    minori_letto: int | None = None

    recinto_car: str | None = None
    recinto_len = 0

    for riga in (testo or "").splitlines():
        s = riga.strip()
        if recinto_car is None:
            if s.startswith("```") or s.startswith("~~~"):
                car = s[0]
                recinto_car = car
                recinto_len = len(s) - len(s.lstrip(car))
                continue
        else:
            if s.startswith(recinto_car * recinto_len) and s.strip(recinto_car) == "":
                recinto_car = None
                recinto_len = 0
            continue

        pulita = s.lstrip("-*#>_ \t")
        if ":" not in pulita:
            continue
        chiave_grezza, valore_grezzo = pulita.split(":", 1)
        chiave = chiave_grezza.strip("*_` \t").upper()
        valore = valore_grezzo.strip("*_` \t")

        if chiave == "VERDETTO" and stato_letto is None:
            norm = " ".join(valore.upper().split()).replace(" ", "_")
            stato_letto = norm if norm in ("APPROVATO", "RILIEVI_GRAVI", "SICUREZZA") else "non_valido"
        elif chiave == "GRAVI" and gravi_letto is None and valore:
            try:
                val = int(valore.split()[0])
                if val >= 0:
                    gravi_letto = val
            except ValueError:
                pass
        elif chiave == "MINORI" and minori_letto is None and valore:
            try:
                val = int(valore.split()[0])
                if val >= 0:
                    minori_letto = val
            except ValueError:
                pass

    if stato_letto is None or stato_letto == "non_valido":
        return Verdetto(stato="non_valido", gravi=0, minori=0, sicurezza=False, valido=False)

    gravi = gravi_letto if gravi_letto is not None else 0
    minori = minori_letto if minori_letto is not None else 0

    if stato_letto == "APPROVATO":
        if gravi > 0:
            return Verdetto(stato="RILIEVI_GRAVI", gravi=gravi, minori=minori, sicurezza=False, valido=True)
        return Verdetto(stato="APPROVATO", gravi=0, minori=minori, sicurezza=False, valido=True)

    if stato_letto == "RILIEVI_GRAVI":
        return Verdetto(stato="RILIEVI_GRAVI", gravi=max(gravi, 1), minori=minori, sicurezza=False, valido=True)

    return Verdetto(stato="SICUREZZA", gravi=max(gravi, 1), minori=minori, sicurezza=True, valido=True)


def classifica_diff(
    percorsi: Sequence[str],
    categorie: Mapping[str, Sequence[str]],
    *,
    etichette_pr: Sequence[str] = (),
    sicurezza: bool = False,
) -> EsitoCategoria:
    """Classifica i percorsi del diff rispetto a `[categorie]`, pavimento protetto, etichette e sicurezza."""
    motivi: list[str] = []
    delicata = False

    if not percorsi:
        delicata = True
        motivi.append("nessun file nel diff")

    etichette_trovate = sorted({e.strip().lower() for e in etichette_pr if e.strip().lower() in ETICHETTE_DELICATE})
    if etichette_trovate:
        delicata = True
        motivi.append(f"etichette delicate: {', '.join(etichette_trovate)}")

    if sicurezza:
        delicata = True
        motivi.append("segnalazione di sicurezza nella revisione")

    toccate: set[str] = set()
    fuori: list[str] = []
    for p in percorsi:
        if percorso_protetto(p):
            fuori.append(p)
            continue
        trovata = False
        for cat, modelli in categorie.items():
            if any(corrisponde_glob(p, m) for m in modelli):
                toccate.add(cat)
                trovata = True
        if not trovata:
            fuori.append(p)

    fuori_ordinate = tuple(sorted(set(fuori)))
    if fuori_ordinate:
        delicata = True
        motivi.append(f"file fuori elenco o protetti: {', '.join(fuori_ordinate)}")

    return EsitoCategoria(
        delicata=delicata,
        categorie_toccate=tuple(sorted(toccate)),
        fuori_elenco=fuori_ordinate,
        motivi=tuple(motivi),
    )


def file_del_diff(base: str, ramo: str, cartella: Path | None = None) -> list[str]:
    """Restituisce i percorsi toccati tra `base` e `ramo` (inclusi entrambi i lati delle rinominazioni)."""
    res = subprocess.run(
        ["git", "diff", "--raw", "-z", "-M", "--no-ext-diff", f"{base}...{ramo}"],
        cwd=cartella,
        check=True,
        capture_output=True,
    )
    percorsi: dict[str, None] = {}
    for _status, _src_mode, _dst_mode, old_path, new_path in analizza_diff_raw(res.stdout):
        if old_path:
            percorsi.setdefault(old_path, None)
        if new_path:
            percorsi.setdefault(new_path, None)
    return list(percorsi)


def argomenti_categoria(parser: argparse.ArgumentParser) -> None:
    """Registra le opzioni di `bottega categoria`."""
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="TOML",
        help=f"percorso del bottega.toml (predefinito: {PERCORSO_PREDEFINITO})",
    )
    parser.add_argument("--base", default="origin/main", metavar="RIF", help="riferimento base per git diff")
    parser.add_argument("--ramo", default="HEAD", metavar="RIF", help="riferimento ramo per git diff")
    parser.add_argument(
        "--percorsi",
        default=None,
        metavar="FILE",
        help="file con un percorso per riga ('-' per stdin), alternativo a --base/--ramo",
    )
    parser.add_argument(
        "--etichetta",
        action="append",
        default=[],
        dest="etichette",
        metavar="E",
        help="etichetta della PR (ripetibile)",
    )
    parser.add_argument("--verdetto", default=None, metavar="FILE", help="file con l'esito del revisore")
    parser.add_argument("--json", action="store_true", help="stampa l'esito in formato JSON")


def comando_categoria(args: argparse.Namespace) -> int:
    """Classifica un diff per categorie di rischio e verifica il verdetto del revisore."""
    try:
        cfg = leggi_configurazione(Path(args.file))
    except (ErroreConfigurazione, OSError) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2

    try:
        if args.percorsi is not None:
            testo_percorsi = (
                sys.stdin.read() if args.percorsi == "-" else Path(args.percorsi).read_text(encoding="utf-8")
            )
            percorsi = [r.strip() for r in testo_percorsi.splitlines() if r.strip()]
        else:
            percorsi = file_del_diff(args.base, args.ramo)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2

    verdetto: Verdetto | None = None
    if args.verdetto is not None:
        try:
            testo_verdetto = Path(args.verdetto).read_text(encoding="utf-8")
        except OSError as e:
            print(f"errore: {e}", file=sys.stderr)
            return 2
        verdetto = analizza_verdetto(testo_verdetto)

    esito = classifica_diff(
        percorsi,
        cfg.categorie,
        etichette_pr=args.etichette,
        sicurezza=bool(verdetto and verdetto.sicurezza),
    )

    if esito.delicata:
        codice = 1
    elif verdetto is not None and not verdetto.approvato:
        codice = 3
    else:
        codice = 0

    if args.json:
        payload: dict[str, object] = {
            "delicata": esito.delicata,
            "categorie_toccate": list(esito.categorie_toccate),
            "fuori_elenco": list(esito.fuori_elenco),
            "motivi": list(esito.motivi),
            "codice": codice,
            "verdetto": (
                {**asdict(verdetto), "approvato": verdetto.approvato, "bloccante": verdetto.bloccante}
                if verdetto is not None
                else None
            ),
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        stato_cat = f"delicata ({'; '.join(esito.motivi)})" if esito.delicata else (
            f"non delicata ({', '.join(esito.categorie_toccate)})"
        )
        if verdetto is None:
            print(stato_cat)
        else:
            print(f"{stato_cat} — verdetto: {verdetto.stato} (gravi={verdetto.gravi}, minori={verdetto.minori})")

    return codice
