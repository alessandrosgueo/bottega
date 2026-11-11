"""Comando bottega installa e comandi collegati ferma, riparti, aggiorna (Compito B6.5).

Lega la preparazione della macchina, l'installazione del runner e la configurazione del progetto su GitHub.
Solo libreria standard.
"""

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import platform
import re
import sys

from bottega.ci import rischi, rischi_del_ramo
from bottega.configurazione import ErroreConfigurazione, leggi_configurazione
from bottega.forgia import ErroreForgia, Forgia, ForgiaGh
from bottega.macchina import (
    ErroreMacchina,
    Esecutore,
    Utenti,
    esecutore_vero,
    esegui_passi,
    passi_macchina,
    passi_runner,
    sha_della_release,
    systemd_attivo,
)
from bottega.progetto import (
    CAMPI_DEL_PROJECT,
    ErroreProgetto,
    aggiorna_chiamanti,
    campi_mancanti,
    crea_campi,
    ferma,
    file_dell_installazione,
    imposta_segreto,
    riparti,
)


def _adatta_esegui_gh(esegui: Esecutore) -> Callable[[list[str]], str]:
    """Adatta un Esecutore generico alla funzione attesa dalle API di progetto (esegui_gh)."""

    def esegui_gh(cmd: list[str]) -> str:
        codice, uscita = esegui(["gh", *cmd], None)
        if codice != 0:
            raise ErroreForgia(uscita.strip() or f"gh codice {codice}")
        return uscita

    return esegui_gh


def _adatta_forgia_gh(esegui: Esecutore, repo: str) -> ForgiaGh:
    """Crea un'istanza di ForgiaGh che usa l'esecutore iniettato per eseguire gh."""

    def forgia_esegui(cmd: list[str], ingresso: str | None = None) -> str:
        codice, uscita = esegui(["gh", *cmd], None)
        if codice != 0:
            raise ErroreForgia(uscita.strip() or f"gh codice {codice}")
        return uscita

    return ForgiaGh(repo, esegui=forgia_esegui)


# La radice del clone della bottega da cui gira il comando (attrezzi/bottega/installa.py → radice).
_RADICE_BOTTEGA = Path(__file__).resolve().parent.parent.parent
_REPO_VALIDO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# Un tag finisce nell'indirizzo dell'API, nel nome di un ramo e nel YAML dei workflow: solo caratteri innocui.
_TAG_VALIDO = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,99}")


def _repo_della_bottega(scelto: str | None, esegui: Esecutore) -> str | None:
    """OWNER/REPO della bottega: quello scelto con --bottega, altrimenti l'origin del clone della bottega stessa
    (mai quello del progetto, che è la cartella corrente)."""
    repo = scelto
    if not repo:
        cod, url = esegui(["git", "-C", str(_RADICE_BOTTEGA), "remote", "get-url", "origin"], None)
        repo = _estrai_owner_repo(url) if cod == 0 else None
    if not repo or not _REPO_VALIDO.fullmatch(repo):
        return None
    return repo


def _sha_del_tag(esegui: Esecutore, repo_bottega: str, tag: str) -> str | None:
    """Lo SHA del commit del tag nel repo della bottega, o None: mai un valore inventato.

    Si legge `refs/tags/<tag>` (M2: `commits/<x>` risolverebbe anche un ramo o uno SHA, compresi i commit dei fork); un
    tag annotato si segue fino al suo commit.
    """
    domanda = f"repos/{repo_bottega}/git/ref/tags/{tag}"
    for _ in range(3):
        cod, out = esegui(["gh", "api", domanda, "--jq", '.object.type + " " + .object.sha'], None)
        if cod != 0:
            return None
        parti = out.split()
        if len(parti) != 2 or not re.fullmatch(r"[0-9a-fA-F]{40}", parti[1]):
            return None
        tipo, sha = parti
        if tipo == "commit":
            return sha.lower()
        if tipo != "tag":
            return None
        domanda = f"repos/{repo_bottega}/git/tags/{sha}"
    return None


