"""La forgia: come la bottega parla con GitHub (issue, commenti, PR, variabili, workflow, CI)."""

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from bottega.segni import RUOLI, ruolo, segna

_REGEX_SEGNO = re.compile(r"^<!--\s*bottega:[a-z]+\s*-->\s*", re.IGNORECASE)


def _spoglia_segno(testo: str) -> str:
    """Rimuove il segno iniziale dal corpo se presente."""
    return _REGEX_SEGNO.sub("", testo.strip()).strip()


@dataclass(frozen=True)
class Issue:
    """Un'issue di GitHub."""

    numero: int
    titolo: str
    corpo: str = ""
    stato: str = "OPEN"
    etichette: list[str] = field(default_factory=list)

    @property
    def aperta(self) -> bool:
        return self.stato.upper() in ("OPEN", "APERTA")


@dataclass(frozen=True)
class Commento:
    """Un commento a un'issue o PR."""

    autore: str
    corpo: str


class ErroreForgia(Exception):
    """Errore durante una chiamata alla forgia."""


class Forgia(Protocol):
    """Interfaccia verso la forgia di GitHub."""

    def issue(self, n: int) -> Issue: ...

    def sotto_issue(self, n: int) -> list[Issue]: ...

    def commenti(self, n: int) -> list[Commento]: ...

    def commenta(self, n: int, testo: str, ruolo: str) -> None: ...

    def etichetta(self, n: int, nome: str, aggiungi: bool = True) -> None: ...

    def pr_del_ramo(self, ramo: str) -> int | None: ...

    def apri_pr(self, ramo: str, titolo: str, corpo: str) -> int: ...

    def variabile(self, nome: str) -> str | None: ...

    def imposta_variabile(self, nome: str, valore: str) -> None: ...

    def avvia_workflow(self, file: str, input: dict[str, Any]) -> None: ...

    def stato_ci(self, ramo: str) -> str: ...

    def crea_issue(self, titolo: str, corpo: str, madre: int | None = None) -> int: ...

    def chiudi_issue(self, n: int) -> None: ...

    def avviso(self, chiave: str, titolo: str, motivo: str | None) -> None: ...

    def ramo_principale(self) -> str: ...

    def proprietario(self) -> str: ...


