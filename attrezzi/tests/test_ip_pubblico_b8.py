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
    stato_ip_pubblico,
    testo_ip_pubblico,
    testo_rete_esecutore,
    testo_timer_ip_pubblico,
    testo_unita_ip_pubblico,
)

U = Utenti(esecutore="bottega-esecutore")


def _prepara(
    tmp_path: Path, risposte: list[tuple[int, str]], nft_esce: int = 0
) -> tuple[Path, Path, dict[str, str]]:
    """Il programma con `nft` finto (registra lo stdin) e un `curl` finto che dà le risposte in ordine."""
    finti = tmp_path / "finti"
    finti.mkdir()
    registro_nft = tmp_path / "nft.txt"
    contatore = tmp_path / "curl-n"
    contatore.write_text("0", encoding="utf-8")
    righe = []
    for i, (codice, testo) in enumerate(risposte):
        # La risposta da un file, così gli a capo arrivano veri al programma.
        (finti / f"risposta-{i}").write_text(testo, encoding="utf-8")
        righe.append(f'    {i}) cat "{finti / f"risposta-{i}"}"; exit {codice} ;;')
    curl = finti / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        f'n=$(cat "{contatore}"); echo $((n + 1)) > "{contatore}"\n'
        'case "$n" in\n' + "\n".join(righe) + "\n    *) exit 7 ;;\nesac\n",
        encoding="utf-8",
    )
    nft = finti / "nft"
    nft.write_text(f'#!/bin/sh\ncat >> "{registro_nft}"\nexit {nft_esce}\n', encoding="utf-8")
    for f in (curl, nft):
        f.chmod(0o755)
    programma = tmp_path / "ip-pubblico"
    testo = (
        testo_ip_pubblico(U)
        .replace("/usr/sbin/nft", str(nft))
        .replace("/usr/bin/curl", str(curl))
        .replace(stato_ip_pubblico(U), str(tmp_path / "stato" / "ip"))
    )
    programma.write_text(testo, encoding="utf-8")
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
    assert "IP pubblico non letto" in esito.stderr


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
    salvato = comandi.index(f"sudo -n {programma_ip_pubblico(U)} --salvato")
    # Il timer prima dell'avvio a mano: se la prima lettura fallisce, il timer riprova.
    assert carico < salvato < timer < avvio
    programma = next(c for c in comandi if c.endswith(f'"$t" {programma_ip_pubblico(U)}'))
    assert "-m 0755" in programma


def _lancia(programma: Path, env: dict[str, str], *argomenti: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(programma), *argomenti], env=env, capture_output=True, text=True, timeout=30, check=False)


def test_b8_ip_pubblico_su_piu_righe_non_entra(tmp_path: Path) -> None:
    """Una risposta con un IPv4 su una riga e comandi nft sulle altre non arriva a nft (gira come root)."""
    storta = "203.0.113.9\n}\nflush table inet rete_bottega_esecutore\nadd element inet x pubblici4 { 192.0.2.1"
    programma, registro, env = _prepara(tmp_path, [(0, storta), (0, storta)])
    esito = _lancia(programma, env)
    assert esito.returncode == 1
    assert not registro.exists()


def test_b8_ip_pubblico_salva_e_rimette(tmp_path: Path) -> None:
    programma, registro, env = _prepara(tmp_path, [(0, "203.0.113.10"), (22, ""), (22, "")])
    assert _lancia(programma, env).returncode == 0
    assert (tmp_path / "stato" / "ip").read_text(encoding="utf-8") == "203.0.113.10\n"
    registro.unlink()
    # Le fonti non rispondono: rimette l'ultimo salvato ed esce 1 (il timer e Restart= riprovano).
    esito = _lancia(programma, env)
    assert esito.returncode == 1
    assert "{ 203.0.113.10 }" in registro.read_text(encoding="utf-8")
    registro.unlink()
    # Dopo una ricarica della regola: solo l'IP salvato, senza rete.
    assert _lancia(programma, env, "--salvato").returncode == 0
    assert "{ 203.0.113.10 }" in registro.read_text(encoding="utf-8")


def test_b8_ip_pubblico_salvato_assente(tmp_path: Path) -> None:
    programma, registro, env = _prepara(tmp_path, [])
    assert _lancia(programma, env, "--salvato").returncode == 0
    assert not registro.exists()


def test_b8_ip_pubblico_unita_rimette_dopo_la_ricarica() -> None:
    from bottega.macchina import testo_unita_rete

    unita = testo_unita_rete(U)
    assert f"ExecStartPost=-{programma_ip_pubblico(U)} --salvato\n" in unita
    assert f"ExecReload=-{programma_ip_pubblico(U)} --salvato\n" in unita
    assert "Restart=on-failure\n" in testo_unita_ip_pubblico(U)


def test_b8_ip_pubblico_nft_che_fallisce(tmp_path: Path) -> None:
    """Se nft rifiuta il cambio, il programma esce 1 e non salva l'IP."""
    programma, _registro, env = _prepara(tmp_path, [(0, "203.0.113.11")], nft_esce=1)
    assert _lancia(programma, env).returncode == 1
    assert not (tmp_path / "stato" / "ip").exists()