def _architettura_di_serie() -> str | None:
    """Rileva l'architettura della macchina (x64, arm64, arm), o None se sconosciuta."""
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "x64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m.startswith("arm"):
        return "arm"
    return None


def comando_macchina(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
) -> int:
    """Prepara la macchina host per la bottega (utenti, gruppo, spazio, sudoers)."""
    esegui_fn = esegui or esecutore_vero
    if not systemd_attivo(esegui_fn):
        print(
            "errore: systemd non è attivo. Su WSL aggiungere [boot] systemd=true in /etc/wsl.conf "
            "e riavviare con 'wsl --shutdown'",
            file=sys.stderr,
        )
        return 2

    runner = getattr(args, "runner", "bottega-runner")
    esecutore = getattr(args, "esecutore", "bottega-esecutore")
    gruppo = getattr(args, "gruppo", "bottega")
    try:
        u = Utenti(runner=runner, esecutore=esecutore, gruppo=gruppo)
    except ValueError as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
    passi = passi_macchina(u)
    prova = getattr(args, "prova", False)

    try:
        righe = esegui_passi(passi, esegui_fn, prova=prova)
        for riga in righe:
            print(riga)
        return 0
    except ErroreMacchina as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1


def comando_runner(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
) -> int:
    """Installa e registra il runner self-hosted di GitHub Actions."""
    esegui_fn = esegui or esecutore_vero
    prova = getattr(args, "prova", False)
    arch = getattr(args, "arch", None) or _architettura_di_serie()
    if not arch:
        print("errore: architettura sconosciuta, usa --arch", file=sys.stderr)
        return 2

    # Su una macchina dove chi installa non ha `gh` collegato, le chiamate a GitHub passano dall'accesso del runner
    # (fatto prima, INSTALLA §5), senza un secondo login.
    gh: list[str] = ["gh"]
    if getattr(args, "gh_del_runner", False):
        gh = ["sudo", "-n", "-u", getattr(args, "runner", "bottega-runner"), "-H", "gh"]

    porte: dict[str, str] = {}
    for p in getattr(args, "porta", []) or []:
        if "=" not in p:
            print(f"errore: --porta deve essere NOME=PERCORSO, ricevuto: {p}", file=sys.stderr)
            return 2
        k, v = p.split("=", 1)
        porte[k.strip()] = v.strip()

    versione = getattr(args, "versione", None)
    if versione:
        tag = f"v{versione}" if not versione.startswith("v") else versione
        versione_pulita = tag.lstrip("v")
        cmd_rel = [*gh, "api", f"repos/actions/runner/releases/tags/{tag}"]
    else:
        cmd_rel = [*gh, "api", "repos/actions/runner/releases/latest"]
        versione_pulita = None

    cod_rel, out_rel = esegui_fn(cmd_rel, None)
    if cod_rel != 0:
        print(f"errore: impossibile ottenere la release del runner: {out_rel.strip()}", file=sys.stderr)
        return 1

    try:
        dati_rel = json.loads(out_rel)
    except Exception as e:
        print(f"errore nel JSON della release del runner: {e}", file=sys.stderr)
        return 1

    if versione_pulita is None:
        tag_name = dati_rel.get("tag_name", "")
        versione_pulita = tag_name.lstrip("v")
        if not versione_pulita:
            print("errore: tag_name mancante nella release del runner", file=sys.stderr)
            return 1

    corpo = dati_rel.get("body", "")
    sha = sha_della_release(corpo, arch)
    if not sha:
        print(f"errore: sha256 non trovato nella release per architettura linux-{arch}", file=sys.stderr)
        return 1

    try:
        passi_runner(
            u=Utenti(
                runner=getattr(args, "runner", "bottega-runner"),
                esecutore=getattr(args, "esecutore", "bottega-esecutore"),
                gruppo=getattr(args, "gruppo", "bottega"),
            ),
            repo=args.repo,
            versione=versione_pulita,
            arch=arch,
            sha256=sha,
            etichetta=args.etichetta,
            nome=args.nome,
            porte=porte,
            tetto=getattr(args, "tetto", None),
        )
    except ValueError as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2

    token = ""
    if not prova:
        cmd_tok = [
            *gh,
            "api",
            "-X",
            "POST",
            f"repos/{args.repo}/actions/runners/registration-token",
            "--jq",
            ".token",
        ]
        cod_tok, out_tok = esegui_fn(cmd_tok, None)
        if cod_tok != 0:
            print(f"errore nell'ottenimento del token di registrazione: {out_tok.strip()}", file=sys.stderr)
            return 1
        token = out_tok.strip()
        if not token:
            print("errore: token di registrazione vuoto", file=sys.stderr)
            return 1

    runner_utente = getattr(args, "runner", "bottega-runner")
    esecutore_utente = getattr(args, "esecutore", "bottega-esecutore")
    gruppo = getattr(args, "gruppo", "bottega")
    try:
        u = Utenti(runner=runner_utente, esecutore=esecutore_utente, gruppo=gruppo)
    except ValueError as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2

    passi = passi_runner(
        u=u,
        repo=args.repo,
        versione=versione_pulita,
        arch=arch,
        sha256=sha,
        etichetta=args.etichetta,
        nome=args.nome,
        porte=porte,
        token=token,
        tetto=getattr(args, "tetto", None),
    )

    try:
        righe = esegui_passi(passi, esegui_fn, prova=prova)
        for riga in righe:
            print(riga)
        return 0
    except ErroreMacchina as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1


