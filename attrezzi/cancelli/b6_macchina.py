"""Cancello B6: i passi di macchina veri in un contenitore pulito, due volte, e il sudoers alla prova.

Si lancia dentro il contenitore come root, con PYTHONPATH che punta agli attrezzi della bottega.
"""

import subprocess
import sys

from bottega.macchina import Utenti, esecutore_vero, esegui_passi, passi_macchina


def sh(comando: str) -> tuple[int, str]:
    r = subprocess.run(["sh", "-c", comando], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    u = Utenti()
    esiti: list[tuple[str, bool]] = []

    prima = esegui_passi(passi_macchina(u), esecutore_vero)
    print("PRIMA:", *prima, sep="\n  ")
    esiti.append(("la prima installazione fa qualcosa", any(r.startswith("fatto:") for r in prima)))

    seconda = esegui_passi(passi_macchina(u), esecutore_vero)
    print("SECONDA:", *seconda, sep="\n  ")
    esiti.append(("la seconda non cambia niente", all(r.startswith("già fatto:") for r in seconda)))

    codice, uscita = sh("stat -c '%U:%G:%a' /var/lib/bottega/spazio")
    esiti.append((f"spazio runner:gruppo 2770 ({uscita})", uscita == "bottega-runner:bottega:2770"))

    codice, uscita = sh("stat -c '%U:%G:%a' /etc/sudoers.d/bottega-esecutore")
    esiti.append((f"sudoers root:root 440 ({uscita})", uscita == "root:root:440"))

    codice, uscita = sh("visudo -c")
    esiti.append(("visudo -c di tutto il sistema", codice == 0))

    codice, uscita = sh("sudo -u bottega-runner sudo -n -H -u bottega-esecutore -- id -un")
    esiti.append((f"il runner diventa l'esecutore senza password ({uscita})", codice == 0 and uscita == "bottega-esecutore"))

    codice, uscita = sh("sudo -u bottega-runner sudo -n -u bottega-esecutore -- sh -c umask")
    esiti.append((f"umask dell'esecutore via sudo ({uscita})", uscita == "0007"))

    codice, _ = sh("sudo -u bottega-runner sudo -n id -un")
    esiti.append(("il runner NON diventa root", codice != 0))

    codice, _ = sh("sudo -u bottega-runner sudo -n -u nobody id -un")
    esiti.append(("il runner NON diventa un altro utente", codice != 0))

    codice, _ = sh("sudo -u bottega-esecutore sudo -n id -un")
    esiti.append(("l'esecutore NON ha sudo", codice != 0))

    codice, _ = sh("sudo -u bottega-esecutore sh -c 'touch /var/lib/bottega/spazio/prova && rm /var/lib/bottega/spazio/prova'")
    esiti.append(("l'esecutore scrive nello spazio", codice == 0))

    codice, _ = sh("sudo -u nobody sh -c 'ls /var/lib/bottega/spazio'")
    esiti.append(("un estraneo NON legge lo spazio", codice != 0))

    print()
    for descrizione, ok in esiti:
        print(("VERDE " if ok else "ROSSO ") + descrizione)
    return 0 if all(ok for _, ok in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
