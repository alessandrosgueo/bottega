"""Prove per i passi d'installazione nel progetto (attrezzi/bottega/progetto.py)."""

from datetime import date
import json
import pytest

from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
import bottega.misure as misure
from bottega.progetto import (
    CAMPI_DEL_PROJECT,
    ErroreProgetto,
    aggiorna_chiamanti,
    campi_mancanti,
    crea_campi,
    cron_della_notte,
    ferma,
    file_dell_installazione,
    imposta_segreto,
    mutazione_campo,
    rendi_modello,
    riparti,
    workflow_della_bottega,
)


def _configurazione_prova() -> Configurazione:
    return Configurazione(
        versione=1,
        progetto=Progetto(
            comandanti=("comandante",),
            adattatore=None,
            fuso="Europe/Rome",
            notte="01:30",
            manutenzione=(),
            project=1,
            liberi=(),
        ),
        botteghe={
            "principale": Bottega(id="principale", quota="scarsa", porte=("claude-code",)),
        },
        candidati={
            "maestro": Candidato(
                id="maestro",
                nome="Maestro Modello",
                bottega="principale",
                porta="claude-code",
                modello="modello-forte",
                funzioni=("decidere", "rivedere"),
                runner="runner-principale",
            ),
        },
    )


def test_campi_del_project_comprendono_le_misure() -> None:
    # Quelli di B3
    assert "Bottega" in CAMPI_DEL_PROJECT
    assert CAMPI_DEL_PROJECT["Bottega"] == (
        "SINGLE_SELECT",
        ("pronto", "in corso", "in attesa", "consegnato", "bloccato"),
    )
    assert "Esito" in CAMPI_DEL_PROJECT
    assert CAMPI_DEL_PROJECT["Esito"] == (
        "SINGLE_SELECT",
        ("pronta per l'unione", "correzioni", "rifiutata"),
    )
    assert "Esecutore" in CAMPI_DEL_PROJECT
    assert CAMPI_DEL_PROJECT["Esecutore"] == ("TEXT", ())
    assert "Nota del giro" in CAMPI_DEL_PROJECT
    assert CAMPI_DEL_PROJECT["Nota del giro"] == ("TEXT", ())

    # Quelli di misure.CAMPI
    for nome, tipo in misure.CAMPI.items():
        assert nome in CAMPI_DEL_PROJECT, f"Campo di misura {nome} assente"
        if nome == "Esito del compito":
            assert CAMPI_DEL_PROJECT[nome] == ("SINGLE_SELECT", misure.OPZIONI_ESITO)
        else:
            assert CAMPI_DEL_PROJECT[nome] == (tipo, ())


def test_campi_mancanti_ordine() -> None:
    tutti = list(CAMPI_DEL_PROJECT.keys())
    assert campi_mancanti([]) == tutti
    assert campi_mancanti(tutti) == []

    # Se togliamo alcuni campi, l'ordine deve rispettare esattamente CAMPI_DEL_PROJECT
    esistenti = [tutti[0], tutti[2], tutti[4]]
    mancanti = campi_mancanti(esistenti)
    attesi = [k for k in tutti if k not in esistenti]
    assert mancanti == attesi


def test_mutazione_campo_scelta() -> None:
    mut = mutazione_campo("PVT_123", "Bottega")
    assert "createProjectV2Field" in mut
    assert '"PVT_123"' in mut
    assert "dataType: SINGLE_SELECT" in mut
    assert '"Bottega"' in mut
    assert "singleSelectOptions:" in mut

    # Colori assegnati in ordine alle opzioni di Bottega: pronto, in corso, in attesa, consegnato, bloccato
    assert '{ name: "pronto", color: GRAY, description: "" }' in mut
    assert '{ name: "in corso", color: BLUE, description: "" }' in mut
    assert '{ name: "in attesa", color: YELLOW, description: "" }' in mut
    assert '{ name: "consegnato", color: ORANGE, description: "" }' in mut
    assert '{ name: "bloccato", color: GREEN, description: "" }' in mut


