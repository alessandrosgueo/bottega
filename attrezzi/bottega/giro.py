"""Il giro dell'esecutore: regia del lavoro assegnato a una bottega.

Prepara il fascicolo, fa lavorare il modello come utente dell'esecutore e senza chiavi,
gestisce consulto e quota, controlla con l'oracolo e consegna.
Solo libreria standard.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import argparse
import os
import random
import re
import shlex
import shutil
import signal
import subprocess

from bottega.board import Board, BoardComando, BoardProject
from bottega.brief import fatto_quando, ramo
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Candidato,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import Commento, Forgia, ForgiaGh, Issue, _spoglia_segno
from bottega.porte import Controllo, Lancio, Porta, ambiente_ripulito, porta as fabbrica_porte
from bottega.quota import nome_variabile, valore_esaurita
from bottega.scelta import Compito, scegli
from bottega.segni import nota, ruolo, scrivi_nota

# RV2: Ogni git del runner ha opzioni rigorose per isolamento e quotePath disattivato
OPZIONI_GIT_RUNNER: tuple[str, ...] = (
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=false",
    "-c", "diff.external=",
    "-c", "core.quotePath=false",
)

OPZIONI_GIT_CRED: tuple[str, ...] = (
    "-c", "credential.helper=",
    "-c", "credential.helper=!gh auth git-credential",
)


@dataclass(frozen=True)
class EsitoGiro:
    """L'esito complessivo del giro dell'esecutore."""

    esito: str
    motivo: str | None = None
    pr: int | None = None
    oracolo_ok: bool | None = None
    dettagli: dict[str, Any] = field(default_factory=dict)


def recinta_testo_modello(testo: str, limite: int = 60000) -> str:
    """Recinta il testo del modello in un blocco di codice sicuro troncato a limite caratteri.

    Usa un numero di apici (almeno 3) strettamente maggiore di qualsiasi sequenza di apici consecutivi nel testo.
    """
    testo_troncato = (testo or "")[:limite]
    sequenze = re.findall(r"`+", testo_troncato)
    max_apici = max((len(s) for s in sequenze), default=0)
    recinto = "`" * max(3, max_apici + 1)
    return f"{recinto}\n{testo_troncato}\n{recinto}"


def analizza_diff_raw(raw_bytes: bytes) -> list[tuple[str, str, str, str, str]]:
    """Analizza l'output di `git diff --raw -z -M` separato da NUL.

    Restituisce una lista di tuple (status, src_mode, dst_mode, old_path, new_path).
    """
    tokens = raw_bytes.split(b"\0")
    risultato: list[tuple[str, str, str, str, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token:
            i += 1
            continue
        parti = token.decode("utf-8", errors="surrogateescape").split()
        if not parti or not parti[0].startswith(":"):
            i += 1
            continue
        src_mode = parti[0][1:]
        dst_mode = parti[1]
        status = parti[4]
        i += 1
        if i >= len(tokens):
            break
        old_path = tokens[i].decode("utf-8", errors="surrogateescape")
        i += 1
        if status.startswith(("R", "C")):
            if i >= len(tokens):
                break
            new_path = tokens[i].decode("utf-8", errors="surrogateescape")
            i += 1
        else:
            new_path = old_path
        risultato.append((status, src_mode, dst_mode, old_path, new_path))
    return risultato


def controlla_violazioni_diff(diff_entries: list[tuple[str, str, str, str, str]]) -> str | None:
    """Verifica che nessun percorso tocchi .github, .bottega, .gitmodules e nessun modo sia link o submodulo."""
    for status, src_mode, dst_mode, old_path, new_path in diff_entries:
        if src_mode == "120000" or dst_mode == "120000":
            return f"link simbolico vietato: {old_path if src_mode == '120000' else new_path}"
        if src_mode == "160000" or dst_mode == "160000":
            return f"submodulo vietato: {old_path if src_mode == '160000' else new_path}"
        for p in (old_path, new_path):
            p_norm = p.strip("/").lower()
            if p_norm == ".gitmodules" or p_norm.endswith("/.gitmodules"):
                return f".gitmodules vietato: {p}"
            if p_norm == ".github" or p_norm.startswith(".github/") or "/.github/" in p_norm:
                return f"percorso sotto .github vietato: {p}"
            if p_norm == ".bottega" or p_norm.startswith(".bottega/") or "/.bottega/" in p_norm:
                return f"percorso sotto .bottega vietato: {p}"
    return None


def esegui_oracolo(
    cmd: str,
    cartella: Path,
    prefisso: Sequence[str],
    tempo: float,
    env: dict[str, str],
) -> tuple[bool, int, str]:
    """Esegue l'oracolo nel suo gruppo di processi con tetto di tempo.

    Restituisce (ok, codice_uscita, ultime_40_righe).
    Se il tempo scade, uccide il gruppo di processi e restituisce (False, 124, messaggio).
    """
    completo = [*prefisso, "bash", "-c", cmd]
    try:
        proc = subprocess.Popen(
            completo,
            cwd=str(cartella),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
    except Exception as exc:
        return False, 1, f"errore avvio oracolo: {exc}"

    try:
        stdout, stderr = proc.communicate(timeout=tempo)
        codice = proc.returncode
        out = (stdout + "\n" + stderr).strip()
        ultime_40 = "\n".join(out.splitlines()[-40:])
        return (codice == 0), codice, ultime_40
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        proc.communicate()
        return False, 124, f"tempo scaduto per l'oracolo dopo {tempo} secondi"


def _committa_lavoro_pendente(lavoro_dir: Path, prefisso: Sequence[str], env: dict[str, str], messaggio: str) -> None:
    """Esegue git add -A e git commit se vi sono modifiche non committate nell'albero di lavoro."""
    st_proc = subprocess.run(
        [*prefisso, "git", "status", "--porcelain"],
        cwd=str(lavoro_dir),
        capture_output=True,
        text=True,
        env=env,
    )
    if st_proc.stdout.strip():
        subprocess.run([*prefisso, "git", "add", "-A"], cwd=str(lavoro_dir), check=True, capture_output=True, env=env)
        subprocess.run([*prefisso, "git", "commit", "-m", messaggio], cwd=str(lavoro_dir), check=True, capture_output=True, env=env)


