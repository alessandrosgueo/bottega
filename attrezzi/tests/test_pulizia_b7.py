"""Prove della correzione B7-3: pulizia dello spazio e uccisione dei processi a fine giro o annullamento."""

import os
import random
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from bottega.board import Lavoro
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega.porte import Controllo, Lancio


class PortaFinta:
    """Porta finta per le prove di giro."""

    def __init__(self, callback=None) -> None:
        self.nome = "finta"
        self.eseguibile = "finta"
        self.callback = callback
        self.lanci: list[dict] = []

    def controlla(self, prefisso=()) -> Controllo:
        return Controllo(ok=True, versione="1.0")

    def lancia(
        self,
        cartella: Path | str,
        prompt: str,
        modello: str,
        *,
        conversazione: str | None = None,
        sola_lettura: bool = False,
        prefisso: tuple[str, ...] = (),
        tempo: float = 3600,
    ) -> Lancio:
        self.lanci.append(
            {
                "cartella": Path(cartella),
                "prompt": prompt,
                "modello": modello,
                "conversazione": conversazione,
                "sola_lettura": sola_lettura,
                "prefisso": prefisso,
                "tempo": tempo,
            }
        )
        if sola_lettura:
            return Lancio(esito="fatto", testo="revisione: tutto bene")
        if self.callback is not None:
            return self.callback(
                cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura
            )
        return Lancio(esito="fatto", testo="fatto con successo")


def _crea_prefisso_finto(tmp_path: Path) -> tuple[tuple[str, ...], Path]:
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        'case "$1" in\n'
        "    kill|pkill|killall)\n"
        "        exit 0\n"
        "        ;;\n"
        "    id)\n"
        "        echo 54321\n"
        "        exit 0\n"
        "        ;;\n"
        "esac\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)
    return (str(prefisso_sh),), registro


def _crea_ambiente_git(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )

    clone = tmp_path / "progetto"
    subprocess.run(
        ["git", "clone", str(origin), str(clone)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )

    docs = clone / "docs"
    docs.mkdir()
    (docs / "costituzione.md").write_text(
        "# Costituzione\nRegole del repo.\n", encoding="utf-8"
    )
    (clone / "test_file.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "primo commit"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=str(clone),
        check=True,
        capture_output=True,
    )

    return origin, clone


def _crea_configurazione() -> Configurazione:
    progetto = Progetto(
        comandanti=("maestro",),
        adattatore=None,
        fuso="UTC",
        notte=None,
        manutenzione=(),
        project=1,
    )
    botteghe = {
        "principale": Bottega(id="principale", quota="abbondante", porte=("finta",)),
    }
    candidati = {
        "esecutore": Candidato(
            id="esecutore",
            nome="Esecutore Finto",
            bottega="principale",
            porta="finta",
            modello="finto-1",
            funzioni=("eseguire",),
            runner="linux-x64",
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def test_b7_3_toglie_il_giro_segnato(tmp_path: Path) -> None:
    """Una cartella da giro giovane con esecutore/ e segno viene rimossa, il segno tolto e killa i processi."""
    from bottega.giro import pulisci_dopo_il_giro

    prefisso, registro = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    dir_giro = spazio / "123-abcdefgh"
    dir_esec = dir_giro / "esecutore"
    dir_esec.mkdir(parents=True)
    (dir_esec / "file.txt").write_text("dati\n", encoding="utf-8")

    segno = tmp_path / "segno"
    segno.write_text(f"{dir_giro}\n", encoding="utf-8")

    adesso_s = time.time()
    tolti = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=segno, adesso_s=adesso_s
    )

    assert tolti == ["123-abcdefgh"]
    assert not dir_giro.exists()
    assert not segno.exists()

    righe = [
        r.strip()
        for r in registro.read_text(encoding="utf-8").splitlines()
        if r.strip()
    ]
    assert "kill -KILL -1" in righe


def test_b7_3_lascia_le_cartelle_giovani_non_segnate(tmp_path: Path) -> None:
    """Due cartelle da giro giovani, una sola segnata: quella segnata è tolta, l'altra resta."""
    from bottega.giro import pulisci_dopo_il_giro

    prefisso, _ = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    giro_1 = spazio / "101-aaaaaaaa"
    (giro_1 / "esecutore").mkdir(parents=True)
    giro_2 = spazio / "102-bbbbbbbb"
    (giro_2 / "esecutore").mkdir(parents=True)

    segno = tmp_path / "segno"
    segno.write_text(f"{giro_1}\n", encoding="utf-8")

    adesso_s = time.time()
    tolti = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=segno, adesso_s=adesso_s
    )

    assert tolti == ["101-aaaaaaaa"]
    assert not giro_1.exists()
    assert giro_2.exists()
    assert not segno.exists()


def test_b7_3_toglie_le_cartelle_vecchie(tmp_path: Path) -> None:
    """Una cartella da giro vecchia senza segno viene tolta e restituita."""
    from bottega.giro import ETA_GIRO_MORTO_S, pulisci_dopo_il_giro

    prefisso, _ = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    giro_vecchio = spazio / "456-abcdefgh"
    (giro_vecchio / "esecutore").mkdir(parents=True)
    adesso_s = time.time()
    tempo_vecchio = adesso_s - ETA_GIRO_MORTO_S - 60
    os.utime(giro_vecchio, (tempo_vecchio, tempo_vecchio))

    tolti = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=None, adesso_s=adesso_s
    )

    assert tolti == ["456-abcdefgh"]
    assert not giro_vecchio.exists()