def test_mutazione_campo_numero() -> None:
    mut = mutazione_campo("PVT_123", "Durata")
    assert "createProjectV2Field" in mut
    assert '"PVT_123"' in mut
    assert "dataType: NUMBER" in mut
    assert '"Durata"' in mut
    assert "singleSelectOptions" not in mut

    mut_text = mutazione_campo("PVT_123", "Esecutore")
    assert "dataType: TEXT" in mut_text
    assert '"Esecutore"' in mut_text
    assert "singleSelectOptions" not in mut_text


def test_crea_campi_rifatta_niente() -> None:
    # 1. Quando tutti i campi esistono già, non crea nulla
    tutti_i_nodi = [{"id": f"f_{i}", "name": nome} for i, nome in enumerate(CAMPI_DEL_PROJECT.keys())]
    risposta_piena = json.dumps({
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_PROGETTO",
                    "fields": {"nodes": tutti_i_nodi},
                }
            }
        }
    })

    chiamate_gh: list[list[str]] = []

    def esegui_pieno(args: list[str]) -> str:
        chiamate_gh.append(args)
        return risposta_piena

    creati = crea_campi(esegui_pieno, "proprietario", 1)
    assert creati == []
    # Solo la query iniziale, nessuna mutazione
    assert len(chiamate_gh) == 1

    # 2. Quando mancano dei campi, crea solo quelli mancanti nell'ordine
    chiamate_gh.clear()
    nodi_parziali = [{"id": "f_0", "name": "Bottega"}]
    risposta_parziale = json.dumps({
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_PROGETTO",
                    "fields": {"nodes": nodi_parziali},
                }
            }
        }
    })

    def esegui_parziale(args: list[str]) -> str:
        chiamate_gh.append(args)
        if "createProjectV2Field" in " ".join(args):
            return json.dumps({"data": {"createProjectV2Field": {"projectV2Field": {"id": "new"}}}})
        return risposta_parziale

    creati2 = crea_campi(esegui_parziale, "proprietario", 1)
    attesi = [k for k in CAMPI_DEL_PROJECT.keys() if k != "Bottega"]
    assert creati2 == attesi
    assert len(chiamate_gh) == 1 + len(attesi)


def test_cron_della_notte_estate_e_inverno() -> None:
    # Estate: 15 luglio (CEST, UTC+2)
    # Ora locale 01:30 -> in UTC sono le 23:30 del giorno prima
    cron_estate = cron_della_notte("01:30", "Europe/Rome", date(2026, 7, 15))
    assert cron_estate == "30 23 * * *"

    # Inverno: 15 gennaio (CET, UTC+1)
    # Ora locale 01:30 -> in UTC sono le 00:30 dello stesso giorno
    cron_inverno = cron_della_notte("01:30", "Europe/Rome", date(2026, 1, 15))
    assert cron_inverno == "30 0 * * *"


def test_rendi_modello_segnaposto_rimasto() -> None:
    modello = "uses: <proprietario>/repo@<sha>\nref: <tag>"
    # Sostituzione parziale: <sha> e <tag> rimangono
    with pytest.raises(ErroreProgetto, match="<sha>"):
        rendi_modello(modello, {"proprietario": "utente"})

    # Sostituzione completa
    fatto = rendi_modello(modello, {"proprietario": "utente", "sha": "123", "tag": "v1"})
    assert fatto == "uses: utente/repo@123\nref: v1"


