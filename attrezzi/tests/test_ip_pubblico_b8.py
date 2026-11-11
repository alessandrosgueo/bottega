"""Prove dell'IP pubblico nella rete dell'esecutore (B8-3, dalla revisione: G2).

Un router col NAT loopback risponde sul suo IP pubblico anche dalla LAN: il set `pubblici4` lo rifiuta all'esecutore.
Il programma che lo riempie si prova davvero, con `curl` e `nft` finti (indirizzi di documentazione, 203.0.113.0/24).
"""

import os
import subprocess
from pathlib import Path

from bottega.macchina import (
    Utenti,
    passi_rete,
    programma_ip_pubblico,
    testo_ip_pubblico,
    testo_rete_esecutore,
    testo_timer_ip_pubblico,
    testo_unita_ip_pubblico,
)

U = Utenti(esecutore="bottega-esecutore")


def _prepara(tmp_path: Path, risposte: list[tuple[int, str]]) -> tuple[Path, Path, dict[str, str]]:
    """Il programma con `nft` finto (registra lo stdin) e un `curl` finto che dà le risposte in ordine."""
    finti = tmp_path / "finti"
    finti.mkdir()
    registro_nft = tmp_path / "nft.txt"
    contatore = tmp_path / "curl-n"
    contatore.write_text("0", encoding="utf-8")
    righe = []
    for i, (codice, testo) in enumerate(risposte):
        righe.append(f'    {i}) printf "%s" {testo!r}; exit {codice} ;;')
    curl = finti / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        f'n=$(cat "{contatore}"); echo $((n + 1)) > "{contatore}"\n'
        'case "$n" in\n' + "\n".join(righe) + "\n    *) exit 7 ;;\nesac\n",
        encoding="utf-8",
    )
    nft = finti / "nft"
    nft.write_text(f'#!/bin/sh\ncat >> "{registro_nft}"\n', encoding="utf-8")
    for f in (curl, nft):
        f.chmod(0o755)
    programma = tmp_path / "ip-pubblico"
    programma.write_text(testo_ip_pubblico(U).replace("/usr/sbin/nft", str(nft)), encoding="utf-8")
    programma.chmod(0o755)
    env = {**os.environ, "PATH": f"{finti}:/usr/bin:/bin"}
    return programma, registro_nft, env


def test_b8_rete_rifiuta_l_ip_pubblico() -> None:
    testo = testo_rete_esecutore(U, ["192.0.2.53"])
    assert "set pubblici4 {" in testo
    righe = [r.strip() for r in testo.splitlines()]
    assert "ip daddr @pubblici4 reject" in righe
    assert righe.index("ip daddr @pubblici4 reject") > max(i for i, r in enumerate(righe) if "192.0.2.53" in r)


def test_b8_ip_pubblico_valido(tmp_path: Path) -> None:
    programma, registro, env = _prepara(tmp_path, [(0, "203.0.113.7")])
    esito = subprocess.run([str(programma)], env=env, capture_output=True, text=True, timeout=30, check=False)
    assert esito.returncode == 0
    scritto = registro.read_text(encoding="utf-8")
    assert "flush set inet rete_bottega_esecutore pubblici4\n" in scritto
    assert "add element inet rete_bottega_esecutore pubblici4 { 203.0.113.7 }" in scritto


def test_b8_ip_pubblico_seconda_fonte(tmp_path: Path) -> None:
    programma, registro, env = _prepara(tmp_path, [(22, ""), (0, "203.0.113.8")])
    esito = subprocess.run([str(programma)], env=env, capture_output=True, text=True, timeout=30, check=False)
    assert esito.returncode == 0
    assert "{ 203.0.113.8 }" in registro.read_text(encoding="utf-8")


def test_b8_ip_pubblico_storto_non_tocca_il_set(tmp_path: Path) -> None:
    programma, registro, env = _prepara(
        tmp_path, [(0, "<html>non un indirizzo</html>"), (0, "203.0.113.9 }; flush ruleset; add element x { 1")]
    )
    esito = subprocess.run([str(programma)], env=env, capture_output=True, text=True, timeout=30, check=False)
    assert esito.returncode == 1
    assert not registro.exists()
    assert "resta com'era" in esito.stderr


def test_b8_ip_pubblico_unita_e_timer() -> None:
    unita = testo_unita_ip_pubblico(U)
    assert f"ExecStart={programma_ip_pubblico(U)}\n" in unita
    assert "After=network-online.target bottega-esecutore-rete.service\n" in unita
    assert "Requires=bottega-esecutore-rete.service\n" in unita
    timer = testo_timer_ip_pubblico(U)
    assert "OnBootSec=1min\n" in timer
    assert "OnUnitActiveSec=10min\n" in timer
    assert "WantedBy=timers.target\n" in timer


def test_b8_passi_ip_pubblico_dopo_il_carico() -> None:
    comandi = [" ".join(p.comando) for p in passi_rete(U, ["192.0.2.53"])]
    carico = next(i for i, c in enumerate(comandi) if c == "sudo -n nft -f /etc/nftables.d/bottega-esecutore.nft")
    avvio = comandi.index("sudo -n systemctl start bottega-esecutore-ip-pubblico.service")
    timer = comandi.index("sudo -n systemctl enable --now bottega-esecutore-ip-pubblico.timer")
    assert carico < avvio < timer
    programma = next(c for c in comandi if programma_ip_pubblico(U) in c and "install" in c)
    assert "-m 0755" in programma
