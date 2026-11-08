"""Implementazioni finte in memoria di Forgia e Board per le prove e il giro finto."""

from collections.abc import Sequence
from typing import Any

from bottega.board import ErroreBoard, Lavoro
from bottega.forgia import Commento, ErroreForgia, Issue, _spoglia_segno, segna
from bottega.segni import ruolo


class ForgiaFinta:
    """Forgia finta in memoria che tiene traccia dello stato e di tutte le scritture."""

    def __init__(
        self,
        issues: Sequence[Issue] | None = None,
        ramo_principale: str = "main",
        proprietario: str = "bottega",
    ) -> None:
        self._ramo_principale = ramo_principale
        self._proprietario = proprietario
        self._issues: dict[int, Issue] = {}
        self._sotto_issue: dict[int, list[int]] = {}
        self._commenti: dict[int, list[Commento]] = {}
        self._pr: dict[int, dict[str, Any]] = {}
        self._variabili: dict[str, str] = {}
        self._workflow_avviati: list[tuple[str, dict[str, Any]]] = []
        self._stato_ci: dict[str, str] = {}
        self._avvisi: dict[str, int] = {}
        self.registro: list[tuple[Any, ...]] = []
        self._contatore_issue = 0
        self._contatore_pr = 0

        if issues:
            for iss in issues:
                self._issues[iss.numero] = iss
                if iss.numero > self._contatore_issue:
                    self._contatore_issue = iss.numero

    def _prossimo_num_issue(self) -> int:
        self._contatore_issue += 1
        return self._contatore_issue

    def _prossimo_num_pr(self) -> int:
        self._contatore_pr += 1
        return self._contatore_pr

    def issue(self, n: int) -> Issue:
        if n not in self._issues:
            raise ErroreForgia(f"Issue {n} non trovata")
        return self._issues[n]

    def sotto_issue(self, n: int) -> list[Issue]:
        figli_numeri = self._sotto_issue.get(n, [])
        return [self._issues[num] for num in figli_numeri if num in self._issues]

    def commenti(self, n: int) -> list[Commento]:
        return list(self._commenti.get(n, []))

    def commenta(self, n: int, testo: str, ruolo: str) -> None:
        if n not in self._issues and n not in self._pr:
            raise ErroreForgia(f"Issue {n} non trovata")
        corpo = segna(testo, ruolo)
        comm = Commento(autore="bottega", corpo=corpo)
        self._commenti.setdefault(n, []).append(comm)
        self.registro.append(("commenta", n, corpo, ruolo))

    def etichetta(self, n: int, nome: str, aggiungi: bool = True) -> None:
        if n not in self._issues and n not in self._pr:
            raise ErroreForgia(f"Issue {n} non trovata")
        if n in self._issues:
            cur = self._issues[n]
            etichette = list(cur.etichette)
            if aggiungi and nome not in etichette:
                etichette.append(nome)
            elif not aggiungi and nome in etichette:
                etichette.remove(nome)
            self._issues[n] = Issue(
                numero=cur.numero,
                titolo=cur.titolo,
                corpo=cur.corpo,
                stato=cur.stato,
                etichette=etichette,
                autore=cur.autore,
            )
        if n in self._pr:
            etichette = list(self._pr[n].setdefault("etichette", []))
            if aggiungi and nome not in etichette:
                etichette.append(nome)
            elif not aggiungi and nome in etichette:
                etichette.remove(nome)
            self._pr[n]["etichette"] = etichette
        self.registro.append(("etichetta", n, nome, aggiungi))

    def pr_del_ramo(self, ramo: str) -> int | None:
        for num, d in self._pr.items():
            if d.get("ramo") == ramo:
                return num
        return None

    def apri_pr(self, ramo: str, titolo: str, corpo: str) -> int:
        corpo = segna(corpo, "esecutore")  # B3-R2: ogni PR scritta da un giro ha il segno
        num = self._prossimo_num_pr()
        self._pr[num] = {"ramo": ramo, "titolo": titolo, "corpo": corpo}
        self.registro.append(("apri_pr", num, ramo, titolo, corpo))
        return num

    def variabile(self, nome: str) -> str | None:
        return self._variabili.get(nome)

    def imposta_variabile(self, nome: str, valore: str) -> None:
        self._variabili[nome] = valore
        self.registro.append(("imposta_variabile", nome, valore))

    def avvia_workflow(self, file: str, input: dict[str, Any]) -> None:
        input_str = {k: str(v) for k, v in input.items()}
        self._workflow_avviati.append((file, input_str))
        self.registro.append(("avvia_workflow", file, input_str))

    def stato_ci(self, ramo: str) -> str:
        return self._stato_ci.get(ramo, "ignoto")

    def imposta_stato_ci(self, ramo: str, stato: str) -> None:
        self._stato_ci[ramo] = stato

    def crea_issue(self, titolo: str, corpo: str, madre: int | None = None, autore: str = "") -> int:
        num = self._prossimo_num_issue()
        iss = Issue(numero=num, titolo=titolo, corpo=corpo, stato="OPEN", etichette=[], autore=autore)
        self._issues[num] = iss
        if madre is not None:
            self._sotto_issue.setdefault(madre, []).append(num)
        self.registro.append(("crea_issue", num, titolo, corpo, madre))
        return num

    def chiudi_issue(self, n: int) -> None:
        if n not in self._issues:
            raise ErroreForgia(f"Issue {n} non trovata")
        cur = self._issues[n]
        self._issues[n] = Issue(
            numero=cur.numero,
            titolo=cur.titolo,
            corpo=cur.corpo,
            stato="CLOSED",
            etichette=cur.etichette,
            autore=cur.autore,
        )
        self.registro.append(("chiudi_issue", n))

    def avviso(self, chiave: str, titolo: str, motivo: str | None) -> None:
        aperta_num: int | None = None
        for n, iss in self._issues.items():
            if iss.titolo == titolo and iss.aperta and "bottega: avviso" in iss.etichette:
                aperta_num = n
                break

        if motivo is None:
            if aperta_num is not None:
                cur = self._issues[aperta_num]
                self._issues[aperta_num] = Issue(
                    numero=cur.numero,
                    titolo=cur.titolo,
                    corpo=cur.corpo,
                    stato="CLOSED",
                    etichette=cur.etichette,
                    autore=cur.autore,
                )
            self.registro.append(("avviso", chiave, titolo, None))
            return

        if aperta_num is None:
            num = self._prossimo_num_issue()
            corpo = segna(motivo, "avviso")
            iss = Issue(
                numero=num,
                titolo=titolo,
                corpo=corpo,
                stato="OPEN",
                etichette=["bottega: avviso"],
                autore="bottega",
            )
            self._issues[num] = iss
            self._avvisi[chiave] = num
            self.registro.append(("avviso", chiave, titolo, motivo))
            return

        comms = [c for c in self._commenti.get(aperta_num, []) if ruolo(c.corpo) == "avviso"]
        ultimo_testo = comms[-1].corpo if comms else self._issues[aperta_num].corpo
        ultimo_motivo = _spoglia_segno(ultimo_testo)
        if motivo != ultimo_motivo:
            self.commenta(aperta_num, motivo, "avviso")
        self.registro.append(("avviso", chiave, titolo, motivo))

    def ramo_principale(self) -> str:
        return self._ramo_principale

    def proprietario(self) -> str:
        return self._proprietario