def _trova_candidato(
    lavoro_numero: int,
    bottega_id: str,
    configurazione: Configurazione,
    board: Board,
) -> Candidato:
    """Trova il candidato esecutore per la bottega indicata."""
    lav = board.lavoro(lavoro_numero)
    if lav and lav.esecutore:
        for cand in configurazione.candidati.values():
            if (cand.id == lav.esecutore or cand.nome == lav.esecutore) and cand.bottega == bottega_id:
                return cand

    for cand in configurazione.candidati.values():
        if cand.bottega == bottega_id and "eseguire" in cand.funzioni:
            return cand

    raise ValueError(f"Nessun candidato esecutore trovato per la bottega {bottega_id!r}")


def _solo_runner(configurazione: Configurazione, runner: str | None) -> Configurazione:
    """La configurazione coi soli candidati che girano sul runner dato."""
    candidati = {k: c for k, c in configurazione.candidati.items() if runner is not None and c.runner == runner}
    return replace(configurazione, candidati=candidati)


def _ottieni_porta(
    nome_porta: str,
    porte: Mapping[str, Porta] | Callable[[str], Porta] | None,
) -> Porta:
    """Restituisce l'istanza della porta richiesta."""
    if porte is None:
        return fabbrica_porte(nome_porta)
    if isinstance(porte, Mapping):
        if nome_porta not in porte:
            raise ValueError(f"Porta {nome_porta!r} non trovata nelle porte fornite")
        return porte[nome_porta]
    if callable(porte):
        return porte(nome_porta)
    raise TypeError(f"Argomento 'porte' non valido: {porte!r}")


def _rilancia_distributore(forgia: Forgia) -> None:
    """Rilancia il distributore a fine giro; gli errori non bloccano il giro."""
    try:
        forgia.avvia_workflow("bottega-distributore.yml", {})
    except Exception:
        pass


def _prepara_fascicolo(
    fascicolo_dir: Path,
    compito: Issue,
    iss_madre: Issue,
    forgia: Forgia,
    clone_progetto: Path,
    candidato: Candidato,
    nome_ramo: str,
    base_commit: str,
    pr_num: int | None,
    d_nota: dict[str, str],
    ramo_principale: str,
    comandanti: Sequence[str],
) -> None:
    """Prepara tutti i documenti del fascicolo prima del lancio dell'esecutore."""
    fascicolo_dir.mkdir(parents=True, exist_ok=True)
    (fascicolo_dir / "brief.md").write_text(compito.corpo, encoding="utf-8")

    if compito.numero != iss_madre.numero or forgia.sotto_issue(iss_madre.numero):
        (fascicolo_dir / "lavoro.md").write_text(iss_madre.corpo, encoding="utf-8")

    comm_list: list[Commento] = []
    if compito.numero != iss_madre.numero:
        comm_list.extend(forgia.commenti(iss_madre.numero))
    comm_list.extend(forgia.commenti(compito.numero))

    # RV3: solo i commenti dei comandanti (di serie il proprietario)
    comandanti_set = {c.strip().lower() for c in comandanti} | {forgia.proprietario().strip().lower()}
    comm_filtrati = [c for c in comm_list if c.autore.strip().lower() in comandanti_set]
    righe_comm: list[str] = []
    for c in comm_filtrati:
        r = ruolo(c.corpo)
        prefix = f"[{r}] " if r else ""
        testo_pulito = _spoglia_segno(c.corpo)
        righe_comm.append(f"{prefix}{c.autore}:\n{testo_pulito}\n")
    (fascicolo_dir / "commenti.md").write_text("\n---\n".join(righe_comm), encoding="utf-8")

    # RV3: Costituzione letta con git show da origin/<principale>
    res_cost = subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "show", f"origin/{ramo_principale}:docs/costituzione.md"],
        cwd=str(clone_progetto),
        capture_output=True,
        text=True,
    )
    if res_cost.returncode == 0 and res_cost.stdout.strip():
        (fascicolo_dir / "costituzione.md").write_text(res_cost.stdout, encoding="utf-8")

    # RV3: Quaderni
    modello_slug = re.sub(r"[^a-z0-9]+", "-", candidato.modello.lower()).strip("-")
    testi_quaderno: list[str] = []

    bottega_clone_env = os.environ.get("BOTTEGA_CLONE")
    if bottega_clone_env:
        q_bottega = Path(bottega_clone_env) / "quaderni" / f"{modello_slug}.md"
        if q_bottega.exists():
            testi_quaderno.append(q_bottega.read_text(encoding="utf-8"))

    q_locale = Path.cwd() / "quaderni" / f"{modello_slug}.md"
    if q_locale.exists() and not (bottega_clone_env and Path(bottega_clone_env) == Path.cwd()):
        testi_quaderno.append(q_locale.read_text(encoding="utf-8"))

    # Quaderno del progetto letto con git show dal ramo principale
    res_q_prog = subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "show", f"origin/{ramo_principale}:.github/bottega/quaderni/{modello_slug}.md"],
        cwd=str(clone_progetto),
        capture_output=True,
        text=True,
    )
    if res_q_prog.returncode == 0 and res_q_prog.stdout.strip():
        testi_quaderno.append(res_q_prog.stdout)

    if testi_quaderno:
        (fascicolo_dir / "quaderno.md").write_text("\n\n".join(testi_quaderno), encoding="utf-8")

    testo_stato = (
        f"Ramo: {nome_ramo}\n"
        f"Base: {base_commit}\n"
        f"PR: {pr_num if pr_num is not None else 'nessuna'}\n"
        f"Nota: {scrivi_nota(d_nota)}\n"
    )
    (fascicolo_dir / "stato.md").write_text(testo_stato, encoding="utf-8")