def test_b7_3_il_segno_non_esce_dallo_spazio(tmp_path: Path) -> None:
    """Il segno indica una cartella fuori o un link verso fuori: restano entrambi intatti."""
    from bottega.giro import ETA_GIRO_MORTO_S, pulisci_dopo_il_giro

    prefisso, _ = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    # Caso 1: cartella da giro fuori da spazio
    fuori = tmp_path / "fuori" / "123-abcdefgh"
    fuori.mkdir(parents=True)
    segno = tmp_path / "segno"
    segno.write_text(f"{fuori}\n", encoding="utf-8")

    adesso_s = time.time()
    tolti = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=segno, adesso_s=adesso_s
    )
    assert tolti == []
    assert fuori.exists()

    # Caso 2: dentro spazio un link con nome da giro verso una cartella fuori, segnato e invecchiato
    bersaglio = tmp_path / "bersaglio"
    (bersaglio / "esecutore").mkdir(parents=True)
    (bersaglio / "esecutore" / "dentro.txt").write_text("resta\n", encoding="utf-8")
    link_in_spazio = spazio / "999-abcdefgh"
    link_in_spazio.symlink_to(bersaglio)
    tempo_vecchio = adesso_s - ETA_GIRO_MORTO_S - 60
    os.utime(link_in_spazio, (tempo_vecchio, tempo_vecchio), follow_symlinks=False)

    segno.write_text(f"{link_in_spazio}\n", encoding="utf-8")
    tolti_link = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=segno, adesso_s=adesso_s
    )

    assert tolti_link == []
    assert link_in_spazio.is_symlink()
    assert link_in_spazio.exists()
    assert bersaglio.exists()
    # attraverso il link non si toglie niente: né `esecutore/` del bersaglio, né ciò che contiene
    assert (bersaglio / "esecutore" / "dentro.txt").read_text(
        encoding="utf-8"
    ) == "resta\n"


