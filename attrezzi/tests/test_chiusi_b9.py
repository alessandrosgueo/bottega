"""Prove per il compito B9.3: un lavoro chiuso non è mai pronto."""

import json
from typing import Any

from bottega.board import (
    _QUERY_PROJECT_ORG,
    _QUERY_PROJECT_USER,
    BoardComando,
    BoardProject,
    _dati_a_lavoro,
)


def _crea_node(
    numero: int,
    titolo: str,
    *,
    stato: str = "",
    esito: str | None = None,
    esecutore: str | None = None,
    nota: str = "",
    state: str | None = None,
    metti_state: bool = True,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "number": numero,
        "title": titolo,
        "repository": {"nameWithOwner": "proprietario/repo"},
        "labels": {"nodes": []},
    }
    if metti_state and state is not None:
        content["state"] = state
    field_values: list[dict[str, Any]] = []
    if stato:
        field_values.append({"field": {"name": "Bottega"}, "name": stato})
    if esito is not None:
        field_values.append({"field": {"name": "Esito"}, "name": esito})
    if esecutore is not None:
        field_values.append({"field": {"name": "Esecutore"}, "text": esecutore})
    if nota:
        field_values.append({"field": {"name": "Nota del giro"}, "text": nota})
    return {
        "id": f"ITEM_{numero}",
        "content": content,
        "fieldValues": {"nodes": field_values},
    }


def _risposta_graphql(items_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
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
                                    {"id": "OPT_CONSEGNATO", "name": "consegnato"},
                                ],
                            },
                            {
                                "id": "F_ESITO",
                                "name": "Esito",
                                "dataType": "SINGLE_SELECT",
                                "options": [
                                    {"id": "OPT_CORREZIONI", "name": "correzioni"},
                                ],
                            },
                            {
                                "id": "F_ESECUTORE",
                                "name": "Esecutore",
                                "dataType": "TEXT",
                            },
                            {
                                "id": "F_NOTA",
                                "name": "Nota del giro",
                                "dataType": "TEXT",
                            },
                        ]
                    },
                    "items": {"nodes": items_nodes},
                }
            }
        }
    }


def test_query_contengono_state() -> None:
    """1. Le due query contengono state sia per Issue sia per PullRequest."""
    for q in (_QUERY_PROJECT_USER, _QUERY_PROJECT_ORG):
        issue_part = q.split("... on Issue")[1].split("... on PullRequest")[0]
        pr_part = q.split("... on PullRequest")[1].split("fieldValues")[0]
        assert "state" in issue_part.split()
        assert "state" in pr_part.split()


def test_elemento_closed_pronto_non_e_fra_i_pronti() -> None:
    """2. Un elemento CLOSED con Bottega = pronto non è fra i pronti(); uno OPEN uguale sì."""
    n_chiuso = _crea_node(101, "Chiuso pronto", stato="pronto", state="CLOSED")
    n_aperto = _crea_node(102, "Aperto pronto", stato="pronto", state="OPEN")
    risposta = _risposta_graphql([n_chiuso, n_aperto])

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    pronti = board.pronti()
    numeri = [l.numero for l in pronti]
    assert 101 not in numeri
    assert 102 in numeri


def test_elemento_closed_con_correzioni_non_e_fra_i_pronti() -> None:
    """3. Un elemento CLOSED con Esito = correzioni e Bottega = consegnato non è fra i pronti(); OPEN sì."""
    n_chiuso = _crea_node(
        201, "Chiuso correzioni", stato="consegnato", esito="correzioni", state="CLOSED"
    )
    n_aperto = _crea_node(
        202, "Aperto correzioni", stato="consegnato", esito="correzioni", state="OPEN"
    )
    risposta = _risposta_graphql([n_chiuso, n_aperto])

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    pronti = board.pronti()
    numeri = [l.numero for l in pronti]
    assert 201 not in numeri
    assert 202 in numeri


def test_pr_merged_pronto_non_e_fra_i_pronti() -> None:
    """4. Una PR MERGED con Bottega = pronto non è fra i pronti()."""
    n_merged = _crea_node(301, "PR fusa", stato="pronto", state="MERGED")
    risposta = _risposta_graphql([n_merged])

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    pronti = board.pronti()
    numeri = [l.numero for l in pronti]
    assert 301 not in numeri


def test_prendi_su_chiuso_restituisce_false_senza_mutazioni() -> None:
    """5. prendi() su un elemento CLOSED pronto restituisce False e non scrive nessun campo."""
    n_chiuso = _crea_node(401, "Chiuso pronto", stato="pronto", state="CLOSED")
    risposta = _risposta_graphql([n_chiuso])
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    preso = board.prendi(401, "esecutore-test", "nota-test")
    assert preso is False

    mutazioni = [
        c
        for c in chiamate
        if any(
            "updateProjectV2ItemFieldValue" in a or "clearProjectV2ItemFieldValue" in a
            for a in c
        )
    ]
    assert len(mutazioni) == 0


def test_elenco_e_lavoro_danno_chiuso_con_aperta_false() -> None:
    """6. elenco() e lavoro(n) danno anche il chiuso, con aperta falso."""
    n_chiuso = _crea_node(501, "Chiuso", stato="consegnato", state="CLOSED")
    risposta = _risposta_graphql([n_chiuso])

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    elenco = board.elenco()
    lav_elenco = next((l for l in elenco if l.numero == 501), None)
    assert lav_elenco is not None
    assert lav_elenco.aperta is False

    lav = board.lavoro(501)
    assert lav is not None
    assert lav.numero == 501
    assert lav.aperta is False


def test_senza_state_lavoro_conta_aperto() -> None:
    """7. Senza state nella risposta (una board vecchia) il lavoro conta aperto."""
    n_vecchio = _crea_node(
        601, "Vecchio senza state", stato="pronto", metti_state=False
    )
    risposta = _risposta_graphql([n_vecchio])

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps(risposta)

    board = BoardProject("proprietario", 1, esegui=esegui_finto)
    lav = board.lavoro(601)
    assert lav is not None
    assert lav.aperta is True

    pronti = board.pronti()
    numeri = [l.numero for l in pronti]
    assert 601 in numeri


def test_board_comando_pronti_scarta_aperta_falso() -> None:
    """8. BoardComando.pronti() con un JSON che ha un lavoro con aperta: false e uno senza la chiave: solo il secondo."""
    lavori_json = [
        {"numero": 1, "titolo": "Lavoro chiuso", "stato": "pronto", "aperta": False},
        {"numero": 2, "titolo": "Lavoro aperto senza chiave", "stato": "pronto"},
    ]

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        assert argomenti[-1] == "pronti"
        return json.dumps(lavori_json)

    board = BoardComando(["adattatore"], esegui=esegui_finto)
    pronti = board.pronti()
    numeri = [l.numero for l in pronti]
    assert numeri == [2]

    # Verifica anche _dati_a_lavoro direttamente su casi limite
    assert (
        _dati_a_lavoro({"numero": 10, "titolo": "t", "aperta": False}).aperta is False
    )
    assert _dati_a_lavoro({"numero": 20, "titolo": "t", "aperta": True}).aperta is True
    assert _dati_a_lavoro({"numero": 30, "titolo": "t"}).aperta is True
    assert (
        _dati_a_lavoro({"numero": 40, "titolo": "t", "aperta": "qualsiasi"}).aperta
        is True
    )
    assert _dati_a_lavoro({"numero": 50, "titolo": "t", "aperta": None}).aperta is True
    assert _dati_a_lavoro({"numero": 60, "titolo": "t", "aperta": 0}).aperta is True