def _query_campi_mancanti(esegui_gh: Callable[[list[str]], str], proprietario: str, numero: int) -> list[str]:
    """Interroga in sola lettura i campi esistenti del Project e restituisce i mancanti."""
    from bottega.progetto import _QUERY_PROJECT_ORG, _QUERY_PROJECT_USER

    cmd_user = [
        "api",
        "graphql",
        "-f",
        f"owner={proprietario}",
        "-F",
        f"number={numero}",
        "-f",
        f"query={_QUERY_PROJECT_USER}",
    ]
    try:
        out_user = esegui_gh(cmd_user)
        data = json.loads(out_user) if out_user else {}
    except Exception:
        data = {}
    proj = data.get("data", {}).get("user", {}).get("projectV2") if data.get("data") else None
    if not proj:
        cmd_org = [
            "api",
            "graphql",
            "-f",
            f"owner={proprietario}",
            "-F",
            f"number={numero}",
            "-f",
            f"query={_QUERY_PROJECT_ORG}",
        ]
        try:
            out_org = esegui_gh(cmd_org)
            data_org = json.loads(out_org) if out_org else {}
        except Exception:
            data_org = {}
        proj = data_org.get("data", {}).get("organization", {}).get("projectV2") if data_org.get("data") else None

    if not proj:
        return list(CAMPI_DEL_PROJECT.keys())

    fields_nodes = proj.get("fields", {}).get("nodes", [])
    esistenti = [f["name"] for f in fields_nodes if isinstance(f, dict) and "name" in f]
    return campi_mancanti(esistenti)


