"""Prove per la board: BoardProject, BoardComando (contro script finto) e BoardFinta."""

import json
import stat
from pathlib import Path
import pytest

from bottega.board import BoardComando, BoardProject, ErroreBoard, Lavoro
from bottega.finta import BoardFinta


_PROGETTO_GRAPHQL_OK = {
    "data": {
        "user": {
            "projectV2": {
                "id": "PVT_1",
                "title": "Bottega Project",
                "fields": {
                    "nodes": [
                        {"id": "F_BOTTEGA", "name": "Bottega", "dataType": "SINGLE_SELECT"},
                        {"id": "F_ESITO", "name": "Esito", "dataType": "SINGLE_SELECT"},
                        {"id": "F_ESECUTORE", "name": "Esecutore", "dataType": "TEXT"},
                        {"id": "F_NOTA", "name": "Nota del giro", "dataType": "TEXT"},
                    ]
                },
                "items": {
                    "nodes": [
                        {
                            "id": "ITEM_1",
                            "content": {
                                "number": 10,
                                "title": "Compito normale",
                                "repository": {"nameWithOwner": "proprietario/repo"},
                                "labels": {"nodes": [{"name": "bottega: fuori"}]},
                            },
                            "fieldValues": {
                                "nodes": [
                                    {"field": {"name": "Bottega"}, "name": "pronto"},
                                    {"field": {"name": "Nota del giro"}, "text": "inizio=1"},
                                ]
                            },
                        },
                        {
                            "id": "ITEM_2",
                            "content": {
                                "number": 20,
                                "title": "Compito con correzioni",
                                "repository": {"nameWithOwner": "proprietario/repo"},
                                "labels": {"nodes": []},
                            },
                            "fieldValues": {
                                "nodes": [
                                    {"field": {"name": "Bottega"}, "name": "consegnato"},
                                    {"field": {"name": "Esito"}, "name": "correzioni"},
                                ]
                            },
                        },
                        {
                            "id": "ITEM_3",
                            "content": {
                                "number": 30,
                                "title": "Compito già in corso",
                                "repository": {"nameWithOwner": "proprietario/repo"},
                                "labels": {"nodes": []},
                            },
                            "fieldValues": {
                                "nodes": [
                                    {"field": {"name": "Bottega"}, "name": "in corso"},
                                    {"field": {"name": "Esito"}, "name": "correzioni"},
                                ]
                            },
                        },
                        {
                            "id": "ITEM_ALTRO_REPO",
                            "content": {
                                "number": 10,
                                "title": "Compito di altro repo",
                                "repository": {"nameWithOwner": "proprietario/altro-repo"},
                                "labels": {"nodes": [{"name": "bottega: fuori"}]},
                            },
                            "fieldValues": {
                                "nodes": [
                                    {"field": {"name": "Bottega"}, "name": "pronto"},
                                ]
                            },
                        },
                    ]
                },
            }
        }
    }
}


def test_board_project_campo_mancante_solleva_errore() -> None:
    graphql_mancante = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "fields": {
                        "nodes": [
                            {"name": "Bottega"},
                            {"name": "Esito"},
                            # Manca Esecutore e Nota del giro
                        ]
                    },
                    "items": {"nodes": []},
                }
            }
        }
    }

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(graphql_mancante)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    with pytest.raises(ErroreBoard, match="Esecutore"):
        board.pronti()


def test_board_project_pronti_include_correzioni_ed_esclude_in_corso() -> None:
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(_PROGETTO_GRAPHQL_OK)

    board = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_finto)
    pronti = board.pronti()

    numeri = [l.numero for l in pronti]
    assert 10 in numeri  # Bottega == pronto del repo specificato
    assert 20 in numeri  # Esito == correzioni
    assert 30 not in numeri  # Bottega == in corso (anche se Esito == correzioni)

    l10 = next(l for l in pronti if l.numero == 10)
    assert l10.titolo == "Compito normale"
    assert l10.stato == "pronto"
    assert l10.etichette == ["bottega: fuori"]
    assert l10.nota == "inizio=1"
    # L'issue 10 di altro-repo non deve essere stata inserita
    assert len([l for l in pronti if l.numero == 10]) == 1


