"""Cancello B6: i passi di macchina veri in un contenitore pulito, due volte, e il sudoers alla prova.

Si lancia dentro il contenitore come root, con PYTHONPATH che punta agli attrezzi della bottega.
"""

from pathlib import Path
import shutil
import subprocess
import sys

from bottega.macchina import Utenti, esecutore_vero, esegui_passi, passi_macchina, passi_runner


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

    # G1: ogni utente ha il suo gruppo principale, `bottega` solo in più.
    _, uscita = sh("id -gn bottega-runner; id -gn bottega-esecutore; id -Gn bottega-esecutore")
    righe = uscita.splitlines()
    esiti.append(
        (
            f"gruppi principali propri, bottega in più ({' | '.join(righe)})",
            righe[:2] == ["bottega-runner", "bottega-esecutore"] and "bottega" in righe[2].split(),
        )
    )

    # Il giro: il runner crea la cartella del giro (2770), l'esecutore ci lavora, il runner legge e toglie tutto.
    codice, uscita = sh(
        "sudo -u bottega-runner sh -c 'd=$(mktemp -d -p /var/lib/bottega/spazio) && chmod 2770 \"$d\" && "
        "sudo -n -H -u bottega-esecutore -- sh -c \"mkdir $d/lavoro && echo dentro > $d/lavoro/f\" && "
        "cat \"$d/lavoro/f\" && rm -rf \"$d\"'"
    )
    esiti.append((f"il runner legge e toglie ciò che l'esecutore crea nel giro ({uscita})", codice == 0 and uscita == "dentro"))

    # La cartella del runner: sua, 0750, l'esecutore non ci entra.
    passi = passi_runner(
        Utenti(), "o/r", "2.320.0", "x64", "a" * 64, "bottega", "prova", {}, token="finto-123"
    )
    cartella_passo = [p for p in passi if p.descrizione.startswith("cartella runner")]
    esegui_passi(cartella_passo, esecutore_vero)
    cartella = "/var/lib/bottega/runner-o-r"
    _, uscita = sh(f"stat -c '%U:%G:%a' {cartella}")
    esiti.append((f"cartella del runner sua, 750 ({uscita})", uscita == "bottega-runner:bottega-runner:750"))
    codice, _ = sh(f"sudo -u bottega-esecutore ls {cartella}")
    esiti.append(("l'esecutore NON entra nella cartella del runner", codice != 0))

    # G4: sudo azzera l'ambiente, quindi il token arriva a config.sh solo con --preserve-env.
    _, uscita = sh("X=segreto sudo -n -u bottega-runner sh -c 'echo \"[$X]\"'")
    esiti.append((f"sudo senza --preserve-env perde l'ambiente ({uscita})", uscita == "[]"))
    finto = Path(cartella, "config.sh")
    finto.write_text('#!/bin/sh\nprintf %s "$ACTIONS_RUNNER_INPUT_TOKEN" > .runner\n', encoding="utf-8")
    finto.chmod(0o755)
    shutil.chown(finto, "bottega-runner", "bottega-runner")
    configura = [p for p in passi if p.descrizione.startswith("configura runner")]
    esegui_passi(configura, esecutore_vero)
    _, uscita = sh(f"cat {cartella}/.runner")
    esiti.append((f"il token arriva a config.sh nell'ambiente ({uscita!r})", uscita == "finto-123"))

    print()
    for descrizione, ok in esiti:
        print(("VERDE " if ok else "ROSSO ") + descrizione)
    return 0 if all(ok for _, ok in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
