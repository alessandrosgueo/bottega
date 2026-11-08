import os
import subprocess
import sys
from pathlib import Path

import pytest

from bottega.__main__ import main
from bottega.pubblico import Trovata, cerca, controlla, vietate_da_ambiente

ATTREZZI = Path(__file__).resolve().parents[1]
# Gli esempi che il controllo troverebbe si compongono mentre la prova gira: nel repo non compaiono per intero.
PAROLA = "parola" + "finta"


def _repo(cartella: Path, file: dict[str, bytes], link: dict[str, str] | None = None) -> Path:
    """Repo git di prova: i file e i link elencati finiscono nell'indice (git add, nessun commit)."""
    for nome, dati in file.items():
        (cartella / nome).write_bytes(dati)
    for nome, bersaglio in (link or {}).items():
        os.symlink(bersaglio, cartella / nome)
    subprocess.run(["git", "init", "-q"], cwd=cartella, check=True)
    subprocess.run(["git", "add", "-A"], cwd=cartella, check=True)
    return cartella


def test_parola_vietata_senza_badare_alle_maiuscole():
    t = cerca("ciao " + "Mario" + "Rossi", "a.md", ["mario" + "rossi"])
    assert t == [Trovata("a.md", 1, "parola vietata n.1")]


def test_il_motivo_non_ripete_la_parola():
    trovate = cerca("mario" + "rossi", "a.md", ["mario" + "rossi"])
    assert trovate and all("mario" not in x.motivo.lower() for x in trovate)


@pytest.mark.parametrize("testo,motivo", [
    ("/ho" + "me/pippo/x", "percorso di casa"),
    ("C:" + "\\Users\\pippo\\x", "percorso di casa"),
    ("scrivi a a" + "@b.it", "indirizzo email"),
    ("x@" + "example.com.evil.it", "indirizzo email"),
    ("192." + "168.1.42", "indirizzo IP privato"),
    ("172." + "16.0.1", "indirizzo IP privato"),
    ("172." + "31.255.1", "indirizzo IP privato"),
    ("10." + "0.0.1", "indirizzo IP privato"),
    (":".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
    ("-".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
    ("MAC:" + ":".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
])
def test_regole_fisse(testo, motivo):
    assert [x.motivo for x in cerca(testo, "a.md", [])] == [motivo]


def test_sequenza_di_otto_gruppi_non_e_un_mac():
    assert cerca(":".join(["aa", "bb", "cc", "dd", "ee", "ff", "00", "11"]), "a.md", []) == []


@pytest.mark.parametrize("testo", [
    "/home/<utente>/x", "/home/utente/x", "/home/nome/x", "C:\\Users\\<utente>\\x", "C:\\Users\\nome\\x",
    "02:00:00:00:00:01", "192.0.2.1", "172.32.0.1", "172.15.0.1", "noreply@example.com", "noreply@github.com",
    "x@example.org",
])
def test_segnaposto_e_indirizzi_pubblici_ammessi(testo):
    assert cerca(testo, "a.md", []) == []


def test_vietate_da_ambiente():
    assert vietate_da_ambiente(" a, b\nc ,,") == ["a", "b", "c"]
    assert vietate_da_ambiente(None) == []


def test_controlla_legge_solo_i_file_tracciati(tmp_path):
    _repo(tmp_path, {"tracciato.txt": ("ciao " + PAROLA).encode()})
    (tmp_path / "non_tracciato.txt").write_text(PAROLA, encoding="utf-8")
    assert [t.percorso for t in controlla(tmp_path, [PAROLA])] == ["tracciato.txt"]


def test_file_binario_non_fa_cadere_il_controllo(tmp_path):
    _repo(tmp_path, {"binario.bin": b"\xff\xfe\x00", "testo.txt": ("ciao " + PAROLA).encode()})
    assert controlla(tmp_path, [PAROLA]) == [Trovata("testo.txt", 1, "parola vietata n.1")]


def test_il_nome_del_file_conta(tmp_path):
    _repo(tmp_path, {PAROLA.upper() + ".txt": b"ciao"})
    assert controlla(tmp_path, [PAROLA]) == [Trovata(PAROLA.upper() + ".txt", 0, "parola vietata n.1")]


def test_il_bersaglio_di_un_link_viene_letto(tmp_path):
    _repo(tmp_path, {}, {"collegamento": PAROLA})
    assert controlla(tmp_path, [PAROLA]) == [Trovata("collegamento", 1, "parola vietata n.1")]


def test_cli_trova_ed_esce_1(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode(), "binario.bin": b"\xff\xfe\x00"})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.txt:1: parola vietata n.1" in out
    assert PAROLA not in out


def test_cli_maschera_la_parola_nel_nome(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {PAROLA.upper() + ".txt": b"ciao"})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "parola vietata n.1" in out
    assert PAROLA not in out.lower()


def test_cli_senza_elenco(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": b"ciao"})
    monkeypatch.delenv("PAROLE_VIETATE", raising=False)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 0
    assert "nessuna parola vietata" in capsys.readouterr().out


def test_aiuto_del_sottocomando_ha_un_solo_uso(capsys):
    with pytest.raises(SystemExit) as e:
        main(["controlla-pubblico", "--help"])
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("uso: bottega controlla-pubblico ")


def test_cli_radice_che_non_e_un_repo(tmp_path, capsys):
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("errore:") and str(tmp_path) not in err


def test_comando_vero_da_terminale(tmp_path):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode()})
    ambiente = {**os.environ, "PYTHONPATH": str(ATTREZZI)}
    comando = [sys.executable, "-m", "bottega", "controlla-pubblico", "--radice", str(tmp_path)]
    ambiente.pop("PAROLE_VIETATE", None)
    senza_elenco = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
    assert senza_elenco.returncode == 0 and "nessuna parola vietata" in senza_elenco.stdout
    ambiente["PAROLE_VIETATE"] = PAROLA
    con_elenco = subprocess.run(comando, env=ambiente, capture_output=True, text=True)
    assert con_elenco.returncode == 1 and "a.txt:1: parola vietata n.1" in con_elenco.stdout
    assert PAROLA not in con_elenco.stdout
