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
    peso_del_candidato,
    variabile_della_quota,
    variabili_della_quota,
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
    base = _scegli_senza_avvisi(
        compito=compito,
        configurazione=configurazione,
        risultati=risultati,
        quote=quote,
        adesso=adesso,
        caso=caso,
        costo_decisore=costo_decisore,
        costi_propri=costi_propri,
    )
    return _con_avvisi(base, configurazione, quote, adesso)


def _scegli_senza_avvisi(
    compito: Compito,
    configurazione: Configurazione,
    risultati: Mapping[tuple[str, str], Risultati],
    quote: Mapping[str, str | None],
    adesso: datetime,
    caso: random.Random,
    costo_decisore: float,
    costi_propri: Mapping[str, float] | None,
) -> Scelta:
    tutti = list(configurazione.candidati.values())

    # 1. Etichetta esegue (B2-R3.2)
    nome_esegue, conflitti = _ricava_esegue(compito)
    if conflitti:
        return Scelta(
            candidato=None,
            aspetta=False,
            perche=f"etichette esegue in conflitto: {', '.join(conflitti)}",
        )
    if nome_esegue is not None:
        return _scegli_per_etichetta_esegue(nome_esegue, compito, tutti, quote, adesso)

    # 2. Precedente della tappa (B2-R3.3, B12-R6: solo se non è di riserva)
    if compito.precedente is not None:
        esito_precedente = _scegli_per_precedente(compito, configurazione, quote, adesso)
        if esito_precedente is not None:
            return esito_precedente

    # 3. Candidati eleggibili per funzione e runner (B2-R3.1)
    elegibili = [c for c in tutti if _elegibile(c, compito)]
    if not elegibili:
        perche = f"nessun candidato per la funzione «{compito.funzione}»" + (" fuori" if compito.fuori else "")
        return Scelta(candidato=None, aspetta=False, perche=perche)

    cand_prec = configurazione.candidati.get(compito.precedente) if compito.precedente is not None else None
    if cand_prec is not None and not cand_prec.riserva and compito.giri_in_attesa >= 1:
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

    # B12-R6: i normali hanno sempre la precedenza sulle riserve
    normali = [c for c in con_quota if not c.riserva]
    da_riserva = not normali
    candidati_scelta = normali if normali else con_quota

    # 4. Costo atteso con campionamento di Thompson (B2-R3.4 e B2-R3.5)
    scelta = _scegli_per_costo_atteso(
        con_quota=candidati_scelta,
        compito=compito,
        configurazione=configurazione,
        risultati=risultati,
        caso=caso,
        costo_decisore=costo_decisore,
        costi_propri=costi_propri,
    )
    if da_riserva:
        return Scelta(
            candidato=scelta.candidato,
            aspetta=scelta.aspetta,
            perche=f"di riserva: {scelta.perche}",
        )
    return scelta


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


def _carica_risultati_json(percorso: Path) -> tuple[dict[tuple[str, str], Risultati] | None, str | None]:
    try:
        with percorso.open("rb") as f:
            dati = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        return None, motivo

    if not isinstance(dati, dict):
        return None, "la radice del file JSON deve essere un oggetto"

    risultati_map: dict[tuple[str, str], Risultati] = {}
    for c_id, per_etichetta in dati.items():
        if not isinstance(per_etichetta, dict):
            return None, f"il valore per il candidato «{c_id}» deve essere un oggetto"
        for etichetta, conteggi in per_etichetta.items():
            if not isinstance(conteggi, dict):
                return None, f"i conteggi per «{c_id}» ed etichetta «{etichetta}» devono essere un oggetto"
            for k, v in conteggi.items():
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    return None, f"il conteggio «{k}» per «{c_id}» deve essere un intero >= 0 (trovato {v!r})"
            uniti = conteggi.get("uniti", 0)
            corretti = conteggi.get("corretti", 0)
            rifiutati = conteggi.get("rifiutati", 0)
            risultati_map[(c_id, etichetta)] = Risultati(uniti=uniti, corretti=corretti, rifiutati=rifiutati)

    return risultati_map, None