def test_file_dell_installazione_non_sovrascrive() -> None:
    cfg = _configurazione_prova()
    valori = {
        ".github/bottega/bottega.toml": "versione = 1\n",
        "proprietario": "mio-utente",
        "sha": "0123456789abcdef0123456789abcdef01234567",
        "tag": "v1.0.0",
        "etichetta del runner": "runner-principale",
        "id": "principale",
    }

    # Caso 1: AGENTS.md e costituzione esistono già -> non devono comparire nei file da scrivere
    esistenti = ["AGENTS.md", "docs/costituzione.md"]
    file_pr = file_dell_installazione(cfg, valori, esistenti)
    assert "AGENTS.md" not in file_pr
    assert "docs/costituzione.md" not in file_pr
    assert ".github/bottega/bottega.toml" in file_pr
    assert ".github/workflows/bottega-distributore.yml" in file_pr
    assert ".github/workflows/bottega-esecutore-principale.yml" in file_pr

    # Verifica che il workflow distributore contenga il commento sull'ora legale
    dist_wf = file_pr[".github/workflows/bottega-distributore.yml"]
    assert "l'ora legale cambia lo scarto" in dist_wf
    assert "cron:" in dist_wf
    assert "<proprietario>" not in dist_wf
    assert "<sha>" not in dist_wf

    # Caso 2: AGENTS.md e costituzione mancano -> devono comparire nei file da scrivere
    file_completi = file_dell_installazione(cfg, valori, [])
    assert "AGENTS.md" in file_completi
    assert "docs/costituzione.md" in file_completi
    assert ".github/bottega/bottega.toml" in file_completi


def test_token_mai_stampato(capsys: pytest.CaptureFixture[str]) -> None:
    token_finto = "ghp_TOKEN_SEGRETISSIMO_1234567890"
    comandi_eseguiti: list[tuple[list[str], list[str]]] = []

    def esegui_pipe_finto(cmd1: list[str], cmd2: list[str]) -> int:
        comandi_eseguiti.append((cmd1, cmd2))
        return 0

    esito = imposta_segreto("proprietario/repo", "utente-runner", esegui_pipe=esegui_pipe_finto)
    assert esito is True

    # Comandi attesi
    assert len(comandi_eseguiti) == 1
    cmd1, cmd2 = comandi_eseguiti[0]
    assert cmd1 == ["sudo", "-n", "-u", "utente-runner", "-H", "gh", "auth", "token"]
    assert cmd2 == ["gh", "secret", "set", "BOTTEGA_TOKEN", "--repo", "proprietario/repo"]

    # Il token non deve mai finire nei buffer o nell'output
    catturato = capsys.readouterr()
    assert token_finto not in catturato.out
    assert token_finto not in catturato.err


def test_imposta_segreto_fallisce() -> None:
    def pipe_errore(cmd1: list[str], cmd2: list[str]) -> int:
        return 1

    assert imposta_segreto("proprietario/repo", "runner", esegui_pipe=pipe_errore) is False

    def pipe_eccezione(cmd1: list[str], cmd2: list[str]) -> int:
        raise OSError("Pipe rotta")

    assert imposta_segreto("proprietario/repo", "runner", esegui_pipe=pipe_eccezione) is False


def test_ferma_e_riparti() -> None:
    chiamate: list[list[str]] = []
    stato_wf = {
        ".github/workflows/bottega-distributore.yml": "active",
        ".github/workflows/bottega-esecutore-principale.yml": "active",
        ".github/workflows/ci.yml": "active",
    }

    def esegui_gh(args: list[str]) -> str:
        chiamate.append(args)
        if args[:2] == ["workflow", "list"]:
            return json.dumps([{"path": p, "state": s} for p, s in stato_wf.items()])
        if len(args) >= 3 and args[0] == "workflow":
            if args[1] == "disable":
                stato_wf[args[2]] = "disabled_manually"
            elif args[1] == "enable":
                stato_wf[args[2]] = "active"
        return ""

    # Ferma
    wfs_fermati = ferma(esegui_gh, "proprietario/repo")
    assert wfs_fermati == [
        ".github/workflows/bottega-distributore.yml",
        ".github/workflows/bottega-esecutore-principale.yml",
    ]
    cmd_dist_dis = ["workflow", "disable", ".github/workflows/bottega-distributore.yml", "--repo", "proprietario/repo"]
    cmd_esec_dis = [
        "workflow", "disable", ".github/workflows/bottega-esecutore-principale.yml", "--repo", "proprietario/repo"
    ]
    assert cmd_dist_dis in chiamate
    assert cmd_esec_dis in chiamate
    assert not any(c[1] == "disable" and c[2] == ".github/workflows/ci.yml" for c in chiamate)

    # Riparti
    chiamate.clear()
    wfs_ripartiti = riparti(esegui_gh, "proprietario/repo")
    assert wfs_ripartiti == [
        ".github/workflows/bottega-distributore.yml",
        ".github/workflows/bottega-esecutore-principale.yml",
    ]
    cmd_dist_en = ["workflow", "enable", ".github/workflows/bottega-distributore.yml", "--repo", "proprietario/repo"]
    cmd_esec_en = [
        "workflow", "enable", ".github/workflows/bottega-esecutore-principale.yml", "--repo", "proprietario/repo"
    ]
    assert cmd_dist_en in chiamate
    assert cmd_esec_en in chiamate
    assert not any(c[1] == "enable" and c[2] == ".github/workflows/ci.yml" for c in chiamate)


