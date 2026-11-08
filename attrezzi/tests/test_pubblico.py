import codecs
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
# Intestazione di un PNG vero: il byte nullo la rende binaria.
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


@pytest.fixture(autouse=True)
def senza_github_actions(monkeypatch):
    # Su GitHub Actions la variabile è sempre impostata: le prove che la vogliono la impostano da sé.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


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


@pytest.mark.parametrize("testo", [
    "/ho" + "me/pippo/x",
    "/mnt/c/" + "Users/pippo/x",
    "C:/" + "Users/pippo/x",
    "C:" + "\\Users\\pippo\\x",
    "c:" + "\\users\\pippo\\x",
    "file:///C:/" + "Users/pippo/x",
    "\\\\" + "wsl.localhost\\Ubuntu\\home\\pippo\\x",
    "\\\\" + "wsl$\\Ubuntu\\home\\pippo",
    "/" + "Users/pippo/x",
])
def test_percorso_di_casa_si_trova(testo):
    assert [x.motivo for x in cerca(testo, "a.md", [])] == ["percorso di casa"]


@pytest.mark.parametrize("testo", [
    "/home/<utente>/x", "/home/utente/x", "/home/nome/x", "/Users/<utente>/x", "C:/Users/nome/x",
    "C:\\Users\\<utente>\\x", "C:\\Users\\nome\\x", "\\\\wsl.localhost\\<distro>\\home\\<nome>",
    "https://api.github.com/users/octocat",
])
def test_percorso_segnaposto_o_non_di_casa_ammesso(testo):
    assert cerca(testo, "a.md", []) == []


@pytest.mark.parametrize("testo,motivo", [
    ("scrivi a a" + "@b.it", "indirizzo email"),
    ("x@" + "example.com.evil.it", "indirizzo email"),
    ("noreply.mario" + "@ditta.it", "indirizzo email"),
    ("192." + "168.1.42", "indirizzo IP privato"),
    ("172." + "16.0.1", "indirizzo IP privato"),
    ("172." + "31.255.1", "indirizzo IP privato"),
    ("10." + "0.0.1", "indirizzo IP privato"),
    ("100." + "64.0.1", "indirizzo IP privato"),
    ("100." + "127.255.1", "indirizzo IP privato"),
    ("169." + "254.0.1", "indirizzo IP privato"),
    (":".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
    ("-".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
    ("MAC:" + ":".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "indirizzo MAC"),
    (":".join(["aa", "bb", "cc", "dd", "ee", "ff"]) + "-01", "indirizzo MAC"),
])
def test_regole_fisse(testo, motivo):
    assert [x.motivo for x in cerca(testo, "a.md", [])] == [motivo]


@pytest.mark.parametrize("gruppi", [7, 8])
def test_sequenza_piu_lunga_di_sei_gruppi_non_e_un_mac(gruppi):
    coppie = ["aa", "bb", "cc", "dd", "ee", "ff", "00", "11"][:gruppi]
    assert cerca(":".join(coppie), "a.md", []) == []


@pytest.mark.parametrize("testo", [
    "02:00:00:00:00:01", "192.0.2.1", "172.32.0.1", "172.15.0.1", "100.128.0.1",
    "noreply@example.com", "noreply@github.com", "x@example.org", "noreply@" + "ditta.it",
])
def test_segnaposto_e_indirizzi_pubblici_ammessi(testo):
    assert cerca(testo, "a.md", []) == []


def test_vietate_da_ambiente():
    assert vietate_da_ambiente(" a, b\nc ,,") == ["a", "b", "c"]
    assert vietate_da_ambiente("a b, c") == ["a", "b", "c"]
    assert vietate_da_ambiente(None) == []


def test_controlla_legge_solo_i_file_tracciati(tmp_path):
    _repo(tmp_path, {"tracciato.txt": ("ciao " + PAROLA).encode()})
    (tmp_path / "non_tracciato.txt").write_text(PAROLA, encoding="utf-8")
    assert [t.percorso for t in controlla(tmp_path, [PAROLA])] == ["tracciato.txt"]


def test_file_binario_non_fa_cadere_il_controllo(tmp_path):
    _repo(tmp_path, {"binario.png": PNG, "testo.txt": ("ciao " + PAROLA).encode()})
    assert controlla(tmp_path, [PAROLA]) == [Trovata("testo.txt", 1, "parola vietata n.1")]


def test_utf16_con_bom_si_legge_con_la_sua_codifica(tmp_path):
    _repo(tmp_path, {"u.txt": codecs.BOM_UTF16_LE + ("/ho" + "me/pippo/x").encode("utf-16-le")})
    assert controlla(tmp_path, []) == [Trovata("u.txt", 1, "percorso di casa")]


def test_latin1_si_legge_e_il_suo_ip_si_trova(tmp_path):
    _repo(tmp_path, {"l.txt": ("caffè " + "192." + "168.1.42").encode("latin-1")})
    assert controlla(tmp_path, []) == [Trovata("l.txt", 1, "indirizzo IP privato")]


def test_byte_nullo_oltre_gli_ottomila_non_rende_binario(tmp_path):
    _repo(tmp_path, {"lungo.txt": b"a" * 8000 + b"\0 ciao " + PAROLA.encode()})
    assert controlla(tmp_path, [PAROLA]) == [Trovata("lungo.txt", 1, "parola vietata n.1")]


def test_tracciato_ma_assente_dal_disco_non_fa_cadere_il_controllo(tmp_path):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode()})
    (tmp_path / "a.txt").unlink()
    assert controlla(tmp_path, [PAROLA]) == []