class ForgiaGh:
    """Implementazione vera della forgia attraverso la CLI `gh`."""

    def __init__(
        self,
        repo: str,
        esegui: Callable[[list[str], str | None], str] | None = None,
    ) -> None:
        self.repo = repo
        self._esegui = esegui or self._esegui_di_serie
        self._etichette_create: set[str] = set()

    def _assicura_etichetta(self, nome: str) -> None:
        if nome not in self._etichette_create:
            self._esegui(["label", "create", nome, "--force", "--repo", self.repo])
            self._etichette_create.add(nome)

    def _esegui_di_serie(self, argomenti: list[str], ingresso: str | None = None) -> str:
        risultato = subprocess.run(
            ["gh", *argomenti],
            input=ingresso,
            text=True,
            capture_output=True,
        )
        if risultato.returncode != 0:
            raise ErroreForgia(f"gh ha fallito ({risultato.returncode}): {risultato.stderr.strip()}")
        return risultato.stdout

    def issue(self, n: int) -> Issue:
        out = self._esegui([
            "issue", "view", str(n),
            "--repo", self.repo,
            "--json", "number,title,body,state,labels",
        ])
        d = json.loads(out)
        etichette = [et["name"] if isinstance(et, dict) else str(et) for et in d.get("labels", [])]
        return Issue(
            numero=d["number"],
            titolo=d.get("title", ""),
            corpo=d.get("body", "") or "",
            stato=d.get("state", "OPEN"),
            etichette=etichette,
        )

    def sotto_issue(self, n: int) -> list[Issue]:
        out = self._esegui([
            "issue", "view", str(n),
            "--repo", self.repo,
            "--json", "subIssues",
        ])
        d = json.loads(out)
        sotto = d.get("subIssues", [])
        return [self.issue(s["number"]) for s in sotto if "number" in s]

    def commenti(self, n: int) -> list[Commento]:
        out = self._esegui([
            "issue", "view", str(n),
            "--repo", self.repo,
            "--json", "comments",
        ])
        d = json.loads(out)
        commenti_raw = d.get("comments", [])
        risultato: list[Commento] = []
        for c in commenti_raw:
            autore = c.get("author", {}).get("login", "") if isinstance(c.get("author"), dict) else ""
            risultato.append(Commento(autore=autore, corpo=c.get("body", "")))
        return risultato

    def commenta(self, n: int, testo: str, ruolo: str) -> None:
        corpo = segna(testo, ruolo)
        self._esegui(
            ["issue", "comment", str(n), "--repo", self.repo, "--body-file", "-"],
            ingresso=corpo,
        )

    def etichetta(self, n: int, nome: str, aggiungi: bool = True) -> None:
        if aggiungi:
            self._assicura_etichetta(nome)
        flag = "--add-label" if aggiungi else "--remove-label"
        self._esegui(["issue", "edit", str(n), "--repo", self.repo, flag, nome])

    def pr_del_ramo(self, ramo: str) -> int | None:
        out = self._esegui([
            "pr", "list",
            "--repo", self.repo,
            "--head", ramo,
            "--state", "open",
            "--json", "number",
            "--limit", "1",
        ])
        d = json.loads(out)
        return d[0]["number"] if d else None

    def apri_pr(self, ramo: str, titolo: str, corpo: str) -> int:
        corpo = segna(corpo, "esecutore")  # B3-R2: ogni PR scritta da un giro ha il segno
        out = self._esegui(
            ["pr", "create", "--repo", self.repo, "--head", ramo, "--title", titolo, "--draft", "--body-file", "-"],
            ingresso=corpo,
        )
        url_o_num = out.strip().split("/")[-1]
        return int(url_o_num)

    def variabile(self, nome: str) -> str | None:
        try:
            out = self._esegui(["variable", "get", nome, "--repo", self.repo])
            return out.strip()
        except ErroreForgia as e:
            if "not found" in str(e).lower():
                return None
            raise

    def imposta_variabile(self, nome: str, valore: str) -> None:
        self._esegui(["variable", "set", nome, "--repo", self.repo], ingresso=valore)

    def avvia_workflow(self, file: str, input: dict[str, Any]) -> None:
        cmd = ["workflow", "run", file, "--repo", self.repo]
        if input:
            cmd.append("--json")
            input_str = {k: str(v) for k, v in input.items()}
            self._esegui(cmd, ingresso=json.dumps(input_str))
        else:
            self._esegui(cmd)

    def stato_ci(self, ramo: str) -> str:
        out = self._esegui([
            "run", "list",
            "--repo", self.repo,
            "--branch", ramo,
            "--limit", "10",
            "--json", "status,conclusion,headSha,event",
        ])
        runs = json.loads(out)
        if not runs:
            return "ignoto"
        push_runs = [r for r in runs if r.get("event") == "push"]
        if not push_runs:
            return "ignoto"
        sha = push_runs[0].get("headSha")
        if sha:
            push_runs = [r for r in push_runs if r.get("headSha") == sha]
        if any(r.get("conclusion") in ("failure", "timed_out", "startup_failure") for r in push_runs):
            return "rosso"
        esiti_ok = ("success", "skipped", "neutral")
        if all(r.get("status") == "completed" and r.get("conclusion") in esiti_ok for r in push_runs):
            return "verde"
        return "ignoto"

    def crea_issue(self, titolo: str, corpo: str, madre: int | None = None) -> int:
        cmd = ["issue", "create", "--repo", self.repo, "--title", titolo, "--body-file", "-"]
        if madre is not None:
            cmd.extend(["--parent", str(madre)])
        out = self._esegui(cmd, ingresso=corpo)
        url_o_num = out.strip().split("/")[-1]
        return int(url_o_num)

    def chiudi_issue(self, n: int) -> None:
        self._esegui(["issue", "close", str(n), "--repo", self.repo])

    def avviso(self, chiave: str, titolo: str, motivo: str | None) -> None:
        out = self._esegui([
            "issue", "list",
            "--repo", self.repo,
            "--label", "bottega: avviso",
            "--state", "open",
            "--json", "number,title,body",
        ])
        issues = json.loads(out)
        aperta = next((it for it in issues if it.get("title") == titolo), None)

        if motivo is None:
            if aperta is not None:
                self._esegui(["issue", "close", str(aperta["number"]), "--repo", self.repo])
            return

        if aperta is None:
            self._assicura_etichetta("bottega: avviso")
            corpo = segna(motivo, "avviso")
            cmd = [
                "issue", "create",
                "--repo", self.repo,
                "--title", titolo,
                "--label", "bottega: avviso",
                "--body-file", "-",
            ]
            self._esegui(cmd, ingresso=corpo)
            return

        n = aperta["number"]
        comm_out = self._esegui(["issue", "view", str(n), "--repo", self.repo, "--json", "comments"])
        comm_data = json.loads(comm_out)
        comments = comm_data.get("comments", [])
        commenti_avviso = [
            c.get("body", "")
            for c in comments
            if isinstance(c, dict) and ruolo(c.get("body", "")) == "avviso"
        ]
        if commenti_avviso:
            ultimo_motivo = _spoglia_segno(commenti_avviso[-1])
        else:
            ultimo_motivo = _spoglia_segno(aperta.get("body", ""))
        if motivo != ultimo_motivo:
            self.commenta(n, motivo, "avviso")

    def ramo_principale(self) -> str:
        out = self._esegui(["repo", "view", self.repo, "--json", "defaultBranchRef"])
        return json.loads(out)["defaultBranchRef"]["name"]

    def proprietario(self) -> str:
        if "/" in self.repo:
            return self.repo.split("/")[0]
        out = self._esegui(["repo", "view", self.repo, "--json", "owner"])
        return json.loads(out)["owner"]["login"]
