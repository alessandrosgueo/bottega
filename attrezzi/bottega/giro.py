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
import stat
import subprocess
import sys
import tempfile
import time

from bottega.board import Board, BoardComando, BoardProject
from bottega.brief import fatto_quando, ramo
from bottega import ci
from bottega.configurazione import (
    PERCORSO_PREDEFINITO,
    Candidato,
    Configurazione,
    ErroreConfigurazione,
    leggi_configurazione,
)
from bottega.forgia import Commento, Forgia, ForgiaGh, Issue, _spoglia_segno
import bottega.misure as misure
from bottega.porte import Controllo, Lancio, Porta, ambiente_ripulito, esegui_con_tetto, porta as fabbrica_porte
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

# C5: ogni processo del giro ha un tetto (un `git` falso sul PATH dell'esecutore non tiene appeso il giro) e i byte
# che non sono UTF-8 non lo fanno cadere.
TEMPO_GIT = 600


def _esegui(cmd: Sequence[str], **kw: Any) -> subprocess.CompletedProcess:
    kw.setdefault("timeout", TEMPO_GIT)
    if kw.get("text"):
        kw.setdefault("errors", "replace")
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(list(cmd), **kw)


# Parole che chiudono un'issue quando il commit arriva nel ramo principale (anche dopo un'unione).
_CHIUDE_ISSUE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*"
    r"(?:(?:[\w.-]+/[\w.-]+)?#\d+|GH-\d+|https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.IGNORECASE,
)

# File che cambiano come girano le prove anche quando sono nuovi.
_CONFIGURAZIONE_PROVE = {
    "conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg",
    "pyproject.toml", "noxfile.py",
}

# Il ramo viene dalla nota, che un umano può modificare: solo nomi semplici sotto bottega/.
_RAMO_VALIDO = re.compile(r"bottega/[A-Za-z0-9][A-Za-z0-9._/-]*")

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
        token = tokens[i].lstrip(b"\n")
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
    # C5: uscite su file, non su pipe; un orfano col `setsid` non fa aspettare il giro.
    codice, stdout, stderr, scaduto, errore = esegui_con_tetto(completo, cwd=cartella, env=env, tempo=tempo)
    if errore is not None:
        return False, 1, f"errore avvio oracolo: {errore}"
    out = (stdout + "\n" + stderr).strip()
    ultime_40 = "\n".join(out.splitlines()[-40:])
    if scaduto or codice is None:
        return False, 124, f"tempo scaduto per l'oracolo dopo {tempo} secondi\n{ultime_40}".strip()
    return (codice == 0), codice, ultime_40


def _committa_lavoro_pendente(lavoro_dir: Path, prefisso: Sequence[str], env: dict[str, str], messaggio: str) -> None:
    """Esegue git add -A e git commit se vi sono modifiche non committate nell'albero di lavoro."""
    st_proc = _esegui(
        [*prefisso, "git", "status", "--porcelain"],
        cwd=str(lavoro_dir),
        capture_output=True,
        text=True,
        env=env,
    )
    if st_proc.stdout.strip():
        _esegui([*prefisso, "git", "add", "-A"], cwd=str(lavoro_dir), check=True, capture_output=True, env=env)
        _esegui([*prefisso, "git", "commit", "-m", messaggio], cwd=str(lavoro_dir), check=True, capture_output=True, env=env)


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


# Il tetto di un bundle dell'esecutore copiato dal runner: oltre, il disco del runner non si riempie.
TETTO_COPIA = 1024 * 1024 * 1024


def prepara_cartelle_del_giro(spazio: Path, lavoro: int) -> tuple[Path, Path]:
    """Crea la cartella del giro (del runner, 2750) e dentro `esecutore/` (2770) (B6-R22).

    Il bit setgid su tutte e due tiene il gruppo dello spazio su ciò che vi nasce: l'esecutore legge ciò che il runner
    prepara nella cartella del giro (bundle, fascicolo) ma non ci crea niente, e il runner legge e toglie ciò che
    l'esecutore crea in `esecutore/`. Il `chmod` di Python toglie il setgid se il modo non lo nomina: va scritto.
    """
    spazio.mkdir(parents=True, exist_ok=True)
    dir_giro = Path(tempfile.mkdtemp(prefix=f"{lavoro}-", dir=spazio))
    dir_esec = dir_giro / "esecutore"
    try:
        dir_esec.mkdir()
        gid_comune = spazio.stat().st_gid
        for cartella in (dir_giro, dir_esec):
            if cartella.stat().st_gid != gid_comune:
                os.chown(cartella, -1, gid_comune)
        dir_giro.chmod(0o2750)
        dir_esec.chmod(0o2770)
    except BaseException:
        # Una cartella a metà non resta nello spazio: il chiamante non la conosce ancora.
        shutil.rmtree(dir_giro, ignore_errors=True)
        raise
    return dir_giro, dir_esec


def prepara_cartella_del_fascicolo(fascicolo_dir: Path) -> None:
    """La cartella del fascicolo del runner: 2750, così i file che vi scrive prendono il gruppo comune e l'esecutore
    li legge (e li copia), ma non li cambia."""
    fascicolo_dir.mkdir(parents=True, exist_ok=True)
    fascicolo_dir.chmod(0o2750)