def _verifica_e_consegna_bundle(
    clone_progetto: Path,
    bundle_file: Path,
    base_commit: str,
    nome_ramo: str,
    forgia: Forgia,
    compito_numero: int,
    d_nota: dict[str, str],
    board: Board,
    lavoro: int,
) -> tuple[bool, list[tuple[str, str, str, str, str]]]:
    """Verifica il bundle con il git del runner, controlla l'antenato, diff raw -z -M e applica.

    Restituisce (ok, entries_diff).
    """
    if not bundle_file.exists():
        return False, []

    # 1. Verifica bundle col git del runner
    subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "bundle", "verify", str(bundle_file)],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )

    # 2. Fetch nel refrefs/bottega/consegna
    subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "fetch", str(bundle_file), f"+{nome_ramo}:refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )

    # 3. Controllo che base sia antenato
    res_anc = subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "merge-base", "--is-ancestor", base_commit, "refs/bottega/consegna"],
        cwd=str(clone_progetto),
        capture_output=True,
    )
    if res_anc.returncode != 0:
        msg = f"Consegna rifiutata: il commit base {base_commit} non e antenato del ramo consegnato."
        forgia.commenta(compito_numero, msg, ruolo="esecutore")
        d_nota["motivo"] = "base non antenato"
        board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
        return False, []

    # 4. Diff raw -z -M tra base e refs/bottega/consegna letto a NUL
    proc_diff = subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "diff", "--raw", "-z", "-M", "--no-ext-diff", base_commit, "refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )
    entries = analizza_diff_raw(proc_diff.stdout)

    # 5. Controlli di sicurezza sui percorsi e sui modi
    motivo_violazione = controlla_violazioni_diff(entries)
    if motivo_violazione:
        msg = (
            f"Consegna rifiutata: la patch tocca percorsi sotto .github/ ({motivo_violazione})"
            if "github" in motivo_violazione
            else f"Consegna rifiutata: {motivo_violazione}"
        )
        forgia.commenta(compito_numero, msg, ruolo="esecutore")
        d_nota["motivo"] = "modifica a .github vietata" if "github" in motivo_violazione else motivo_violazione
        board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
        return False, []

    # 6. Se vi sono modifiche, aggiorna il ramo locale su refs/bottega/consegna e spinge
    if entries:
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "checkout", "-B", nome_ramo, "refs/bottega/consegna"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "push", "origin", nome_ramo],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
    return True, entries