def test_aggiorna_chiamanti() -> None:
    testi = {
        ".github/workflows/bottega-distributore.yml": (
            "uses: altro/bottega/.github/workflows/distributore.yml@1111111111111111111111111111111111111111\n"
            "with:\n"
            "  bottega_ref: v0.1.0\n"
        ),
        ".github/workflows/bottega-esecutore-p.yml": (
            "uses: altro/bottega/.github/workflows/esecutore.yml@1111111111111111111111111111111111111111\n"
            "with:\n"
            "  bottega_ref: v0.1.0\n"
        ),
    }
    nuovo_sha = "2222222222222222222222222222222222222222"
    nuovo_tag = "v0.2.0"

    aggiornati = aggiorna_chiamanti(testi, nuovo_sha, nuovo_tag, "proprietario/bottega")
    for path, testo in aggiornati.items():
        assert f"uses: proprietario/bottega/" in testo
        assert f"@{nuovo_sha} # {nuovo_tag}" in testo
        assert "@1111111111111111111111111111111111111111" not in testo
        assert f"bottega_ref: {nuovo_sha}" in testo
        assert "bottega_ref: v0.1.0" not in testo


def test_aggiorna_sha_non_valido() -> None:
    testi = {".github/workflows/wf.yml": "uses: bottega@123\n"}
    with pytest.raises(ErroreProgetto, match="SHA non valido"):
        aggiorna_chiamanti(testi, "non-40-hex", "v1.0.0", "proprietario/bottega")

    with pytest.raises(ErroreProgetto, match="SHA non valido"):
        aggiorna_chiamanti(testi, "g" * 40, "v1.0.0", "proprietario/bottega")


def test_g3_bottega_ref_e_lo_sha() -> None:
    """G3: i workflow generati da file_dell_installazione hanno bottega_ref fissato allo SHA e @<sha> # <tag>."""
    cfg = _configurazione_prova()
    sha = "3" * 40
    tag = "v1.2.3"
    valori = {
        "proprietario": "prop",
        "sha": sha,
        "tag": tag,
        "etichetta del runner": "r-1",
        "id": "principale",
    }
    file_pr = file_dell_installazione(cfg, valori, [])
    for nome in (".github/workflows/bottega-distributore.yml", ".github/workflows/bottega-esecutore-principale.yml"):
        testo = file_pr[nome]
        assert f"bottega_ref: {sha}" in testo
        assert f"@{sha} # {tag}" in testo
        assert f"bottega_ref: {tag}" not in testo


def test_m1_aggiorna_lascia_le_altre_azioni() -> None:
    """M1: aggiorna_chiamanti riscrive solo uses della bottega; le altre azioni (actions/checkout@v4) restano intatte."""
    testo = (
        "jobs:\n"
        "  esegui:\n"
        "    uses: altro/bottega/.github/workflows/esecutore.yml@1111111111111111111111111111111111111111\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
    )
    sha = "4" * 40
    out = aggiorna_chiamanti({"wf.yml": testo}, sha, "v2.0.0", "nuovo/bottega")["wf.yml"]
    assert "actions/checkout@v4" in out
    assert f"uses: nuovo/bottega/.github/workflows/esecutore.yml@{sha} # v2.0.0" in out


