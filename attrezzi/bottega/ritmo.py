"""Ritmo della quota e scelta dei riempitivi sulla quota residua."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shlex
import sys

from bottega.board import Board, BoardComando, BoardProject, ErroreBoard, Lavoro
from bottega.brief import fatto_quando
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import ErroreForgia, ForgiaGh
from bottega.porte.antigravity import Antigravity
from bottega.quota import PuntoQuota, analizza_uscita_quota

SOGLIA_RITARDO = 15
RISERVA_CINQUE_ORE = 30
RISERVA_SETTIMANA = 15
DURATA_SETTIMANA_S = 7 * 24 * 3600
EPOCH_SOGLIA = datetime(1970, 1, 2, tzinfo=timezone.utc)

ETICHETTE_ESCLUSE_RIEMPITIVI: frozenset[str] = frozenset({
    "attesa utente",
    "design",
    "delicato",
    "bottega: sospeso",
    "bottega: bozza di piano",
})

_FASCIA_DEBITO = frozenset({"debito", "bug", "debt"})
_FASCIA_PROVE = frozenset({"prove", "test", "tests", "copertura"})
_FASCIA_DOCS = frozenset({"docs", "documenti", "documentazione", "guida"})


@dataclass(frozen=True)
class EsitoRitmo:
    """Risultato della valutazione del ritmo rispetto al tempo trascorso e alle riserve."""

    lancia: bool
    gruppo: str
    settimana_residua: int
    cinque_ore_effettiva: int
    atteso_speso: float
    speso: int
    ritardo: float
    motivo: str


def _adesso_utc() -> datetime:
    """Istante corrente in UTC (isolato per le prove)."""
    return datetime.now(timezone.utc)


def _in_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def valuta_ritmo(
    punto: PuntoQuota,
    adesso: datetime,
    *,
    soglia_ritardo: int = SOGLIA_RITARDO,
    riserva_5h: int = RISERVA_CINQUE_ORE,
    riserva_settimana: int = RISERVA_SETTIMANA,
) -> EsitoRitmo:
    """Valuta se la quota è abbastanza indietro rispetto al tempo trascorso da lanciare un riempitivo."""
    adesso_utc = _in_utc(adesso)
    rin_sett = _in_utc(punto.rinnovo_settimana)
    rin_5h = _in_utc(punto.rinnovo_cinque_ore)
    speso = 100 - punto.settimana

    if rin_5h > EPOCH_SOGLIA and adesso_utc >= rin_5h:
        cinque_ore_eff = 100
    else:
        cinque_ore_eff = punto.cinque_ore

    if rin_sett <= EPOCH_SOGLIA:
        return EsitoRitmo(
            lancia=False,
            gruppo=punto.gruppo,
            settimana_residua=punto.settimana,
            cinque_ore_effettiva=cinque_ore_eff,
            atteso_speso=0.0,
            speso=speso,
            ritardo=0.0,
            motivo="finestra settimanale non ancora avviata",
        )

    if adesso_utc >= rin_sett:
        return EsitoRitmo(
            lancia=False,
            gruppo=punto.gruppo,
            settimana_residua=punto.settimana,
            cinque_ore_effettiva=cinque_ore_eff,
            atteso_speso=100.0,
            speso=speso,
            ritardo=100.0 - speso,
            motivo="rilevazione scaduta (rinnovo settimanale superato)",
        )

    inizio_settimana = rin_sett - timedelta(days=7)
    frazione_passata = max(0.0, min(1.0, (adesso_utc - inizio_settimana).total_seconds() / float(DURATA_SETTIMANA_S)))
    atteso_speso = frazione_passata * 100.0
    ritardo = atteso_speso - speso

    if cinque_ore_eff < riserva_5h:
        lancia = False
        motivo = f"riserva cinque ore ({cinque_ore_eff}% < {riserva_5h}%)"
    elif punto.settimana < riserva_settimana:
        lancia = False
        motivo = f"riserva settimanale ({punto.settimana}% < {riserva_settimana}%)"
    elif ritardo < soglia_ritardo:
        lancia = False
        motivo = f"quota in passo (ritardo {ritardo:.1f} < {soglia_ritardo})"
    else:
        lancia = True
        motivo = f"quota indietro (ritardo {ritardo:.1f} >= {soglia_ritardo})"

    return EsitoRitmo(
        lancia=lancia,
        gruppo=punto.gruppo,
        settimana_residua=punto.settimana,
        cinque_ore_effettiva=cinque_ore_eff,
        atteso_speso=atteso_speso,
        speso=speso,
        ritardo=ritardo,
        motivo=motivo,
    )


def seleziona_gruppo_punti(
    punti: Mapping[str, PuntoQuota],
    cfg: Configurazione,
    id_bottega: str,
) -> PuntoQuota | None:
    """Sceglie il gruppo di punti da valutare: quello configurato in `[ritmo]` o il primo attivo."""
    if not punti:
        return None
    if cfg.ritmo.gruppo:
        if cfg.ritmo.gruppo in punti:
            return punti[cfg.ritmo.gruppo]
        gruppo_cf = cfg.ritmo.gruppo.strip().casefold()
        for nome, p in punti.items():
            if nome.strip().casefold() == gruppo_cf:
                return p
        return None
    if id_bottega == "google" and "Gemini Models" in punti:
        return punti["Gemini Models"]
    for p in punti.values():
        if _in_utc(p.rinnovo_settimana) > EPOCH_SOGLIA:
            return p
    return next(iter(punti.values()))


def fascia_riempitivo(etichette: Sequence[str]) -> int:
    """Restituisce la fascia di priorità (0 più alta) in base alle etichette del lavoro."""
    et_cf = {e.strip().casefold() for e in etichette if e.strip()}
    if et_cf & _FASCIA_DEBITO:
        return 0
    if et_cf & _FASCIA_PROVE:
        return 1
    if et_cf & _FASCIA_DOCS:
        return 2
    return 3


def scegli_riempitivo(
    lavori: Sequence[Lavoro],
    *,
    aree_non_delicate: Sequence[str],
    ha_fatto_quando: Callable[[int], bool],
    autore_valido: Callable[[int], bool],
) -> tuple[Lavoro, int] | None:
    """Sceglie il primo riempitivo ammissibile ordinato per fascia di priorità e numero crescente."""
    aree_cf = {a.strip().casefold() for a in aree_non_delicate if a.strip()}
    if not aree_cf:
        return None

    candidati: list[tuple[int, int, Lavoro]] = []
    for lav in lavori:
        if not lav.aperta:
            continue
        eleggibile_stato = lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso")
        if not eleggibile_stato:
            continue
        et_cf = {e.strip().casefold() for e in lav.etichette if e.strip()}
        if et_cf & ETICHETTE_ESCLUSE_RIEMPITIVI:
            continue
        if "bottega: fuori" in et_cf or any(e.startswith("esegue:") for e in et_cf):
            continue
        if not (et_cf & aree_cf):
            continue
        if not autore_valido(lav.numero) or not ha_fatto_quando(lav.numero):
            continue
        candidati.append((fascia_riempitivo(lav.etichette), lav.numero, lav))

    if not candidati:
        return None
    candidati.sort(key=lambda t: (t[0], t[1]))
    fascia, _num, scelto = candidati[0]
    return scelto, fascia


def _primo_riempitivo_da_forgia(cfg: Configurazione, repo: str) -> tuple[Lavoro, int] | None:
    """Interroga forgia e board reali per proporre il primo riempitivo ammissibile."""
    forgia = ForgiaGh(repo)
    board: Board
    if cfg.progetto.adattatore:
        board = BoardComando(shlex.split(cfg.progetto.adattatore))
    else:
        if cfg.progetto.project is None:
            raise ErroreBoard("configurazione priva di progetto.project e senza adattatore")
        board = BoardProject(proprietario=forgia.proprietario(), numero=cfg.progetto.project, repo=repo)

    comandanti_cf = {c.strip().casefold() for c in cfg.progetto.comandanti} | {
        forgia.proprietario().strip().casefold()
    }
    cache_issue: dict[int, object] = {}

    def _issue(num: int):
        if num not in cache_issue:
            cache_issue[num] = forgia.issue(num)
        return cache_issue[num]

    def _autore_valido(num: int) -> bool:
        iss = _issue(num)
        autore = iss.autore.strip().casefold() if iss.autore else ""
        return autore in comandanti_cf

    def _ha_fq(num: int) -> bool:
        iss = _issue(num)
        return fatto_quando(iss.corpo) is not None

    return scegli_riempitivo(
        board.elenco(),
        aree_non_delicate=cfg.progetto.aree_non_delicate,
        ha_fatto_quando=_ha_fq,
        autore_valido=_autore_valido,
    )


def argomenti_ritmo(parser: argparse.ArgumentParser) -> None:
    """Registra gli argomenti CLI del sottocomando `bottega ritmo`."""
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="TOML",
        help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
    )
    parser.add_argument("--gruppo", default=None, metavar="NOME", help="gruppo di quota da valutare")
    parser.add_argument("--soglia-ritardo", type=int, default=None, metavar="N", help="soglia minima di ritardo (%%)")
    parser.add_argument("--riserva-5h", type=int, default=None, metavar="N", help="riserva minima finestra 5 ore (%%)")
    parser.add_argument(
        "--riserva-settimana",
        type=int,
        default=None,
        metavar="N",
        help="riserva minima finestra settimanale (%%)",
    )
    parser.add_argument("--da-quota", default=None, metavar="FILE", help="legge l'uscita di /quota da file o '-'")
    parser.add_argument("--proponi", action="store_true", help="propone il primo riempitivo pronto")
    parser.add_argument("--repo", default=None, metavar="REPO", help="repository owner/name per --proponi")
    parser.add_argument("--json", action="store_true", help="stampa l'esito in formato JSON")


def comando_ritmo(args: argparse.Namespace) -> int:
    """Esegue `bottega ritmo`: valuta la quota e, se richiesto, propone il primo riempitivo."""
    try:
        cfg = leggi_configurazione(Path(args.file))
    except (ErroreConfigurazione, FileNotFoundError) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2

    if args.da_quota is not None:
        try:
            testo = sys.stdin.read() if args.da_quota == "-" else Path(args.da_quota).read_text(encoding="utf-8")
        except OSError as e:
            motivo = e.strerror or str(e)
            print(f"errore: impossibile leggere «{args.da_quota}»: {motivo}", file=sys.stderr)
            return 2
        punti = analizza_uscita_quota(testo)
        if not punti:
            print("errore: uscita /quota illeggibile o vuota", file=sys.stderr)
            return 2
    else:
        punti_letti = Antigravity().leggi_quota()
        if not punti_letti:
            print("errore: impossibile leggere la quota da Antigravity", file=sys.stderr)
            return 2
        punti = punti_letti

    if args.gruppo:
        punto = punti.get(args.gruppo)
    else:
        id_bottega = next(iter(cfg.botteghe), "google")
        punto = seleziona_gruppo_punti(punti, cfg, id_bottega)

    if punto is None:
        print("errore: gruppo di quota non trovato", file=sys.stderr)
        return 2

    soglia_ritardo = cfg.ritmo.ritardo if args.soglia_ritardo is None else args.soglia_ritardo
    riserva_5h = cfg.ritmo.riserva_5h if args.riserva_5h is None else args.riserva_5h
    riserva_settimana = cfg.ritmo.riserva_settimana if args.riserva_settimana is None else args.riserva_settimana

    esito = valuta_ritmo(
        punto,
        _adesso_utc(),
        soglia_ritardo=soglia_ritardo,
        riserva_5h=riserva_5h,
        riserva_settimana=riserva_settimana,
    )

    proposto: tuple[Lavoro, int] | None = None
    if args.proponi and esito.lancia:
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")
        if not repo:
            print("errore: specifica --repo o GITHUB_REPOSITORY per --proponi", file=sys.stderr)
            return 2
        try:
            proposto = _primo_riempitivo_da_forgia(cfg, repo)
        except (ErroreBoard, ErroreForgia, FileNotFoundError) as e:
            print(f"errore: {e}", file=sys.stderr)
            return 2

    if args.json:
        dati = asdict(esito)
        if args.proponi and esito.lancia:
            dati["riempitivo"] = (
                {"numero": proposto[0].numero, "titolo": proposto[0].titolo, "fascia": proposto[1]}
                if proposto is not None
                else None
            )
        print(json.dumps(dati, ensure_ascii=False))
    else:
        stato_txt = "lancia" if esito.lancia else "fermo"
        print(f"{stato_txt}: {esito.motivo}")
        if args.proponi and esito.lancia:
            if proposto is not None:
                lav, fascia = proposto
                print(f"#{lav.numero} {lav.titolo} [fascia {fascia}]")
            else:
                print("nessun riempitivo pronto")

    return 0 if esito.lancia else 1