def giro(
    lavoro: int,
    bottega: str,
    *,
    configurazione: Configurazione,
    forgia: Forgia,
    board: Board,
    porte: Mapping[str, Porta] | Callable[[str], Porta] | None = None,
    clone_progetto: Path,
    spazio: Path,
    prefisso: Sequence[str] = (),
    adesso: datetime,
    caso: random.Random,
) -> EsitoGiro:
    """Esegue un giro dell'esecutore per il lavoro e la bottega indicati."""
    if bottega not in configurazione.botteghe:
        raise ValueError(f"Bottega sconosciuta: {bottega!r}")
    bottega_cfg = configurazione.botteghe[bottega]

    candidato = _trova_candidato(lavoro, bottega, configurazione, board)
    porta_esecutore = _ottieni_porta(candidato.porta, porte)

    # RV9: Controllo all'apertura con prefisso
    try:
        controllo = porta_esecutore.controlla(prefisso=prefisso)
    except TypeError:
        controllo = porta_esecutore.controlla()

    chiave_avviso = f"porta_{porta_esecutore.nome}"
    titolo_avviso = f"Avviso della bottega: porta {porta_esecutore.nome}"
    if not controllo.ok:
        forgia.avviso(chiave_avviso, titolo_avviso, controllo.motivo or "porta non pronta")
        board.stato(lavoro, "pronto")
        return EsitoGiro("porta_non_pronta", motivo=controllo.motivo)
    else:
        forgia.avviso(chiave_avviso, titolo_avviso, None)

    # Identificazione compito e madre
    iss_madre = forgia.issue(lavoro)
    sotto_issues = forgia.sotto_issue(lavoro)
    aperte = [s for s in sotto_issues if s.aperta]

    lav_attuale = board.lavoro(lavoro)
    d_nota = nota(lav_attuale.nota if lav_attuale else "")

    if sotto_issues:
        if not aperte:
            nome_ramo = d_nota.get("ramo") or ramo(iss_madre.numero, iss_madre.titolo)
            pr_num = forgia.pr_del_ramo(nome_ramo) or 0
            board.consegna(lavoro, pr=pr_num)
            _rilancia_distributore(forgia)
            return EsitoGiro("consegnato", motivo="tutte le sotto-issue gia chiuse", pr=pr_num)
        compito = aperte[0]
        ultima_sotto_issue = len(aperte) == 1
    else:
        compito = iss_madre
        ultima_sotto_issue = True

    # RV8: ramo si scrive al primo giro e si riusa (il titolo della madre può cambiare)
    if not d_nota.get("ramo"):
        d_nota["ramo"] = ramo(iss_madre.numero, iss_madre.titolo)
    nome_ramo = d_nota["ramo"]

    # RV8: azzeramento tentativi e attese al cambio di compito
    compito_salvato = d_nota.get("compito")
    if compito_salvato and compito_salvato != str(compito.numero):
        d_nota.pop("tentativi", None)
        d_nota.pop("attese", None)
    d_nota["compito"] = str(compito.numero)

    ramo_principale = forgia.ramo_principale()
    if not nome_ramo.startswith("bottega/") or nome_ramo == ramo_principale:
        msg = f"Consegna rifiutata: ramo {nome_ramo!r} non valido o principale"
        forgia.commenta(compito.numero, msg, ruolo="esecutore")
        board.stato(lavoro, "bloccato", nota=scrivi_nota({"motivo": "ramo non valido"}))
        _rilancia_distributore(forgia)
        return EsitoGiro("bloccato", motivo="ramo non valido")

    cmd_fatto_quando = fatto_quando(compito.corpo)
    if not cmd_fatto_quando:
        msg = "Lavoro non pronto: manca il blocco «Fatto quando» nel brief."
        forgia.commenta(compito.numero, msg, ruolo="esecutore")
        board.stato(lavoro, "pronto", nota=scrivi_nota({"motivo": "manca fatto quando"}))
        _rilancia_distributore(forgia)
        return EsitoGiro("senza_fatto_quando", motivo="manca fatto quando")

    d_nota["inizio"] = adesso.isoformat()
    if not prefisso:
        d_nota["utente"] = "runner"
    board.stato(lavoro, "in corso", nota=scrivi_nota(d_nota))

    # Spazio del giro
    timestamp_str = str(int(adesso.timestamp()))
    dir_giro = spazio / f"{lavoro}-{timestamp_str}"
    dir_giro.mkdir(parents=True, exist_ok=True)
    env_rip = ambiente_ripulito()

    # RV5: try/except attorno a tutto il giro: nessuna eccezione deve uscire da giro()
    try:
        # RV2: Pulizia del clone del runner da giri precedenti e rebase-apply
        subprocess.run(["git", *OPZIONI_GIT_RUNNER, "am", "--abort"], cwd=str(clone_progetto), capture_output=True)
        rebase_apply = clone_progetto / ".git" / "rebase-apply"
        if rebase_apply.exists():
            shutil.rmtree(rebase_apply, ignore_errors=True)
        subprocess.run(["git", *OPZIONI_GIT_RUNNER, "reset", "--hard"], cwd=str(clone_progetto), capture_output=True)
        subprocess.run(["git", *OPZIONI_GIT_RUNNER, "clean", "-fdx"], cwd=str(clone_progetto), capture_output=True)

        res_shallow = subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--is-shallow-repository"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        if res_shallow.stdout.strip() == "true" or (clone_progetto / ".git" / "shallow").exists():
            subprocess.run(
                ["git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "fetch", "--unshallow"],
                cwd=str(clone_progetto),
                capture_output=True,
            )

        # Prepara il ramo in clone_progetto con credenziali gh
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "fetch", "origin"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        res_verify = subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", f"origin/{nome_ramo}"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        if res_verify.returncode == 0:
            subprocess.run(
                ["git", *OPZIONI_GIT_RUNNER, "checkout", "-B", nome_ramo, f"origin/{nome_ramo}"],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )
        else:
            res_main = subprocess.run(
                ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", f"origin/{ramo_principale}"],
                cwd=str(clone_progetto),
                capture_output=True,
                text=True,
            )
            base_ref = f"origin/{ramo_principale}" if res_main.returncode == 0 else ramo_principale
            subprocess.run(
                ["git", *OPZIONI_GIT_RUNNER, "checkout", "-B", nome_ramo, base_ref],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )

        base_commit = subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "HEAD"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Bundle iniziale per clonare nella copia dell'esecutore
        bundle_file_iniziale = dir_giro / "ramo.bundle"
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "bundle", "create", str(bundle_file_iniziale), nome_ramo],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )

        lavoro_dir = dir_giro / "lavoro"
        cmd_clone = [*prefisso, "git", "clone", str(bundle_file_iniziale), str(lavoro_dir), "-b", nome_ramo]
        subprocess.run(cmd_clone, check=True, capture_output=True, env=env_rip)
        subprocess.run(
            [*prefisso, "git", "config", "user.name", "Bottega"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            env=env_rip,
        )
        subprocess.run(
            [*prefisso, "git", "config", "user.email", "bottega@local"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            env=env_rip,
        )

        # RV3: Il fascicolo sta nella copia dell'esecutore in .bottega/fascicolo/, esclusa con .git/info/exclude
        exclude_path = lavoro_dir / ".git" / "info" / "exclude"
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        exclude_path.write_text(".bottega/\n", encoding="utf-8")
        fascicolo_dir = lavoro_dir / ".bottega" / "fascicolo"

        pr_esistente = forgia.pr_del_ramo(nome_ramo)
        _prepara_fascicolo(
            fascicolo_dir=fascicolo_dir,
            compito=compito,
            iss_madre=iss_madre,
            forgia=forgia,
            clone_progetto=clone_progetto,
            candidato=candidato,
            nome_ramo=nome_ramo,
            base_commit=base_commit,
            pr_num=pr_esistente,
            d_nota=d_nota,
            ramo_principale=ramo_principale,
            comandanti=configurazione.progetto.comandanti,
        )

        conversazione_id = d_nota.get("conversazione")
        prompt_testo = (
            f"Sei l'esecutore per il compito {compito.numero}: {compito.titolo}.\n\n"
            f"Il fascicolo in {fascicolo_dir} contiene:\n"
            "- brief.md: il brief del compito\n"
            "- lavoro.md: il corpo della madre se tappa\n"
            "- commenti.md: tutti i commenti del compito e della madre\n"
            "- costituzione.md: la costituzione del progetto\n"
            "- quaderno.md: il quaderno del modello\n"
            "- stato.md: ramo, base, PR e nota\n\n"
            f"Fatto quando:\n{cmd_fatto_quando}\n\n"
            "Istruzioni:\n"
            f"1. Lavora in questa cartella e committa nel ramo corrente ({nome_ramo}) un commit per compito.\n"
            "2. Non toccare mai .github/ o .bottega/.\n"
            "3. Alla fine scrivi il rapporto come ultimo messaggio.\n"
            "4. Se sei bloccato o se una scelta contraddice il piano o tocca le quattro barriere, "
            "chiudi con DOMANDA PER CHI DECIDE: seguita dalla domanda precisa.\n"
        )
        consulti_effettuati = 0

        while True:
            lancio = porta_esecutore.lancia(
                cartella=lavoro_dir,
                prompt=prompt_testo,
                modello=candidato.modello,
                conversazione=conversazione_id,
                prefisso=prefisso,
            )

            # RV7: Il consulto parte solo con esito == "fatto" e se l'ultima riga non vuota comincia con DOMANDA PER CHI DECIDE:
            righe_lancio = [r.strip() for r in lancio.testo.splitlines() if r.strip()]
            e_consulto = (
                lancio.esito == "fatto"
                and bool(righe_lancio and righe_lancio[-1].startswith("DOMANDA PER CHI DECIDE:"))
            )

            if e_consulto:
                consulti_effettuati += 1
                if consulti_effettuati > 2:
                    d_nota["motivo"] = "troppi consulti"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="troppi consulti")

                idx = lancio.testo.find("DOMANDA PER CHI DECIDE:")
                domanda = lancio.testo[idx:].strip()
                forgia.commenta(compito.numero, f"Consulto dell'esecutore:\n\n{recinta_testo_modello(domanda)}", ruolo="esecutore")

                compito_cons = Compito(funzione="consigliare", fuori=True)
                quote_map = {b_id: forgia.variabile(nome_variabile(b_id)) for b_id in configurazione.botteghe}
                scelta_cons = scegli(
                    compito=compito_cons,
                    configurazione=_solo_runner(configurazione, candidato.runner),
                    risultati={},
                    quote=quote_map,
                    adesso=adesso,
                    caso=caso,
                )

                if not scelta_cons.candidato or scelta_cons.aspetta:
                    msg = "Nessun consigliere con quota disponibile per il consulto."
                    forgia.commenta(compito.numero, msg, ruolo="avviso")
                    d_nota["motivo"] = "senza consigliere con quota"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="senza consigliere con quota")

                cand_cons = configurazione.candidati[scelta_cons.candidato]
                porta_cons = _ottieni_porta(cand_cons.porta, porte)
                prompt_cons = (
                    f"Rispondi al consulto sul compito {compito.numero}:\n\n"
                    f"{domanda}\n\n"
                    "La prima riga della risposta DEVE essere 'RISPOSTA' oppure 'A CHI DECIDE'."
                )

                # RV7: Il consigliere lavora in una copia usa e getta
                dir_cons = dir_giro / f"consigliere-{consulti_effettuati}"
                shutil.copytree(str(lavoro_dir), str(dir_cons), symlinks=False)
                try:
                    lancio_cons = porta_cons.lancia(
                        cartella=dir_cons,
                        prompt=prompt_cons,
                        modello=cand_cons.modello,
                        sola_lettura=True,
                        prefisso=prefisso,
                    )
                finally:
                    shutil.rmtree(dir_cons, ignore_errors=True)

                if lancio_cons.esito == "quota":
                    rinnovo_cons = lancio_cons.rinnovo or (adesso + timedelta(hours=1))
                    if rinnovo_cons.tzinfo is None:
                        rinnovo_cons = rinnovo_cons.replace(tzinfo=adesso.tzinfo or timezone.utc)
                    forgia.imposta_variabile(nome_variabile(cand_cons.bottega), valore_esaurita(rinnovo_cons))
                    d_nota["motivo"] = "quota"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="quota")

                if lancio_cons.esito != "fatto":
                    d_nota["motivo"] = lancio_cons.esito
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo=lancio_cons.esito)

                msg_cons = f"Risposta del consigliere ({cand_cons.nome}):\n\n{recinta_testo_modello(lancio_cons.testo)}"
                forgia.commenta(compito.numero, msg_cons, ruolo="consigliere")

                righe_cons = [r.strip() for r in lancio_cons.testo.splitlines() if r.strip()]
                prima_riga_cons = righe_cons[0].upper() if righe_cons else ""
                if prima_riga_cons.startswith("RISPOSTA"):
                    # RV7: Dopo RISPOSTA il prompt di ripresa ripete compito e fascicolo
                    prompt_testo = (
                        f"Compito {compito.numero}: {compito.titolo}.\n"
                        f"Fascicolo in {fascicolo_dir}.\n\n"
                        f"Risposta del consigliere:\n{lancio_cons.testo}"
                    )
                    conversazione_id = lancio.conversazione
                    continue
                else:
                    d_nota["motivo"] = "consulto a chi decide"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="consulto a chi decide")

            break

        # RV4: Il lavoro non committato si committa prima di OGNI uscita dopo il lancio
        _committa_lavoro_pendente(lavoro_dir, prefisso, env_rip, f"salvataggio per compito {compito.numero}")

        # B3-R14: Quota esaurita
        if lancio.esito == "quota":
            rinnovo = lancio.rinnovo or (adesso + timedelta(hours=1))
            if rinnovo.tzinfo is None:
                rinnovo = rinnovo.replace(tzinfo=adesso.tzinfo or timezone.utc)
            var_quota = nome_variabile(bottega_cfg.id)
            forgia.imposta_variabile(var_quota, valore_esaurita(rinnovo))

            cur_head = subprocess.run(
                [*prefisso, "git", "rev-parse", "HEAD"],
                cwd=str(lavoro_dir),
                check=True,
                capture_output=True,
                text=True,
                env=env_rip,
            ).stdout.strip()

            if cur_head != base_commit:
                bundle_salv = dir_giro / "salvataggio.bundle"
                subprocess.run(
                    [*prefisso, "git", "bundle", "create", str(bundle_salv), nome_ramo],
                    cwd=str(lavoro_dir),
                    check=True,
                    capture_output=True,
                    env=env_rip,
                )
                ok_salv, _ = _verifica_e_consegna_bundle(
                    clone_progetto=clone_progetto,
                    bundle_file=bundle_salv,
                    base_commit=base_commit,
                    nome_ramo=nome_ramo,
                    forgia=forgia,
                    compito_numero=compito.numero,
                    d_nota=d_nota,
                    board=board,
                    lavoro=lavoro,
                )
                if not ok_salv:
                    _rilancia_distributore(forgia)
                    return EsitoGiro("bloccato", motivo=d_nota.get("motivo", "modifica a .github vietata"))
                pr_num = forgia.pr_del_ramo(nome_ramo)
                if pr_num is None:
                    titolo_salv = iss_madre.titolo
                    corpo_salv = f"Lavoro: #{iss_madre.numero}\n\nSalvataggio parziale per quota esaurita."
                    forgia.apri_pr(nome_ramo, titolo_salv, corpo_salv)

            # RV8: attese non viene cresciuta dal giro!
            if lancio.conversazione:
                d_nota["conversazione"] = lancio.conversazione
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
            _rilancia_distributore(forgia)
            return EsitoGiro("quota", motivo="quota esaurita")

        # Accesso o errore
        if lancio.esito in ("accesso", "errore"):
            tentativi = int(d_nota.get("tentativi", 0)) + 1
            d_nota["tentativi"] = str(tentativi)
            if tentativi >= 3:
                d_nota["motivo"] = lancio.esito
                board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
                msg_err = f"Lavoro bloccato dopo 3 tentativi ({lancio.esito}):\n\n{recinta_testo_modello(lancio.testo)}"
                forgia.commenta(compito.numero, msg_err, ruolo="esecutore")
                _rilancia_distributore(forgia)
                return EsitoGiro("bloccato", motivo=f"3 tentativi falliti ({lancio.esito})")
            else:
                board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
                _rilancia_distributore(forgia)
                return EsitoGiro("errore", motivo=f"tentativo {tentativi} fallito ({lancio.esito})")

        if lancio.esito != "fatto":
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
            _rilancia_distributore(forgia)
            return EsitoGiro(lancio.esito, motivo=lancio.testo)

        # RV4: Niente commit nuovi -> nessuna PR nuova, il lavoro torna pronto con tentativi+1 e rapporto in commento
        cur_head = subprocess.run(
            [*prefisso, "git", "rev-parse", "HEAD"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            text=True,
            env=env_rip,
        ).stdout.strip()

        if cur_head == base_commit:
            tentativi = int(d_nota.get("tentativi", 0)) + 1
            d_nota["tentativi"] = str(tentativi)
            d_nota["motivo"] = "nessun commit"
            stato_dest = "bloccato" if tentativi >= 3 else "pronto"
            board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
            forgia.commenta(
                compito.numero,
                f"Rapporto dell'esecutore per il compito {compito.numero}:\n\n{recinta_testo_modello(lancio.testo)}",
                ruolo="esecutore",
            )
            _rilancia_distributore(forgia)
            return EsitoGiro(stato_dest, motivo="nessun commit")

        # Genera bundle di consegna dall'esecutore (RV1)
        bundle_file = dir_giro / "consegna.bundle"
        subprocess.run(
            [*prefisso, "git", "bundle", "create", str(bundle_file), nome_ramo],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            env=env_rip,
        )

        # Controlli, verifica e applicazione eseguiti ESCLUSIVAMENTE dal runner col suo git
        ok_consegna, entries_diff = _verifica_e_consegna_bundle(
            clone_progetto=clone_progetto,
            bundle_file=bundle_file,
            base_commit=base_commit,
            nome_ramo=nome_ramo,
            forgia=forgia,
            compito_numero=compito.numero,
            d_nota=d_nota,
            board=board,
            lavoro=lavoro,
        )
        if not ok_consegna:
            _rilancia_distributore(forgia)
            return EsitoGiro("bloccato", motivo=d_nota.get("motivo", "consegna rifiutata"))

        # RV4: Se il commit è vuoto (nessun file toccato nel diff)
        if not entries_diff:
            tentativi = int(d_nota.get("tentativi", 0)) + 1
            d_nota["tentativi"] = str(tentativi)
            d_nota["motivo"] = "commit vuoto"
            stato_dest = "bloccato" if tentativi >= 3 else "pronto"
            board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
            forgia.commenta(
                compito.numero,
                f"Rapporto dell'esecutore per il compito {compito.numero}:\n\n{recinta_testo_modello(lancio.testo)}",
                ruolo="esecutore",
            )
            _rilancia_distributore(forgia)
            return EsitoGiro(stato_dest, motivo="commit vuoto")

        # B3-R12: Oracolo su copia fresca
        dir_oracolo = dir_giro / "oracolo"
        bundle_oracolo = dir_giro / "oracolo.bundle"
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "bundle", "create", str(bundle_oracolo), nome_ramo],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        cmd_clone_oracolo = [*prefisso, "git", "clone", str(bundle_oracolo), str(dir_oracolo), "-b", nome_ramo]
        subprocess.run(cmd_clone_oracolo, check=True, capture_output=True, env=env_rip)

        tempo_oracolo_env = os.environ.get("BOTTEGA_TEMPO_ORACOLO")
        tempo_oracolo = float(tempo_oracolo_env) if tempo_oracolo_env else 1800.0

        oracolo_ok, codice_oracolo, ultime_40 = esegui_oracolo(
            cmd=cmd_fatto_quando,
            cartella=dir_oracolo,
            prefisso=prefisso,
            tempo=tempo_oracolo,
            env=env_rip,
        )

        testo_oracolo = (
            f"Esito dell'oracolo: {'VERDE' if oracolo_ok else 'ROSSO'} (codice {codice_oracolo})\n\n"
            f"```\n{ultime_40}\n```"
        )
        forgia.commenta(compito.numero, testo_oracolo, ruolo="esecutore")

        # RV6: Apertura o recupero PR con testi del modello recintati
        pr_num = forgia.pr_del_ramo(nome_ramo)
        esito_oracolo_str = "VERDE" if oracolo_ok else "ROSSO"
        testo_recintato = recinta_testo_modello(lancio.testo)
        if pr_num is None:
            titolo_pr = iss_madre.titolo
            corpo_pr = (
                f"Lavoro: #{iss_madre.numero}\n\n"
                f"## Rapporto dell'esecutore\n\n{testo_recintato}\n\n"
                f"## Esito dell'oracolo\n\n{esito_oracolo_str}\n"
            )
            pr_num = forgia.apri_pr(nome_ramo, titolo_pr, corpo_pr)
        else:
            comm_rapporto = (
                f"Rapporto dell'esecutore per il compito {compito.numero}:\n\n"
                f"{testo_recintato}\n\n"
                f"Esito oracolo: {esito_oracolo_str}"
            )
            forgia.commenta(pr_num, comm_rapporto, ruolo="esecutore")

        # RV8: «Prove cambiate»: ogni stato diverso da 'A' su un percorso di prova, dal diff a NUL
        prove_cambiate = False
        for st, _sm, _dm, old_p, new_p in entries_diff:
            if st != "A":
                if "test" in old_p.lower() or "test" in new_p.lower():
                    prove_cambiate = True
                    break
        if prove_cambiate:
            forgia.etichetta(pr_num, "bottega: prove cambiate", aggiungi=True)

        # RV8: gitleaks scattato o .gitleaksignore/.gitleaks.toml toccati -> bottega: segreti
        segreti_trovati = False
        for st, _sm, _dm, old_p, new_p in entries_diff:
            for p in (old_p, new_p):
                p_norm = p.strip("/").lower()
                if p_norm in (".gitleaksignore", ".gitleaks.toml") or p_norm.endswith(("/.gitleaksignore", "/.gitleaks.toml")):
                    segreti_trovati = True
                    break
            if segreti_trovati:
                break

        if not segreti_trovati and shutil.which("gitleaks"):
            proc_gl = subprocess.run(
                ["gitleaks", "git", "--pre-commit", "--log-opts", f"{base_commit}..refs/bottega/consegna"],
                cwd=str(clone_progetto),
                capture_output=True,
            )
            if proc_gl.returncode != 0:
                segreti_trovati = True

        if segreti_trovati:
            forgia.etichetta(pr_num, "bottega: segreti", aggiungi=True)

        # B3-R17: Rilettura del consigliere
        compito_cons = Compito(funzione="consigliare", fuori=True)
        quote_map = {b_id: forgia.variabile(nome_variabile(b_id)) for b_id in configurazione.botteghe}
        scelta_cons = scegli(
            compito=compito_cons,
            configurazione=_solo_runner(configurazione, candidato.runner),
            risultati={},
            quote=quote_map,
            adesso=adesso,
            caso=caso,
        )
        if scelta_cons.candidato and not scelta_cons.aspetta:
            cand_cons = configurazione.candidati[scelta_cons.candidato]
            porta_cons = _ottieni_porta(cand_cons.porta, porte)
            diff_testo = subprocess.run(
                ["git", *OPZIONI_GIT_RUNNER, "diff", f"{base_commit}..refs/bottega/consegna"],
                cwd=str(clone_progetto),
                capture_output=True,
                text=True,
            ).stdout
            prompt_rev = f"Rileggi il seguente diff per il compito {compito.numero}:\n\n{diff_testo}"
            dir_rev = dir_giro / "revisione"
            dir_rev.mkdir(exist_ok=True)
            lancio_rev = porta_cons.lancia(
                cartella=dir_rev,
                prompt=prompt_rev,
                modello=cand_cons.modello,
                sola_lettura=True,
                prefisso=prefisso,
            )
            if lancio_rev.esito == "fatto":
                msg_rev = f"Revisione del consigliere ({cand_cons.nome}):\n\n{recinta_testo_modello(lancio_rev.testo)}"
                forgia.commenta(pr_num, msg_rev, ruolo="consigliere")
            else:
                forgia.commenta(pr_num, "compito senza rilettura", ruolo="consigliere")
        else:
            forgia.commenta(pr_num, "compito senza rilettura", ruolo="consigliere")

        # B3-R4: Chiusura sotto-issue o completamento madre
        if compito.numero != iss_madre.numero:
            forgia.chiudi_issue(compito.numero)

        if ultima_sotto_issue:
            board.consegna(lavoro, pr=pr_num)
        else:
            # RV8: precedente è l'id del candidato; azzeramento tentativi e attese
            d_nota["precedente"] = candidato.id
            d_nota.pop("conversazione", None)
            d_nota.pop("tentativi", None)
            d_nota.pop("attese", None)
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))

        _rilancia_distributore(forgia)
        return EsitoGiro("consegnato", pr=pr_num, oracolo_ok=oracolo_ok)

    except Exception as exc:
        # RV5: Nessuna eccezione esce da giro()
        tentativi = int(d_nota.get("tentativi", 0)) + 1
        d_nota["tentativi"] = str(tentativi)
        d_nota["motivo"] = f"errore: {exc}"
        stato_dest = "bloccato" if tentativi >= 3 else "pronto"
        board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
        try:
            target_comm = compito.numero if "compito" in locals() else lavoro
            forgia.commenta(target_comm, f"Errore durante il giro dell'esecutore: {exc}", ruolo="esecutore")
        except Exception:
            pass
        _rilancia_distributore(forgia)
        return EsitoGiro("bloccato" if tentativi >= 3 else "errore", motivo=str(exc))

    finally:
        # Pulizia completa dello spazio del giro
        if dir_giro.exists():
            if prefisso:
                subprocess.run([*prefisso, "rm", "-rf", str(dir_giro)], capture_output=True)
            shutil.rmtree(dir_giro, ignore_errors=True)