def test_m1_aggiorna_riscrive_il_repo_della_bottega() -> None:
    """M1: aggiorna_chiamanti riscrive il repo della bottega sia nell'uses che in bottega_repo."""
    testo = (
        "jobs:\n"
        "  a:\n"
        "    uses: vecchio/bottega/.github/workflows/distributore.yml@1111111111111111111111111111111111111111\n"
        "    with:\n"
        "      bottega_repo: vecchio/bottega\n"
        "      bottega_ref: 1111111111111111111111111111111111111111\n"
    )
    sha = "5" * 40
    out = aggiorna_chiamanti({"wf.yml": testo}, sha, "v3.0.0", "mio/bottega")["wf.yml"]
    assert f"uses: mio/bottega/.github/workflows/distributore.yml@{sha} # v3.0.0" in out
    assert "bottega_repo: mio/bottega" in out
    assert f"bottega_ref: {sha}" in out


def test_m1_aggiorna_senza_chiamata_e_un_errore() -> None:
    """M1: aggiorna_chiamanti solleva ErroreProgetto se un file non contiene nessuna chiamata a un workflow bottega."""
    testo = "jobs:\n  a:\n    uses: actions/checkout@v4\n"
    with pytest.raises(ErroreProgetto, match="nessuna chiamata a un workflow della bottega"):
        aggiorna_chiamanti({"wf.yml": testo}, "6" * 40, "v4.0.0", "mio/bottega")


def test_g5_riparti_vede_i_disabilitati() -> None:
    chiamate: list[list[str]] = []

    def esegui_gh(args: list[str]) -> str:
        chiamate.append(args)
        # Il finto risponde coi workflow disabled_manually solo se il comando ha --all
        if "--all" in args and args[:2] == ["workflow", "list"]:
            return json.dumps([
                {"path": ".github/workflows/bottega-distributore.yml", "state": "disabled_manually"},
                {"path": ".github/workflows/bottega-esecutore-principale.yml", "state": "disabled_manually"},
            ])
        if args[:2] == ["workflow", "list"]:
            # Senza --all non compaiono i disabilitati
            return json.dumps([])
        return ""

    wfs = riparti(esegui_gh, "owner/repo")
    assert wfs == [
        ".github/workflows/bottega-distributore.yml",
        ".github/workflows/bottega-esecutore-principale.yml",
    ]
    assert any(
        c == ["workflow", "list", "--all", "--limit", "200", "--repo", "owner/repo", "--json", "path,state"]
        for c in chiamate
    )


def test_g5_ferma_e_riparti_guardano_lo_stato() -> None:
    """G5: ferma disabilita solo workflow active, riparti abilita solo workflow con state != active."""
    chiamate: list[list[str]] = []

    # Un workflow è active, l'altro è disabled_manually, ci.yml non è bottega
    risposta_wf = json.dumps([
        {"path": ".github/workflows/bottega-distributore.yml", "state": "active"},
        {"path": ".github/workflows/bottega-esecutore-principale.yml", "state": "disabled_manually"},
        {"path": ".github/workflows/ci.yml", "state": "active"},
    ])

    def esegui_gh(args: list[str]) -> str:
        chiamate.append(args)
        if args[:2] == ["workflow", "list"]:
            return risposta_wf
        return ""

    # 1. ferma disabilita SOLO quello active
    toccati_ferma = ferma(esegui_gh, "owner/repo")
    assert toccati_ferma == [".github/workflows/bottega-distributore.yml"]
    cmd_list_atteso = ["workflow", "list", "--all", "--limit", "200", "--repo", "owner/repo", "--json", "path,state"]
    assert cmd_list_atteso in chiamate
    assert ["workflow", "disable", ".github/workflows/bottega-distributore.yml", "--repo", "owner/repo"] in chiamate
    # NON deve disabilitare quello già spento né ci.yml
    assert not any(c[0] == "workflow" and c[1] == "disable" and "bottega-esecutore" in c[2] for c in chiamate)
    assert not any(c[0] == "workflow" and c[1] == "disable" and "ci.yml" in c[2] for c in chiamate)

    # 2. riparti abilita SOLO quello con state != active
    chiamate.clear()
    toccati_riparti = riparti(esegui_gh, "owner/repo")
    assert toccati_riparti == [".github/workflows/bottega-esecutore-principale.yml"]
    assert cmd_list_atteso in chiamate
    assert ["workflow", "enable", ".github/workflows/bottega-esecutore-principale.yml", "--repo", "owner/repo"] in chiamate
    # NON deve abilitare quello già attivo né ci.yml
    assert not any(c[0] == "workflow" and c[1] == "enable" and "bottega-distributore" in c[2] for c in chiamate)
    assert not any(c[0] == "workflow" and c[1] == "enable" and "ci.yml" in c[2] for c in chiamate)