def test_b7_3_restano_i_nomi_che_non_sono_giri(tmp_path: Path) -> None:
    """Nomi che non sono da giro (<cifre>-<8 caratteri>) o file non vengono tolti anche se vecchi."""
    from bottega.giro import ETA_GIRO_MORTO_S, pulisci_dopo_il_giro

    prefisso, _ = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    cartella_lavoro = spazio / "lavoro"
    cartella_lavoro.mkdir()
    cartella_corta = spazio / "12-abc"
    cartella_corta.mkdir()
    file_vecchio = spazio / "7-abcdefgh"
    file_vecchio.write_text("contenuto\n", encoding="utf-8")

    adesso_s = time.time()
    tempo_vecchio = adesso_s - ETA_GIRO_MORTO_S - 60
    os.utime(cartella_lavoro, (tempo_vecchio, tempo_vecchio))
    os.utime(cartella_corta, (tempo_vecchio, tempo_vecchio))
    os.utime(file_vecchio, (tempo_vecchio, tempo_vecchio))

    tolti = pulisci_dopo_il_giro(
        prefisso=prefisso, spazio=spazio, segno=None, adesso_s=adesso_s
    )

    assert tolti == []
    assert cartella_lavoro.exists()
    assert cartella_corta.exists()
    assert file_vecchio.exists()


def test_b7_3_senza_prefisso_non_fa_niente(tmp_path: Path) -> None:
    """Senza prefisso non rimuove nulla e restituisce lista vuota."""
    from bottega.giro import ETA_GIRO_MORTO_S, pulisci_dopo_il_giro

    spazio = tmp_path / "spazio"
    spazio.mkdir()

    giro_vecchio = spazio / "111-abcdefgh"
    giro_vecchio.mkdir()
    giro_segnato = spazio / "222-abcdefgh"
    giro_segnato.mkdir()

    segno = tmp_path / "segno"
    segno.write_text(f"{giro_segnato}\n", encoding="utf-8")

    adesso_s = time.time()
    tempo_vecchio = adesso_s - ETA_GIRO_MORTO_S - 60
    os.utime(giro_vecchio, (tempo_vecchio, tempo_vecchio))

    tolti = pulisci_dopo_il_giro(
        prefisso=(), spazio=spazio, segno=segno, adesso_s=adesso_s
    )

    assert tolti == []
    assert giro_vecchio.exists()
    assert giro_segnato.exists()
    assert segno.exists()


def test_b7_3_il_giro_segna_la_sua_cartella(tmp_path: Path) -> None:
    """Il giro scrive il segno con la sua cartella all'avvio e lo toglie nel finally."""
    from bottega.giro import giro

    _origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    segno = tmp_path / "segno"
    prefisso, _ = _crea_prefisso_finto(tmp_path)

    segno_visto: list[Path] = []
    cartella_giro_vista: list[Path] = []

    def callback_porta(cartella, prompt, **kwargs):
        p_lavoro = Path(cartella)
        p_esec = p_lavoro.parent
        p_giro = p_esec.parent
        cartella_giro_vista.append(p_giro)
        if segno.exists():
            valore = segno.read_text(encoding="utf-8").strip()
            segno_visto.append(Path(valore))
        (p_lavoro / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(p_lavoro),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: file"],
            cwd=str(p_lavoro),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=callback_porta)
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=prefisso,
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        caso=random.Random(42),
        segno=segno,
    )

    assert esito.esito == "consegnato"
    assert len(cartella_giro_vista) == 1
    assert len(segno_visto) == 1
    assert segno_visto[0].resolve() == cartella_giro_vista[0].resolve()
    assert not segno.exists()


def test_b7_3_il_giro_spazza_i_giri_vecchi(tmp_path: Path) -> None:
    """All'avvio del giro le cartelle da giro vecchie nello spazio vengono spazzate via."""
    from bottega.giro import ETA_GIRO_MORTO_S, giro

    _origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    prefisso, _ = _crea_prefisso_finto(tmp_path)
    spazio = tmp_path / "spazio"
    spazio.mkdir()

    giro_vecchio = spazio / "99-abcdefgh"
    (giro_vecchio / "esecutore").mkdir(parents=True)
    (giro_vecchio / "esecutore" / "vecchio.txt").write_text(
        "vecchio\n", encoding="utf-8"
    )
    adesso_s = time.time()
    tempo_vecchio = adesso_s - ETA_GIRO_MORTO_S - 60
    os.utime(giro_vecchio, (tempo_vecchio, tempo_vecchio))

    def callback_porta(cartella, prompt, **kwargs):
        p_lavoro = Path(cartella)
        (p_lavoro / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(p_lavoro),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: file"],
            cwd=str(p_lavoro),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="ok")

    porta = PortaFinta(callback=callback_porta)
    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=prefisso,
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        caso=random.Random(42),
    )

    assert not giro_vecchio.exists()


