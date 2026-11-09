"""Controllo della CI del progetto sui rami `bottega/*` (B6-R7).

Un workflow è un rischio se parte sui rami `bottega/*` e ha qualcosa da dare (segreti o runner self-hosted).
Nel dubbio (ancore YAML, flussi multilinea, trigger non chiari) è un rischio.
Solo libreria standard, nessun parser YAML esterno.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

RUNNER_GITHUB_ESATTI: frozenset[str] = frozenset({
    "ubuntu-latest",
    "ubuntu-24.04",
    "ubuntu-22.04",
    "ubuntu-24.04-arm",
    "ubuntu-22.04-arm",
    "windows-latest",
    "windows-2025",
    "windows-2022",
    "macos-latest",
    "macos-15",
    "macos-14",
    "macos-13",
})


@dataclass(frozen=True)
class Rischio:
    """Un workflow pericoloso o dubbio."""

    file: str
    motivo: str


def togli_commento(riga: str) -> str:
    """Toglie il commento (#) se non è racchiuso tra apici singoli o doppi."""
    in_singolo = False
    in_doppio = False
    fuga = False
    for i, c in enumerate(riga):
        if fuga:
            fuga = False
            continue
        if c == "\\" and in_doppio:
            fuga = True
            continue
        if c == "'" and not in_doppio:
            in_singolo = not in_singolo
            continue
        if c == '"' and not in_singolo:
            in_doppio = not in_doppio
            continue
        if c == "#" and not in_singolo and not in_doppio:
            return riga[:i].rstrip()
    return riga.rstrip()


def _ha_ancora_o_alias(riga: str) -> bool:
    """Rileva ancore (&nome) o alias (*nome) YAML fuori dagli apici."""
    senza_stringhe = re.sub(r"'[^']*'|\"[^\"]*\"", "", riga)
    if re.search(r"(?<!&)&[A-Za-z_][A-Za-z0-9_-]*", senza_stringhe):
        return True
    if re.search(r"(?<!\*)\*[A-Za-z_][A-Za-z0-9_-]*", senza_stringhe):
        return True
    return False


def _ha_flusso_multilinea(righe_pulite: list[str]) -> bool:
    """Rileva parentesi graffe aperte fuori dagli apici e non chiuse sulla stessa riga.

    Le espressioni `${{ … }}` si tolgono prima, anche quando vanno a capo: il distributore della bottega ne ha una su
    più righe, e contarla come flusso faceva di ogni progetto installato un rischio (ogni giro restava in attesa).
    """
    testo = re.sub(r"\$\{\{.*?\}\}", "", "\n".join(righe_pulite), flags=re.DOTALL)
    for riga in testo.split("\n"):
        senza_stringhe = re.sub(r"'[^']*'|\"[^\"]*\"", "", riga)
        aperte = senza_stringhe.count("{")
        chiuse = senza_stringhe.count("}")
        if aperte != chiuse:
            return True
    return False


def modello_combacia_bottega(modello: str) -> bool:
    """True se il modello glob di GitHub Actions seleziona rami bottega/*."""
    modello = modello.strip().strip("'\"")
    if modello == "**":
        return True
    if modello.startswith("bottega/**") or modello.startswith("bottega/*"):
        return True
    if modello.startswith("bottega/"):
        return True
    if modello == "*/*":
        return True
    regex_parti = ["^"]
    i = 0
    while i < len(modello):
        if modello[i : i + 2] == "**":
            regex_parti.append(".*")
            i += 2
        elif modello[i] == "*":
            regex_parti.append("[^/]*")
            i += 1
        elif modello[i] == "?":
            regex_parti.append("[^/]")
            i += 1
        else:
            regex_parti.append(re.escape(modello[i]))
            i += 1
    regex_parti.append("$")
    pattern = re.compile("".join(regex_parti))
    return bool(pattern.match("bottega/prova") or pattern.match("bottega/b6-1"))


def _branches_prendono_bottega(modelli: list[str]) -> bool:
    if not modelli:
        return True
    if all(m.strip().strip("'\"").startswith("!") for m in modelli):
        for mod in modelli:
            mod = mod.strip().strip("'\"")
            if modello_combacia_bottega(mod[1:]):
                return False
        return True

    positivo = False
    for mod in modelli:
        mod = mod.strip().strip("'\"")
        if mod.startswith("!"):
            if modello_combacia_bottega(mod[1:]):
                positivo = False
        else:
            if modello_combacia_bottega(mod):
                positivo = True
    return positivo


def _branches_ignore_esclude_bottega(modelli: list[str]) -> bool:
    for mod in modelli:
        mod = mod.strip().strip("'\"")
        if modello_combacia_bottega(mod):
            return True
    return False


def _estrai_lista_inline(valore: str) -> list[str]:
    """Estrae gli elementi di una lista inline [a, b, c]."""
    valore = valore.strip()
    if valore.startswith("[") and valore.endswith("]"):
        valore = valore[1:-1]
    return [elem.strip().strip("'\"") for elem in valore.split(",") if elem.strip()]


def _e_runner_github(etichetta: str) -> bool:
    et = etichetta.lower().strip("'\" ")
    return et in RUNNER_GITHUB_ESATTI


def _trova_pericolo(righe_pulite: list[str]) -> str | None:
    """Verifica se il workflow ha qualcosa da dare: segreti o runner self-hosted."""
    # 1. secrets: inherit
    for riga in righe_pulite:
        if re.search(r"\bsecrets\s*:\s*inherit\b", riga, re.IGNORECASE):
            return "usa secrets: inherit"

    # 2. secrets in espressione ${{ ... }}
    testo_senza_commenti = "\n".join(righe_pulite)
    for expr in re.findall(r"\$\{\{(.*?)\}\}", testo_senza_commenti, re.DOTALL):
        if re.search(r"\bsecrets\b", expr, re.IGNORECASE):
            m_dot = re.search(r"\bsecrets\.([A-Za-z0-9_]+)\b", expr, re.IGNORECASE)
            if m_dot:
                return f"usa secrets.{m_dot.group(1)}"
            m_br = re.search(r"\bsecrets\s*\[\s*['\"]?([A-Za-z0-9_-]+)['\"]?\s*\]", expr, re.IGNORECASE)
            if m_br:
                return f"usa secrets['{m_br.group(1)}']"
            return f"usa secrets ({expr.strip()})"

    # 3. secrets. in qualsiasi punto (anche fuori da ${{ }})
    for riga in righe_pulite:
        m = re.search(r"\bsecrets\.([A-Za-z0-9_]+)\b", riga, re.IGNORECASE)
        if m:
            return f"usa secrets.{m.group(1)}"
        if re.search(r"\bsecrets\.", riga, re.IGNORECASE):
            return "usa secrets."

    # 4. un workflow riusabile (locale o di un altro repo): il chiamato può avere segreti o runner self-hosted, e
    # qui non si vede. Nel dubbio è un rischio. Le azioni (`actions/checkout@…`) non passano da `.github/workflows/`.
    for riga in righe_pulite:
        m = re.match(r"^\s*(?:-\s*)?uses\s*:\s*['\"]?([^\s'\"]+)", riga)
        if m and ".github/workflows/" in m.group(1):
            return f"chiama il workflow riusabile {m.group(1)}"

    # 5. runs-on
    i = 0
    righe_chiave_runs_on: set[int] = set()
    while i < len(righe_pulite):
        riga = righe_pulite[i]
        m = re.match(r"^(\s*)(?:'runs-on'|\"runs-on\"|runs-on)\s*:\s*(.*)$", riga, re.IGNORECASE)
        if m:
            righe_chiave_runs_on.add(i)
            indent = len(m.group(1))
            valore = m.group(2).strip()
            if valore:
                if "${{" in valore:
                    return f"usa runs-on con espressione ({valore})"
                if valore.startswith("{"):
                    return f"usa runs-on a mappa o forma non riconosciuta ({valore})"
                if valore.startswith("["):
                    elementi = _estrai_lista_inline(valore)
                    if not elementi:
                        return "usa runs-on con lista vuota"
                    for el in elementi:
                        if "${{" in el:
                            return f"usa runs-on con espressione ({el})"
                        if el == "self-hosted" or "self-hosted" in el:
                            return "usa runner self-hosted"
                        if not _e_runner_github(el):
                            return f"usa runner non GitHub ({el})"
                else:
                    el = valore.strip("'\"")
                    if el == "self-hosted" or "self-hosted" in el:
                        return "usa runner self-hosted"
                    if not _e_runner_github(el):
                        return f"usa runner non GitHub ({el})"
            else:
                j = i + 1
                righe_figli: list[str] = []
                while j < len(righe_pulite):
                    riga_sub = righe_pulite[j]
                    if not riga_sub.strip():
                        j += 1
                        continue
                    indent_sub = len(riga_sub) - len(riga_sub.lstrip())
                    if indent_sub <= indent:
                        break
                    righe_figli.append(riga_sub)
                    j += 1

                if not righe_figli:
                    return "usa runs-on vuoto o non riconosciuto"

                if not all(r_sub.lstrip().startswith("-") for r_sub in righe_figli):
                    return "usa runs-on a mappa o forma non riconosciuta"

                for riga_sub in righe_figli:
                    m_item = re.match(r"^\s*-\s*(.*)$", riga_sub)
                    if m_item:
                        el = m_item.group(1).strip().strip("'\"")
                        if "${{" in el:
                            return f"usa runs-on con espressione ({el})"
                        if el == "self-hosted" or "self-hosted" in el:
                            return "usa runner self-hosted"
                        if not _e_runner_github(el):
                            return f"usa runner non GitHub ({el})"
        i += 1

    # 6. ogni comparsa di runs-on nel testo (fuori dai commenti, maiuscole o no) che la lettura riga per riga non ha
    # letto come chiave di un job è un dubbio
    for idx, riga in enumerate(righe_pulite):
        if "runs-on" in riga.lower():
            if idx not in righe_chiave_runs_on or riga.lower().count("runs-on") > 1:
                return f"runs-on non riconosciuto o dubbio ({riga.strip()})"

    # 7. una chiave fra doppi apici con una sequenza di escape (`"\x72uns-on":`) può nascondere qualunque chiave
    for riga in righe_pulite:
        if re.search(r'(?:^\s*(?:-\s*)?|[{,]\s*)"[^"]*\\[^"]*"\s*:', riga):
            return f"chiave con escape, dubbio ({riga.strip()})"

    return None


def _condizione_if_e_protetta(cond: str) -> bool:
    """Verifica se la condizione if: protegge il job dai rami bottega/*.

    Conta solo se la condizione è esattamente !startsWith(github.head_ref, 'bottega/')
    (spazi a parte, con o senza ${{ }}) o se è unita al resto solo con && al livello più esterno;
    con un || (o parentesi che non sai leggere) non protegge.
    """
    cond = cond.strip()
    if (cond.startswith("'") and cond.endswith("'")) or (cond.startswith('"') and cond.endswith('"')):
        cond = cond[1:-1].strip()
    if cond.startswith("${{") and cond.endswith("}}"):
        cond = cond[3:-2].strip()
    if (cond.startswith("'") and cond.endswith("'")) or (cond.startswith('"') and cond.endswith('"')):
        cond = cond[1:-1].strip()

    if "||" in cond:
        return False

    clausole: list[str] = []
    corrente: list[str] = []
    in_apice: str | None = None
    profondita = 0
    i = 0
    while i < len(cond):
        c = cond[i]
        if in_apice:
            if c == in_apice:
                in_apice = None
            corrente.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            in_apice = c
            corrente.append(c)
            i += 1
            continue
        if c == "(":
            profondita += 1
            corrente.append(c)
            i += 1
            continue
        if c == ")":
            profondita -= 1
            if profondita < 0:
                return False
            corrente.append(c)
            i += 1
            continue
        if profondita == 0 and cond[i : i + 2] == "&&":
            clausole.append("".join(corrente).strip())
            corrente = []
            i += 2
            continue
        corrente.append(c)
        i += 1

    if in_apice or profondita != 0:
        return False
    if corrente:
        clausole.append("".join(corrente).strip())

    for cl in clausole:
        cl_pulita = cl.strip()
        while cl_pulita.startswith("(") and cl_pulita.endswith(")"):
            p = 0
            spezzata = False
            for ch in cl_pulita[:-1]:
                if ch == "(":
                    p += 1
                elif ch == ")":
                    p -= 1
                    if p == 0:
                        spezzata = True
                        break
            if spezzata:
                break
            cl_pulita = cl_pulita[1:-1].strip()

        if re.match(r"^!\s*startsWith\(\s*github\.head_ref\s*,\s*['\"]bottega/['\"]\s*\)$", cl_pulita):
            return True

    return False


def _esamina_jobs_guardia(righe_pulite: list[str]) -> bool:
    """Verifica se OGNI job ha una guardia if: con !startsWith(github.head_ref, 'bottega/')."""
    indice_jobs = None
    for idx, r in enumerate(righe_pulite):
        if re.match(r"^jobs\s*:", r):
            indice_jobs = idx
            break
    if indice_jobs is None:
        return False

    job_indent = None
    for r in righe_pulite[indice_jobs + 1 :]:
        if not r.strip():
            continue
        indent = len(r) - len(r.lstrip())
        if indent == 0:
            break
        job_indent = indent
        break

    if job_indent is None:
        return False

    jobs_trovati = 0
    jobs_protetti = 0

    i = indice_jobs + 1
    while i < len(righe_pulite):
        r = righe_pulite[i]
        if not r.strip():
            i += 1
            continue
        indent = len(r) - len(r.lstrip())
        if indent == 0:
            break
        if indent == job_indent:
            m_job = re.match(r"^[A-Za-z0-9_-]+\s*:\s*$", r.strip())
            if m_job:
                jobs_trovati += 1
                protetto = False
                j = i + 1
                while j < len(righe_pulite):
                    r_sub = righe_pulite[j]
                    if not r_sub.strip():
                        j += 1
                        continue
                    indent_sub = len(r_sub) - len(r_sub.lstrip())
                    if indent_sub <= job_indent:
                        break
                    m_if = re.match(r"^\s*if\s*:\s*(.*)$", r_sub)
                    if m_if:
                        cond = m_if.group(1)
                        k = j + 1
                        while k < len(righe_pulite):
                            r_k = righe_pulite[k]
                            if not r_k.strip():
                                k += 1
                                continue
                            indent_k = len(r_k) - len(r_k.lstrip())
                            if indent_k <= indent_sub:
                                break
                            cond += " " + r_k.strip()
                            k += 1
                        if _condizione_if_e_protetta(cond):
                            protetto = True
                    j += 1
                if protetto:
                    jobs_protetti += 1
        i += 1

    return jobs_trovati > 0 and jobs_trovati == jobs_protetti


def _esamina_workflow(file: str, testo: str) -> list[Rischio]:
    """Esamina un singolo workflow per individuare rischi o dubbi."""
    righe_grezze = testo.splitlines()
    righe_pulite = [togli_commento(r) for r in righe_grezze]

    for riga in righe_pulite:
        if _ha_ancora_o_alias(riga):
            return [Rischio(file=file, motivo="sintassi YAML con ancore (& o *) non supportata")]

    if _ha_flusso_multilinea(righe_pulite):
        return [Rischio(file=file, motivo="flusso {...} multilinea non supportato")]

    indice_on = None
    for idx, riga in enumerate(righe_pulite):
        if re.match(r"^(?:['\"]?on['\"]?)\s*:", riga):
            indice_on = idx
            break

    if indice_on is None:
        return [Rischio(file=file, motivo="blocco on non trovato o non riconosciuto")]

    riga_on = righe_pulite[indice_on]
    valore_on = riga_on.split(":", 1)[1].strip()

    parte_push = False
    motivo_push = ""
    parte_pr = False
    motivo_pr = ""
    dubbio_on = False

    tutti_job_protetti = _esamina_jobs_guardia(righe_pulite)

    if valore_on:
        if valore_on.startswith("[") and valore_on.endswith("]"):
            eventi = _estrai_lista_inline(valore_on)
            if "push" in eventi:
                parte_push = True
                motivo_push = "parte su push in ogni ramo"
            if "pull_request" in eventi or "pull_request_target" in eventi:
                if not tutti_job_protetti:
                    parte_pr = True
                    motivo_pr = "parte su pull_request senza guardia in ogni job"
        else:
            evento = valore_on.strip("'\"")
            if evento == "push":
                parte_push = True
                motivo_push = "parte su push in ogni ramo"
            elif evento in ("pull_request", "pull_request_target"):
                if not tutti_job_protetti:
                    parte_pr = True
                    motivo_pr = f"parte su {evento} senza guardia in ogni job"
            elif evento not in (
                "workflow_dispatch",
                "schedule",
                "workflow_call",
                "issues",
                "issue_comment",
                "release",
            ):
                dubbio_on = True
    else:
        i = indice_on + 1
        righe_on: list[str] = []
        while i < len(righe_pulite):
            r = righe_pulite[i]
            if not r.strip():
                i += 1
                continue
            indent = len(r) - len(r.lstrip())
            if indent == 0:
                break
            righe_on.append(r)
            i += 1

        if not righe_on:
            dubbio_on = True
        elif all(r.lstrip().startswith("-") for r in righe_on):
            eventi = [r.lstrip().lstrip("-").strip().strip("'\"") for r in righe_on]
            if "push" in eventi:
                parte_push = True
                motivo_push = "parte su push in ogni ramo"
            if "pull_request" in eventi or "pull_request_target" in eventi:
                if not tutti_job_protetti:
                    parte_pr = True
                    motivo_pr = "parte su pull_request senza guardia in ogni job"
        else:
            indent_ev = len(righe_on[0]) - len(righe_on[0].lstrip())
            idx_sub = 0
            while idx_sub < len(righe_on):
                r = righe_on[idx_sub]
                indent_r = len(r) - len(r.lstrip())
                if indent_r != indent_ev:
                    dubbio_on = True
                    break

                m_ev = re.match(r"^\s*(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9_-]+))\s*:\s*(.*)$", r)
                if not m_ev:
                    dubbio_on = True
                    break

                ev_nome = m_ev.group(1) or m_ev.group(2) or m_ev.group(3)
                ev_val = m_ev.group(4).strip()

                sub_ev_righe: list[str] = []
                k = idx_sub + 1
                while k < len(righe_on):
                    r_k = righe_on[k]
                    indent_k = len(r_k) - len(r_k.lstrip())
                    if indent_k <= indent_ev:
                        break
                    sub_ev_righe.append(r_k)
                    k += 1

                if ev_nome == "push":
                    modelli_branches: list[str] | None = None
                    modelli_ignore: list[str] | None = None

                    if not sub_ev_righe and not ev_val:
                        parte_push = True
                        motivo_push = "parte su push in ogni ramo"
                    else:
                        for idx_p, r_p in enumerate(sub_ev_righe):
                            m_br = re.match(r"^\s*(?:'branches'|\"branches\"|branches)\s*:\s*(.*)$", r_p)
                            if m_br:
                                val_br = m_br.group(1).strip()
                                if val_br.startswith("["):
                                    modelli_branches = _estrai_lista_inline(val_br)
                                else:
                                    modelli_branches = []
                                    for r_seq in sub_ev_righe[idx_p + 1 :]:
                                        if re.match(r"^\s*(?:'[A-Za-z0-9_-]+'|\"[A-Za-z0-9_-]+\"|[A-Za-z0-9_-]+)\s*:", r_seq):
                                            break
                                        m_seq = re.match(r"^\s*-\s*(.*)$", r_seq)
                                        if m_seq:
                                            modelli_branches.append(m_seq.group(1).strip().strip("'\""))

                            m_ign = re.match(r"^\s*(?:'branches-ignore'|\"branches-ignore\"|branches-ignore)\s*:\s*(.*)$", r_p)
                            if m_ign:
                                val_ign = m_ign.group(1).strip()
                                if val_ign.startswith("["):
                                    modelli_ignore = _estrai_lista_inline(val_ign)
                                else:
                                    modelli_ignore = []
                                    for r_seq in sub_ev_righe[idx_p + 1 :]:
                                        if re.match(r"^\s*(?:'[A-Za-z0-9_-]+'|\"[A-Za-z0-9_-]+\"|[A-Za-z0-9_-]+)\s*:", r_seq):
                                            break
                                        m_seq = re.match(r"^\s*-\s*(.*)$", r_seq)
                                        if m_seq:
                                            modelli_ignore.append(m_seq.group(1).strip().strip("'\""))

                        if modelli_ignore is not None:
                            if not _branches_ignore_esclude_bottega(modelli_ignore):
                                parte_push = True
                                motivo_push = "parte su push con branches-ignore che non esclude bottega/*"
                        elif modelli_branches is not None:
                            if _branches_prendono_bottega(modelli_branches):
                                parte_push = True
                                motivo_push = "parte su push sui rami bottega/*"
                        else:
                            parte_push = True
                            motivo_push = "parte su push in ogni ramo"

                elif ev_nome in ("pull_request", "pull_request_target"):
                    if not tutti_job_protetti:
                        parte_pr = True
                        motivo_pr = f"parte su {ev_nome} senza guardia in ogni job"
                elif ev_nome not in (
                    "workflow_dispatch",
                    "schedule",
                    "workflow_call",
                    "issues",
                    "issue_comment",
                    "release",
                ):
                    dubbio_on = True

                idx_sub = k

    if dubbio_on:
        return [Rischio(file=file, motivo="evento on non riconosciuto o dubbio")]

    pericolo = _trova_pericolo(righe_pulite)

    if (parte_push or parte_pr) and pericolo:
        motivo_trigger = motivo_push if parte_push else motivo_pr
        return [Rischio(file=file, motivo=f"{motivo_trigger} e {pericolo}")]

    return []


def rischi(testi: Mapping[str, str]) -> list[Rischio]:
    """Analizza una mappa di nome file -> testo del workflow e restituisce l'elenco dei rischi."""
    trovati: list[Rischio] = []
    for nome, testo in testi.items():
        trovati.extend(_esamina_workflow(nome, testo))
    return trovati


def rischi_del_ramo(clone: Path, ramo: str) -> list[Rischio]:
    """Legge e controlla i workflow .yml e .yaml dal ramo remoto refs/remotes/origin/<ramo>."""
    ref_ramo = f"refs/remotes/origin/{ramo}"
    try:
        proc_ls = subprocess.run(
            ["git", "-C", str(clone), "ls-tree", "--name-only", ref_ramo, ".github/workflows/"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc_ls.returncode != 0:
            return [Rischio(file=".github/workflows", motivo="workflow illeggibili")]

        righe = [r.strip() for r in proc_ls.stdout.splitlines() if r.strip()]
        testi: dict[str, str] = {}
        for nome_file in righe:
            if not (nome_file.endswith(".yml") or nome_file.endswith(".yaml")):
                continue
            proc_show = subprocess.run(
                ["git", "-C", str(clone), "show", f"{ref_ramo}:{nome_file}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc_show.returncode != 0:
                return [Rischio(file=nome_file, motivo="workflow illeggibili")]
            testi[nome_file] = proc_show.stdout

        return rischi(testi)
    except OSError:
        return [Rischio(file=".github/workflows", motivo="workflow illeggibili")]
