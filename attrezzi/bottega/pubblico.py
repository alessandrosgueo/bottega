"""Controllo pubblico: cerca nei file del repo i dati personali che non devono diventare pubblici.

Due famiglie di regole: le parole vietate (dalla variabile `PAROLE_VIETATE`) e le regole fisse (percorsi di casa,
email, IP privati, MAC). Il motivo di una segnalazione dice che cosa è stato trovato, mai la parola: i log di un repo
pubblico sono pubblici.
"""

import argparse
import codecs
import ipaddress
import itertools
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Trovata:
    """Una segnalazione: dove (riga 0 = nel nome del file) e che cosa."""

    percorso: str
    riga: int
    motivo: str


class ErroreControllo(RuntimeError):
    """Il controllo non può girare. Il messaggio non contiene mai percorsi né parole vietate."""


# Percorsi di casa. /home/<nome> in ogni maiuscola; con la lettera di unità (C:/Users, /mnt/c/Users, file:///C:/Users,
# c:\users) in ogni maiuscola; \\wsl.localhost e \\wsl$ con home; /Users/<nome> (macOS) solo con la maiuscola, perché
# un /users/<account> di un'API non è un percorso. Il segnaposto <utente> ha le parentesi angolari, che la classe dei
# caratteri non prende; utente e nome (in ogni maiuscola) si saltano.
_NOME = r"([\w.-]+)"
_PERCORSI_DI_CASA = (
    re.compile(r"/home/" + _NOME, re.IGNORECASE),
    re.compile(r"(?:/mnt/[a-z]|[a-z]:)[\\/]+Users[\\/]+" + _NOME, re.IGNORECASE),
    re.compile(r"\\\\wsl(?:\.localhost|\$)\\+[\w.-]+\\+home\\+" + _NOME, re.IGNORECASE),
    re.compile(r"/Users/" + _NOME),
)
_SEGNAPOSTO_NOME = {"utente", "nome"}

# Email: parte locale, chiocciola, dominio. Esenti i domini di esempio e la parte locale noreply esatta. La forma di
# GitHub con l'account nella parte locale si segnala, perché porta l'account.
_EMAIL = re.compile(r"([A-Za-z0-9._%+-]+)@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![A-Za-z0-9-])")
_DOMINI_DI_ESEMPIO = {"example.com", "example.org"}

# IPv4 con quattro ottetti, fuori da numeri più lunghi. Le reti private e riservate sono scritte in esadecimale, così il
# controllo non trova se stesso nel suo sorgente: RFC 1918 (10/8, 172.16/12, 192.168/16), RFC 6598 (100.64/10, quella delle
# VPN a maglia), RFC 3927 (169.254/16, link-local).
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?!\d|\.\d)")
_RETI_PRIVATE = (
    ipaddress.ip_network((0x0A000000, 8)),
    ipaddress.ip_network((0xAC100000, 12)),
    ipaddress.ip_network((0xC0A80000, 16)),
    ipaddress.ip_network((0x64400000, 10)),
    ipaddress.ip_network((0xA9FE0000, 16)),
)

# MAC: coppie esadecimali con lo stesso separatore (: o -), su un confine di parola. Vale come MAC un gruppo di sei
# coppie con lo stesso separatore: un gruppo in più con un altro separatore non lo annulla; sette o otto con lo stesso
# separatore no (sono sequenze più lunghe, tipo IPv6). Esente il prefisso di esempio.
_CATENA_MAC = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2})+(?![0-9A-Za-z])")
_PREFISSO_MAC_DI_ESEMPIO = "02:00:00:00:00:"

# Codifiche riconosciute dal BOM, la più lunga per prima (il BOM di UTF-32 LE comincia come quello di UTF-16 LE).
_BOM = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
# Come git: un byte nullo nei primi byte di un file senza BOM lo rende binario.
_FINESTRA_BINARIA = 8000


def vietate_da_ambiente(valore: str | None) -> list[str]:
    """Le parole di PAROLE_VIETATE, separate da virgole, spazi o a capo: una voce di due parole diventa due parole."""
    return [p for p in re.split(r"[,\s]", valore or "") if p]


def cerca(testo: str, percorso: str, vietate: Sequence[str]) -> list[Trovata]:
    """Cerca riga per riga, con le righe contate da 1: una segnalazione per riga e per motivo."""
    return [
        Trovata(percorso, numero, motivo)
        for numero, riga in enumerate(testo.split("\n"), 1)
        for motivo in _motivi(riga, vietate)
    ]


def controlla(radice: Path, vietate: Sequence[str]) -> list[Trovata]:
    """Cerca nei nomi e nel contenuto dei file che git ls-files elenca in radice (i binari si saltano)."""
    return _esamina(radice, vietate)[0]


def argomenti_controlla_pubblico(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--radice",
        default=".",
        metavar="PERCORSO",
        help="cartella del repo da controllare (predefinita: quella attuale)",
    )
    parser.add_argument(
        "--richiedi-elenco",
        action="store_true",
        help="esce 2 se PAROLE_VIETATE è vuota o assente",
    )


def controlla_pubblico(args: argparse.Namespace) -> int:
    """Cerca dati personali nei file del repo: esce 1 se ne trova, 0 se no, 2 se il controllo non può girare."""
    vietate = vietate_da_ambiente(os.environ.get("PAROLE_VIETATE"))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Prima di ogni altra riga, così Actions maschera le parole nel log. Il % va escapato nel comando.
        for parola in vietate:
            print("::add-mask::" + parola.replace("%", "%25"))
    if args.richiedi_elenco and not vietate:
        print("errore: PAROLE_VIETATE è vuota o assente", file=sys.stderr)
        return 2
    try:
        trovate, non_controllati = _esamina(Path(args.radice), vietate)
    except ErroreControllo as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
    if not vietate:
        print("nessuna parola vietata: controllo solo delle regole fisse")
    for t in trovate:
        print(f"{_maschera(t.percorso, vietate)}:{t.riga}: {t.motivo}")
    if non_controllati:
        print(f"file non controllati: {non_controllati}")
    return 1 if trovate else 0