def comando_progetto(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
    forgia: Forgia | None = None,
    esegui_pipe: Callable[[list[str], list[str]], int] | None = None,
) -> int:
    """Configura il progetto su GitHub: controlla CI, prepara file, ramo, PR in bozza e segreto."""
    esegui_fn = esegui or esecutore_vero
    cartella = getattr(args, "cartella", None) or Path.cwd()
    prova = getattr(args, "prova", False)

    # 1. Parsing valori
    valori: dict[str, str] = {}
    for item in getattr(args, "valore", []) or []:
        if "=" not in item:
            print(f"errore: --valore deve essere CHIAVE=VALORE, ricevuto: {item}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        valori[k.strip()] = v.strip()

    # 2. Lettura configurazione
    cfg_path = Path(args.configurazione)
    if not cfg_path.is_file():
        print(f"errore: configurazione non trovata: {cfg_path}", file=sys.stderr)
        return 2
    try:
        cfg = leggi_configurazione(cfg_path)
    except ErroreConfigurazione as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1

    # 3. Controllo rischi CI
    wf_dir = cartella / ".github" / "workflows"
    avvisi = []
    if wf_dir.is_dir():
        testi_wf: dict[str, str] = {}
        for p in sorted(wf_dir.glob("*.y*ml")):
            if p.is_file():
                try:
                    rel = str(p.relative_to(cartella))
                except ValueError:
                    rel = str(p)
                testi_wf[rel] = p.read_text(encoding="utf-8", errors="replace")
        avvisi.extend(rischi(testi_wf))

    forgia_inst = forgia or _adatta_forgia_gh(esegui_fn, args.repo)
    if (cartella / ".git").exists():
        try:
            ramo_principale = forgia_inst.ramo_principale()
            cod_f, out_f = esegui_fn(["git", "-C", str(cartella), "fetch", "origin", ramo_principale], None)
            if cod_f != 0:
                print(f"errore git fetch: {out_f.strip()}", file=sys.stderr)
                return 1
            avvisi.extend(rischi_del_ramo(cartella, ramo_principale))
        except ErroreForgia as e:
            print(f"errore: {e}", file=sys.stderr)
            return 1

    if avvisi:
        for r in avvisi:
            print(f"rischio: {r.file}: {r.motivo}")
        return 1

    # 4. Controllo ramo bottega/installazione
    cod_br, _ = esegui_fn(["git", "-C", str(cartella), "rev-parse", "--verify", "bottega/installazione"], None)
    if cod_br == 0:
        print("errore: il ramo bottega/installazione esiste già", file=sys.stderr)
        return 1
    cod_rem, out_rem = esegui_fn(
        ["git", "-C", str(cartella), "ls-remote", "--heads", "origin", "bottega/installazione"], None
    )
    if cod_rem == 0 and out_rem.strip():
        print("errore: il ramo bottega/installazione esiste già su origin", file=sys.stderr)
        return 1

    # 5. File esistenti per la preparazione
    esistenti_file: list[str] = []
    if cartella.is_dir():
        for p in cartella.rglob("*"):
            if p.is_file():
                try:
                    rel = str(p.relative_to(cartella))
                    if not rel.startswith(".git/"):
                        esistenti_file.append(rel)
                except ValueError:
                    pass

    percorso_firme = ".github/bottega/firme-ammesse"
    ha_firme = (cartella / percorso_firme).is_file()
    solo_sessione = getattr(args, "solo_sessione", False)

    proprietario = args.repo.split("/", 1)[0]
    if ".github/bottega/bottega.toml" not in valori and "bottega.toml" not in valori:
        valori[".github/bottega/bottega.toml"] = cfg_path.read_text(encoding="utf-8")

    if solo_sessione:
        file_preparati = {
            ".github/bottega/bottega.toml": (
                valori.get(".github/bottega/bottega.toml") or cfg_path.read_text(encoding="utf-8")
            )
        }
    else:
        tag = getattr(args, "tag", None)
        if not tag:
            print("errore: il tag è obbligatorio senza --solo-sessione", file=sys.stderr)
            return 2

        # I workflow chiamanti puntano al repo della bottega, a un commit fissato: proprietario, tag e SHA vengono solo
        # da lì (B6-R13), mai dal progetto, da --valore o da un valore di serie.
        for chiave in ("proprietario", "tag", "sha"):
            if chiave in valori:
                print(f"errore: {chiave} viene dal repo della bottega, non da --valore", file=sys.stderr)
                return 2
        if not _TAG_VALIDO.fullmatch(tag):
            print("errore: tag non valido", file=sys.stderr)
            return 2
        repo_bottega = _repo_della_bottega(getattr(args, "bottega", None), esegui_fn)
        if not repo_bottega:
            print("errore: non trovo il repo della bottega dal suo origin; usa --bottega OWNER/REPO", file=sys.stderr)
            return 2
        if repo_bottega.split("/", 1)[1] != "bottega":
            print(
                f"errore: i modelli dei workflow chiamano <proprietario>/bottega, e il repo della bottega è {repo_bottega}",
                file=sys.stderr,
            )
            return 2
        sha = _sha_del_tag(esegui_fn, repo_bottega, tag)
        if not sha:
            print(f"errore: non trovo lo SHA del tag {tag} in {repo_bottega}", file=sys.stderr)
            return 1
        valori["proprietario"] = repo_bottega.split("/", 1)[0]
        valori["tag"] = tag
        valori["sha"] = sha

        try:
            file_preparati = file_dell_installazione(cfg, valori, esistenti_file)
        except Exception as e:
            print(f"errore nella preparazione dei file: {e}", file=sys.stderr)
            return 1
    esegui_gh = _adatta_esegui_gh(esegui_fn)

    # 6. Modalità --prova
    if prova:
        try:
            mancanti = _query_campi_mancanti(esegui_gh, proprietario, args.project)
        except Exception:
            mancanti = list(CAMPI_DEL_PROJECT.keys())
        for f in sorted(file_preparati.keys()):
            print(f"scriverei: {f}")
        if ha_firme:
            print(f"includerei: {percorso_firme}")
        for c in mancanti:
            print(f"creerei campo: {c}")
        print("etichetta: bottega: fuori")
        return 0

    # 7. Creazione campi mancanti
    try:
        creati = crea_campi(esegui_gh, proprietario, args.project)
        for c in creati:
            print(f"creato campo: {c}")
    except Exception as e:
        print(f"errore nella creazione dei campi del Project: {e}", file=sys.stderr)
        return 1

    try:
        esegui_gh([
            "label",
            "create",
            "bottega: fuori",
            "--repo",
            args.repo,
            "--color",
            "5319E7",
            "--description",
            "Lavoro per l'esecutore fuori della bottega",
            "--force",
        ])
    except Exception as e:
        print(f"errore nella creazione dell'etichetta: {e}", file=sys.stderr)
        return 1

    # 8. Scrittura dei file
    for p_rel, testo in file_preparati.items():
        dest = cartella / p_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(testo, encoding="utf-8")

    # 9. Operazioni Git
    cod, out = esegui_fn(["git", "-C", str(cartella), "switch", "-c", "bottega/installazione"], None)
    if cod != 0:
        print(f"errore git switch: {out.strip()}", file=sys.stderr)
        return 1

    file_da_aggiungere = list(file_preparati.keys())
    if ha_firme and percorso_firme not in file_da_aggiungere:
        file_da_aggiungere.append(percorso_firme)

    cod, out = esegui_fn(["git", "-C", str(cartella), "add", *file_da_aggiungere], None)
    if cod != 0:
        print(f"errore git add: {out.strip()}", file=sys.stderr)
        return 1

    cod, out = esegui_fn(["git", "-C", str(cartella), "commit", "-m", "Installa la bottega"], None)
    if cod != 0:
        print(f"errore git commit: {out.strip()}", file=sys.stderr)
        return 1

    cod, out = esegui_fn(["git", "-C", str(cartella), "push", "-u", "origin", "bottega/installazione"], None)
    if cod != 0:
        print(f"errore git push: {out.strip()}", file=sys.stderr)
        return 1

    # 10. Apertura PR in bozza
    try:
        pr_num = forgia_inst.apri_pr("bottega/installazione", "Installa la bottega", "Installazione della bottega.")
        print(f"aperta PR #{pr_num}")
    except Exception as e:
        print(f"errore nell'apertura della PR: {e}", file=sys.stderr)
        return 1

    # 11. Impostazione segreto
    if not solo_sessione and getattr(args, "senza_segreto", False):
        # Chi installa il progetto non è sulla macchina del runner: il segreto si mette da lì, dal suo accesso.
        runner_utente = getattr(args, "runner", "bottega-runner")
        print(
            "segreto BOTTEGA_TOKEN non impostato: sulla macchina del runner lancia "
            f"`sudo -u {runner_utente} -H sh -c 'gh auth token | gh secret set BOTTEGA_TOKEN --repo {args.repo}'`"
        )
    elif not solo_sessione:
        runner_utente = getattr(args, "runner", "bottega-runner")
        if esegui_pipe is None and esegui is not None:
            print("errore: con un esecutore iniettato serve anche la sua pipe", file=sys.stderr)
            return 1
        try:
            if esegui_pipe is None:
                # La pipe vera: il token passa da `gh auth token` dell'utente del runner a `gh secret set`, mai in memoria
                # di questo processo né in un argomento.
                ok_segreto = imposta_segreto(args.repo, runner_utente)
            else:
                ok_segreto = imposta_segreto(args.repo, runner_utente, esegui_pipe=esegui_pipe)
            if not ok_segreto:
                print("errore: impostazione del segreto BOTTEGA_TOKEN fallita", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"errore nell'impostazione del segreto: {e}", file=sys.stderr)
            return 1

    return 0


def comando_ferma(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
) -> int:
    """Disabilita i workflow bottega-*.yml nel repository del progetto."""
    esegui_fn = esegui or esecutore_vero
    esegui_gh = _adatta_esegui_gh(esegui_fn)
    try:
        wfs = ferma(esegui_gh, args.repo)
        if not wfs:
            print(f"i workflow della bottega in {args.repo} erano già spenti")
        for wf in wfs:
            print(f"fermato: {wf}")
        return 0
    except Exception as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1


def comando_riparti(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
) -> int:
    """Abilita i workflow bottega-*.yml nel repository del progetto."""
    esegui_fn = esegui or esecutore_vero
    esegui_gh = _adatta_esegui_gh(esegui_fn)
    try:
        wfs = riparti(esegui_gh, args.repo)
        if not wfs:
            print(f"i workflow della bottega in {args.repo} erano già accesi")
        for wf in wfs:
            print(f"ripartito: {wf}")
        return 0
    except Exception as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1


_ORIGIN_GITHUB = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?"
)


