"""Cancello B6, Review Focus 1: un sudoers rotto non si installa e sudo resta vivo."""
import subprocess, sys
from bottega.macchina import ErroreMacchina, esecutore_vero, esegui_passi, passo_file

rotto = passo_file("sudoers rotto", "questa riga non è sudoers ALL=(\n", "/etc/sudoers.d/bottega", "0440", controlla_sudoers=True)
try:
    esegui_passi([rotto], esecutore_vero)
    print("ROSSO il sudoers rotto è passato"); sys.exit(1)
except ErroreMacchina as e:
    print("VERDE rifiutato:", str(e)[:120])
import os
print(("VERDE" if not os.path.exists("/etc/sudoers.d/bottega") else "ROSSO") + " nessun file installato")
r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
print(("VERDE" if r.returncode == 0 else "ROSSO") + " sudo funziona ancora")
r = subprocess.run(["sh", "-c", "ls /tmp | grep -c bottega || true"], capture_output=True, text=True)
print(("VERDE" if r.stdout.strip() == "0" else "ROSSO") + " niente temporanei bottega in /tmp")
