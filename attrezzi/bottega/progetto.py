"""I passi d'installazione nel progetto: campi del Project, modelli, workflow, segreti."""

from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

from bottega.configurazione import Configurazione
import bottega.misure as misure


class ErroreProgetto(Exception):
    """Errore durante le operazioni di configurazione del progetto GitHub."""


_CAMPI_B3: dict[str, tuple[str, tuple[str, ...]]] = {
    "Bottega": ("SINGLE_SELECT", ("pronto", "in corso", "in attesa", "consegnato", "bloccato")),
    "Esito": ("SINGLE_SELECT", ("pronta per l'unione", "correzioni", "rifiutata")),
    "Esecutore": ("TEXT", ()),
    "Nota del giro": ("TEXT", ()),
}

CAMPI_DEL_PROJECT: dict[str, tuple[str, tuple[str, ...]]] = dict(_CAMPI_B3)
for _nome, _tipo in misure.CAMPI.items():
    if _nome == "Esito del compito":
        CAMPI_DEL_PROJECT[_nome] = (_tipo, tuple(misure.OPZIONI_ESITO))
    else:
        CAMPI_DEL_PROJECT[_nome] = (_tipo, ())

COLORI: tuple[str, ...] = ("GRAY", "BLUE", "YELLOW", "ORANGE", "GREEN", "RED", "PURPLE", "PINK")


def campi_mancanti(esistenti: Iterable[str]) -> list[str]:
    """Campi del Project non ancora presenti, nell'ordine di CAMPI_DEL_PROJECT."""
    presenti = set(esistenti)
    return [nome for nome in CAMPI_DEL_PROJECT if nome not in presenti]


def mutazione_campo(project_id: str, nome: str) -> str:
    """Il testo della mutazione GraphQL createProjectV2Field per il campo specificato."""
    if nome not in CAMPI_DEL_PROJECT:
        raise ErroreProgetto(f"Campo sconosciuto: {nome}")
    tipo, opzioni = CAMPI_DEL_PROJECT[nome]
    if tipo == "SINGLE_SELECT":
        opzioni_str = ",\n".join(
            f'      {{ name: {json.dumps(opt)}, color: {COLORI[i % len(COLORI)]}, description: "" }}'
            for i, opt in enumerate(opzioni)
        )
        return f"""mutation {{
  createProjectV2Field(input: {{
    projectId: {json.dumps(project_id)}
    dataType: SINGLE_SELECT
    name: {json.dumps(nome)}
    singleSelectOptions: [
{opzioni_str}
    ]
  }}) {{
    projectV2Field {{
      ... on ProjectV2FieldCommon {{
        id
        name
      }}
    }}
  }}
}}"""
    return f"""mutation {{
  createProjectV2Field(input: {{
    projectId: {json.dumps(project_id)}
    dataType: {tipo}
    name: {json.dumps(nome)}
  }}) {{
    projectV2Field {{
      ... on ProjectV2FieldCommon {{
        id
        name
      }}
    }}
  }}
}}"""


_QUERY_PROJECT_USER = """
query($owner: String!, $number: Int!) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
"""

_QUERY_PROJECT_ORG = """
query($owner: String!, $number: Int!) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
"""


