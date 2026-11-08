"""La scelta viva: decide chi esegue un compito come funzione pura.

Dati il compito, la configurazione, i risultati storici e le quote, sceglie il candidato migliore con il campionamento
di Thompson (Beta sui risultati) e il costo atteso pesato per la quota. L'etichetta `esegue` vince sempre; un candidato
senza quota non è mai scelto. Solo libreria standard.
"""

import argparse
import json
import random
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Candidato,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.quota import disponibile, nome_variabile

PESI_QUOTA = {
    "scarsa": 1.0,
    "normale": 0.25,
    "abbondante": 0.0,
}


@dataclass(frozen=True)
class Risultati:
    """I conteggi passati di un candidato su un'etichetta o sul totale (*)."""

    uniti: int = 0
    corretti: int = 0
    rifiutati: int = 0


@dataclass(frozen=True)
class Compito:
    """I dati del compito da assegnare."""

    funzione: str
    fuori: bool
    etichette: frozenset[str] = frozenset()
    esegue: str | None = None
    precedente: str | None = None
    giri_in_attesa: int = 0


@dataclass(frozen=True)
class Scelta:
    """L'esito della scelta: id del candidato scelto (o None), se aspettare, e il perché in una riga."""

    candidato: str | None
    aspetta: bool
    perche: str


def scegli(
    compito: Compito,
    configurazione: Configurazione,
    risultati: Mapping[tuple[str, str], Risultati],
    quote: Mapping[str, str | None],
    adesso: datetime,
    caso: random.Random,
    costo_decisore: float = 1.0,
    costi_propri: Mapping[str, float] | None = None,
) -> Scelta:
    """Sceglie il candidato per il compito secondo le regole B2-R3 e B2-R4."""
    tutti = list(configurazione.candidati.values())

    # 1. Etichetta esegue (B2-R3.2)
    nome_esegue = _ricava_esegue(compito)
    if nome_esegue is not None:
        return _scegli_per_etichetta_esegue(nome_esegue, compito, tutti, quote, adesso)

    # 2. Precedente della tappa (B2-R3.3)
    if compito.precedente is not None:
        esito_precedente = _scegli_per_precedente(compito, configurazione, quote, adesso)
        if esito_precedente is not None:
            return esito_precedente

    # 3. Candidati eleggibili per funzione e runner (B2-R3.1)
    elegibili = [c for c in tutti if _elegibile(c, compito)]
    if compito.precedente is not None and compito.giri_in_attesa >= 1:
        # Dopo un giro di attesa si sceglie fra gli altri
        elegibili = [c for c in elegibili if c.id != compito.precedente]

    # Candidati con quota disponibile
    con_quota = [c for c in elegibili if _ha_quota(c, quote, adesso)[0]]
    if not con_quota:
        return Scelta(
            candidato=None,
            aspetta=True,
            perche=f"aspetta: nessun candidato con quota disponibile per la funzione «{compito.funzione}»",
        )

    # 4. Costo atteso con campionamento di Thompson (B2-R3.4 e B2-R3.5)
    return _scegli_per_costo_atteso(
        con_quota=con_quota,
        compito=compito,
        configurazione=configurazione,
        risultati=risultati,
        caso=caso,
        costo_decisore=costo_decisore,
        costi_propri=costi_propri,
    )