def test_board_project_prendi_e_concorrenza() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if "api" in argomenti:
            return json.dumps(_PROGETTO_GRAPHQL_OK)
        return ""

    board = BoardProject("proprietario", 1, esegui=esegui_finto)

    # Prendi lavoro pronto (10)
    ok = board.prendi(10, "claude", "attese=0")
    assert ok is True
    # Controlla che siano state fatte le chiamate item-edit per Bottega, Esecutore, Nota del giro
    modifiche = [c for c in chiamate if "item-edit" in c]
    assert len(modifiche) == 3

    # Prendi lavoro già in corso (30) -> deve fallire (False)
    ok_occupato = board.prendi(30, "claude", "attese=0")
    assert ok_occupato is False


def test_board_project_stato_consegna_e_campo() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if "api" in argomenti:
            return json.dumps(_PROGETTO_GRAPHQL_OK)
        return ""

    board = BoardProject("proprietario", 1, esegui=esegui_finto)

    board.stato(10, "in attesa", nota="motivo=quota")
    modifiche = [c for c in chiamate if "item-edit" in c]
    assert len(modifiche) == 2
    assert "--value" in modifiche[0]
    assert "in attesa" in modifiche[0]
    assert "--text" in modifiche[1]
    assert "motivo=quota" in modifiche[1]

    chiamate.clear()
    board.consegna(10, pr=42)
    mod_consegna = [c for c in chiamate if "item-edit" in c]
    assert len(mod_consegna) == 1
    assert "consegnato" in mod_consegna[0]

    chiamate.clear()
    board.campo(10, "Nota del giro", "inizio=2")
    mod_campo = [c for c in chiamate if "item-edit" in c]
    assert len(mod_campo) == 1
    assert "inizio=2" in mod_campo[0]


def test_board_comando_con_script_finto(tmp_path: Path) -> None:
    # Crea uno script Python finto che fa da adattatore
    script = tmp_path / "finto_adattatore.py"
    script.write_text(
        """#!/usr/bin/env python3
import sys
import json

args = sys.argv[1:]
if not args or args[0] != "bottega":
    sys.exit(2)

cmd = args[1]
if cmd == "pronti":
    print(json.dumps([
        {
            "numero": 100,
            "titolo": "Lavoro Adattatore",
            "etichette": ["bottega: fuori"],
            "stato": "pronto",
            "esito": None,
            "esecutore": None,
            "nota": "",
        }
    ]))
    sys.exit(0)
elif cmd == "prendi":
    n = int(args[2])
    # 100 si prende, 101 è già preso
    if n == 100:
        sys.exit(0)
    else:
        sys.exit(1)
elif cmd in ("stato", "consegna", "campo"):
    sys.exit(0)
else:
    sys.exit(2)
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    board = BoardComando([str(script)])

    pronti = board.pronti()
    assert len(pronti) == 1
    assert pronti[0].numero == 100
    assert pronti[0].titolo == "Lavoro Adattatore"

    assert board.prendi(100, "antigravity", "nota=1") is True
    assert board.prendi(101, "antigravity", "nota=1") is False

    board.stato(100, "in attesa", nota="stop")
    board.consegna(100, pr=77)
    board.campo(100, "Nota del giro", "nuova")


def test_board_finta_in_memoria() -> None:
    finta = BoardFinta(
        [
            Lavoro(numero=1, titolo="Compito 1", stato="pronto", repo="proprietario/repo"),
            Lavoro(numero=2, titolo="Compito 2", stato="consegnato", esito="correzioni", repo="proprietario/repo"),
            Lavoro(numero=3, titolo="Compito 3", stato="in corso", esito="correzioni", repo="proprietario/repo"),
            Lavoro(numero=1, titolo="Compito 1 altro repo", stato="pronto", repo="proprietario/altro-repo"),
        ],
        repo="proprietario/repo",
    )

    pronti = finta.pronti()
    numeri = [l.numero for l in pronti]
    assert numeri == [1, 2]
    # Issue 1 di altro repo è stata ignorata
    assert len(pronti) == 2

    # Prendi lavoro pronto
    assert finta.prendi(1, "claude", "inizio=1") is True
    # Riprova: non è più pronto
    assert finta.prendi(1, "claude", "inizio=2") is False

    finta.stato(1, "bloccato", nota="errore")
    finta.consegna(2, pr=99)
    finta.campo(2, "Esecutore", "nuovo")

    azioni = [r[0] for r in finta.registro]
    assert azioni == ["prendi", "stato", "consegna", "campo"]