def crea_campi(esegui_gh: Callable[[list[str]], str], proprietario: str, numero: int) -> list[str]:
    """Legge i campi del Project, crea i mancanti e restituisce i nomi di quelli creati."""
    cmd_user = [
        "api", "graphql",
        "-f", f"owner={proprietario}",
        "-F", f"number={numero}",
        "-f", f"query={_QUERY_PROJECT_USER}",
    ]
    out_user = esegui_gh(cmd_user)
    data = json.loads(out_user) if out_user else {}
    proj = data.get("data", {}).get("user", {}).get("projectV2") if data.get("data") else None
    if not proj:
        cmd_org = [
            "api", "graphql",
            "-f", f"owner={proprietario}",
            "-F", f"number={numero}",
            "-f", f"query={_QUERY_PROJECT_ORG}",
        ]
        out_org = esegui_gh(cmd_org)
        data_org = json.loads(out_org) if out_org else {}
        proj = data_org.get("data", {}).get("organization", {}).get("projectV2") if data_org.get("data") else None

    if not proj:
        raise ErroreProgetto(f"Project {numero} non trovato per {proprietario}")

    project_id = proj["id"]
    fields_nodes = proj.get("fields", {}).get("nodes", [])
    esistenti = [f["name"] for f in fields_nodes if isinstance(f, dict) and "name" in f]
    mancanti = campi_mancanti(esistenti)
    if not mancanti:
        return []

    creati: list[str] = []
    for nome in mancanti:
        mutazione = mutazione_campo(project_id, nome)
        esegui_gh(["api", "graphql", "-f", f"query={mutazione}"])
        creati.append(nome)
    return creati


def cron_della_notte(notte: str, fuso: str, oggi: date) -> str:
    """Calcola la stringa cron 'M H * * *' in UTC per l'ora locale del fuso alla data oggi."""
    parti = [int(p) for p in notte.strip().split(":")]
    if len(parti) != 2:
        raise ErroreProgetto(f"Ora della notte non valida: {notte}")
    ore, minuti = parti
    try:
        tz = ZoneInfo(fuso)
    except Exception as e:
        raise ErroreProgetto(f"Fuso orario non valido: {fuso} ({e})") from None
    dt_locale = datetime.combine(oggi, time(ore, minuti), tzinfo=tz)
    dt_utc = dt_locale.astimezone(timezone.utc)
    return f"{dt_utc.minute} {dt_utc.hour} * * *"


def rendi_modello(testo: str, valori: Mapping[str, str]) -> str:
    """Sostituisce i segnaposti <…> conosciuti; ErroreProgetto se ne resta uno."""
    risultato = testo
    for k, v in valori.items():
        segnaposto = k if k.startswith("<") and k.endswith(">") else f"<{k}>"
        risultato = risultato.replace(segnaposto, str(v))
    rimasti = [r for r in re.findall(r"<([^!>\n.][^>\n]*)>", risultato) if r != "..."]
    if rimasti:
        raise ErroreProgetto(f"Segnaposti rimasti nel modello: {', '.join(f'<{r}>' for r in rimasti)}")
    return risultato


_CARTELLA_MODELLI = (
    Path(__file__).resolve().parent.parent.parent
    / "plugin"
    / "skills"
    / "bottega"
    / "modelli"
)


