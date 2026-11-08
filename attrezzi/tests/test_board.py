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
                        {
                            "id": "F_BOTTEGA",
                            "name": "Bottega",
                            "dataType": "SINGLE_SELECT",
                            "options": [
                                {"id": "OPT_PRONTO", "name": "pronto"},
                                {"id": "OPT_IN_CORSO", "name": "in corso"},
                                {"id": "OPT_IN_ATTESA", "name": "in attesa"},
                                {"id": "OPT_CONSEGNATO", "name": "consegnato"},
                                {"id": "OPT_BLOCCATO", "name": "bloccato"},
                            ],
                        },
                        {
                            "id": "F_ESITO",
                            "name": "Esito",
                            "dataType": "SINGLE_SELECT",
                            "options": [
                                {"id": "OPT_CORREZIONI", "name": "correzioni"},
                                {"id": "OPT_UNIONE", "name": "pronta per l'unione"},
                                {"id": "OPT_RIFIUTATA", "name": "rifiutata"},
                            ],
                        },
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
    # Controlla che siano state fatte le chiamate GraphQL per Bottega, Esito, Esecutore, Nota del giro
    modifiche = [c for c in chiamate if any("updateProjectV2ItemFieldValue" in a or "clearProjectV2ItemFieldValue" in a for a in c)]
    assert len(modifiche) == 4

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
    modifiche = [c for c in chiamate if any("updateProjectV2ItemFieldValue" in a for a in c)]
    assert len(modifiche) == 2
    assert "value[singleSelectOptionId]=OPT_IN_ATTESA" in modifiche[0]
    assert "value[text]=motivo=quota" in modifiche[1]

    chiamate.clear()
    board.consegna(10, pr=42)
    mod_consegna = [c for c in chiamate if any("updateProjectV2ItemFieldValue" in a for a in c)]
    assert len(mod_consegna) == 1
    assert "value[singleSelectOptionId]=OPT_CONSEGNATO" in mod_consegna[0]

    chiamate.clear()
    board.campo(10, "Nota del giro", "inizio=2")
    mod_campo = [c for c in chiamate if any("updateProjectV2ItemFieldValue" in a for a in c)]
    assert len(mod_campo) == 1
    assert "value[text]=inizio=2" in mod_campo[0]


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


def test_board_in_corso() -> None:
    # 1. BoardProject
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(_PROGETTO_GRAPHQL_OK)

    board_proj = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_finto)
    in_corso_proj = board_proj.in_corso()
    assert len(in_corso_proj) == 1
    assert in_corso_proj[0].numero == 30

    # 2. BoardFinta
    finta = BoardFinta(
        [
            Lavoro(numero=1, titolo="Compito 1", stato="pronto", repo="proprietario/repo"),
            Lavoro(numero=2, titolo="Compito 2", stato="in corso", repo="proprietario/repo"),
        ],
        repo="proprietario/repo",
    )
    in_corso_finta = finta.in_corso()
    assert len(in_corso_finta) == 1
    assert in_corso_finta[0].numero == 2


# Prove per RV11: fedeltà a gh 2.100.0, GraphQL, paginazione, aggiungi e tolleranza


_PROGETTO_CON_OPZIONI = {
    "data": {
        "user": {
            "projectV2": {
                "id": "PVT_1",
                "title": "Bottega Project",
                "fields": {
                    "nodes": [
                        {
                            "id": "F_BOTTEGA",
                            "name": "Bottega",
                            "dataType": "SINGLE_SELECT",
                            "options": [
                                {"id": "OPT_PRONTO", "name": "pronto"},
                                {"id": "OPT_IN_CORSO", "name": "in corso"},
                                {"id": "OPT_IN_ATTESA", "name": "in attesa"},
                                {"id": "OPT_CONSEGNATO", "name": "consegnato"},
                                {"id": "OPT_BLOCCATO", "name": "bloccato"},
                            ],
                        },
                        {
                            "id": "F_ESITO",
                            "name": "Esito",
                            "dataType": "SINGLE_SELECT",
                            "options": [
                                {"id": "OPT_CORREZIONI", "name": "correzioni"},
                                {"id": "OPT_UNIONE", "name": "pronta per l'unione"},
                            ],
                        },
                        {"id": "F_ESECUTORE", "name": "Esecutore", "dataType": "TEXT"},
                        {"id": "F_NOTA", "name": "Nota del giro", "dataType": "TEXT"},
                    ]
                },
                "items": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
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
                    ],
                },
            }
        }
    }
}


def test_rv11_rifiuta_item_edit_e_usa_graphql_mutations() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        # Imitazione di gh 2.100.0: item-edit con --id e --field fallisce
        if argomenti[:2] == ["project", "item-edit"]:
            if "--id" in argomenti and "--field" in argomenti:
                raise ErroreBoard("gh: item-edit cannot accept both --id and --field")
        if "api" in argomenti and "graphql" in argomenti:
            return json.dumps(_PROGETTO_CON_OPZIONI)
        return ""

    board = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_finto)
    # Scrittura campo select: deve usare updateProjectV2ItemFieldValue con singleSelectOptionId
    board.campo(10, "Bottega", "in corso")
    # Scrittura campo testo: deve usare updateProjectV2ItemFieldValue con text
    board.campo(10, "Nota del giro", "inizio=2")

    mutazioni = [c for c in chiamate if "api" in c and any("updateProjectV2ItemFieldValue" in arg for arg in c)]
    assert len(mutazioni) == 2

    # Verifica prima mutazione (Bottega -> in corso)
    m1 = mutazioni[0]
    assert "-F" not in m1  # i valori passano col -f: testo tale e quale, mai un file con @
    assert "projectId=PVT_1" in m1
    assert "itemId=ITEM_1" in m1
    assert "fieldId=F_BOTTEGA" in m1
    assert "value[singleSelectOptionId]=OPT_IN_CORSO" in m1

    # Verifica seconda mutazione (Nota del giro -> inizio=2)
    m2 = mutazioni[1]
    assert "fieldId=F_NOTA" in m2
    assert "value[text]=inizio=2" in m2


