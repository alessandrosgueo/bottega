"""Controllo pubblico: cerca nei file del repo i dati personali che non devono diventare pubblici.

Due famiglie di regole: le parole vietate (dalla variabile `PAROLE_VIETATE`) e le regole fisse (percorsi di casa,
email, IP privati, MAC). Il motivo di una segnalazione dice che cosa è stato trovato, mai la parola: i log di un repo
pubblico sono pubblici.
"""

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from collections.abc import Sequence
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


# Percorsi di casa: /home/<nome>/ e C:\Users\<nome>\. Il segnaposto <utente> ha le parentesi angolari, quindi
# la classe dei caratteri non lo prende; utente e nome (in ogni maiuscola) si saltano.
_PERCORSO_DI_CASA = re.compile(r"/home/([\w.-]+)|[A-Za-z]:\\+Users\\+([\w.-]+)", re.IGNORECASE)
_SEGNAPOSTO_NOME = {"utente", "nome"}

# Email: parte locale, chiocciola, dominio. Esenti i domini di esempio e i locali che cominciano con noreply.
_EMAIL = re.compile(r"([A-Za-z0-9._%+-]+)@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![A-Za-z0-9-])")
_DOMINI_DI_ESEMPIO = {"example.com", "example.org"}

# IPv4 con quattro ottetti, fuori da numeri più lunghi. Le reti private dello standard RFC 1918 (10/8, 172.16/12,
# 192.168/16) sono scritte in esadecimale: il controllo non deve trovare se stesso nel suo sorgente.
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?!\d|\.\d)")
_RETI_PRIVATE = (
    ipaddress.ip_network((0x0A000000, 8)),
    ipaddress.ip_network((0xAC100000, 12)),
    ipaddress.ip_network((0xC0A80000, 16)),
)

# MAC: la sequenza massima di coppie esadecimali separate da : o -, che inizia e finisce su un confine di parola.
# Vale come MAC solo se ha sei gruppi: una sequenza più lunga (tipo IPv6) non è un MAC. Esente il prefisso di esempio.
_MAC = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2})+(?![0-9A-Za-z])")
_PREFISSO_MAC_DI_ESEMPIO = "02:00:00:00:00:"


def vietate_da_ambiente(valore: str | None) -> list[str]:
    """Le parole di PAROLE_VIETATE, separate da virgole o a capo; spazi e vuoti via."""
    return [p for p in (x.strip() for x in re.split(r"[,\n]", valore or "")) if p]


def cerca(testo: str, percorso: str, vietate: Sequence[str]) -> list[Trovata]:
    """Cerca riga per riga, con le righe contate da 1: una segnalazione per riga e per motivo."""
    return [
        Trovata(percorso, numero, motivo)
        for numero, riga in enumerate(testo.split("\n"), 1)
        for motivo in _motivi(riga, vietate)
    ]


def controlla(radice: Path, vietate: Sequence[str]) -> list[Trovata]:
    """Cerca nei nomi e nel contenuto dei file che git ls-files elenca in radice. I file non UTF-8 si saltano."""
    trovate: list[Trovata] = []
    for nome in _tracciati(radice):
        trovate += [Trovata(nome, 0, motivo) for motivo in _motivi(nome, vietate)]
        percorso = radice / nome
        try:
            if percorso.is_symlink():
                testo = os.readlink(percorso)  # il contenuto di un link git è il suo bersaglio
            elif percorso.is_file():
                testo = percorso.read_bytes().decode("utf-8")
            else:
                continue
        except UnicodeDecodeError:
            continue
        except OSError:
            raise ErroreControllo(f"file non leggibile: {_maschera(nome, vietate)}") from None
        trovate += cerca(testo, nome, vietate)
    return trovate


def argomenti_controlla_pubblico(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--radice",
        default=".",
        metavar="PERCORSO",
        help="cartella del repo da controllare (predefinita: quella attuale)",
    )


def controlla_pubblico(args: argparse.Namespace) -> int:
    """Cerca dati personali nei file del repo: esce 1 se ne trova, 0 se no."""
    vietate = vietate_da_ambiente(os.environ.get("PAROLE_VIETATE"))
    try:
        trovate = controlla(Path(args.radice), vietate)
    except ErroreControllo as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
    if not vietate:
        print("nessuna parola vietata: controllo solo delle regole fisse")
    for t in trovate:
        print(f"{_maschera(t.percorso, vietate)}:{t.riga}: {t.motivo}")
    return 1 if trovate else 0


def _motivi(riga: str, vietate: Sequence[str]) -> list[str]:
    """I motivi di un testo (una riga o il nome di un file): uno per tipo, mai la parola."""
    motivi = [
        f"parola vietata n.{i}"
        for i, parola in enumerate(vietate, 1)
        if parola.strip() and parola.casefold() in riga.casefold()
    ]
    if _ha_percorso_di_casa(riga):
        motivi.append("percorso di casa")
    if _ha_email(riga):
        motivi.append("indirizzo email")
    if _ha_ip_privato(riga):
        motivi.append("indirizzo IP privato")
    if _ha_mac(riga):
        motivi.append("indirizzo MAC")
    return motivi


def _ha_percorso_di_casa(riga: str) -> bool:
    for m in _PERCORSO_DI_CASA.finditer(riga):
        if (m.group(1) or m.group(2)).casefold() not in _SEGNAPOSTO_NOME:
            return True
    return False


def _ha_email(riga: str) -> bool:
    for m in _EMAIL.finditer(riga):
        locale, dominio = m.group(1).casefold(), m.group(2).casefold()
        if dominio not in _DOMINI_DI_ESEMPIO and not locale.startswith("noreply"):
            return True
    return False


def _ha_ip_privato(riga: str) -> bool:
    for m in _IPV4.finditer(riga):
        ottetti = [int(x) for x in m.group(1).split(".")]
        if max(ottetti) > 255:
            continue
        ip = ipaddress.IPv4Address(int.from_bytes(bytes(ottetti), "big"))
        if any(ip in rete for rete in _RETI_PRIVATE):
            return True
    return False


def _ha_mac(riga: str) -> bool:
    for m in _MAC.finditer(riga):
        mac = m.group().replace("-", ":").lower()
        if mac.count(":") == 5 and not mac.startswith(_PREFISSO_MAC_DI_ESEMPIO):
            return True
    return False


def _tracciati(radice: Path) -> list[str]:
    """I file che git ls-files elenca in radice; con -z i nomi strani non si rompono."""
    try:
        esito = subprocess.run(["git", "-C", str(radice), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise ErroreControllo("la radice non è un repo git leggibile") from None
    return [os.fsdecode(nome) for nome in esito.stdout.split(b"\0") if nome]


def _maschera(percorso: str, vietate: Sequence[str]) -> str:
    """Il percorso da stampare: le parole vietate diventano asterischi, così il log non le ripete."""
    mascherato = percorso
    for parola in vietate:
        if parola.strip():
            mascherato = re.sub(re.escape(parola), lambda m: "*" * len(m.group()), mascherato, flags=re.IGNORECASE)
    if any(p.strip() and p.casefold() in mascherato.casefold() for p in vietate):
        return "<percorso mascherato>"
    return mascherato