def test_c3_ferma_spegne_lo_stato_mancante() -> None:
    """C3: ferma spegne anche un workflow con stato mancante o vuoto."""
    chiamate: list[list[str]] = []
    risposta_wf = json.dumps([
        {"path": ".github/workflows/bottega-distributore.yml"},  # stato assente
        {"path": ".github/workflows/bottega-esecutore-principale.yml", "state": ""},  # stato vuoto
        {"path": ".github/workflows/bottega-altri.yml", "state": "disabled_manually"},
    ])

    def esegui_gh(args: list[str]) -> str:
        chiamate.append(args)
        if args[:2] == ["workflow", "list"]:
            return risposta_wf
        return ""

    toccati = ferma(esegui_gh, "owner/repo")
    assert ".github/workflows/bottega-distributore.yml" in toccati
    assert ".github/workflows/bottega-esecutore-principale.yml" in toccati
    assert ".github/workflows/bottega-altri.yml" not in toccati
    assert ["workflow", "disable", ".github/workflows/bottega-distributore.yml", "--repo", "owner/repo"] in chiamate
    assert ["workflow", "disable", ".github/workflows/bottega-esecutore-principale.yml", "--repo", "owner/repo"] in chiamate


def test_c3_riparti_non_tocca_i_cancellati() -> None:
    """C3: riparti non tocca deleted e active, ma abilita disabled_manually e disabled_inactivity."""
    chiamate: list[list[str]] = []
    risposta_wf = json.dumps([
        {"path": ".github/workflows/bottega-attivo.yml", "state": "active"},
        {"path": ".github/workflows/bottega-cancellato.yml", "state": "deleted"},
        {"path": ".github/workflows/bottega-manualmente.yml", "state": "disabled_manually"},
        {"path": ".github/workflows/bottega-inattivita.yml", "state": "disabled_inactivity"},
    ])

    def esegui_gh(args: list[str]) -> str:
        chiamate.append(args)
        if args[:2] == ["workflow", "list"]:
            return risposta_wf
        return ""

    toccati = riparti(esegui_gh, "owner/repo")
    assert ".github/workflows/bottega-manualmente.yml" in toccati
    assert ".github/workflows/bottega-inattivita.yml" in toccati
    assert ".github/workflows/bottega-attivo.yml" not in toccati
    assert ".github/workflows/bottega-cancellato.yml" not in toccati
    assert ["workflow", "enable", ".github/workflows/bottega-manualmente.yml", "--repo", "owner/repo"] in chiamate
    assert ["workflow", "enable", ".github/workflows/bottega-inattivita.yml", "--repo", "owner/repo"] in chiamate
    assert not any(c[0] == "workflow" and c[1] == "enable" and "cancellato" in c[2] for c in chiamate)
    assert not any(c[0] == "workflow" and c[1] == "enable" and "attivo" in c[2] for c in chiamate)



