import pytest

from bottega.__main__ import ARGOMENTI, COMANDI, _Parser, main


def test_versione(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == "bottega 0.1.0"


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