def _esamina(radice: Path, vietate: Sequence[str]) -> tuple[list[Trovata], int]:
    """Le segnalazioni e quanti file non si sono controllati: binari, o tracciati ma assenti dal disco."""
    trovate: list[Trovata] = []
    non_controllati = 0
    for nome in _tracciati(radice):
        trovate += [Trovata(nome, 0, motivo) for motivo in _motivi(nome, vietate)]
        percorso = radice / nome
        try:
            if percorso.is_symlink():
                testo = os.readlink(percorso)  # il contenuto di un link git è il suo bersaglio
            elif percorso.is_file():
                testo = _testo(percorso.read_bytes())
            else:
                testo = None
        except OSError:
            raise ErroreControllo(f"file non leggibile: {_maschera(nome, vietate)}") from None
        if testo is None:
            non_controllati += 1
        else:
            trovate += cerca(testo, nome, vietate)
    return trovate, non_controllati


def _testo(dati: bytes) -> str | None:
    """Il testo di un file, o None se è binario. Con un BOM si usa la sua codifica; senza, un byte nullo nei primi byte
    rende il file binario; il resto è UTF-8, con i byte non validi (latin-1, per esempio) sostituiti."""
    for bom, codifica in _BOM:
        if dati.startswith(bom):
            return dati.decode(codifica, errors="replace")
    if b"\0" in dati[:_FINESTRA_BINARIA]:
        return None
    return dati.decode("utf-8", errors="replace")


def _motivi(riga: str, vietate: Sequence[str]) -> list[str]:
    """I motivi di un testo (una riga o il nome di un file): uno per tipo, mai la parola."""
    motivi = [
        f"parola vietata n.{i}"
        for i, parola in enumerate(vietate, 1)
        if parola.strip() and parola.casefold() in riga.casefold()
    ]
    motivi += [motivo for motivo, trova in _REGOLE_FISSE if trova(riga)]
    return motivi


def _percorsi_di_casa(riga: str) -> list[tuple[int, int]]:
    return [
        m.span()
        for regex in _PERCORSI_DI_CASA
        for m in regex.finditer(riga)
        if m.group(1).casefold() not in _SEGNAPOSTO_NOME
    ]


def _emails(riga: str) -> list[tuple[int, int]]:
    return [
        m.span()
        for m in _EMAIL.finditer(riga)
        if m.group(1).casefold() != "noreply" and m.group(2).casefold() not in _DOMINI_DI_ESEMPIO
    ]


def _ip_privati(riga: str) -> list[tuple[int, int]]:
    spans = []
    for m in _IPV4.finditer(riga):
        ottetti = [int(x) for x in m.group(1).split(".")]
        if max(ottetti) > 255:
            continue
        ip = ipaddress.IPv4Address(int.from_bytes(bytes(ottetti), "big"))
        if any(ip in rete for rete in _RETI_PRIVATE):
            spans.append(m.span())
    return spans


def _mac(riga: str) -> list[tuple[int, int]]:
    spans = []
    for m in _CATENA_MAC.finditer(riga):
        catena = m.group()
        if _sei_gruppi(catena) and not catena.replace("-", ":").lower().startswith(_PREFISSO_MAC_DI_ESEMPIO):
            spans.append(m.span())
    return spans


def _sei_gruppi(catena: str) -> bool:
    """Vero se una serie di separatori uguali ne ha cinque: sei gruppi con lo stesso separatore."""
    separatori = re.findall(r"[:-]", catena)
    return any(len(list(uguali)) == 5 for _, uguali in itertools.groupby(separatori))


# Le regole fisse: il motivo di ognuna e le posizioni (inizio, fine) dei dati che trova in un testo.
_REGOLE_FISSE: tuple[tuple[str, Callable[[str], list[tuple[int, int]]]], ...] = (
    ("percorso di casa", _percorsi_di_casa),
    ("indirizzo email", _emails),
    ("indirizzo IP privato", _ip_privati),
    ("indirizzo MAC", _mac),
)


def _tracciati(radice: Path) -> list[str]:
    """I file che git ls-files elenca in radice; con -z i nomi strani non si rompono."""
    try:
        esito = subprocess.run(["git", "-C", str(radice), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise ErroreControllo("la radice non è un repo git leggibile") from None
    return [os.fsdecode(nome) for nome in esito.stdout.split(b"\0") if nome]


def _maschera(testo: str, vietate: Sequence[str]) -> str:
    """Il nome da stampare: parole vietate e dati delle regole fisse diventano asterischi, così il log non li ripete."""
    intervalli = [
        m.span()
        for parola in vietate
        if parola.strip()
        for m in re.finditer(re.escape(parola), testo, re.IGNORECASE)
    ]
    intervalli += [span for _, trova in _REGOLE_FISSE for span in trova(testo)]
    caratteri = list(testo)
    for inizio, fine in intervalli:
        caratteri[inizio:fine] = "*" * (fine - inizio)
    mascherato = "".join(caratteri)
    if _motivi(mascherato, vietate):  # se resta qualcosa che la regola trova, il nome non si stampa
        return "<percorso mascherato>"
    return mascherato