def argomenti_scegli(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--funzione", required=True, metavar="F", help="funzione richiesta per il compito")
    parser.add_argument("--fuori", action="store_true", help="il compito gira su runner esterno")
    parser.add_argument(
        "--etichetta",
        action="append",
        default=[],
        dest="etichette",
        metavar="E",
        help="etichetta del compito (ripetibile)",
    )
    parser.add_argument("--esegue", default=None, metavar="NOME", help="candidato forzato dall'etichetta esegue")
    parser.add_argument("--precedente", default=None, metavar="ID", help="id del candidato precedente")
    parser.add_argument("--giri-in-attesa", type=int, default=0, metavar="N", help="giri di attesa già trascorsi")
    parser.add_argument("--risultati", default=None, metavar="FILE", help="file JSON coi risultati storici")
    parser.add_argument("--quote", default=None, metavar="FILE", help="file JSON con lo stato delle quote")
    parser.add_argument("--seme", type=int, default=None, metavar="N", help="seme per il generatore casuale")
    parser.add_argument(
        "--file",
        default=PERCORSO_PREDEFINITO,
        metavar="PERCORSO",
        help=f"il file di configurazione (predefinito: {PERCORSO_PREDEFINITO})",
    )


def comando_scegli(args: argparse.Namespace) -> int:
    """Sceglie il candidato per un compito: esce 0 (o aspetta), 1 se non esiste, 2 con errore."""
    percorso_cfg = Path(args.file)
    try:
        cfg = leggi_configurazione(percorso_cfg)
    except (ErroreConfigurazione, OSError) as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        print(f"errore: {percorso_cfg}: {motivo}", file=sys.stderr)
        return 2

    risultati_map: dict[tuple[str, str], Risultati] = {}
    if args.risultati:
        percorso_ris = Path(args.risultati)
        try:
            with percorso_ris.open("rb") as f:
                dati_ris = json.load(f)
            for c_id, per_etichetta in dati_ris.items():
                if isinstance(per_etichetta, dict):
                    for etichetta, conteggi in per_etichetta.items():
                        if isinstance(conteggi, dict):
                            risultati_map[(c_id, etichetta)] = Risultati(
                                uniti=int(conteggi.get("uniti", 0)),
                                corretti=int(conteggi.get("corretti", 0)),
                                rifiutati=int(conteggi.get("rifiutati", 0)),
                            )
        except (OSError, json.JSONDecodeError, ValueError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_ris}: {motivo}", file=sys.stderr)
            return 2

    quote_map: dict[str, str | None] = {}
    if args.quote:
        percorso_quote = Path(args.quote)
        try:
            with percorso_quote.open("rb") as f:
                quote_map = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
            print(f"errore: {percorso_quote}: {motivo}", file=sys.stderr)
            return 2

    try:
        fuso = ZoneInfo(cfg.progetto.fuso)
    except Exception:
        fuso = ZoneInfo("UTC")
    adesso = datetime.now(fuso)

    caso = random.Random(args.seme)
    compito = Compito(
        funzione=args.funzione,
        fuori=args.fuori,
        etichette=frozenset(args.etichette),
        esegue=args.esegue,
        precedente=args.precedente,
        giri_in_attesa=args.giri_in_attesa,
    )

    esito = scegli(compito, cfg, risultati_map, quote_map, adesso, caso)
    if esito.candidato is not None:
        print(f"{esito.candidato}\t{esito.perche}")
        return 0
    if esito.aspetta:
        print(f"aspetta\t{esito.perche}")
        return 0
    print(f"nessuno\t{esito.perche}")
    return 1


def _ricava_esegue(compito: Compito) -> str | None:
    if compito.esegue is not None and compito.esegue.strip():
        return compito.esegue.strip()
    for etichetta in compito.etichette:
        if etichetta.lower().startswith("esegue:"):
            return etichetta.split(":", 1)[1].strip()
    return None


def _scegli_per_etichetta_esegue(
    nome_esegue: str,
    compito: Compito,
    tutti: list[Candidato],
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> Scelta:
    trovato = next(
        (c for c in tutti if c.id.casefold() == nome_esegue.casefold() or c.nome.casefold() == nome_esegue.casefold()),
        None,
    )
    if trovato is None:
        return Scelta(
            candidato=None,
            aspetta=False,
            perche=f"nessun candidato corrisponde all'etichetta esegue «{nome_esegue}»",
        )
    if not _elegibile(trovato, compito):
        return Scelta(
            candidato=None,
            aspetta=False,
            perche=(
                f"il candidato «{trovato.id}» richiesto da «{nome_esegue}» "
                f"non può svolgere la funzione «{compito.funzione}»"
                + (" fuori" if compito.fuori else "")
            ),
        )
    ha_quota, _ = _ha_quota(trovato, quote, adesso)
    if ha_quota:
        return Scelta(
            candidato=trovato.id,
            aspetta=False,
            perche=f"scelto «{trovato.id}» per l'etichetta esegue «{nome_esegue}»",
        )
    return Scelta(
        candidato=None,
        aspetta=True,
        perche=f"aspetta: il candidato «{trovato.id}» richiesto dall'etichetta «{nome_esegue}» ha la quota esaurita",
    )


def _scegli_per_precedente(
    compito: Compito,
    configurazione: Configurazione,
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> Scelta | None:
    assert compito.precedente is not None
    cand_prec = configurazione.candidati.get(compito.precedente)
    if cand_prec is not None and _elegibile(cand_prec, compito):
        ha_quota, _ = _ha_quota(cand_prec, quote, adesso)
        if ha_quota:
            return Scelta(
                candidato=cand_prec.id,
                aspetta=False,
                perche=f"scelto «{cand_prec.id}» come precedente della tappa",
            )
        if compito.giri_in_attesa < 1:
            return Scelta(
                candidato=None,
                aspetta=True,
                perche=f"aspetta: il precedente «{cand_prec.id}» ha la quota esaurita e non ha ancora atteso un giro",
            )
    return None


def _scegli_per_costo_atteso(
    con_quota: list[Candidato],
    compito: Compito,
    configurazione: Configurazione,
    risultati: Mapping[tuple[str, str], Risultati],
    caso: random.Random,
    costo_decisore: float,
    costi_propri: Mapping[str, float] | None,
) -> Scelta:
    valutazioni = []
    for c in con_quota:
        u, cr, rf, tot = _conteggia_risultati(c.id, compito.etichette, risultati)
        a = 1.0 + u
        b = 1.0 + cr + rf
        p = max(caso.betavariate(a, b), 1e-9)
        bottega = configurazione.botteghe[c.bottega]
        peso_quota = PESI_QUOTA.get(bottega.quota, 1.0)
        c_proprio = costi_propri.get(c.id, 1.0) if costi_propri else 1.0
        numeratore = costo_decisore + peso_quota * c_proprio
        costo = numeratore / p
        valutazioni.append(
            {
                "candidato": c,
                "costo": costo,
                "numeratore": numeratore,
                "p": p,
                "totale": tot,
            }
        )

    migliore = valutazioni[0]
    for v in valutazioni[1:]:
        if v["costo"] < migliore["costo"]:
            migliore = v

    scelto = migliore["candidato"]
    costo_txt = _virgola(migliore["costo"], 1)
    num_txt = _virgola(migliore["numeratore"], 1)
    p_txt = _virgola(migliore["p"], 2)
    perche = (
        f"costo atteso {costo_txt} per «{scelto.id}» ({num_txt} / {p_txt} su {migliore['totale']} risultati)"
    )

    altri = [v for v in valutazioni if v["candidato"].id != scelto.id]
    if altri:
        altri.sort(key=lambda v: v["costo"])
        altri_txt = "; ".join(f"poi «{v['candidato'].id}» {_virgola(v['costo'], 1)}" for v in altri)
        perche += f"; {altri_txt}"

    return Scelta(candidato=scelto.id, aspetta=False, perche=perche)


def _conteggia_risultati(
    candidato_id: str,
    etichette: frozenset[str],
    risultati: Mapping[tuple[str, str], Risultati],
) -> tuple[int, int, int, int]:
    if etichette:
        u = sum(risultati.get((candidato_id, e), Risultati()).uniti for e in etichette)
        cr = sum(risultati.get((candidato_id, e), Risultati()).corretti for e in etichette)
        rf = sum(risultati.get((candidato_id, e), Risultati()).rifiutati for e in etichette)
        tot = u + cr + rf
        if tot > 0:
            return u, cr, rf, tot
    r_star = risultati.get((candidato_id, "*"), Risultati())
    return r_star.uniti, r_star.corretti, r_star.rifiutati, r_star.uniti + r_star.corretti + r_star.rifiutati


def _elegibile(c: Candidato, compito: Compito) -> bool:
    if compito.funzione not in c.funzioni:
        return False
    if compito.fuori and not c.runner:
        return False
    return True


def _ha_quota(c: Candidato, quote: Mapping[str, str | None], adesso: datetime) -> tuple[bool, str | None]:
    valore = quote.get(c.bottega)
    if valore is None:
        valore = quote.get(nome_variabile(c.bottega))
    return disponibile(valore, adesso)


def _virgola(valore: float, decimali: int = 1) -> str:
    return f"{valore:.{decimali}f}".replace(".", ",")