def _carica_quote_json(percorso: Path) -> tuple[dict[str, str | None] | None, str | None]:
    try:
        with percorso.open("rb") as f:
            dati = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        motivo = e.strerror or str(e) if isinstance(e, OSError) else str(e)
        return None, motivo

    if not isinstance(dati, dict):
        return None, "la radice del file JSON deve essere un oggetto"

    for k, v in dati.items():
        if v is not None and (not isinstance(v, str) or isinstance(v, bool)):
            return None, f"il valore della quota per «{k}» deve essere una stringa o null (trovato {v!r})"

    return dati, None


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
        dati_ris, errore = _carica_risultati_json(percorso_ris)
        if errore is not None:
            print(f"errore: {percorso_ris}: {errore}", file=sys.stderr)
            return 2
        assert dati_ris is not None
        risultati_map = dati_ris

    quote_map: dict[str, str | None] = {}
    if args.quote:
        percorso_quote = Path(args.quote)
        dati_quote, errore = _carica_quote_json(percorso_quote)
        if errore is not None:
            print(f"errore: {percorso_quote}: {errore}", file=sys.stderr)
            return 2
        assert dati_quote is not None
        quote_map = dati_quote

    try:
        fuso = ZoneInfo(cfg.progetto.fuso)
    except Exception:
        fuso = ZoneInfo("UTC")
    adesso = datetime.now(fuso)

    # Stampa gli avvisi della quota su stderr, uno per variabile
    for avviso in _avvisi_quote(cfg, quote_map, adesso):
        print(f"avviso: {avviso}", file=sys.stderr)

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


def _ricava_esegue(compito: Compito) -> tuple[str | None, list[str]]:
    nomi: list[str] = []
    if compito.esegue is not None and compito.esegue.strip():
        nomi.append(compito.esegue.strip())
    for etichetta in compito.etichette:
        if etichetta.casefold().startswith("esegue:"):
            val = etichetta.split(":", 1)[1].strip()
            if val:
                nomi.append(val)
    if not nomi:
        return None, []

    unici_cf: dict[str, str] = {}
    for n in nomi:
        cf = n.casefold()
        if cf not in unici_cf:
            unici_cf[cf] = n

    if len(unici_cf) > 1:
        ordinati = sorted(unici_cf.values(), key=str.casefold)
        return None, ordinati

    return nomi[0], []


def _scegli_per_etichetta_esegue(
    nome_esegue: str,
    compito: Compito,
    tutti: list[Candidato],
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> Scelta:
    nome_cf = nome_esegue.casefold()
    trovato = next((c for c in tutti if c.id.casefold() == nome_cf), None)
    if trovato is None:
        trovato = next((c for c in tutti if c.nome.casefold() == nome_cf), None)

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
                f"non può svolgere la funzione «{compito.funzione}»" + (" fuori" if compito.fuori else "")
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


def _chiavi_quote(configurazione: Configurazione) -> list[str]:
    chiavi: list[str] = list(variabili_della_quota(configurazione))
    for b in sorted(configurazione.botteghe.values(), key=lambda x: x.id):
        var_bottega = nome_variabile(b.id)
        if var_bottega not in chiavi:
            chiavi.append(var_bottega)
        if b.id not in chiavi:
            chiavi.append(b.id)
    return chiavi


def _avvisi_quote(
    configurazione: Configurazione,
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> list[str]:
    avvisi: list[str] = []
    for chiave in _chiavi_quote(configurazione):
        valore = quote.get(chiave)
        if valore is None:
            continue
        _, avviso = disponibile(valore, adesso)
        if avviso is not None:
            messaggio = f"{chiave}: {avviso}"
            if messaggio not in avvisi:
                avvisi.append(messaggio)
    return avvisi


def _con_avvisi(
    scelta: Scelta,
    configurazione: Configurazione,
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> Scelta:
    avvisi = _avvisi_quote(configurazione, quote, adesso)
    if not avvisi:
        return scelta
    return Scelta(
        candidato=scelta.candidato,
        aspetta=scelta.aspetta,
        perche=scelta.perche + "".join(f"; avviso: {' '.join(a.split())}" for a in avvisi),  # mai a capo
    )


def _scegli_per_precedente(
    compito: Compito,
    configurazione: Configurazione,
    quote: Mapping[str, str | None],
    adesso: datetime,
) -> Scelta | None:
    assert compito.precedente is not None
    cand_prec = configurazione.candidati.get(compito.precedente)
    if cand_prec is not None and not cand_prec.riserva and _elegibile(cand_prec, compito):
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
        peso_quota = PESI_QUOTA.get(peso_del_candidato(configurazione, c), 1.0)
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
    perche = f"costo atteso {costo_txt} per «{scelto.id}» ({num_txt} / {p_txt} su {migliore['totale']} risultati)"

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
    chiavi = [variabile_della_quota(c)]
    if c.quota is not None:
        chiavi.append(nome_variabile(c.bottega))
    chiavi.append(c.bottega)
    primo_avviso: str | None = None
    for chiave in chiavi:
        valore = quote.get(chiave)
        if valore is None:
            continue
        ok, avviso = disponibile(valore, adesso)
        if not ok:
            return False, None
        if primo_avviso is None and avviso is not None:
            primo_avviso = avviso
    return True, primo_avviso


def _virgola(valore: float, decimali: int = 1) -> str:
    return f"{valore:.{decimali}f}".replace(".", ",")