def chiudi_file_del_fascicolo(fascicolo_dir: Path) -> None:
    """I file del fascicolo a 0640: leggibili dal gruppo comune senza dipendere dall'umask del runner."""
    for f in fascicolo_dir.iterdir():
        if f.is_file() and not f.is_symlink():
            f.chmod(0o640)


def _copia_dall_esecutore(origine: Path, destinazione: Path) -> None:
    """Copia nella cartella del runner un file scritto dall'esecutore, senza seguire link.

    Al posto del file l'esecutore può aver messo un link a un file del runner o una FIFO: si apre con `O_NOFOLLOW` e
    si accetta solo un file normale. La destinazione è nella cartella del runner, dove l'esecutore non scrive.
    """
    fd = os.open(origine, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as sorgente:
        if not stat.S_ISREG(os.fstat(sorgente.fileno()).st_mode):
            raise ValueError(f"{origine.name} non è un file normale")
        copiati = 0
        with open(destinazione, "xb") as copia:
            while blocco := sorgente.read(1024 * 1024):
                copiati += len(blocco)
                if copiati > TETTO_COPIA:
                    raise ValueError(f"{origine.name} supera {TETTO_COPIA} byte")
                copia.write(blocco)


def togli_come_esecutore(prefisso: Sequence[str], cartella: Path) -> None:
    """L'esecutore toglie ciò che ha creato in `cartella`, anche le sue cartelle chiuse (`chmod -R` ignora i link
    che incontra). Dalla radice: la cartella corrente del runner è chiusa all'esecutore."""
    if not prefisso:
        return
    try:
        _esegui([*prefisso, "chmod", "-R", "u+rwX", "--", str(cartella)], capture_output=True, cwd="/")
        _esegui([*prefisso, "rm", "-rf", "--", str(cartella)], capture_output=True, cwd="/")
    except (OSError, subprocess.SubprocessError):
        pass


def _uccidi_processi_esecutore(prefisso: Sequence[str]) -> None:
    """B6-R6: uccide i processi lasciati dall'utente dell'esecutore, con `kill -KILL -1` lanciato attraverso il prefisso.

    `kill -1` colpisce tutti i processi dell'utente che lo lancia. Si lancia solo se il prefisso porta davvero a un
    altro utente: un prefisso finto o sbagliato, che resta su chi esegue il giro, ucciderebbe il runner e tutta la
    sessione; come root ucciderebbe la macchina. Per questo prima si chiede `id -u` attraverso lo stesso prefisso, e
    ogni dubbio (errore, uscita illeggibile, uid uguale al nostro o 0) vuol dire non uccidere.
    """
    if not prefisso:
        return
    try:
        res = _esegui([*prefisso, "id", "-u"], capture_output=True, text=True, cwd="/")
        uid = int(res.stdout.strip()) if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return
    if uid is None or uid == 0 or uid == os.getuid():
        return
    try:
        _esegui([*prefisso, "kill", "-KILL", "-1"], capture_output=True, cwd="/")
    except (OSError, subprocess.SubprocessError):
        pass


def _rilancia_distributore(forgia: Forgia) -> None:
    """Rilancia il distributore a fine giro; gli errori non bloccano il giro."""
    try:
        forgia.avvia_workflow("bottega-distributore.yml", {})
    except Exception:
        pass


def _scrivi_misure(
    board: Board,
    compito_numero: int,
    candidato: Candidato,
    durata_secondi: int,
    consulti: int,
    token_esecutore: int,
) -> None:
    """Scrive le misure del compito sulla board nel finally del giro (B5-R6)."""
    lav = None
    try:
        lav = board.lavoro(compito_numero)
        if lav is None:
            board.aggiungi(compito_numero)
    except Exception as exc:
        print(f"misure: errore verifica/aggiunta compito #{compito_numero}: {exc}", file=sys.stderr)

    # Un compito già misurato per un altro candidato (cambio dopo una quota): le misure si sommano, ma il compito si
    # segna «più esecutori» e non entra né nei risultati né nei costi di un candidato. Chi ha misurato per primo sta in
    # `Misurato da` (l'id del candidato), che scrive solo il giro: `Esecutore` lo riscrive `prendi` prima del giro.
    precedente = (lav.campi.get("Misurato da") or "").strip() if lav is not None else ""
    if not precedente:
        try:
            board.campo(compito_numero, "Misurato da", candidato.id)
        except Exception as exc:
            print(f"misure: errore scrittura Misurato da per #{compito_numero}: {exc}", file=sys.stderr)
    if precedente and precedente.lower() != candidato.id.lower():
        voci = [v.strip() for v in (lav.campi.get("Misure parziali") or "").split(",") if v.strip()]
        if misure.PIU_ESECUTORI not in voci:
            voci.append(misure.PIU_ESECUTORI)
            try:
                board.campo(compito_numero, "Misure parziali", ", ".join(voci))
            except Exception as exc:
                print(f"misure: errore scrittura Misure parziali per #{compito_numero}: {exc}", file=sys.stderr)
        # Esecutore resta com'è (lo usa `prendi` per il lavoro in corso): il compito è fuori dalle statistiche.
        da_scrivere: tuple[tuple[str, str], ...] = ()
    else:
        da_scrivere = (("Esecutore", candidato.nome), ("Porta", candidato.porta), ("Dove", "fuori"))

    for nome_campo, val in da_scrivere:
        try:
            board.campo(compito_numero, nome_campo, val)
        except Exception as exc:
            print(f"misure: errore scrittura {nome_campo} per #{compito_numero}: {exc}", file=sys.stderr)

    misure.somma(board, compito_numero, "Durata", durata_secondi)
    misure.somma(board, compito_numero, "Giri", 1)
    misure.somma(board, compito_numero, "Consulti", consulti)
    misure.somma(board, compito_numero, "Token esecutore", token_esecutore)


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
    prepara_cartella_del_fascicolo(fascicolo_dir)
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
    res_cost = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "show", f"refs/remotes/origin/{ramo_principale}:docs/costituzione.md"],
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

    # Quaderno del progetto letto con git show dal ramo principale
    res_q_prog = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "show", f"refs/remotes/origin/{ramo_principale}:.github/bottega/quaderni/{modello_slug}.md"],
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
    _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "bundle", "verify", str(bundle_file)],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )

    # 2. Fetch nel refrefs/bottega/consegna
    _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "fetch", "--no-tags", str(bundle_file), f"+refs/heads/{nome_ramo}:refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )

    # 3. Controllo che base sia antenato
    res_anc = _esegui(
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
    proc_diff = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "diff", "--raw", "-z", "-M", "--no-ext-diff", base_commit, "refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )
    entries = analizza_diff_raw(proc_diff.stdout)

    # 4b. La storia: niente commit di unione, e ogni commit passa gli stessi controlli del diff netto
    # (un file sotto .github/ aggiunto e poi tolto non compare nel diff netto, ma resta nella storia spinta).
    unioni = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "rev-list", "--merges", f"{base_commit}..refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    proc_storia = _esegui(
        [
            "git", *OPZIONI_GIT_RUNNER, "log", "--raw", "-z", "-M", "--no-ext-diff", "--no-merges", "--format=",
            f"{base_commit}..refs/bottega/consegna",
        ],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )
    entries_storia = analizza_diff_raw(proc_storia.stdout)

    messaggi = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "log", "--format=%B", f"{base_commit}..refs/bottega/consegna"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    # 5. Controlli di sicurezza sui percorsi, sui modi e sui messaggi
    if not unioni and _CHIUDE_ISSUE.search(messaggi):
        # C6: un vizio innocuo dei modelli, non un attacco: un tentativo in più, e il commento (nel fascicolo del giro
        # dopo) dice perché.
        tentativi = int(d_nota.get("tentativi", 0)) + 1
        d_nota["tentativi"] = str(tentativi)
        d_nota["motivo"] = "messaggio di commit che chiude un'issue"
        stato_dest = "bloccato" if tentativi >= 3 else "pronto"
        forgia.commenta(
            compito_numero,
            "Consegna rifiutata: un messaggio di commit chiude un'issue (Closes, Fixes o Resolves seguiti da un "
            "numero). Riscrivi i messaggi senza quelle parole davanti a un numero d'issue.",
            ruolo="esecutore",
        )
        board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
        return False, []
    if unioni:
        motivo_violazione = "commit di unione vietati"
    else:
        motivo_violazione = controlla_violazioni_diff(entries_storia + entries)
    if motivo_violazione:
        # Il motivo può contenere un nome di file del modello: va nel recinto, la categoria (testo nostro) fuori.
        categoria = motivo_violazione.split(":", 1)[0]
        intestazione = (
            "Consegna rifiutata: la patch tocca percorsi sotto .github/"
            if "github" in categoria
            else f"Consegna rifiutata: {categoria}"
        )
        forgia.commenta(compito_numero, f"{intestazione}\n\n{recinta_testo_modello(motivo_violazione)}", ruolo="esecutore")
        d_nota["motivo"] = "modifica a .github vietata" if "github" in categoria else categoria
        board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
        return False, []

    # 6. Se vi sono modifiche, il ramo locale va su refs/bottega/consegna e si spinge. Niente checkout: l'albero del
    # runner resta quello del ramo principale, e nessun file del modello (un adattatore, un modulo) ci entra (C5).
    if entries:
        _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "update-ref", f"refs/heads/{nome_ramo}", "refs/bottega/consegna"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        _esegui(
            [
                "git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "push", "origin",
                f"refs/bottega/consegna:refs/heads/{nome_ramo}",
            ],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
    return True, entries


def _base_della_consegna_fatta(
    d_nota: dict[str, str], compito: int, punta: str, clone_progetto: Path
) -> str | None:
    """B7-2: la base della consegna di questo compito, se la nota dice che la punta del ramo è proprio quella consegna.

    La nota porta `consegnato=<compito>:<base>:<sha>` dalla consegna spinta. Vale solo per lo stesso compito, con lo sha
    uguale alla punta di partenza del giro e la base sua antenata; in ogni altro caso `None`.
    """
    pezzi = d_nota.get("consegnato", "").split(":")
    if len(pezzi) != 3 or pezzi[0] != str(compito) or pezzi[2] != punta:
        return None
    base = pezzi[1]
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
        return None
    res = _esegui(
        ["git", *OPZIONI_GIT_RUNNER, "merge-base", "--is-ancestor", base, punta],
        cwd=str(clone_progetto),
        capture_output=True,
    )
    return base if res.returncode == 0 else None


def _esito_del_rifiuto(d_nota: dict[str, str]) -> str:
    """L'esito di una consegna rifiutata: `errore` (un tentativo) per i messaggi che chiudono un'issue sotto il terzo
    tentativo, altrimenti `bloccato`."""
    if d_nota.get("motivo") == "messaggio di commit che chiude un'issue" and int(d_nota.get("tentativi", 0)) < 3:
        return "errore"
    return "bloccato"


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
    """Esegue un giro dell'esecutore per il lavoro e la bottega indicati. Non solleva mai (RV5).

    Un errore prima dell'avvio (forgia o board che non rispondono, bottega sconosciuta) lascia il lavoro
    `pronto` senza rilanciare il distributore: lo riprende il giro programmato, così un guasto fisso
    non diventa un anello di workflow.
    """
    try:
        return _giro(
            lavoro,
            bottega,
            configurazione=configurazione,
            forgia=forgia,
            board=board,
            porte=porte,
            clone_progetto=clone_progetto,
            spazio=spazio,
            prefisso=prefisso,
            adesso=adesso,
            caso=caso,
        )
    except Exception as exc:
        try:
            board.stato(lavoro, "pronto")
        except Exception:
            pass
        return EsitoGiro("errore", motivo=f"errore prima del giro: {exc}")


def _giro(
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
    """Il corpo del giro; `giro` lo avvolge."""
    if bottega not in configurazione.botteghe:
        raise ValueError(f"Bottega sconosciuta: {bottega!r}")
    bottega_cfg = configurazione.botteghe[bottega]

    candidato = _trova_candidato(lavoro, bottega, configurazione, board)
    porta_esecutore = _ottieni_porta(candidato.porta, porte)

    try:
        lavori_elenco = board.elenco()
        risultati_storici = misure.risultati(lavori_elenco, configurazione)
        costi_relativi = misure.costi_propri(lavori_elenco, configurazione)
    except Exception as exc:
        print(f"giro: errore lettura elenco board: {exc}", file=sys.stderr)
        risultati_storici = {}
        costi_relativi = None

    # RV9: Controllo all'apertura con prefisso
    controllo = porta_esecutore.controlla(prefisso=prefisso)

    chiave_avviso = f"porta_{porta_esecutore.nome}"
    titolo_avviso = f"Avviso della bottega: porta {porta_esecutore.nome}"
    if not controllo.ok:
        forgia.avviso(chiave_avviso, titolo_avviso, recinta_testo_modello(controllo.motivo or "porta non pronta"))
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
        d_nota.pop("quote", None)
    d_nota["compito"] = str(compito.numero)

    # C5: il brief lo può cambiare il suo autore anche dopo l'etichetta: solo issue di un comandante.
    comandanti_ok = {c.strip().lower() for c in configurazione.progetto.comandanti} | {
        forgia.proprietario().strip().lower()
    }
    for iss_controllo in (iss_madre, compito):
        if iss_controllo.autore.strip().lower() not in comandanti_ok:
            forgia.commenta(
                compito.numero,
                f"Lavoro non eseguito: l'issue #{iss_controllo.numero} non è di un comandante.",
                ruolo="esecutore",
            )
            d_nota["motivo"] = "autore non comandante"
            board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
            _rilancia_distributore(forgia)
            return EsitoGiro("bloccato", motivo="autore non comandante")

    ramo_principale = forgia.ramo_principale()
    if not _RAMO_VALIDO.fullmatch(nome_ramo) or ".." in nome_ramo or nome_ramo == ramo_principale:
        msg = f"Consegna rifiutata: ramo {nome_ramo!r} non valido o principale"
        forgia.commenta(compito.numero, msg, ruolo="esecutore")
        d_nota["motivo"] = "ramo non valido"
        board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
        _rilancia_distributore(forgia)
        return EsitoGiro("bloccato", motivo="ramo non valido")

    cmd_fatto_quando = fatto_quando(compito.corpo)
    if not cmd_fatto_quando:
        msg = "Lavoro non pronto: manca il blocco «Fatto quando» nel brief."
        forgia.commenta(compito.numero, msg, ruolo="esecutore")
        d_nota["motivo"] = "manca fatto quando"
        board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
        _rilancia_distributore(forgia)
        return EsitoGiro("senza_fatto_quando", motivo="manca fatto quando")

    d_nota["inizio"] = adesso.isoformat()
    if not prefisso:
        d_nota["utente"] = "runner"
    board.stato(lavoro, "in corso", nota=scrivi_nota(d_nota))

    # M3: un processo dell'esecutore sopravvissuto a un consulto o a un giro di prima non deve vedere questo giro.
    _uccidi_processi_esecutore(prefisso)

    env_rip = ambiente_ripulito()

    # RV5: try/except attorno a tutto il giro: nessuna eccezione deve uscire da giro()
    try:
        # Spazio del giro (B6-R22): la cartella del giro è del runner, l'esecutore lavora in `esecutore/`. Dentro il
        # try: un errore qui non lascia il lavoro «in corso».
        dir_giro, dir_esec = prepara_cartelle_del_giro(spazio, lavoro)
        # RV2: Pulizia del clone del runner da giri precedenti e rebase-apply
        _esegui(["git", *OPZIONI_GIT_RUNNER, "am", "--abort"], cwd=str(clone_progetto), capture_output=True)
        rebase_apply = clone_progetto / ".git" / "rebase-apply"
        if rebase_apply.exists():
            shutil.rmtree(rebase_apply, ignore_errors=True)
        _esegui(["git", *OPZIONI_GIT_RUNNER, "reset", "--hard"], cwd=str(clone_progetto), capture_output=True)
        _esegui(["git", *OPZIONI_GIT_RUNNER, "clean", "-fdx"], cwd=str(clone_progetto), capture_output=True)

        res_shallow = _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--is-shallow-repository"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        if res_shallow.stdout.strip() == "true" or (clone_progetto / ".git" / "shallow").exists():
            _esegui(
                ["git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "fetch", "--unshallow"],
                cwd=str(clone_progetto),
                capture_output=True,
            )

        # Prepara il ramo in clone_progetto con credenziali gh
        _esegui(
            ["git", *OPZIONI_GIT_RUNNER, *OPZIONI_GIT_CRED, "fetch", "origin"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )

        # B6-R7: Controllo rischi della CI del progetto sul ramo principale prima di lavorare
        elenco_rischi = ci.rischi_del_ramo(clone_progetto, ramo_principale)
        chiave_avviso_ci = "ci"
        titolo_avviso_ci = "Avviso della bottega: la CI del progetto parte sui rami bottega/*"
        if elenco_rischi:
            testo_rischi = "\n".join(f"{r.file}: {r.motivo}" for r in elenco_rischi)
            forgia.avviso(chiave_avviso_ci, titolo_avviso_ci, recinta_testo_modello(testo_rischi))
            d_nota["motivo"] = "ci del progetto"
            board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
            return EsitoGiro("in_attesa", motivo="ci del progetto")
        else:
            forgia.avviso(chiave_avviso_ci, titolo_avviso_ci, None)

        # C5: niente checkout nel clone del runner. Il ramo del lavoro è solo un riferimento mosso con update-ref;
        # se HEAD lo indica (un clone di prima), si stacca senza cambiare l'albero.
        testa = _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "symbolic-ref", "-q", "HEAD"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        ).stdout.strip()
        if testa == f"refs/heads/{nome_ramo}":
            _esegui(
                ["git", *OPZIONI_GIT_RUNNER, "checkout", "-q", "--detach", f"refs/remotes/origin/{ramo_principale}"],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )
        res_verify = _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{nome_ramo}^{{commit}}"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        if res_verify.returncode == 0:
            base_commit = res_verify.stdout.strip()
        else:
            res_main = _esegui(
                [
                    "git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", "-q",
                    f"refs/remotes/origin/{ramo_principale}^{{commit}}",
                ],
                cwd=str(clone_progetto),
                capture_output=True,
                text=True,
            )
            if res_main.returncode != 0:
                res_main = _esegui(
                    ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", f"refs/heads/{ramo_principale}^{{commit}}"],
                    cwd=str(clone_progetto),
                    check=True,
                    capture_output=True,
                    text=True,
                )
            base_commit = res_main.stdout.strip()
        _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "update-ref", f"refs/heads/{nome_ramo}", base_commit],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )

        # Bundle iniziale per clonare nella copia dell'esecutore
        bundle_file_iniziale = dir_giro / "ramo.bundle"
        _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "bundle", "create", str(bundle_file_iniziale), f"refs/heads/{nome_ramo}"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        bundle_file_iniziale.chmod(0o640)

        lavoro_dir = dir_esec / "lavoro"
        cmd_clone = [*prefisso, "git", "clone", str(bundle_file_iniziale), str(lavoro_dir), "-b", nome_ramo]
        _esegui(cmd_clone, check=True, capture_output=True, env=env_rip, cwd=str(dir_esec))
        _esegui(
            [*prefisso, "git", "config", "user.name", "Bottega"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            env=env_rip,
        )
        _esegui(
            [*prefisso, "git", "config", "user.email", "bottega@local"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            env=env_rip,
        )

        # RV3: Il fascicolo sta nella copia dell'esecutore in .bottega/fascicolo/, esclusa con .git/info/exclude.
        # C5: il runner lo prepara nella sua cartella; nella copia lo mette l'esecutore, così un link piantato nella
        # copia si segue coi permessi dell'esecutore, non del runner.
        exclude_path = lavoro_dir / ".git" / "info" / "exclude"
        fascicolo_dir = lavoro_dir / ".bottega" / "fascicolo"
        fascicolo_runner = dir_giro / "fascicolo"

        pr_esistente = forgia.pr_del_ramo(nome_ramo)
        _prepara_fascicolo(
            fascicolo_dir=fascicolo_runner,
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
        chiudi_file_del_fascicolo(fascicolo_runner)
        _esegui(
            [*prefisso, "sh", "-c", 'mkdir -p -- "$1" && printf \'.bottega/\\n\' >> "$2"', "sh",
             str(exclude_path.parent), str(exclude_path)],
            check=True,
            capture_output=True,
            env=env_rip,
            cwd=str(lavoro_dir),
        )
        _esegui(
            [*prefisso, "mkdir", "-p", "--", str(lavoro_dir / ".bottega")],
            check=True,
            capture_output=True,
            env=env_rip,
            cwd=str(lavoro_dir),
        )
        _esegui(
            [*prefisso, "cp", "-R", "--", str(fascicolo_runner), str(fascicolo_dir)],
            check=True,
            capture_output=True,
            env=env_rip,
            cwd=str(lavoro_dir),
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
            "2. Non toccare mai .github/ o .bottega/. Nei messaggi di commit non scrivere Closes, Fixes o Resolves "
            "davanti a un numero d'issue.\n"
            "3. Alla fine scrivi il rapporto come ultimo messaggio.\n"
            "4. Se sei bloccato o se una scelta contraddice il piano o tocca le quattro barriere, "
            "chiudi con DOMANDA PER CHI DECIDE: seguita dalla domanda precisa.\n"
        )
        consulti_effettuati = 0
        lanci_esecutore: list[Lancio] = []
        lancio_partito = False
        tempo_inizio_lancio: float | None = None

        while True:
            if tempo_inizio_lancio is None:
                tempo_inizio_lancio = time.monotonic()
            lancio_partito = True
            lancio = porta_esecutore.lancia(
                cartella=lavoro_dir,
                prompt=prompt_testo,
                modello=candidato.modello,
                conversazione=conversazione_id,
                prefisso=prefisso,
            )
            lanci_esecutore.append(lancio)

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

                idx = lancio.testo.rfind("DOMANDA PER CHI DECIDE:")
                domanda = lancio.testo[idx:].strip()
                forgia.commenta(compito.numero, f"Consulto dell'esecutore:\n\n{recinta_testo_modello(domanda)}", ruolo="esecutore")

                compito_cons = Compito(funzione="consigliare", fuori=True)
                quote_map = {b_id: forgia.variabile(nome_variabile(b_id)) for b_id in configurazione.botteghe}
                scelta_cons = scegli(
                    compito=compito_cons,
                    configurazione=_solo_runner(configurazione, candidato.runner),
                    risultati=risultati_storici,
                    quote=quote_map,
                    adesso=adesso,
                    caso=caso,
                    costi_propri=costi_relativi,
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
                dir_cons = dir_esec / f"consigliere-{consulti_effettuati}"
                # La copia la fa l'utente dell'esecutore: il runner non deve seguire link messi dal modello.
                _esegui(
                    [*prefisso, "cp", "-a", "--", str(lavoro_dir), str(dir_cons)],
                    cwd=str(dir_esec),
                    check=True,
                    capture_output=True,
                    env=env_rip,
                )
                try:
                    lancio_cons = porta_cons.lancia(
                        cartella=dir_cons,
                        prompt=prompt_cons,
                        modello=cand_cons.modello,
                        sola_lettura=True,
                        prefisso=prefisso,
                    )
                finally:
                    if prefisso:
                        _esegui([*prefisso, "rm", "-rf", "--", str(dir_cons)], capture_output=True, cwd=str(dir_esec))
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

            cur_head = _esegui(
                [*prefisso, "git", "rev-parse", "HEAD"],
                cwd=str(lavoro_dir),
                check=True,
                capture_output=True,
                text=True,
                env=env_rip,
            ).stdout.strip()

            if cur_head != base_commit:
                bundle_salv_esec = dir_esec / "salvataggio.bundle"
                _esegui(
                    [*prefisso, "git", "bundle", "create", str(bundle_salv_esec), nome_ramo],
                    cwd=str(lavoro_dir),
                    check=True,
                    capture_output=True,
                    env=env_rip,
                )
                bundle_salv = dir_giro / "salvataggio.bundle"
                _copia_dall_esecutore(bundle_salv_esec, bundle_salv)
                ok_salv, entries_salv = _verifica_e_consegna_bundle(
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
                    return EsitoGiro(_esito_del_rifiuto(d_nota), motivo=d_nota.get("motivo", "consegna rifiutata"))
                pr_num = forgia.pr_del_ramo(nome_ramo)
                if pr_num is None and entries_salv:
                    titolo_salv = iss_madre.titolo
                    corpo_salv = f"Lavoro: #{iss_madre.numero}\n\nSalvataggio parziale per quota esaurita."
                    forgia.apri_pr(nome_ramo, titolo_salv, corpo_salv)

            # RV8: attese non viene cresciuta dal giro!
            if lancio.conversazione:
                d_nota["conversazione"] = lancio.conversazione
            # C5: la quota si può fingere (un messaggio scritto nello stderr della porta). Tre giri di fila finiti in
            # quota sullo stesso compito bloccano il lavoro, che riparte con `/bottega riprova`.
            quote = int(d_nota.get("quote", 0)) + 1
            d_nota["quote"] = str(quote)
            if quote >= 3:
                d_nota["motivo"] = "quota ripetuta"
                board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
                _rilancia_distributore(forgia)
                return EsitoGiro("bloccato", motivo="quota ripetuta")
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
            _rilancia_distributore(forgia)
            return EsitoGiro("quota", motivo="quota esaurita")

        # Accesso, errore o ogni altro esito che non è «fatto»: conta un tentativo
        if lancio.esito != "fatto":
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

        # RV4: Niente commit nuovi -> nessuna PR nuova, il lavoro torna pronto con tentativi+1 e rapporto in commento
        cur_head = _esegui(
            [*prefisso, "git", "rev-parse", "HEAD"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            text=True,
            env=env_rip,
        ).stdout.strip()

        # B7-2: il giro di prima ha consegnato questo compito ed è caduto dopo; il ramo è ancora la sua consegna. Il
        # modello non ha niente da aggiungere: si riprende dall'oracolo, coi controlli sulla base di quella consegna.
        base_consegna = base_commit
        base_ripresa = (
            _base_della_consegna_fatta(d_nota, compito.numero, base_commit, clone_progetto)
            if cur_head == base_commit
            else None
        )
        if cur_head == base_commit and base_ripresa is None:
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

        if base_ripresa is not None:
            base_consegna = base_ripresa
            _esegui(
                ["git", *OPZIONI_GIT_RUNNER, "update-ref", "refs/bottega/consegna", base_commit],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )
            proc_ripresa = _esegui(
                [
                    "git", *OPZIONI_GIT_RUNNER, "diff", "--raw", "-z", "-M", "--no-ext-diff", base_consegna,
                    "refs/bottega/consegna",
                ],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )
            entries_diff = analizza_diff_raw(proc_ripresa.stdout)
            forgia.commenta(
                compito.numero,
                f"Il compito era già consegnato sul ramo ({base_commit[:12]}): il giro riprende dall'oracolo.",
                ruolo="esecutore",
            )
        else:
            # Genera bundle di consegna dall'esecutore (RV1)
            bundle_esec = dir_esec / "consegna.bundle"
            _esegui(
                [*prefisso, "git", "bundle", "create", str(bundle_esec), nome_ramo],
                cwd=str(lavoro_dir),
                check=True,
                capture_output=True,
                env=env_rip,
            )
            bundle_file = dir_giro / "consegna.bundle"
            _copia_dall_esecutore(bundle_esec, bundle_file)

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
                return EsitoGiro(_esito_del_rifiuto(d_nota), motivo=d_nota.get("motivo", "consegna rifiutata"))

            # RV4: Se il commit è vuoto (nessun file toccato nel diff)
            if not entries_diff:
                tentativi = int(d_nota.get("tentativi", 0)) + 1
                d_nota["tentativi"] = str(tentativi)
                d_nota["motivo"] = "commit vuoto"
                stato_dest = "bloccato" if tentativi >= 3 else "pronto"
                board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
                rapporto_vuoto = recinta_testo_modello(lancio.testo)
                forgia.commenta(
                    compito.numero,
                    f"Rapporto dell'esecutore per il compito {compito.numero}:\n\n{rapporto_vuoto}",
                    ruolo="esecutore",
                )
                _rilancia_distributore(forgia)
                return EsitoGiro(stato_dest, motivo="commit vuoto")

            # B7-2: la consegna è sul ramo remoto. La nota lo dice subito, prima dell'oracolo: se il giro cade dopo
            # (anche senza passare dal gestore d'errore), il giro seguente riprende da qui invece di contare un
            # tentativo.
            sha_consegna = _esegui(
                ["git", *OPZIONI_GIT_RUNNER, "rev-parse", "--verify", "refs/bottega/consegna^{commit}"],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            d_nota["consegnato"] = f"{compito.numero}:{base_commit}:{sha_consegna}"
            board.stato(lavoro, "in corso", nota=scrivi_nota(d_nota))

        # B3-R12: Oracolo su copia fresca
        dir_oracolo = dir_esec / "oracolo"
        bundle_oracolo = dir_giro / "oracolo.bundle"
        _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "bundle", "create", str(bundle_oracolo), f"refs/heads/{nome_ramo}"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        bundle_oracolo.chmod(0o640)
        _uccidi_processi_esecutore(prefisso)
        cmd_clone_oracolo = [*prefisso, "git", "clone", str(bundle_oracolo), str(dir_oracolo), "-b", nome_ramo]
        _esegui(cmd_clone_oracolo, check=True, capture_output=True, env=env_rip, cwd=str(dir_esec))

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
            f"{recinta_testo_modello(ultime_40)}"
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
        # C5: anche i file che cambiano come girano le prove (conftest.py, pyproject.toml…), nuovi o no.
        prove_cambiate = False
        for st, _sm, _dm, old_p, new_p in entries_diff:
            nomi_base = {Path(old_p).name.lower(), Path(new_p).name.lower()}
            if (st != "A" and ("test" in old_p.lower() or "test" in new_p.lower())) or nomi_base & _CONFIGURAZIONE_PROVE:
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

        # C5: diff della consegna, letto una volta (serve qui e alla rilettura del consigliere).
        diff_consegna = _esegui(
            ["git", *OPZIONI_GIT_RUNNER, "diff", "--no-ext-diff", "--no-textconv", f"{base_consegna}..refs/bottega/consegna"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        ).stdout
        # Una riga aggiunta con `gitleaks:allow` zittisce gitleaks: conta come segreto. C6: si guarda la patch di ogni
        # commit (aggiunta e poi tolta, la riga resta nella storia spinta).
        patch_storia = _esegui(
            [
                "git", *OPZIONI_GIT_RUNNER, "log", "-p", "--no-ext-diff", "--no-textconv", "--format=",
                f"{base_consegna}..refs/bottega/consegna",
            ],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        ).stdout
        if any(r.startswith("+") and "gitleaks:allow" in r for r in patch_storia.splitlines()):
            segreti_trovati = True

        if not segreti_trovati and shutil.which("gitleaks"):
            proc_gl = _esegui(
                [
                    "gitleaks", "git", "--no-banner", "--redact",
                    f"--log-opts={base_consegna}..refs/bottega/consegna", str(clone_progetto),
                ],
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
            risultati=risultati_storici,
            quote=quote_map,
            adesso=adesso,
            caso=caso,
            costi_propri=costi_relativi,
        )
        if scelta_cons.candidato and not scelta_cons.aspetta:
            cand_cons = configurazione.candidati[scelta_cons.candidato]
            porta_cons = _ottieni_porta(cand_cons.porta, porte)
            diff_testo = diff_consegna
            if len(diff_testo) > 60000:
                diff_testo = diff_testo[:60000] + "\n[diff troncato a 60 000 caratteri]"
            prompt_rev = f"Rileggi il seguente diff per il compito {compito.numero}:\n\n{diff_testo}"
            dir_rev = dir_esec / "revisione"
            # La crea l'esecutore: il runner non crea né cambia niente in `esecutore/` (un link al posto della cartella
            # porterebbe un chmod del runner fuori dal giro).
            _esegui([*prefisso, "mkdir", "-p", "--", str(dir_rev)], check=True, capture_output=True, cwd=str(dir_esec))
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
            d_nota.pop("quote", None)
            d_nota.pop("consegnato", None)
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))

        _rilancia_distributore(forgia)
        return EsitoGiro("consegnato", pr=pr_num, oracolo_ok=oracolo_ok)

    except Exception as exc:
        # RV5: Nessuna eccezione esce da giro()
        tentativi = int(d_nota.get("tentativi", 0)) + 1
        d_nota["tentativi"] = str(tentativi)
        d_nota["motivo"] = f"errore: {exc}"
        stato_dest = "bloccato" if tentativi >= 3 else "pronto"
        try:
            board.stato(lavoro, stato_dest, nota=scrivi_nota(d_nota))
        except Exception:
            pass
        try:
            target_comm = compito.numero if "compito" in locals() else lavoro
            forgia.commenta(
                target_comm, f"Errore durante il giro dell'esecutore:\n\n{recinta_testo_modello(str(exc))}", ruolo="esecutore"
            )
        except Exception:
            pass
        _rilancia_distributore(forgia)
        return EsitoGiro("bloccato" if tentativi >= 3 else "errore", motivo=str(exc))

    finally:
        if "lancio_partito" in locals() and lancio_partito:
            try:
                durata_sec = int(time.monotonic() - tempo_inizio_lancio) if tempo_inizio_lancio is not None else 0
                token_tot = sum(misure.token_dei_contatori(candidato.porta, l.contatori) for l in lanci_esecutore)
                _scrivi_misure(
                    board=board,
                    compito_numero=compito.numero,
                    candidato=candidato,
                    durata_secondi=durata_sec,
                    consulti=consulti_effettuati,
                    token_esecutore=token_tot,
                )
            except Exception as exc:
                print(f"misure: errore in _scrivi_misure: {exc}", file=sys.stderr)

        _uccidi_processi_esecutore(prefisso)

        # Pulizia completa dello spazio del giro. C6: un errore qui (un `rm` che supera il tetto) non deve sostituire
        # l'esito già scritto sulla board.
        try:
            if "dir_giro" in locals() and dir_giro.exists():
                togli_come_esecutore(prefisso, dir_esec)
                shutil.rmtree(dir_giro, ignore_errors=True)
        except Exception:
            pass


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
        res = _esegui(["gh", "repo", "view", "--json", "nameWithOwner"], capture_output=True, text=True)
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
    # Mai dentro il clone del progetto: il giro fa `git clean -fdx` e lo cancellerebbe.
    spazio = Path(spazio_env) if spazio_env else Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "bottega-spazio"

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