def argomenti_giro(parser: argparse.ArgumentParser) -> None:
    """Argomenti per il sottocomando `bottega giro`."""
    parser.add_argument("--lavoro", type=int, required=True, help="numero del lavoro da eseguire")
    parser.add_argument("--bottega", type=str, required=True, help="id della bottega assegnata")
    parser.add_argument(
        "--configurazione",
        type=Path,
        default=Path(PERCORSO_PREDEFINITO),
        help=f"percorso di bottega.toml (di serie: {PERCORSO_PREDEFINITO})",
    )


def comando_giro(args: argparse.Namespace) -> int:
    """Esegue il giro dell'esecutore da riga di comando."""
    cfg = leggi_configurazione(args.configurazione)

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        res = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"], capture_output=True, text=True)
        if res.returncode == 0:
            import json

            repo = json.loads(res.stdout).get("nameWithOwner", "")
        if not repo:
            raise ErroreConfigurazione("Impossibile determinare il repository GitHub (manca GITHUB_REPOSITORY)")

    forgia = ForgiaGh(repo)

    if cfg.progetto.adattatore:
        board: Board = BoardComando(shlex.split(cfg.progetto.adattatore))
    elif cfg.progetto.project is not None:
        board = BoardProject(proprietario=forgia.proprietario(), numero=cfg.progetto.project, repo=repo)
    else:
        raise ErroreConfigurazione("Né [progetto].project né [progetto].adattatore configurati per la board")

    env_pref = os.environ.get("BOTTEGA_PREFISSO_ESECUTORE", "").strip()
    prefisso = tuple(shlex.split(env_pref)) if env_pref else ()

    spazio_env = os.environ.get("BOTTEGA_SPAZIO")
    spazio = Path(spazio_env) if spazio_env else Path.cwd() / ".bottega_spazio"

    clone_progetto = Path.cwd()

    try:
        fuso = ZoneInfo(cfg.progetto.fuso)
    except Exception:
        fuso = timezone.utc
    adesso = datetime.now(fuso)
    caso = random.Random()

    esito = giro(
        lavoro=args.lavoro,
        bottega=args.bottega,
        configurazione=cfg,
        forgia=forgia,
        board=board,
        clone_progetto=clone_progetto,
        spazio=spazio,
        prefisso=prefisso,
        adesso=adesso,
        caso=caso,
    )

    print(f"Esito giro: {esito.esito} ({esito.motivo or 'completato'})")
    if esito.esito in ("consegnato", "quota", "in_attesa"):
        return 0
    return 1