def file_dell_installazione(
    cfg: Configurazione,
    valori: Mapping[str, str],
    esistenti: Iterable[str],
) -> dict[str, str]:
    """Genera la mappa percorso -> testo per i file da inserire nella PR d'installazione."""
    file_esistenti = set(esistenti)
    risultati: dict[str, str] = {}

    # 1. .github/bottega/bottega.toml (dato da chi chiama)
    percorso_toml = ".github/bottega/bottega.toml"
    testo_toml = (
        valori.get(percorso_toml)
        or valori.get("bottega.toml")
        or valori.get("testo_toml")
    )
    if not testo_toml:
        modello_toml = _CARTELLA_MODELLI / "bottega.toml"
        if modello_toml.is_file():
            testo_toml = modello_toml.read_text(encoding="utf-8")
        else:
            testo_toml = ""
    risultati[percorso_toml] = testo_toml

    # 2. Distributore workflow
    percorso_dist = ".github/workflows/bottega-distributore.yml"
    modello_dist = _CARTELLA_MODELLI / "workflows" / "bottega-distributore.yml"
    testo_dist = modello_dist.read_text(encoding="utf-8")

    mappa_valori = dict(valori)
    notte = cfg.progetto.notte or mappa_valori.get("notte")
    fuso = cfg.progetto.fuso or mappa_valori.get("fuso", "Europe/Rome")
    if notte:
        cron = cron_della_notte(notte, fuso, date.today())
        testo_dist = re.sub(
            r"- cron: ['\"].*?['\"]\s*(?:#.*)?",
            f"- cron: '{cron}'  # {notte} ({fuso}), l'ora legale cambia lo scarto",
            testo_dist,
        )
    else:
        testo_dist = testo_dist.replace("# <ora in UTC>", "# nessun giro notturno programmato")

    if "etichetta del runner" not in mappa_valori and "runner" in mappa_valori:
        mappa_valori["etichetta del runner"] = mappa_valori["runner"]
    if "etichetta del runner" not in mappa_valori:
        for cand in cfg.candidati.values():
            if cand.runner:
                mappa_valori["etichetta del runner"] = cand.runner
                break
        else:
            mappa_valori["etichetta del runner"] = "self-hosted"

    risultati[percorso_dist] = rendi_modello(testo_dist, mappa_valori)

    # 3. Esecutore workflow
    modello_esec = _CARTELLA_MODELLI / "workflows" / "bottega-esecutore.yml"
    testo_esec = modello_esec.read_text(encoding="utf-8")

    botteghe_ids = list(cfg.botteghe.keys()) if cfg.botteghe else []
    if "id" in mappa_valori and mappa_valori["id"] not in botteghe_ids:
        botteghe_ids.append(mappa_valori["id"])
    if not botteghe_ids:
        botteghe_ids = ["principale"]

    for b_id in botteghe_ids:
        percorso_esec = f".github/workflows/bottega-esecutore-{b_id}.yml"
        valori_esec = dict(mappa_valori)
        valori_esec["id"] = b_id
        for cand in cfg.candidati.values():
            if cand.bottega == b_id and cand.runner:
                valori_esec["etichetta del runner"] = cand.runner
                break
        risultati[percorso_esec] = rendi_modello(testo_esec, valori_esec)

    # 4. AGENTS.md (solo se non esiste già)
    percorso_agents = "AGENTS.md"
    if percorso_agents not in file_esistenti and "agents.md" not in file_esistenti:
        modello_agents = _CARTELLA_MODELLI / "agents.md"
        risultati[percorso_agents] = modello_agents.read_text(encoding="utf-8")

    # 5. Costituzione (solo se non esiste già)
    percorso_cost = "docs/costituzione.md"
    if percorso_cost not in file_esistenti:
        modello_cost = _CARTELLA_MODELLI / "costituzione.md"
        risultati[percorso_cost] = modello_cost.read_text(encoding="utf-8")

    return risultati


