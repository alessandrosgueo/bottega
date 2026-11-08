"""La board: interfaccia e adattatori per GitHub Projects (BoardProject e BoardComando)."""

import json
import math
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, Protocol


@dataclass(frozen=True)
class Lavoro:
    """Un elemento della board."""

    numero: int
    titolo: str
    etichette: list[str] = field(default_factory=list)
    stato: str = ""
    esito: str | None = None
    esecutore: str | None = None
    nota: str = ""
    repo: str | None = None
    campi: dict[str, str] = field(default_factory=dict)


class ErroreBoard(Exception):
    """Errore della board o campo mancante nel Project."""


class Board(Protocol):
    """Interfaccia verso la board del progetto (le cinque operazioni di B3-R7 più aggiungi di RV11)."""

    def pronti(self) -> list[Lavoro]: ...

    def in_corso(self) -> list[Lavoro]: ...

    def elenco(self) -> list[Lavoro]: ...

    def lavoro(self, numero: int) -> Lavoro | None: ...

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool: ...

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None: ...

    def consegna(self, numero: int, pr: int) -> None: ...

    def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None: ...

    def aggiungi(self, numero: int) -> None: ...


_QUERY_PROJECT_USER = """
query($owner: String!, $number: Int!, $cursor: String) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      title
      fields(first: 50) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
          ... on ProjectV2SingleSelectField {
            options {
              id
              name
            }
          }
        }
      }
      items(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          content {
            ... on Issue {
              number
              title
              url
              repository {
                nameWithOwner
              }
              labels(first: 20) {
                nodes { name }
              }
            }
            ... on PullRequest {
              number
              title
              url
              repository {
                nameWithOwner
              }
              labels(first: 20) {
                nodes { name }
              }
            }
          }
          fieldValues(first: 100) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                optionId
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""

_QUERY_PROJECT_ORG = """
query($owner: String!, $number: Int!, $cursor: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      title
      fields(first: 50) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
          ... on ProjectV2SingleSelectField {
            options {
              id
              name
            }
          }
        }
      }
      items(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          content {
            ... on Issue {
              number
              title
              url
              repository {
                nameWithOwner
              }
              labels(first: 20) {
                nodes { name }
              }
            }
            ... on PullRequest {
              number
              title
              url
              repository {
                nameWithOwner
              }
              labels(first: 20) {
                nodes { name }
              }
            }
          }
          fieldValues(first: 100) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                optionId
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""

_MUTATION_UPDATE = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $projectId
      itemId: $itemId
      fieldId: $fieldId
      value: $value
    }
  ) {
    projectV2Item { id }
  }
}
"""

_MUTATION_CLEAR = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
  clearProjectV2ItemFieldValue(
    input: {
      projectId: $projectId
      itemId: $itemId
      fieldId: $fieldId
    }
  ) {
    projectV2Item { id }
  }
}
"""


def _formatta_numero_str(val: Any) -> str:
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return str(val)
        if val.is_integer() or val == int(val):
            return str(int(val))
        return str(val)
    if isinstance(val, str):
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return val
            if f.is_integer() or f == int(f):
                return str(int(f))
            return str(f)
        except ValueError:
            return val
    return str(val)


def _valida_e_formatta_numero(nome: str, valore: Any) -> str:
    if isinstance(valore, bool) or valore is None:
        raise ErroreBoard(f"Campo {nome}: valore non numerico {valore!r}")
    if isinstance(valore, (int, float)):
        if math.isnan(valore) or math.isinf(valore):
            raise ErroreBoard(f"Campo {nome}: valore non numerico {valore!r}")
        if isinstance(valore, float) and (valore.is_integer() or valore == int(valore)):
            return str(int(valore))
        return str(valore)
    if isinstance(valore, str):
        try:
            f = float(valore)
        except ValueError:
            raise ErroreBoard(f"Campo {nome}: valore non numerico {valore!r}")
        if math.isnan(f) or math.isinf(f):
            raise ErroreBoard(f"Campo {nome}: valore non numerico {valore!r}")
        if f.is_integer() or f == int(f):
            return str(int(f))
        return str(f)
    raise ErroreBoard(f"Campo {nome}: valore non numerico {valore!r}")


