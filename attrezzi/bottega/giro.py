"""Il giro dell'esecutore: regia del lavoro assegnato a una bottega.

Prepara il fascicolo, fa lavorare il modello come utente dell'esecutore e senza chiavi,
gestisce consulto e quota, controlla con l'oracolo e consegna.
Solo libreria standard.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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

OPZIONI_GIT_RUNNER: tuple[str, ...] = (
    "-c", "credential.helper=",
    "-c", "credential.helper=!gh auth git-credential",
    "-c", "core.hooksPath=/dev/null",
)


@dataclass(frozen=True)
class EsitoGiro:
    """L'esito complessivo del giro dell'esecutore."""

    esito: str
    motivo: str | None = None
    pr: int | None = None
    oracolo_ok: bool | None = None
    dettagli: dict[str, Any] = field(default_factory=dict)


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

    righe_comm: list[str] = []
    for c in comm_list:
        r = ruolo(c.corpo)
        prefix = f"[{r}] " if r else ""
        testo_pulito = _spoglia_segno(c.corpo)
        righe_comm.append(f"{prefix}{c.autore}:\n{testo_pulito}\n")
    (fascicolo_dir / "commenti.md").write_text("\n---\n".join(righe_comm), encoding="utf-8")

    costituzione_src = clone_progetto / "docs" / "costituzione.md"
    if costituzione_src.exists():
        (fascicolo_dir / "costituzione.md").write_text(
            costituzione_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

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

    q_prog = clone_progetto / ".github" / "bottega" / "quaderni" / f"{modello_slug}.md"
    if q_prog.exists():
        testi_quaderno.append(q_prog.read_text(encoding="utf-8"))

    if testi_quaderno:
        (fascicolo_dir / "quaderno.md").write_text("\n\n".join(testi_quaderno), encoding="utf-8")

    testo_stato = (
        f"Ramo: {nome_ramo}\n"
        f"Base: {base_commit}\n"
        f"PR: {pr_num if pr_num is not None else 'nessuna'}\n"
        f"Nota: {scrivi_nota(d_nota)}\n"
    )
    (fascicolo_dir / "stato.md").write_text(testo_stato, encoding="utf-8")


def _applica_e_controlla_patch(
    clone_progetto: Path,
    patch_file: Path,
    base_commit: str,
    nome_ramo: str,
    forgia: Forgia,
    compito_numero: int,
    d_nota: dict[str, str],
    board: Board,
    lavoro: int,
) -> tuple[bool, list[str]]:
    """Applica la patch nel clone del runner, controlla con il git del runner e spinge.

    Restituisce (ok, righe_diff). Se un percorso tocca .github/, fa reset --hard <base>,
    nessuna spinta, commenta col motivo e blocca il lavoro.
    """
    if not patch_file.exists() or not patch_file.read_text(encoding="utf-8").strip():
        return True, []

    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "am", "--3way", str(patch_file)],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )

    diff_proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "diff", "--name-status", "-M", base_commit, "HEAD"],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
        text=True,
    )
    righe_diff = diff_proc.stdout.strip().splitlines()

    for riga in righe_diff:
        parti = riga.split()
        for p in parti[1:]:
            p_norm = p.strip().lower()
            if p_norm.startswith(".github/") or "/.github/" in p_norm or p_norm == ".github":
                subprocess.run(
                    ["git", "-c", "core.hooksPath=/dev/null", "reset", "--hard", base_commit],
                    cwd=str(clone_progetto),
                    check=True,
                    capture_output=True,
                )
                msg_vietato = "Consegna rifiutata: la patch tocca percorsi sotto .github/"
                forgia.commenta(compito_numero, msg_vietato, ruolo="esecutore")
                d_nota["motivo"] = "modifica a .github vietata"
                board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
                return False, []

    subprocess.run(
        ["git", *OPZIONI_GIT_RUNNER, "push", "origin", nome_ramo],
        cwd=str(clone_progetto),
        check=True,
        capture_output=True,
    )
    return True, righe_diff


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

    # B3-R15: Controllo all'apertura
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

    if sotto_issues:
        if not aperte:
            nome_ramo = ramo(iss_madre.numero, iss_madre.titolo)
            pr_num = forgia.pr_del_ramo(nome_ramo) or 0
            board.consegna(lavoro, pr=pr_num)
            _rilancia_distributore(forgia)
            return EsitoGiro("consegnato", motivo="tutte le sotto-issue gia chiuse", pr=pr_num)
        compito = aperte[0]
        ultima_sotto_issue = len(aperte) == 1
    else:
        compito = iss_madre
        ultima_sotto_issue = True

    # Ramo della madre (o del lavoro sciolto)
    nome_ramo = ramo(iss_madre.numero, iss_madre.titolo)
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

    lav_attuale = board.lavoro(lavoro)
    d_nota = nota(lav_attuale.nota if lav_attuale else "")
    d_nota["inizio"] = adesso.isoformat()
    if not prefisso:
        d_nota["utente"] = "runner"
    board.stato(lavoro, "in corso", nota=scrivi_nota(d_nota))

    # B3-R10: Spazio del giro
    timestamp_str = str(int(adesso.timestamp()))
    dir_giro = spazio / f"{lavoro}-{timestamp_str}"
    dir_giro.mkdir(parents=True, exist_ok=True)

    env_rip = ambiente_ripulito()

    try:
        # Prepara il ramo in clone_progetto con credenziali gh
        subprocess.run(
            ["git", *OPZIONI_GIT_RUNNER, "fetch", "origin"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        res_verify = subprocess.run(
            ["git", "rev-parse", "--verify", f"origin/{nome_ramo}"],
            cwd=str(clone_progetto),
            capture_output=True,
            text=True,
        )
        if res_verify.returncode == 0:
            subprocess.run(
                ["git", "checkout", "-B", nome_ramo, f"origin/{nome_ramo}"],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )
        else:
            res_main = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{ramo_principale}"],
                cwd=str(clone_progetto),
                capture_output=True,
                text=True,
            )
            base_ref = f"origin/{ramo_principale}" if res_main.returncode == 0 else ramo_principale
            subprocess.run(
                ["git", "checkout", "-B", nome_ramo, base_ref],
                cwd=str(clone_progetto),
                check=True,
                capture_output=True,
            )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Fascicolo completo (B3-R10)
        fascicolo_dir = dir_giro / "fascicolo"
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
        )

        # Bundle e clone nella copia dell'esecutore
        bundle_file = dir_giro / "ramo.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle_file), nome_ramo],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )

        lavoro_dir = dir_giro / "lavoro"
        cmd_clone = [*prefisso, "git", "clone", str(bundle_file), str(lavoro_dir), "-b", nome_ramo]
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

        # Lancio dell'esecutore con prompt descrittivo
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
            "2. Non toccare mai .github/.\n"
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

            # Consulto (B3-R13)
            if "DOMANDA PER CHI DECIDE:" in lancio.testo:
                idx = lancio.testo.find("DOMANDA PER CHI DECIDE:")
                domanda = lancio.testo[idx:].strip()
                forgia.commenta(compito.numero, f"Consulto dell'esecutore:\n\n{domanda}", ruolo="esecutore")
                consulti_effettuati += 1
                if consulti_effettuati > 2:
                    d_nota["motivo"] = "troppi consulti"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="troppi consulti")

                compito_cons = Compito(funzione="consigliare", fuori=True)
                quote_map = {b_id: forgia.variabile(nome_variabile(b_id)) for b_id in configurazione.botteghe}
                scelta_cons = scegli(
                    compito=compito_cons,
                    configurazione=configurazione,
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
                lancio_cons = porta_cons.lancia(
                    cartella=dir_giro,
                    prompt=prompt_cons,
                    modello=cand_cons.modello,
                    sola_lettura=True,
                    prefisso=prefisso,
                )
                msg_cons = f"Risposta del consigliere ({cand_cons.nome}):\n\n{lancio_cons.testo}"
                forgia.commenta(compito.numero, msg_cons, ruolo="consigliere")

                righe_cons = lancio_cons.testo.strip().splitlines()
                prima_riga_cons = righe_cons[0].strip().upper() if righe_cons else ""
                if prima_riga_cons.startswith("RISPOSTA"):
                    prompt_testo = lancio_cons.testo
                    conversazione_id = lancio.conversazione
                    continue
                else:
                    d_nota["motivo"] = "consulto a chi decide"
                    board.stato(lavoro, "in attesa", nota=scrivi_nota(d_nota))
                    _rilancia_distributore(forgia)
                    return EsitoGiro("in_attesa", motivo="consulto a chi decide")

            break

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
                patch_salv = subprocess.run(
                    [*prefisso, "git", "format-patch", f"{base_commit}..HEAD", "--stdout"],
                    cwd=str(lavoro_dir),
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env_rip,
                ).stdout
                if patch_salv.strip():
                    patch_file = dir_giro / "consegna.patch"
                    patch_file.write_text(patch_salv, encoding="utf-8")
                    ok_patch, _ = _applica_e_controlla_patch(
                        clone_progetto=clone_progetto,
                        patch_file=patch_file,
                        base_commit=base_commit,
                        nome_ramo=nome_ramo,
                        forgia=forgia,
                        compito_numero=compito.numero,
                        d_nota=d_nota,
                        board=board,
                        lavoro=lavoro,
                    )
                    if not ok_patch:
                        _rilancia_distributore(forgia)
                        return EsitoGiro("bloccato", motivo="modifica a .github vietata")
                    pr_num = forgia.pr_del_ramo(nome_ramo)
                    if pr_num is None:
                        titolo_salv = iss_madre.titolo
                        corpo_salv = f"Lavoro: #{iss_madre.numero}\n\nSalvataggio parziale per quota esaurita."
                        forgia.apri_pr(nome_ramo, titolo_salv, corpo_salv)

            attese = int(d_nota.get("attese", 0)) + 1
            d_nota["attese"] = str(attese)
            if lancio.conversazione:
                d_nota["conversazione"] = lancio.conversazione
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))
            _rilancia_distributore(forgia)
            return EsitoGiro("quota", motivo="quota esaurita")

        # Accesso o errore (B3-R14)
        if lancio.esito in ("accesso", "errore"):
            tentativi = int(d_nota.get("tentativi", 0)) + 1
            d_nota["tentativi"] = str(tentativi)
            if tentativi >= 3:
                d_nota["motivo"] = lancio.esito
                board.stato(lavoro, "bloccato", nota=scrivi_nota(d_nota))
                msg_err = f"Lavoro bloccato dopo 3 tentativi ({lancio.esito}): {lancio.testo}"
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

        # Esito "fatto": commit di eventuali file rimasti nell'indice
        st_proc = subprocess.run(
            [*prefisso, "git", "status", "--porcelain"],
            cwd=str(lavoro_dir),
            capture_output=True,
            text=True,
            env=env_rip,
        )
        if st_proc.stdout.strip():
            cmd_add = [*prefisso, "git", "add", "-A"]
            subprocess.run(cmd_add, cwd=str(lavoro_dir), check=True, capture_output=True, env=env_rip)
            msg_commit = f"consegna per compito {compito.numero}"
            cmd_comm = [*prefisso, "git", "commit", "-m", msg_commit]
            subprocess.run(cmd_comm, cwd=str(lavoro_dir), check=True, capture_output=True, env=env_rip)

        cur_head = subprocess.run(
            [*prefisso, "git", "rev-parse", "HEAD"],
            cwd=str(lavoro_dir),
            check=True,
            capture_output=True,
            text=True,
            env=env_rip,
        ).stdout.strip()

        # Genera patch dall'esecutore
        patch_file = dir_giro / "consegna.patch"
        if cur_head != base_commit:
            patch_data = subprocess.run(
                [*prefisso, "git", "format-patch", f"{base_commit}..HEAD", "--stdout"],
                cwd=str(lavoro_dir),
                check=True,
                capture_output=True,
                text=True,
                env=env_rip,
            ).stdout
            patch_file.write_text(patch_data, encoding="utf-8")

        # Controlli, applicazione e spinta eseguiti ESCLUSIVAMENTE dal runner
        ok_consegna, righe_diff = _applica_e_controlla_patch(
            clone_progetto=clone_progetto,
            patch_file=patch_file,
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
            return EsitoGiro("bloccato", motivo="modifica a .github vietata")

        # B3-R12: Oracolo su copia fresca
        dir_oracolo = dir_giro / "oracolo"
        bundle_oracolo = dir_giro / "oracolo.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle_oracolo), nome_ramo],
            cwd=str(clone_progetto),
            check=True,
            capture_output=True,
        )
        cmd_clone_oracolo = [*prefisso, "git", "clone", str(bundle_oracolo), str(dir_oracolo), "-b", nome_ramo]
        subprocess.run(cmd_clone_oracolo, check=True, capture_output=True, env=env_rip)

        proc_oracolo = subprocess.run(
            [*prefisso, "bash", "-c", cmd_fatto_quando],
            cwd=str(dir_oracolo),
            capture_output=True,
            text=True,
            timeout=1800,
            env=env_rip,
        )
        oracolo_ok = proc_oracolo.returncode == 0
        oracolo_out = (proc_oracolo.stdout + "\n" + proc_oracolo.stderr).strip()
        ultime_40 = "\n".join(oracolo_out.splitlines()[-40:])
        testo_oracolo = (
            f"Esito dell'oracolo: {'VERDE' if oracolo_ok else 'ROSSO'} (codice {proc_oracolo.returncode})\n\n"
            f"```\n{ultime_40}\n```"
        )
        forgia.commenta(compito.numero, testo_oracolo, ruolo="esecutore")

        # Apertura o recupero PR con corpo e rapporto
        pr_num = forgia.pr_del_ramo(nome_ramo)
        esito_oracolo_str = "VERDE" if oracolo_ok else "ROSSO"
        if pr_num is None:
            titolo_pr = iss_madre.titolo
            corpo_pr = (
                f"Lavoro: #{iss_madre.numero}\n\n"
                f"## Rapporto dell'esecutore\n\n{lancio.testo}\n\n"
                f"## Esito dell'oracolo\n\n{esito_oracolo_str}\n"
            )
            pr_num = forgia.apri_pr(nome_ramo, titolo_pr, corpo_pr)
        else:
            comm_rapporto = (
                f"Rapporto dell'esecutore per il compito {compito.numero}:\n\n"
                f"{lancio.testo}\n\n"
                f"Esito oracolo: {esito_oracolo_str}"
            )
            forgia.commenta(pr_num, comm_rapporto, ruolo="esecutore")

        # B3-R18: Segnali sulla PR
        prove_cambiate = False
        for riga in righe_diff:
            parti = riga.split()
            if len(parti) >= 2 and parti[0] == "M":
                if "test" in parti[1].lower():
                    prove_cambiate = True
                    break
        if prove_cambiate:
            forgia.etichetta(pr_num, "bottega: prove cambiate", aggiungi=True)

        if shutil.which("gitleaks") and cur_head != base_commit:
            proc_gl = subprocess.run(
                ["gitleaks", "git", "--pre-commit", "--log-opts", f"{base_commit}..HEAD"],
                cwd=str(clone_progetto),
                capture_output=True,
            )
            if proc_gl.returncode != 0:
                forgia.etichetta(pr_num, "bottega: segreti", aggiungi=True)

        # B3-R17: Rilettura del consigliere
        compito_cons = Compito(funzione="consigliare", fuori=True)
        quote_map = {b_id: forgia.variabile(nome_variabile(b_id)) for b_id in configurazione.botteghe}
        scelta_cons = scegli(
            compito=compito_cons,
            configurazione=configurazione,
            risultati={},
            quote=quote_map,
            adesso=adesso,
            caso=caso,
        )
        if scelta_cons.candidato and not scelta_cons.aspetta:
            cand_cons = configurazione.candidati[scelta_cons.candidato]
            porta_cons = _ottieni_porta(cand_cons.porta, porte)
            diff_testo = subprocess.run(
                ["git", "diff", f"{base_commit}..HEAD"],
                cwd=str(clone_progetto),
                capture_output=True,
                text=True,
            ).stdout
            prompt_rev = f"Rileggi il seguente diff per il compito {compito.numero}:\n\n{diff_testo}"
            lancio_rev = porta_cons.lancia(
                cartella=dir_giro,
                prompt=prompt_rev,
                modello=cand_cons.modello,
                sola_lettura=True,
                prefisso=prefisso,
            )
            if lancio_rev.esito == "fatto":
                msg_rev = f"Revisione del consigliere ({cand_cons.nome}):\n\n{lancio_rev.testo}"
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
            d_nota["precedente"] = str(compito.numero)
            d_nota.pop("conversazione", None)
            board.stato(lavoro, "pronto", nota=scrivi_nota(d_nota))

        _rilancia_distributore(forgia)
        return EsitoGiro("consegnato", pr=pr_num, oracolo_ok=oracolo_ok)

    finally:
        # B3-R10: Pulizia completa dello spazio del giro
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
