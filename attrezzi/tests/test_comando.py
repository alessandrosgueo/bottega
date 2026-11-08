import pytest

from bottega.__main__ import main


def test_versione(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == "bottega 0.1.0"


def test_senza_comando_esce_2(capsys):
    assert main([]) == 2
    assert "uso:" in capsys.readouterr().err
