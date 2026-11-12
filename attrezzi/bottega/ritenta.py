"""I ritentativi sugli errori passeggeri di GitHub (Ruling B9-R1)."""

import re
import sys
import time
from collections.abc import Callable, Sequence

ATTESE_S: tuple[float, ...] = (10.0, 30.0)

_REGEX_HTTP_50X = re.compile(r"HTTP 50[0234]\b", re.IGNORECASE)

_FRASI_PASSEGGERO: tuple[str, ...] = (
    "no server is currently available",
    "connection reset",
    "connection refused",
    "timeout",
    "timed out",
    "tls handshake",
    "unexpected eof",
    "could not resolve host",
    "temporary failure in name resolution",
    "non ha risposto in",
)

_FRASI_NON_CONSEGNATO: tuple[str, ...] = (
    "no server is currently available",
    "connection refused",
    "could not resolve host",
    "temporary failure in name resolution",
)

_COMANDI_LETTURA = {
    "issue",
    "pr",
    "run",
    "repo",
    "label",
    "release",
    "workflow",
    "project",
    "search",
}

_SOTTOCOMANDI_LETTURA = {
    "view",
    "list",
    "status",
    "diff",
    "checks",
}

_FLAG_CAMPI_POST = ("-f", "-F", "--field", "--raw-field", "--input")


def passeggero(testo: str) -> bool:
    """True se il testo contiene un errore passeggero di GitHub (senza distinguere maiuscole)."""
    if _REGEX_HTTP_50X.search(testo):
        return True
    testo_basso = testo.lower()
    return any(frase in testo_basso for frase in _FRASI_PASSEGGERO)


def non_consegnato(testo: str) -> bool:
    """True se l'errore indica che la richiesta non è arrivata a GitHub (senza maiuscole)."""
    testo_basso = testo.lower()
    return any(frase in testo_basso for frase in _FRASI_NON_CONSEGNATO)


def di_sola_lettura(argomenti: Sequence[str]) -> bool:
    """True se il comando gh è di sola lettura."""
    if not argomenti:
        return False

    primo = argomenti[0]
    if (
        len(argomenti) >= 2
        and primo in _COMANDI_LETTURA
        and argomenti[1] in _SOTTOCOMANDI_LETTURA
    ):
        return True

    if primo == "api":
        if len(argomenti) < 2:
            return False
        if argomenti[1] == "graphql":
            return not any(
                re.search(r"\bmutation\b", a, re.IGNORECASE) for a in argomenti
            )

        # api su un altro percorso: vero se non c'è -X/--method != GET e non ci sono campi
        i = 1
        while i < len(argomenti):
            a = argomenti[i]
            if a in ("-X", "--method"):
                if i + 1 < len(argomenti):
                    if argomenti[i + 1].upper() != "GET":
                        return False
                    i += 2
                    continue
                return False
            if a.startswith("--method="):
                if a.split("=", 1)[1].upper() != "GET":
                    return False
                i += 1
                continue
            if a.startswith("-X"):
                val = a[2:].lstrip("=")
                if val.upper() != "GET":
                    return False
                i += 1
                continue
            if a in _FLAG_CAMPI_POST or any(
                a.startswith(p + "=") for p in _FLAG_CAMPI_POST
            ):
                return False
            if a.startswith(("-f", "-F")) and not a.startswith("--"):
                return False
            i += 1
        return True

    return False


def ritenta(
    prova: Callable[[], tuple[int, str, str]],
    argomenti: Sequence[str],
    *,
    lettura: bool | None = None,
    dormi: Callable[[float], None] | None = None,
    nome: str | None = None,
) -> tuple[int, str, str]:
    """Chiama prova() e ripete su errori passeggeri secondo le regole B9-R1 (`dormi` di serie: `time.sleep`, letto
    alla chiamata, così le prove possono sostituirlo)."""
    funzione_dormi = dormi if dormi is not None else time.sleep
    is_lettura = lettura if lettura is not None else di_sola_lettura(argomenti)

    if nome is not None:
        nome_cmd = nome
    else:
        primo = argomenti[0] if len(argomenti) > 0 else ""
        secondo = argomenti[1] if len(argomenti) > 1 else ""
        parti = [p for p in (primo, secondo) if p]
        nome_cmd = f"gh {' '.join(parti)}".strip()

    risultato = prova()
    if risultato[0] == 0:
        return risultato

    for attesa in ATTESE_S:
        _, _, stderr = risultato
        if not (passeggero(stderr) and (is_lettura or non_consegnato(stderr))):
            return risultato
        print(
            f"avviso: {nome_cmd}: errore passeggero, riprovo fra {int(attesa)} s",
            file=sys.stderr,
        )
        funzione_dormi(attesa)
        risultato = prova()
        if risultato[0] == 0:
            return risultato

    return risultato