def test_b7_3_workflow_pulisce_se_annullato() -> None:
    """In esecutore.yml c'è il passo che pulisce se annullato ed ETA_GIRO_MORTO_S supera il timeout del job."""
    from bottega.giro import ETA_GIRO_MORTO_S

    radice = Path(__file__).resolve().parent.parent.parent
    esecutore_yml = radice / ".github" / "workflows" / "esecutore.yml"
    assert esecutore_yml.is_file(), f"Manca il file: {esecutore_yml}"

    testo = esecutore_yml.read_text(encoding="utf-8")

    match_timeout = re.search(r"timeout-minutes:\s*(\d+)", testo)
    assert match_timeout is not None, "timeout-minutes non trovato nel job esecutore"
    timeout_minuti = int(match_timeout.group(1))
    assert ETA_GIRO_MORTO_S > timeout_minuti * 60

    match_export = re.search(r"(export BOTTEGA_SPAZIO=.*)", testo)
    assert match_export is not None, (
        "Riga export BOTTEGA_SPAZIO non trovata nel passo del giro"
    )
    riga_export_giro = match_export.group(1).strip()

    idx_giro = testo.find("python3 -P -m bottega giro")
    idx_pulisci = testo.find("python3 -P -m bottega pulisci")
    assert idx_giro != -1, "Passo del giro non trovato in esecutore.yml"
    assert idx_pulisci != -1, (
        "Passo python3 -P -m bottega pulisci non trovato in esecutore.yml"
    )
    assert idx_pulisci > idx_giro, (
        "Il passo pulisci deve comparire dopo il passo del giro"
    )

    blocchi_passi = re.split(r"\n\s+-\s+", testo)
    passo_annullato = next((b for b in blocchi_passi if "cancelled()" in b), None)
    assert passo_annullato is not None, (
        "Manca il passo con if: ${{ cancelled() }} in esecutore.yml"
    )

    assert re.search(r"if:\s*\${{\s*cancelled\(\)\s*}}", passo_annullato) is not None
    assert "working-directory: progetto" in passo_annullato
    assert riga_export_giro in passo_annullato
    assert "python3 -P -m bottega pulisci" in passo_annullato
    assert "PYTHONPATH:" in passo_annullato


def test_b7_3_comando_pulisci(tmp_path: Path) -> None:
    """Il comando python3 -m bottega pulisci toglie la cartella segnata e ne stampa il nome."""
    from bottega.giro import NOME_SEGNO_GIRO

    spazio = tmp_path / "spazio"
    spazio.mkdir()
    cartella_giro = spazio / "321-abcdefgh"
    (cartella_giro / "esecutore").mkdir(parents=True)

    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    segno = runner_temp / NOME_SEGNO_GIRO
    segno.write_text(f"{cartella_giro}\n", encoding="utf-8")

    prefisso, _ = _crea_prefisso_finto(tmp_path)

    radice_attrezzi = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(radice_attrezzi)
    env["BOTTEGA_PREFISSO_ESECUTORE"] = prefisso[0]
    env["BOTTEGA_SPAZIO"] = str(spazio)
    env["RUNNER_TEMP"] = str(runner_temp)

    risultato = subprocess.run(
        [sys.executable, "-m", "bottega", "pulisci"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert risultato.returncode == 0, (
        f"Codice di uscita {risultato.returncode}: {risultato.stderr}"
    )
    assert "321-abcdefgh" in risultato.stdout
    assert not cartella_giro.exists()
    assert not segno.exists()