class BoardProject:
    """Implementazione diretta su GitHub Projects (v2) tramite query GraphQL e comandi `gh`."""

    def __init__(
        self,
        proprietario: str,
        numero: int,
        repo: str | None = None,
        esegui: Callable[[list[str], str | None], str] | None = None,
    ) -> None:
        self.proprietario = proprietario
        self.numero = numero
        self.repo = repo
        self._esegui = esegui or self._esegui_di_serie
        self._tipo_proprietario: str | None = None

    def _esegui_di_serie(self, argomenti: list[str], ingresso: str | None = None) -> str:
        try:
            risultato = subprocess.run(
                ["gh", *argomenti],
                input=ingresso,
                text=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise ErroreBoard(f"gh non ha risposto in 120 secondi: {argomenti[:2]}") from None
        if risultato.returncode != 0:
            raise ErroreBoard(f"gh ha fallito ({risultato.returncode}): {risultato.stderr.strip()}")
        return risultato.stdout

    def _leggi_progetto(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[int, tuple[str, Lavoro]]]:
        cursor: str | None = None
        tutti_items_nodes: list[dict[str, Any]] = []
        proj_info: dict[str, Any] | None = None
        campi: dict[str, dict[str, Any]] | None = None

        while True:
            cmd = [
                "api", "graphql",
                "-f", f"owner={self.proprietario}",
                "-F", f"number={self.numero}",  # intero per GraphQL: -F (è un numero nostro, non un testo)
            ]
            if cursor:
                cmd.extend(["-f", f"cursor={cursor}"])

            if self._tipo_proprietario == "organization":
                cmd.extend(["-f", f"query={_QUERY_PROJECT_ORG}"])
                out = self._esegui(cmd)
                data = json.loads(out)
                proj = data.get("data", {}).get("organization", {}).get("projectV2") if data.get("data") else None
            elif self._tipo_proprietario == "user":
                cmd.extend(["-f", f"query={_QUERY_PROJECT_USER}"])
                out = self._esegui(cmd)
                data = json.loads(out)
                proj = data.get("data", {}).get("user", {}).get("projectV2") if data.get("data") else None
            else:
                # Prova prima user
                cmd_user = [*cmd, "-f", f"query={_QUERY_PROJECT_USER}"]
                out = self._esegui(cmd_user)
                data = json.loads(out)
                user_obj = data.get("data", {}).get("user") if data.get("data") else None
                proj = user_obj.get("projectV2") if isinstance(user_obj, dict) else None
                if proj:
                    self._tipo_proprietario = "user"
                else:
                    cmd_org = [*cmd, "-f", f"query={_QUERY_PROJECT_ORG}"]
                    out = self._esegui(cmd_org)
                    data = json.loads(out)
                    org_obj = data.get("data", {}).get("organization") if data.get("data") else None
                    proj = org_obj.get("projectV2") if isinstance(org_obj, dict) else None
                    if proj:
                        self._tipo_proprietario = "organization"

            if not proj:
                raise ErroreBoard(f"Project {self.numero} non trovato per {self.proprietario}")

            if proj_info is None:
                proj_info = proj
                fields_nodes = proj.get("fields", {}).get("nodes", [])
                campi = {f.get("name"): f for f in fields_nodes if isinstance(f, dict) and "name" in f}
                for obbligatorio in ("Bottega", "Esito", "Esecutore", "Nota del giro"):
                    if obbligatorio not in campi:
                        raise ErroreBoard(f"Campo mancante nel Project: {obbligatorio}")

            items_obj = proj.get("items", {})
            nodes = items_obj.get("nodes", [])
            tutti_items_nodes.extend(nodes)

            page_info = items_obj.get("pageInfo")
            if isinstance(page_info, dict) and page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        assert campi is not None
        assert proj_info is not None

        items: dict[int, tuple[str, Lavoro]] = {}
        for it in tutti_items_nodes:
            item_id = it.get("id")
            content = it.get("content") or {}
            num = content.get("number")
            if num is None:
                continue
            repo_info = content.get("repository") or {}
            item_repo = repo_info.get("nameWithOwner")
            if self.repo is not None and item_repo is not None and item_repo != self.repo:
                continue
            titolo = content.get("title", "")
            labels_nodes = content.get("labels", {}).get("nodes", [])
            etichette = [l.get("name") for l in labels_nodes if isinstance(l, dict) and "name" in l]

            valori: dict[str, str] = {}
            for fv in it.get("fieldValues", {}).get("nodes", []):
                f_info = fv.get("field") or {}
                fn = f_info.get("name")
                if not fn:
                    continue
                if "name" in fv and fv["name"] is not None:
                    valori[fn] = str(fv["name"])
                elif "text" in fv and fv["text"] is not None:
                    valori[fn] = str(fv["text"])
                elif "number" in fv and fv["number"] is not None:
                    valori[fn] = _formatta_numero_str(fv["number"])
                elif "date" in fv and fv["date"] is not None:
                    valori[fn] = str(fv["date"])

            lav = Lavoro(
                numero=num,
                titolo=titolo,
                etichette=etichette,
                stato=valori.get("Bottega", ""),
                esito=valori.get("Esito"),
                esecutore=valori.get("Esecutore"),
                nota=valori.get("Nota del giro", ""),
                repo=item_repo,
                campi=valori,
            )
            items[num] = (item_id, lav)

        return proj_info, campi, items

    def pronti(self) -> list[Lavoro]:
        _, _, items = self._leggi_progetto()
        risultato: list[Lavoro] = []
        for _, lav in items.values():
            if lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso"):
                risultato.append(lav)
        return risultato

    def in_corso(self) -> list[Lavoro]:
        _, _, items = self._leggi_progetto()
        return [lav for _, lav in items.values() if lav.stato == "in corso"]

    def elenco(self) -> list[Lavoro]:
        _, _, items = self._leggi_progetto()
        return [lav for _, lav in items.values()]

    def lavoro(self, numero: int) -> Lavoro | None:
        _, _, items = self._leggi_progetto()
        if numero in items:
            return items[numero][1]
        return None

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool:
        _, _, items = self._leggi_progetto()
        if numero not in items:
            return False
        _, lav = items[numero]
        if not (lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso")):
            return False

        self.campo(numero, "Bottega", "in corso")
        self.campo(numero, "Esito", None)
        self.campo(numero, "Esecutore", esecutore)
        if nota:
            self.campo(numero, "Nota del giro", nota)
        return True

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None:
        self.campo(numero, "Bottega", stato)
        if nota is not None:
            self.campo(numero, "Nota del giro", nota)

    def consegna(self, numero: int, pr: int) -> None:
        self.campo(numero, "Bottega", "consegnato")

    def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
        proj, campi, items = self._leggi_progetto()
        if nome not in campi:
            raise ErroreBoard(f"Campo mancante nel Project: {nome}")
        if numero not in items:
            raise ErroreBoard(f"Lavoro {numero} non trovato nel Project")

        project_id = proj["id"]
        item_id, _ = items[numero]
        field_info = campi[nome]
        field_id = field_info["id"]

        if valore is None:
            self._esegui([
                "api", "graphql",
                "-f", f"query={_MUTATION_CLEAR}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
            ])
            return

        is_number = field_info.get("dataType") == "NUMBER"
        is_select = field_info.get("dataType") == "SINGLE_SELECT" or "options" in field_info
        if is_number:
            val_num_str = _valida_e_formatta_numero(nome, valore)
            self._esegui([
                "api", "graphql",
                "-f", f"query={_MUTATION_UPDATE}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
                "-F", f"value[number]={val_num_str}",
            ])
        elif is_select:
            valore_str = str(valore)
            options = field_info.get("options", [])
            opt = next((o for o in options if isinstance(o, dict) and o.get("name") == valore_str), None)
            if not opt or "id" not in opt:
                raise ErroreBoard(f"Opzione {valore_str!r} non trovata per il campo {nome}")
            opt_id = opt["id"]
            self._esegui([
                "api", "graphql",
                "-f", f"query={_MUTATION_UPDATE}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
                "-f", f"value[singleSelectOptionId]={opt_id}",
            ])
        else:
            self._esegui([
                "api", "graphql",
                "-f", f"query={_MUTATION_UPDATE}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
                "-f", f"value[text]={valore}",
            ])

    def aggiungi(self, numero: int) -> None:
        url = (
            f"https://github.com/{self.repo}/issues/{numero}"
            if self.repo
            else f"https://github.com/{self.proprietario}/issues/{numero}"
        )
        self._esegui([
            "project", "item-add", str(self.numero),
            "--owner", self.proprietario,
            "--url", url,
        ])


_CAMPI_LAVORO = {f.name for f in fields(Lavoro)}


def _dati_a_lavoro(d: dict[str, Any]) -> Lavoro:
    d_filtrato = {k: v for k, v in d.items() if k in _CAMPI_LAVORO}
    if "campi" in d_filtrato and isinstance(d_filtrato["campi"], dict):
        d_filtrato["campi"] = {
            str(k): _formatta_numero_str(v) if isinstance(v, (int, float)) else str(v)
            for k, v in d_filtrato["campi"].items()
            if v is not None
        }
    return Lavoro(**d_filtrato)


class BoardComando:
    """Implementazione della board attraverso un comando adattatore esterno (B3-R7)."""

    def __init__(
        self,
        comando: Sequence[str],
        esegui: Callable[[list[str], str | None], str] | None = None,
    ) -> None:
        cmd = list(comando)
        # C5: un percorso relativo si fissa adesso, dall'albero di partenza (il ramo principale). Più tardi la
        # cartella corrente potrebbe contenere file del modello.
        if cmd and "/" in cmd[0] and not os.path.isabs(cmd[0]):
            cmd[0] = os.path.abspath(cmd[0])
        if not cmd or cmd[-1] != "bottega":
            cmd.append("bottega")
        self._cmd = tuple(cmd)
        self._esegui_custom = esegui

    def _esegui(self, argomenti: list[str], ingresso: str | None = None) -> str:
        if self._esegui_custom is not None:
            return self._esegui_custom(argomenti, ingresso)
        try:
            risultato = subprocess.run(
                argomenti,
                input=ingresso,
                text=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise ErroreBoard(f"l'adattatore non ha risposto in 120 secondi: {argomenti[-2:]}") from None
        if risultato.returncode != 0:
            raise ErroreBoard(f"Comando {argomenti} fallito ({risultato.returncode}): {risultato.stderr.strip()}")
        return risultato.stdout

    def pronti(self) -> list[Lavoro]:
        out = self._esegui([*self._cmd, "pronti"])
        dati = json.loads(out)
        return [_dati_a_lavoro(d) for d in dati]

    def in_corso(self) -> list[Lavoro]:
        out = self._esegui([*self._cmd, "in-corso"])
        dati = json.loads(out)
        return [_dati_a_lavoro(d) for d in dati]

    def elenco(self) -> list[Lavoro]:
        out = self._esegui([*self._cmd, "elenco"])
        dati = json.loads(out)
        return [_dati_a_lavoro(d) for d in dati]

    def lavoro(self, numero: int) -> Lavoro | None:
        # B5: si cerca fra tutti gli elementi (anche un compito consegnato o senza stato riceve le sue misure); un
        # adattatore di prima di B5, senza `elenco`, cerca ancora fra in corso e pronti.
        try:
            tutti = self.elenco()
        except ErroreBoard:
            tutti = [*self.in_corso(), *self.pronti()]
        for lav in tutti:
            if lav.numero == numero:
                return lav
        return None

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool:
        cmd = [*self._cmd, "prendi", str(numero), "--esecutore", esecutore, "--nota", nota]
        if self._esegui_custom is not None:
            try:
                self._esegui_custom(cmd, None)
                return True
            except ErroreBoard:
                return False
        risultato = subprocess.run(cmd, text=True, capture_output=True)
        if risultato.returncode == 0:
            return True
        if risultato.returncode == 1:
            return False
        raise ErroreBoard(f"prendi fallito ({risultato.returncode}): {risultato.stderr.strip()}")

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None:
        cmd = [*self._cmd, "stato", str(numero), stato]
        if nota is not None:
            cmd.extend(["--nota", nota])
        self._esegui(cmd)

    def consegna(self, numero: int, pr: int) -> None:
        self._esegui([*self._cmd, "consegna", str(numero), "--pr", str(pr)])

    def campo(self, numero: int, nome: str, valore: str | int | float | None) -> None:
        val_str = "" if valore is None else str(valore)
        self._esegui([*self._cmd, "campo", str(numero), nome, val_str])

    def aggiungi(self, numero: int) -> None:
        self._esegui([*self._cmd, "aggiungi", str(numero)])