def test_il_nome_del_file_conta(tmp_path):
    _repo(tmp_path, {PAROLA.upper() + ".txt": b"ciao"})
    assert controlla(tmp_path, [PAROLA]) == [Trovata(PAROLA.upper() + ".txt", 0, "parola vietata n.1")]


def test_il_bersaglio_di_un_link_viene_letto(tmp_path):
    _repo(tmp_path, {}, {"collegamento": PAROLA})
    assert controlla(tmp_path, [PAROLA]) == [Trovata("collegamento", 1, "parola vietata n.1")]


def test_cli_trova_ed_esce_1(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode(), "binario.png": PNG})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.txt:1: parola vietata n.1" in out
    assert "file non controllati: 1" in out
    assert PAROLA not in out


def test_cli_binario_saltato_esce_0_senza_nomi(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"immagine.png": PNG, "a.txt": b"ciao"})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "file non controllati: 1" in out and "immagine" not in out


def test_cli_maschera_la_parola_nel_nome(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {PAROLA.upper() + ".txt": b"ciao"})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "parola vietata n.1" in out
    assert PAROLA not in out.lower()


def test_cli_maschera_il_dato_delle_regole_fisse_nel_nome(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"ip-" + "192." + "168.1.42.txt": b"ciao"})
    monkeypatch.setenv("PAROLE_VIETATE", "")
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    assert "ip-" + "*" * 12 + ".txt:0: indirizzo IP privato" in capsys.readouterr().out


def test_cli_senza_elenco(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": b"ciao"})
    monkeypatch.delenv("PAROLE_VIETATE", raising=False)
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 0
    assert "nessuna parola vietata" in capsys.readouterr().out


def test_elenco_vuoto_controlla_le_regole_fisse(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ip " + "192." + "168.1.42").encode()})
    monkeypatch.setenv("PAROLE_VIETATE", "")
    assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.txt:1: indirizzo IP privato" in out and "nessuna parola vietata" in out


def test_richiedi_elenco_con_elenco_vuoto_esce_2(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": b"ciao"})
    monkeypatch.setenv("PAROLE_VIETATE", "")
    assert main(["controlla-pubblico", "--radice", str(tmp_path), "--richiedi-elenco"]) == 2
    assert capsys.readouterr().err.startswith("errore:")


def test_richiedi_elenco_con_elenco_pieno_come_senza(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode()})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    esiti = []
    for opzioni in ([], ["--richiedi-elenco"]):
        esito = main(["controlla-pubblico", "--radice", str(tmp_path), *opzioni])
        esiti.append((esito, capsys.readouterr().out))
    assert esiti[0] == esiti[1] and esiti[0][0] == 1


def test_file_illeggibile_esce_2_col_nome_mascherato(tmp_path, monkeypatch, capsys):
    if os.geteuid() == 0:
        pytest.skip("come root i permessi non fermano la lettura")
    nome = PAROLA.upper() + ".txt"
    _repo(tmp_path, {nome: b"ciao"})
    (tmp_path / nome).chmod(0)
    try:
        monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
        assert main(["controlla-pubblico", "--radice", str(tmp_path)]) == 2
    finally:
        (tmp_path / nome).chmod(0o644)
    err = capsys.readouterr().err
    assert err.startswith("errore:") and PAROLA not in err.lower() and "*" in err


def test_github_actions_mette_le_maschere_per_prima_cosa(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode()})
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA + ", altra")
    main(["controlla-pubblico", "--radice", str(tmp_path)])
    righe = capsys.readouterr().out.splitlines()
    assert righe[:2] == ["::add-mask::" + PAROLA, "::add-mask::altra"]
    assert "a.txt:1: parola vietata n.1" in righe


def test_github_actions_escapa_il_per_cento_della_maschera(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": b"ciao"})
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PAROLE_VIETATE", "a%b")
    main(["controlla-pubblico", "--radice", str(tmp_path)])
    assert capsys.readouterr().out.splitlines()[0] == "::add-mask::a%25b"


def test_fuori_da_github_actions_niente_maschere(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a.txt": ("ciao " + PAROLA).encode()})
    monkeypatch.setenv("PAROLE_VIETATE", PAROLA)
    main(["controlla-pubblico", "--radice", str(tmp_path)])
    assert "::add-mask::" not in capsys.readouterr().out


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
