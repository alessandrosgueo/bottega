"""La board: interfaccia e adattatori per GitHub Projects (BoardProject e BoardComando)."""

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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


class ErroreBoard(Exception):
    """Errore della board o campo mancante nel Project."""


class Board(Protocol):
    """Interfaccia verso la board del progetto (le cinque operazioni di B3-R7)."""

    def pronti(self) -> list[Lavoro]: ...

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool: ...

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None: ...

    def consegna(self, numero: int, pr: int) -> None: ...

    def campo(self, numero: int, nome: str, valore: str) -> None: ...


_QUERY_PROJECT = """
query($owner: String!, $number: Int!) {
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
      items(first: 100) {
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
          fieldValues(first: 20) {
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
            }
          }
        }
      }
    }
  }
}
"""


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

    def _esegui_di_serie(self, argomenti: list[str], ingresso: str | None = None) -> str:
        risultato = subprocess.run(
            ["gh", *argomenti],
            input=ingresso,
            text=True,
            capture_output=True,
        )
        if risultato.returncode != 0:
            raise ErroreBoard(f"gh ha fallito ({risultato.returncode}): {risultato.stderr.strip()}")
        return risultato.stdout

    def _leggi_progetto(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[int, tuple[str, Lavoro]]]:
        out = self._esegui([
            "api", "graphql",
            "-F", f"owner={self.proprietario}",
            "-F", f"number={self.numero}",
            "-f", f"query={_QUERY_PROJECT}",
        ])
        data = json.loads(out)
        proj = data.get("data", {}).get("user", {}).get("projectV2")
        if not proj:
            raise ErroreBoard(f"Project {self.numero} non trovato per {self.proprietario}")

        fields_nodes = proj.get("fields", {}).get("nodes", [])
        campi = {f.get("name"): f for f in fields_nodes if isinstance(f, dict) and "name" in f}
        for obbligatorio in ("Bottega", "Esito", "Esecutore", "Nota del giro"):
            if obbligatorio not in campi:
                raise ErroreBoard(f"Campo mancante nel Project: {obbligatorio}")

        items_nodes = proj.get("items", {}).get("nodes", [])
        items: dict[int, tuple[str, Lavoro]] = {}
        for it in items_nodes:
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
                if "name" in fv:
                    valori[fn] = str(fv["name"])
                elif "text" in fv:
                    valori[fn] = str(fv["text"])
                elif "number" in fv:
                    valori[fn] = str(fv["number"])

            lav = Lavoro(
                numero=num,
                titolo=titolo,
                etichette=etichette,
                stato=valori.get("Bottega", ""),
                esito=valori.get("Esito"),
                esecutore=valori.get("Esecutore"),
                nota=valori.get("Nota del giro", ""),
                repo=item_repo,
            )
            items[num] = (item_id, lav)

        return proj, campi, items

    def pronti(self) -> list[Lavoro]:
        _, _, items = self._leggi_progetto()
        risultato: list[Lavoro] = []
        for _, lav in items.values():
            if lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso"):
                risultato.append(lav)
        return risultato

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool:
        _, _, items = self._leggi_progetto()
        if numero not in items:
            return False
        _, lav = items[numero]
        if not (lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso")):
            return False

        self.campo(numero, "Bottega", "in corso")
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

    def campo(self, numero: int, nome: str, valore: str) -> None:
        _, campi, items = self._leggi_progetto()
        if nome not in campi:
            raise ErroreBoard(f"Campo mancante nel Project: {nome}")
        if numero not in items:
            raise ErroreBoard(f"Lavoro {numero} non trovato nel Project")

        item_id, _ = items[numero]
        field_info = campi[nome]
        is_select = field_info.get("dataType") == "SINGLE_SELECT" or "options" in field_info
        val_flag = "--value" if is_select else "--text"
        self._esegui([
            "project", "item-edit", str(self.numero),
            "--owner", self.proprietario,
            "--id", item_id,
            "--field", nome,
            val_flag, valore,
        ])


class BoardComando:
    """Implementazione della board attraverso un comando adattatore esterno (B3-R7)."""

    def __init__(
        self,
        comando: Sequence[str],
        esegui: Callable[[list[str], str | None], str] | None = None,
    ) -> None:
        cmd = list(comando)
        if not cmd or cmd[-1] != "bottega":
            cmd.append("bottega")
        self._cmd = tuple(cmd)
        self._esegui_custom = esegui

    def _esegui(self, argomenti: list[str], ingresso: str | None = None) -> str:
        if self._esegui_custom is not None:
            return self._esegui_custom(argomenti, ingresso)
        risultato = subprocess.run(
            argomenti,
            input=ingresso,
            text=True,
            capture_output=True,
        )
        if risultato.returncode != 0:
            raise ErroreBoard(f"Comando {argomenti} fallito ({risultato.returncode}): {risultato.stderr.strip()}")
        return risultato.stdout

    def pronti(self) -> list[Lavoro]:
        out = self._esegui([*self._cmd, "pronti"])
        dati = json.loads(out)
        return [Lavoro(**d) for d in dati]

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

    def campo(self, numero: int, nome: str, valore: str) -> None:
        self._esegui([*self._cmd, "campo", str(numero), nome, valore])