def _esegui_pipe_di_serie(cmd1: list[str], cmd2: list[str]) -> int:
    p1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(cmd2, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p1.stdout:
        p1.stdout.close()
    p2.communicate()
    p1.wait()
    return p2.returncode or p1.returncode


def imposta_segreto(
    repo: str,
    utente_runner: str,
    esegui_pipe: Callable[[list[str], list[str]], int] = _esegui_pipe_di_serie,
) -> bool:
    """Imposta BOTTEGA_TOKEN nel repo prelevandolo dall'utente runner tramite pipe sicura."""
    cmd1 = ["sudo", "-n", "-u", utente_runner, "-H", "gh", "auth", "token"]
    cmd2 = ["gh", "secret", "set", "BOTTEGA_TOKEN", "--repo", repo]
    try:
        codice = esegui_pipe(cmd1, cmd2)
        return codice == 0
    except Exception:
        return False


def workflow_della_bottega(esegui_gh: Callable[[list[str]], str], repo: str) -> list[dict[str, str]]:
    """Elenco dei workflow della bottega (.github/workflows/bottega-*.yml) nel repository."""
    out = esegui_gh(["workflow", "list", "--all", "--limit", "200", "--repo", repo, "--json", "path,state"])
    dati = json.loads(out) if out else []
    trovati: list[dict[str, str]] = []
    for item in dati:
        path = item.get("path", "")
        if (
            (path.startswith(".github/workflows/bottega-") or path.startswith("bottega-"))
            and path.endswith(".yml")
        ):
            trovati.append({"path": path, "state": item.get("state", "")})
    return trovati


def ferma(esegui_gh: Callable[[list[str]], str], repo: str) -> list[str]:
    """Disabilita solo i workflow bottega-*.yml attivi nel repository; restituisce quelli toccati (vuoto: erano già
    tutti spenti). ErroreProgetto se il repository non ha workflow della bottega."""
    wfs = workflow_della_bottega(esegui_gh, repo)
    if not wfs:
        raise ErroreProgetto(f"nessun workflow bottega-*.yml in {repo}")
    toccati: list[str] = []
    for item in wfs:
        path = item["path"] if isinstance(item, dict) else item
        state = (item.get("state") or "") if isinstance(item, dict) else ""
        # Uno stato mancante conta come acceso: l'interruttore spegne nel dubbio.
        if state in ("active", ""):
            esegui_gh(["workflow", "disable", path, "--repo", repo])
            toccati.append(path)
    return toccati


def riparti(esegui_gh: Callable[[list[str]], str], repo: str) -> list[str]:
    """Abilita solo i workflow bottega-*.yml non attivi nel repository; restituisce quelli toccati (vuoto: erano già
    tutti accesi). ErroreProgetto se il repository non ha workflow della bottega."""
    wfs = workflow_della_bottega(esegui_gh, repo)
    if not wfs:
        raise ErroreProgetto(f"nessun workflow bottega-*.yml in {repo}")
    toccati: list[str] = []
    for item in wfs:
        path = item["path"] if isinstance(item, dict) else item
        state = (item.get("state") or "") if isinstance(item, dict) else ""
        # Solo gli spenti (disabled_manually, disabled_inactivity…): un workflow cancellato non si riaccende.
        if state.startswith("disabled"):
            esegui_gh(["workflow", "enable", path, "--repo", repo])
            toccati.append(path)
    return toccati


_SHA_REGEX = re.compile(r"^[0-9a-fA-F]{40}$")


_USES_DELLA_BOTTEGA = re.compile(
    r"^(?P<testa>[ \t]*(?:-[ \t]+)?uses:[ \t]*)[A-Za-z0-9_.-]+/bottega/(?P<file>\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)"
    r"@[0-9A-Za-z._-]+(?:[ \t]+#[^\n]*)?$",
    re.MULTILINE,
)


def aggiorna_chiamanti(testi: Mapping[str, str], sha: str, tag: str, repo_bottega: str) -> dict[str, str]:
    """Porta i workflow chiamanti al commit `sha` del tag `tag` del repo della bottega.

    Si riscrivono solo le righe `uses:` che chiamano un workflow della bottega (M1: le altre azioni restano com'erano),
    con `@<sha> # <tag>`, e `bottega_ref:` diventa lo SHA (G3: il codice che gira è quello del commit fissato, non
    quello di un tag che si può spostare). Un file senza una chiamata della bottega è un errore.
    """
    if not isinstance(sha, str) or not _SHA_REGEX.match(sha):
        raise ErroreProgetto(f"SHA non valido (richieste 40 cifre esadecimali): {sha!r}")

    aggiornati: dict[str, str] = {}
    for percorso, testo in testi.items():
        nuovo, quanti = _USES_DELLA_BOTTEGA.subn(
            lambda m: f"{m.group('testa')}{repo_bottega}/{m.group('file')}@{sha} # {tag}", testo
        )
        if quanti == 0:
            raise ErroreProgetto(f"{percorso}: nessuna chiamata a un workflow della bottega")
        nuovo = re.sub(r"(?m)^([ \t]*bottega_ref:[ \t]*)\S+[^\n]*$", rf"\g<1>{sha}", nuovo)
        nuovo = re.sub(r"(?m)^([ \t]*bottega_repo:[ \t]*)\S+[^\n]*$", rf"\g<1>{repo_bottega}", nuovo)
        aggiornati[percorso] = nuovo
    return aggiornati
