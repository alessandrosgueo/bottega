from pathlib import Path

import pytest

from bottega.__main__ import ARGOMENTI, COMANDI, _Parser, main


def test_versione(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == "bottega 0.2.1"


def test_senza_comando_esce_2(capsys):
    assert main([]) == 2
    assert "uso:" in capsys.readouterr().err


def test_argomenti_solo_di_comandi_esistenti():
    assert set(ARGOMENTI) <= set(COMANDI)


def test_argomento_posizionale_resta_fuori_dal_gruppo_opzioni():
    parser = _Parser(prog="bottega")
    parser.add_argument("nome")
    parser.add_argument("--volume")
    assert [a.dest for a in parser.opzioni._group_actions] == ["help", "volume"]


def test_c4_errore_di_configurazione_senza_traccia(tmp_path: Path, capsys: pytest.CaptureFixture):
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[non valido toml", encoding="utf-8")
    rc = main(["giro", "--lavoro", "1", "--bottega", "x", "--configurazione", str(bad_toml)])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("errore:")
    assert "Traceback" not in err