def test_rv11_prendi_svuota_esito() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if "api" in argomenti and "graphql" in argomenti:
            return json.dumps(_PROGETTO_CON_OPZIONI)
        return ""

    board = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_finto)
    # Prende il lavoro 20 (che aveva Esito=correzioni)
    ok = board.prendi(20, "esecutore_test", "nota=1")
    assert ok is True

    # Deve aver chiamato clearProjectV2ItemFieldValue su Esito
    svuotamenti = [c for c in chiamate if any("clearProjectV2ItemFieldValue" in arg for arg in c)]
    assert len(svuotamenti) == 1
    s1 = svuotamenti[0]
    assert "projectId=PVT_1" in s1
    assert "itemId=ITEM_2" in s1
    assert "fieldId=F_ESITO" in s1


def test_rv11_paginazione_cursori() -> None:
    p1 = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "fields": _PROGETTO_CON_OPZIONI["data"]["user"]["projectV2"]["fields"],
                    "items": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "CURSORE_P1"},
                        "nodes": [_PROGETTO_CON_OPZIONI["data"]["user"]["projectV2"]["items"]["nodes"][0]],
                    },
                }
            }
        }
    }
    p2 = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "fields": _PROGETTO_CON_OPZIONI["data"]["user"]["projectV2"]["fields"],
                    "items": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [_PROGETTO_CON_OPZIONI["data"]["user"]["projectV2"]["items"]["nodes"][1]],
                    },
                }
            }
        }
    }

    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if "cursor=CURSORE_P1" in argomenti:
            return json.dumps(p2)
        return json.dumps(p1)

    board = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_finto)
    pronti = board.pronti()

    # Ha recuperato entrambi i lavori (10 da pagina 1, 20 da pagina 2)
    numeri = [l.numero for l in pronti]
    assert 10 in numeri
    assert 20 in numeri
    assert len(chiamate) == 2
    assert "cursor=CURSORE_P1" in chiamate[1]


def test_rv11_fallback_organization() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        # Se query per user, risponde vuoto/non trovato
        q = next(a for a in argomenti if a.startswith("query="))
        if "user(login:" in q:
            return json.dumps({"data": {"user": None}})
        if "organization(login:" in q:
            # Organizzazione ha il project
            d = dict(_PROGETTO_CON_OPZIONI)
            return json.dumps({
                "data": {
                    "organization": d["data"]["user"]
                }
            })
        return "{}"

    board = BoardProject("mia-org", 1, repo="proprietario/repo", esegui=esegui_finto)
    pronti = board.pronti()
    assert len(pronti) >= 1
    # Ha provato prima user, poi organization
    assert any("user(login:" in next(a for a in c if a.startswith("query=")) for c in chiamate)
    assert any("organization(login:" in next(a for a in c if a.startswith("query=")) for c in chiamate)


def test_rv11_aggiungi_project_comando_e_finta() -> None:
    # 1. BoardProject
    chiamate_proj: list[list[str]] = []

    def esegui_proj(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate_proj.append(argomenti)
        return ""

    bp = BoardProject("proprietario", 1, repo="proprietario/repo", esegui=esegui_proj)
    bp.aggiungi(42)
    assert len(chiamate_proj) == 1
    assert chiamate_proj[0] == [
        "project", "item-add", "1",
        "--owner", "proprietario",
        "--url", "https://github.com/proprietario/repo/issues/42",
    ]

    # 2. BoardComando
    chiamate_cmd: list[list[str]] = []

    def esegui_cmd(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate_cmd.append(argomenti)
        return ""

    bc = BoardComando(["adattatore"], esegui=esegui_cmd)
    bc.aggiungi(42)
    assert len(chiamate_cmd) == 1
    assert chiamate_cmd[0] == ["adattatore", "bottega", "aggiungi", "42"]

    # 3. BoardFinta
    bf = BoardFinta(repo="proprietario/repo")
    bf.aggiungi(42)
    assert ("aggiungi", 42) in bf.registro
    assert bf.lavoro(42) is not None
    assert bf.lavoro(42).numero == 42


def test_rv11_board_comando_ignora_campi_in_piu() -> None:
    def esegui_cmd(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps([
            {
                "numero": 100,
                "titolo": "Compito",
                "etichette": ["bottega: fuori"],
                "stato": "pronto",
                "esito": None,
                "esecutore": None,
                "nota": "",
                "repo": "proprietario/repo",
                "scadenza": "2026-11-30",
                "priorita": "alta",
                "metadati_extra": {"autore": "qualcuno"},
            }
        ])

    bc = BoardComando(["adattatore"], esegui=esegui_cmd)
    pronti = bc.pronti()
    assert len(pronti) == 1
    assert pronti[0].numero == 100
    assert pronti[0].titolo == "Compito"


def test_rv11_board_finta_prendi_svuota_esito() -> None:
    bf = BoardFinta(
        [
            Lavoro(
                numero=1,
                titolo="Compito",
                stato="consegnato",
                esito="correzioni",
                repo="proprietario/repo",
            )
        ],
        repo="proprietario/repo",
    )
    assert bf.prendi(1, "antigravity", "nota=1") is True
    lav = bf.lavoro(1)
    assert lav is not None
    assert lav.stato == "in corso"
    assert lav.esito is None