def _estrai_owner_repo(url: str) -> str | None:
    """OWNER/REPO da un origin di GitHub, o None: un origin su un'altra forgia o una cartella locale darebbero un nome
    che su GitHub può essere di un altro (G8)."""
    m = _ORIGIN_GITHUB.fullmatch(url.strip())
    return m.group(1) if m else None


def comando_aggiorna(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
    forgia: Forgia | None = None,
) -> int:
    """Aggiorna i riferimenti ai workflow della bottega al tag indicato."""
    esegui_fn = esegui or esecutore_vero
    cartella = getattr(args, "cartella", None) or Path.cwd()
    prova = getattr(args, "prova", False)

    # 1. Repo della bottega: --bottega, altrimenti l'origin del clone della bottega (mai quello del progetto)
    if not _TAG_VALIDO.fullmatch(args.tag):
        print("errore: tag non valido", file=sys.stderr)
        return 2
    repo_bottega = _repo_della_bottega(getattr(args, "bottega", None), esegui_fn)
    if not repo_bottega:
        print("errore: non trovo il repo della bottega dal suo origin; usa --bottega OWNER/REPO", file=sys.stderr)
        return 2

    # 2. SHA del tag
    sha = _sha_del_tag(esegui_fn, repo_bottega, args.tag)
    if not sha:
        print(f"errore: non trovo lo SHA del tag {args.tag} in {repo_bottega}", file=sys.stderr)
        return 1

    # 3. Trova workflow chiamanti
    wf_dir = cartella / ".github" / "workflows"
    testi: dict[str, str] = {}
    if wf_dir.is_dir():
        for p in sorted(wf_dir.glob("bottega-*.y*ml")):
            if p.is_file():
                try:
                    rel = str(p.relative_to(cartella))
                except ValueError:
                    rel = str(p)
                testi[rel] = p.read_text(encoding="utf-8")

    if not testi:
        print("errore: nessun workflow chiamante bottega-*.yml trovato", file=sys.stderr)
        return 1

    try:
        if repo_bottega.split("/", 1)[1] != "bottega":
            print(f"errore: i workflow chiamano <proprietario>/bottega, e il repo è {repo_bottega}", file=sys.stderr)
            return 2
        nuovi = aggiorna_chiamanti(testi, sha, args.tag, repo_bottega)
    except ErroreProgetto as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1

    # 4. Prova
    if prova:
        for p_rel in sorted(nuovi.keys()):
            print(f"aggiornerei: {p_rel} a {args.tag} ({sha})")
        return 0

    # 5. Ramo aggiorna
    ramo = f"bottega/aggiorna-{args.tag}"
    cod_br, _ = esegui_fn(["git", "-C", str(cartella), "rev-parse", "--verify", ramo], None)
    if cod_br == 0:
        print(f"errore: il ramo {ramo} esiste già", file=sys.stderr)
        return 1
    cod_rem, out_rem = esegui_fn(["git", "-C", str(cartella), "ls-remote", "--heads", "origin", ramo], None)
    if cod_rem == 0 and out_rem.strip():
        print(f"errore: il ramo {ramo} esiste già su origin", file=sys.stderr)
        return 1

    cod, out = esegui_fn(["git", "-C", str(cartella), "switch", "-c", ramo], None)
    if cod != 0:
        print(f"errore git switch: {out.strip()}", file=sys.stderr)
        return 1

    for p_rel, testo in nuovi.items():
        (cartella / p_rel).write_text(testo, encoding="utf-8")

    cod, out = esegui_fn(["git", "-C", str(cartella), "add", *nuovi.keys()], None)
    if cod != 0:
        print(f"errore git add: {out.strip()}", file=sys.stderr)
        return 1

    cod, out = esegui_fn(["git", "-C", str(cartella), "commit", "-m", f"Aggiorna la bottega a {args.tag}"], None)
    if cod != 0:
        print(f"errore git commit: {out.strip()}", file=sys.stderr)
        return 1

    cod, out = esegui_fn(["git", "-C", str(cartella), "push", "-u", "origin", ramo], None)
    if cod != 0:
        print(f"errore git push: {out.strip()}", file=sys.stderr)
        return 1

    forgia_inst = forgia or _adatta_forgia_gh(esegui_fn, args.repo)
    try:
        pr_num = forgia_inst.apri_pr(
            ramo,
            f"Aggiorna la bottega a {args.tag}",
            f"Aggiornamento della bottega al tag {args.tag} ({sha}).",
        )
        print(f"aperta PR #{pr_num}")
    except Exception as e:
        print(f"errore nell'apertura della PR: {e}", file=sys.stderr)
        return 1

    return 0


