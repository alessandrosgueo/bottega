"""Prove per la forgia: comandi gh, assenza di chiamate di rete, corpi da stdin, avvisi e finta."""

import json
import pytest

from bottega.forgia import Commento, ErroreForgia, ForgiaGh, Issue
from bottega.finta import ForgiaFinta


def test_commenta_mette_segno_e_passa_da_stdin() -> None:
    chiamate: list[tuple[list[str], str | None]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append((argomenti, ingresso))
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    forgia.commenta(42, "Tutto a posto", "esecutore")

    assert len(chiamate) == 1
    args, stdin = chiamate[0]
    assert args == ["issue", "comment", "42", "--repo", "proprietario/repo", "--body-file", "-"]
    assert stdin is not None
    assert stdin.startswith("<!-- bottega:esecutore -->\n")
    assert "Tutto a posto" in stdin


def test_commenta_rifiuta_ruolo_sconosciuto() -> None:
    forgia = ForgiaGh("proprietario/repo", esegui=lambda args, ing=None: "")
    with pytest.raises(ValueError, match="Ruolo non valido"):
        forgia.commenta(1, "testo", "fantasma")


def test_dati_liberi_mai_su_riga_di_comando() -> None:
    chiamate: list[tuple[list[str], str | None]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append((argomenti, ingresso))
        if argomenti[:4] == ["api", "-X", "POST", "repos/proprietario/repo/issues"]:
            return json.dumps({"number": 101, "id": 9101})
        if argomenti[0] == "pr" and argomenti[1] == "create":
            return "https://github.com/proprietario/repo/pull/55\n"
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)

    corpo_issue = "Descrizione con caratteri speciali $ & e a capo\nseconda riga"
    n_issue = forgia.crea_issue("Titolo", corpo_issue, madre=10)
    assert n_issue == 101

    args_iss, stdin_iss = chiamate[0]
    assert args_iss == ["api", "-X", "POST", "repos/proprietario/repo/issues", "--input", "-"]
    assert stdin_iss is not None
    assert json.loads(stdin_iss) == {"title": "Titolo", "body": corpo_issue}
    # B7 (J4): la figlia si aggancia alla madre con l'API REST delle sotto-issue (il gh 2.46 non ha `--parent`).
    assert chiamate[1] == (
        ["api", "-X", "POST", "repos/proprietario/repo/issues/10/sub_issues", "-F", "sub_issue_id=9101"],
        None,
    )

    corpo_pr = "Corpo della PR con testo libero"
    n_pr = forgia.apri_pr("bottega/101-ramo", "Titolo PR", corpo_pr)
    assert n_pr == 55

    args_pr, stdin_pr = chiamate[2]
    assert "--draft" in args_pr
    assert "--body-file" in args_pr
    assert "-" in args_pr
    assert corpo_pr not in args_pr
    assert stdin_pr == "<!-- bottega:esecutore -->\n" + corpo_pr  # la forgia mette il segno (B3-R2)

    valore_var = "valore_segreto_o_lungo"
    forgia.imposta_variabile("BOTTEGA_QUOTA", valore_var)

    args_var, stdin_var = chiamate[3]
    assert args_var == ["variable", "set", "BOTTEGA_QUOTA", "--repo", "proprietario/repo"]
    assert valore_var not in args_var
    assert stdin_var == valore_var


def test_issue_e_sotto_issue() -> None:
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        if argomenti[0] == "api":
            return json.dumps([
                {"number": 11, "title": "Compito 1", "body": "Corpo 11", "state": "open", "labels": [],
                 "user": {"login": "proprietario"}},
                {"number": 12, "title": "Compito 2", "body": "Corpo 12", "state": "closed", "labels": [],
                 "user": {"login": "proprietario"}},
            ])
        n = int(argomenti[2])
        return json.dumps({
            "number": n,
            "title": "Tappa",
            "body": "Brief della tappa",
            "state": "OPEN",
            "labels": [{"name": "bottega: fuori"}, {"name": "tappa"}],
        })

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    iss = forgia.issue(10)
    assert iss.numero == 10
    assert iss.titolo == "Tappa"
    assert iss.corpo == "Brief della tappa"
    assert iss.aperta is True
    assert iss.etichette == ["bottega: fuori", "tappa"]

    sotto = forgia.sotto_issue(10)
    assert len(sotto) == 2
    assert sotto[0].numero == 11
    assert sotto[0].titolo == "Compito 1"
    assert sotto[0].corpo == "Corpo 11"
    assert sotto[0].aperta is True
    assert sotto[1].aperta is False


def test_etichetta_aggiungi_e_rimuovi() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    forgia.etichetta(42, "bottega: fuori", aggiungi=True)
    forgia.etichetta(42, "bottega: in corso", aggiungi=False)

    assert chiamate[0] == ["label", "create", "bottega: fuori", "--force", "--repo", "proprietario/repo"]
    assert chiamate[1] == ["issue", "edit", "42", "--repo", "proprietario/repo", "--add-label", "bottega: fuori"]
    assert chiamate[2] == ["issue", "edit", "42", "--repo", "proprietario/repo", "--remove-label", "bottega: in corso"]


def test_pr_del_ramo() -> None:
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        if "trovato" in argomenti:
            return json.dumps([{"number": 99}])
        return json.dumps([])

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    assert forgia.pr_del_ramo("trovato") == 99
    assert forgia.pr_del_ramo("mancante") is None


def test_b7_variabile_dall_api_rest() -> None:
    # B7 (J4): il gh 2.46 del server non ha `gh variable get`; l'API REST va con ogni gh.
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if argomenti[1].endswith("/ESISTE"):
            return "2026-11-08T18:00:00Z\n"
        raise ErroreForgia("gh ha fallito (1): gh: Not Found (HTTP 404)")

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    assert forgia.variabile("ESISTE") == "2026-11-08T18:00:00Z"
    assert chiamate[0] == ["api", "repos/proprietario/repo/actions/variables/ESISTE", "--jq", ".value"]
    assert forgia.variabile("MANCA") is None


def test_b7_crea_issue_senza_madre_una_chiamata_sola() -> None:
    chiamate: list[tuple[list[str], str | None]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append((argomenti, ingresso))
        return json.dumps({"number": 7, "id": 707})

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    assert forgia.crea_issue("Madre", "corpo") == 7
    assert len(chiamate) == 1
    assert not any("sub_issues" in a for a in chiamate[0][0])


def test_b7_crea_issue_risposta_storta() -> None:
    forgia = ForgiaGh("proprietario/repo", esegui=lambda args, ingresso=None: json.dumps({"message": "boh"}))
    with pytest.raises(ErroreForgia, match="risposta inattesa"):
        forgia.crea_issue("Titolo", "corpo")


def test_avvia_workflow() -> None:
    chiamate: list[tuple[list[str], str | None]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append((argomenti, ingresso))
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    forgia.avvia_workflow("distributore.yml", {"lavoro": 42})

    args, stdin = chiamate[0]
    assert args == ["workflow", "run", "distributore.yml", "--repo", "proprietario/repo", "--json"]
    assert stdin is not None
    assert json.loads(stdin) == {"lavoro": "42"}


def test_stato_ci() -> None:
    def esegui_verde(argomenti: list[str], ingresso: str | None = None) -> str:
        assert "event" in argomenti[argomenti.index("--json") + 1]
        return json.dumps([
            {"headSha": "abc", "event": "push", "status": "completed", "conclusion": "success"},
            {"headSha": "abc", "event": "push", "status": "completed", "conclusion": "skipped"},
            {"headSha": "abc", "event": "workflow_dispatch", "status": "completed", "conclusion": "failure"},
        ])

    def esegui_rosso(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps([
            {"headSha": "def", "event": "push", "status": "completed", "conclusion": "failure"},
            {"headSha": "def", "event": "push", "status": "completed", "conclusion": "success"},
        ])

    def esegui_bottega_fallita_ma_push_verde(argomenti: list[str], ingresso: str | None = None) -> str:
        # workflow_dispatch o schedule falliti non devono rendere rosso il ramo
        return json.dumps([
            {"headSha": "ghi", "event": "schedule", "status": "completed", "conclusion": "failure"},
            {"headSha": "ghi", "event": "workflow_dispatch", "status": "completed", "conclusion": "failure"},
            {"headSha": "ghi", "event": "push", "status": "completed", "conclusion": "success"},
        ])

    def esegui_ignoto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps([])

    assert ForgiaGh("proprietario/repo", esegui=esegui_verde).stato_ci("main") == "verde"
    assert ForgiaGh("proprietario/repo", esegui=esegui_rosso).stato_ci("main") == "rosso"
    assert ForgiaGh("proprietario/repo", esegui=esegui_bottega_fallita_ma_push_verde).stato_ci("main") == "verde"
    assert ForgiaGh("proprietario/repo", esegui=esegui_ignoto).stato_ci("main") == "ignoto"


def test_avviso_ciclo_completo() -> None:
    archivio_issue: list[dict] = []
    commenti_per_issue: dict[int, list[dict]] = {}

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        sottocmd = argomenti[0]
        azione = argomenti[1] if len(argomenti) > 1 else ""

        if sottocmd == "issue" and azione == "list":
            aperti = [i for i in archivio_issue if i["state"] == "OPEN"]
            return json.dumps(aperti)
        if sottocmd == "issue" and azione == "create":
            idx = len(archivio_issue) + 1
            archivio_issue.append({
                "number": idx,
                "title": argomenti[argomenti.index("--title") + 1],
                "body": ingresso or "",
                "state": "OPEN",
                "labels": [{"name": "bottega: avviso"}],
            })
            commenti_per_issue[idx] = []
            return f"https://github.com/proprietario/repo/issues/{idx}\n"
        if sottocmd == "issue" and azione == "view":
            n = int(argomenti[2])
            return json.dumps({"comments": commenti_per_issue.get(n, [])})
        if sottocmd == "issue" and azione == "comment":
            n = int(argomenti[2])
            commenti_per_issue.setdefault(n, []).append({
                "author": {"login": "bottega"},
                "body": ingresso or "",
            })
            return ""
        if sottocmd == "issue" and azione == "close":
            n = int(argomenti[2])
            for i in archivio_issue:
                if i["number"] == n:
                    i["state"] = "CLOSED"
            return ""
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)

    # 1. Primo avviso: crea issue
    forgia.avviso("porta-p", "Avviso della bottega: porta p", "CLI assente")
    assert len(archivio_issue) == 1
    assert archivio_issue[0]["number"] == 1
    assert archivio_issue[0]["state"] == "OPEN"
    assert "CLI assente" in archivio_issue[0]["body"]
    assert len(commenti_per_issue[1]) == 0

    # 2. Secondo avviso con motivo identico: non commenta
    forgia.avviso("porta-p", "Avviso della bottega: porta p", "CLI assente")
    assert len(commenti_per_issue[1]) == 0

    # 3. Terzo avviso con motivo mutato: commenta con segno
    forgia.avviso("porta-p", "Avviso della bottega: porta p", "Token scaduto")
    assert len(commenti_per_issue[1]) == 1
    assert "<!-- bottega:avviso -->" in commenti_per_issue[1][0]["body"]
    assert "Token scaduto" in commenti_per_issue[1][0]["body"]

    # 4. Quarto avviso con motivo None: chiude l'issue aperta
    forgia.avviso("porta-p", "Avviso della bottega: porta p", None)
    assert archivio_issue[0]["state"] == "CLOSED"

    # 5. Quinto avviso con motivo None: niente da chiudere
    forgia.avviso("porta-p", "Avviso della bottega: porta p", None)
    assert archivio_issue[0]["state"] == "CLOSED"


def test_forgia_finta_in_memoria() -> None:
    finta = ForgiaFinta()
    n = finta.crea_issue("Titolo Madre", "Corpo madre")
    figlia = finta.crea_issue("Compito 1", "Corpo 1", madre=n)

    assert finta.issue(n).titolo == "Titolo Madre"
    sotto = finta.sotto_issue(n)
    assert len(sotto) == 1
    assert sotto[0].numero == figlia

    finta.commenta(figlia, "Un commento", "esecutore")
    comms = finta.commenti(figlia)
    assert len(comms) == 1
    assert comms[0].corpo.startswith("<!-- bottega:esecutore -->\n")

    finta.etichetta(figlia, "bottega: fuori", aggiungi=True)
    assert "bottega: fuori" in finta.issue(figlia).etichette

    pr_num = finta.apri_pr("bottega/1-ramo", "PR 1", "Corpo PR")
    assert finta.pr_del_ramo("bottega/1-ramo") == pr_num

    finta.imposta_variabile("QUOTA", "10")
    assert finta.variabile("QUOTA") == "10"

    finta.avvia_workflow("esecutore.yml", {"lavoro": 1})

    # Verifica avviso in memoria
    finta.avviso("k1", "Avviso test", "errore a")
    assert len([i for i in finta.registro if i[0] == "avviso"]) == 1
    finta.avviso("k1", "Avviso test", "errore a")  # stesso motivo, nessun nuovo commento
    assert len(finta.commenti(finta.registro[0][1] if isinstance(finta.registro[0][1], int) else 3)) == 0
    finta.avviso("k1", "Avviso test", "errore b")  # motivo cambiato -> commento
    finta.avviso("k1", "Avviso test", None)  # chiusura

    # Registro ha tutte le scritture
    azioni = [r[0] for r in finta.registro]
    assert "crea_issue" in azioni
    assert "commenta" in azioni
    assert "etichetta" in azioni
    assert "apri_pr" in azioni
    assert "imposta_variabile" in azioni
    assert "avvia_workflow" in azioni
    assert "avviso" in azioni


# Prove per RV12: fedeltà a gh 2.100.0 e requisiti della revisione


def test_b7_sotto_issue_dall_api_rest() -> None:
    """B7 (J4): le sotto-issue vengono dall'API REST, che va con ogni `gh`. `gh issue view --json subIssues` non c'è
    nella 2.46 di Ubuntu, e nelle versioni nuove risponde un oggetto `{"nodes": [...]}` senza corpo."""
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if argomenti == ["api", "repos/proprietario/repo/issues/20/sub_issues?per_page=100"]:
            return json.dumps([
                {"number": 21, "title": "Primo compito", "body": "Fatto quando del compito 21", "state": "open",
                 "labels": [{"name": "bottega: fuori"}], "user": {"login": "chi-decide"}},
                {"number": 22, "title": "Secondo compito", "body": None, "state": "closed", "labels": [],
                 "user": {"login": "chi-decide"}},
            ])
        raise ErroreForgia(f"chiamata inattesa: {argomenti}")

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    sotto = forgia.sotto_issue(20)

    assert [s.numero for s in sotto] == [21, 22]
    assert sotto[0].corpo == "Fatto quando del compito 21"
    assert sotto[0].aperta is True
    assert sotto[0].etichette == ["bottega: fuori"]
    assert sotto[0].autore == "chi-decide"
    assert sotto[1].corpo == ""
    assert sotto[1].aperta is False
    assert not any("subIssues" in a for a in chiamate)


def test_b7_sotto_issue_risposta_storta() -> None:
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        return json.dumps({"nodes": [{"number": 21}], "totalCount": 1})

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    with pytest.raises(ErroreForgia):
        forgia.sotto_issue(20)


def test_rv12_pr_del_ramo_solo_aperte() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if "--state" in argomenti:
            stato = argomenti[argomenti.index("--state") + 1]
            if stato == "open":
                return json.dumps([{"number": 77}])
            if stato == "all":
                # Rifiutiamo o segnaliamo stato non conforme a RV12
                return json.dumps([{"number": 999}])
        return json.dumps([])

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    res = forgia.pr_del_ramo("bottega/1-test")
    assert res == 77
    assert chiamate[0][chiamate[0].index("--state") + 1] == "open"


def test_rv12_variabile_distingue_mancante_da_errore_generico() -> None:
    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        var = argomenti[1].rsplit("/", 1)[-1]
        if var == "MANCA":
            raise ErroreForgia("gh ha fallito (1): gh: Not Found (HTTP 404)")
        if var == "RETE_ROTTA":
            raise ErroreForgia("gh ha fallito (1): connection refused")
        return "valore"

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    assert forgia.variabile("MANCA") is None
    with pytest.raises(ErroreForgia, match="connection refused"):
        forgia.variabile("RETE_ROTTA")


def test_rv12_avviso_confronta_con_ultimo_commento_con_segno_avviso() -> None:
    commenti_view: list[dict] = [
        {"author": {"login": "bottega"}, "body": "<!-- bottega:avviso -->\nMotivo iniziale"},
        {"author": {"login": "comandante"}, "body": "Commento di un comandante senza segno"},
    ]
    chiamate_comment: list[str] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        cmd = argomenti[0]
        sub = argomenti[1] if len(argomenti) > 1 else ""
        if cmd == "issue" and sub == "list":
            return json.dumps([{"number": 5, "title": "Avviso prova", "body": "<!-- bottega:avviso -->\nMotivo iniziale"}])
        if cmd == "issue" and sub == "view":
            return json.dumps({"comments": commenti_view})
        if cmd == "issue" and sub == "comment":
            chiamate_comment.append(ingresso or "")
            return ""
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    # Stesso motivo iniziale: l'ultimo commento è dell'utente ma l'ultimo con segno avviso è identico
    forgia.avviso("k", "Avviso prova", "Motivo iniziale")
    assert len(chiamate_comment) == 0

    # Motivo mutato: deve commentare
    forgia.avviso("k", "Avviso prova", "Nuovo motivo")
    assert len(chiamate_comment) == 1
    assert "Nuovo motivo" in chiamate_comment[0]


def test_rv12_avvia_workflow_converte_input_in_stringhe() -> None:
    chiamate: list[tuple[list[str], str | None]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append((argomenti, ingresso))
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    forgia.avvia_workflow("esecutore.yml", {"lavoro": 42, "attivo": True, "nome": "antigravity"})

    _, stdin = chiamate[0]
    assert stdin is not None
    dati = json.loads(stdin)
    assert dati == {"lavoro": "42", "attivo": "True", "nome": "antigravity"}


def test_rv12_etichette_create_una_sola_volta() -> None:
    chiamate: list[list[str]] = []

    def esegui_finto(argomenti: list[str], ingresso: str | None = None) -> str:
        chiamate.append(argomenti)
        if argomenti[0] == "issue" and argomenti[1] == "list":
            return json.dumps([])
        if argomenti[0] == "issue" and argomenti[1] == "create":
            return "https://github.com/proprietario/repo/issues/1\n"
        return ""

    forgia = ForgiaGh("proprietario/repo", esegui=esegui_finto)
    # 1. Aggiungi etichetta: crea label con --force e poi issue edit
    forgia.etichetta(1, "bottega: fuori", aggiungi=True)
    # 2. Aggiungi stessa etichetta su altra issue: non deve ricrearla
    forgia.etichetta(2, "bottega: fuori", aggiungi=True)
    # 3. Rimuovi etichetta: non crea nulla
    forgia.etichetta(1, "bottega: fuori", aggiungi=False)
    # 4. Avviso crea etichetta "bottega: avviso" una sola volta
    forgia.avviso("k", "Avviso", "motivo")
    forgia.avviso("k2", "Avviso 2", "motivo")

    label_create = [c for c in chiamate if c[:2] == ["label", "create"]]
    assert len(label_create) == 2
    assert label_create[0] == ["label", "create", "bottega: fuori", "--force", "--repo", "proprietario/repo"]
    assert label_create[1] == ["label", "create", "bottega: avviso", "--force", "--repo", "proprietario/repo"]