class BoardFinta:
    """Board finta in memoria con registro delle scritture."""

    def __init__(
        self,
        lavori: Sequence[Lavoro] | None = None,
        repo: str | None = None,
    ) -> None:
        self.repo = repo
        self._lavori: dict[tuple[str | None, int], dict[str, Any]] = {}
        self.registro: list[tuple[Any, ...]] = []

        if lavori:
            for lav in lavori:
                self._carica_lavoro(lav)

    def _carica_lavoro(self, lavoro: Lavoro) -> None:
        chiave = (lavoro.repo, lavoro.numero)
        self._lavori[chiave] = {
            "numero": lavoro.numero,
            "titolo": lavoro.titolo,
            "etichette": list(lavoro.etichette),
            "stato": lavoro.stato,
            "esito": lavoro.esito,
            "esecutore": lavoro.esecutore,
            "nota": lavoro.nota,
            "repo": lavoro.repo,
            "campi": {},
        }

    def aggiungi(self, lavoro: int | Lavoro, titolo: str = "", stato: str = "pronto") -> None:
        if isinstance(lavoro, Lavoro):
            self._carica_lavoro(lavoro)
            self.registro.append(("aggiungi", lavoro.numero))
        else:
            numero = lavoro
            chiave = (self.repo, numero)
            self._lavori[chiave] = {
                "numero": numero,
                "titolo": titolo or f"Issue {numero}",
                "etichette": [],
                "stato": stato,
                "esito": None,
                "esecutore": None,
                "nota": "",
                "repo": self.repo,
                "campi": {},
            }
            self.registro.append(("aggiungi", numero))

    def _trova_lavoro(self, numero: int) -> dict[str, Any] | None:
        if self.repo is not None:
            return self._lavori.get((self.repo, numero))
        for (r, n), d in self._lavori.items():
            if n == numero:
                return d
        return None

    def _a_lavoro(self, d: dict[str, Any]) -> Lavoro:
        return Lavoro(
            numero=d["numero"],
            titolo=d["titolo"],
            etichette=list(d.get("etichette", [])),
            stato=d.get("stato", ""),
            esito=d.get("esito"),
            esecutore=d.get("esecutore"),
            nota=d.get("nota", ""),
            repo=d.get("repo"),
        )

    def pronti(self) -> list[Lavoro]:
        risultato: list[Lavoro] = []
        for (r, n), d in self._lavori.items():
            if self.repo is not None and r is not None and r != self.repo:
                continue
            if d["stato"] == "pronto" or (d.get("esito") == "correzioni" and d["stato"] != "in corso"):
                risultato.append(self._a_lavoro(d))
        return risultato

    def in_corso(self) -> list[Lavoro]:
        risultato: list[Lavoro] = []
        for (r, n), d in self._lavori.items():
            if self.repo is not None and r is not None and r != self.repo:
                continue
            if d.get("stato") == "in corso":
                risultato.append(self._a_lavoro(d))
        return risultato

    def lavoro(self, numero: int) -> Lavoro | None:
        d = self._trova_lavoro(numero)
        return self._a_lavoro(d) if d is not None else None

    def prendi(self, numero: int, esecutore: str, nota: str = "") -> bool:
        d = self._trova_lavoro(numero)
        if d is None:
            return False
        if not (d["stato"] == "pronto" or (d.get("esito") == "correzioni" and d["stato"] != "in corso")):
            return False

        d["stato"] = "in corso"
        d["esecutore"] = esecutore
        d["nota"] = nota
        d["esito"] = None
        self.registro.append(("prendi", numero, esecutore, nota))
        return True

    def stato(self, numero: int, stato: str, nota: str | None = None) -> None:
        d = self._trova_lavoro(numero)
        if d is None:
            raise ErroreBoard(f"Lavoro {numero} non trovato")
        d["stato"] = stato
        if nota is not None:
            d["nota"] = nota
        self.registro.append(("stato", numero, stato, nota))

    def consegna(self, numero: int, pr: int) -> None:
        d = self._trova_lavoro(numero)
        if d is None:
            raise ErroreBoard(f"Lavoro {numero} non trovato")
        d["stato"] = "consegnato"
        self.registro.append(("consegna", numero, pr))

    def campo(self, numero: int, nome: str, valore: str | None) -> None:
        d = self._trova_lavoro(numero)
        if d is None:
            raise ErroreBoard(f"Lavoro {numero} non trovato")
        if valore is None:
            if nome == "Bottega":
                d["stato"] = ""
            elif nome == "Esito":
                d["esito"] = None
            elif nome == "Esecutore":
                d["esecutore"] = None
            elif nome == "Nota del giro":
                d["nota"] = ""
            else:
                d.setdefault("campi", {}).pop(nome, None)
        else:
            if nome == "Bottega":
                d["stato"] = valore
            elif nome == "Esito":
                d["esito"] = valore
            elif nome == "Esecutore":
                d["esecutore"] = valore
            elif nome == "Nota del giro":
                d["nota"] = valore
            else:
                d.setdefault("campi", {})[nome] = valore
        self.registro.append(("campo", numero, nome, valore))