def comando_installa(
    args: argparse.Namespace,
    esegui: Esecutore | None = None,
) -> int:
    """Smista l'azione del sottocomando installa (macchina, runner, progetto)."""
    azione = getattr(args, "azione", None)
    if azione == "macchina":
        return comando_macchina(args, esegui=esegui)
    if azione == "runner":
        return comando_runner(args, esegui=esegui)
    if azione == "progetto":
        return comando_progetto(args, esegui=esegui)
    print("errore: serve specificare macchina, runner o progetto", file=sys.stderr)
    return 2


def argomenti_installa(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il comando bottega installa e le sue azioni."""
    sottocomandi = parser.add_subparsers(dest="azione", title="azioni", metavar="AZIONE", required=True)

    # installa macchina
    p_macchina = sottocomandi.add_parser("macchina", help="prepara la macchina host per la bottega")
    p_macchina.add_argument("--prova", action="store_true", help="mostra i passi senza eseguirli")
    p_macchina.add_argument("--runner", default="bottega-runner", help="nome utente del runner")
    p_macchina.add_argument("--esecutore", default="bottega-esecutore", help="nome utente dell'esecutore")
    p_macchina.add_argument("--gruppo", default="bottega", help="nome del gruppo comune")

    # installa runner
    p_runner = sottocomandi.add_parser("runner", help="installa e registra il runner self-hosted")
    p_runner.add_argument("--repo", required=True, metavar="OWNER/REPO", help="repository GitHub")
    p_runner.add_argument("--etichetta", required=True, metavar="E", help="etichetta del runner")
    p_runner.add_argument("--nome", required=True, metavar="N", help="nome del runner")
    p_runner.add_argument(
        "--versione", default=None, metavar="V", help="versione del runner (predefinito: ultima release)"
    )
    p_runner.add_argument("--arch", default=None, metavar="A", help="architettura di macchina")
    p_runner.add_argument(
        "--porta", action="append", default=[], metavar="NOME=PERCORSO", help="porta dell'esecutore (ripetibile)"
    )
    p_runner.add_argument(
        "--gh-del-runner",
        action="store_true",
        help="le chiamate a GitHub passano dall'accesso gh del runner (chi installa non ha gh su questa macchina)",
    )
    p_runner.add_argument(
        "--tetto", default=None, metavar="T", help="tetto di memoria del servizio del runner (per esempio 6G)"
    )
    p_runner.add_argument("--prova", action="store_true", help="mostra i passi senza scaricare né registrare")
    p_runner.add_argument("--runner", default="bottega-runner", help=argparse.SUPPRESS)
    p_runner.add_argument("--esecutore", default="bottega-esecutore", help=argparse.SUPPRESS)
    p_runner.add_argument("--gruppo", default="bottega", help=argparse.SUPPRESS)

    # installa progetto
    p_progetto = sottocomandi.add_parser("progetto", help="configura il progetto GitHub")
    p_progetto.add_argument("--repo", required=True, metavar="OWNER/REPO", help="repository GitHub")
    p_progetto.add_argument("--project", required=True, type=int, metavar="N", help="numero del GitHub Project")
    p_progetto.add_argument("--configurazione", required=True, type=Path, metavar="PERCORSO", help="file bottega.toml")
    p_progetto.add_argument(
        "--valore", action="append", default=[], metavar="CHIAVE=VALORE", help="valori per i modelli (ripetibile)"
    )
    p_progetto.add_argument(
        "--solo-sessione",
        action="store_true",
        help="installa la bottega solo per la sessione, senza runner né workflow chiamanti",
    )
    p_progetto.add_argument(
        "--tag", default=None, metavar="T", help="tag della bottega a cui fissare i workflow"
    )
    p_progetto.add_argument(
        "--bottega", default=None, metavar="OWNER/REPO", help="repo della bottega (di serie: l'origin di questo clone)"
    )
    p_progetto.add_argument(
        "--senza-segreto",
        action="store_true",
        help="non imposta BOTTEGA_TOKEN (chi installa non è sulla macchina del runner): stampa il comando da lanciare lì",
    )
    p_progetto.add_argument("--prova", action="store_true", help="mostra i file e i campi senza scrivere")
    p_progetto.add_argument("--cartella", type=Path, default=None, help=argparse.SUPPRESS)
    p_progetto.add_argument("--runner", default="bottega-runner", help=argparse.SUPPRESS)


def argomenti_ferma(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il comando bottega ferma."""
    parser.add_argument("--repo", required=True, metavar="R", help="repository GitHub (OWNER/REPO)")


def argomenti_riparti(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il comando bottega riparti."""
    parser.add_argument("--repo", required=True, metavar="R", help="repository GitHub (OWNER/REPO)")


def argomenti_aggiorna(parser: argparse.ArgumentParser) -> None:
    """Configura gli argomenti per il comando bottega aggiorna."""
    parser.add_argument("--repo", required=True, metavar="R", help="repository del progetto da aggiornare")
    parser.add_argument("--tag", required=True, metavar="T", help="tag di bottega a cui aggiornare")
    parser.add_argument("--bottega", default=None, metavar="OWNER/REPO", help="repository della bottega sorgente")
    parser.add_argument("--prova", action="store_true", help="mostra le modifiche senza applicarle")
    parser.add_argument("--cartella", type=Path, default=None, help=argparse.SUPPRESS)
