"""Prove del giro B6: esecutore come utente diverso, kill dei processi, fascicolo 0750 e CI del progetto."""

from datetime import datetime, timezone
import os
from pathlib import Path
import random
import stat
import subprocess
import pytest

from bottega.board import Lavoro
from bottega.ci import Rischio, rischi_del_ramo
from bottega.configurazione import Bottega, Candidato, Configurazione, Progetto
from bottega.finta import BoardFinta, ForgiaFinta
from bottega.forgia import Issue
from bottega import giro as modulo_giro
from bottega.giro import _uccidi_processi_esecutore, giro
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
        tempo: int | float = 3600,
    ) -> Lancio:
        self.lanci.append({
            "cartella": Path(cartella),
            "prompt": prompt,
            "modello": modello,
            "conversazione": conversazione,
            "sola_lettura": sola_lettura,
            "prefisso": prefisso,
            "tempo": tempo,
        })
        if sola_lettura:
            return Lancio(esito="fatto", testo="revisione: tutto bene")
        if self.callback is not None:
            return self.callback(cartella, prompt, conversazione=conversazione, sola_lettura=sola_lettura)
        return Lancio(esito="fatto", testo="fatto con successo")


def _crea_ambiente_git(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)

    clone = tmp_path / "progetto"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(clone), check=True, capture_output=True)

    docs = clone / "docs"
    docs.mkdir()
    (docs / "costituzione.md").write_text("# Costituzione\nRegole del repo.\n", encoding="utf-8")
    (clone / "test_file.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "primo commit"], cwd=str(clone), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone), check=True, capture_output=True)

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
        "consigliere": Candidato(
            id="consigliere",
            nome="Consigliere Finto",
            bottega="principale",
            porta="finta",
            modello="finto-consigliere",
            funzioni=("consigliare",),
            runner="linux-x64",
        ),
    }
    return Configurazione(1, progetto, botteghe, candidati)


def test_kill_prima_dell_oracolo(tmp_path: Path) -> None:
    """B6-R6: col prefisso finto, kill -KILL -1 prima del clone oracolo e a fine giro nel finally."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(str(prefisso_sh),),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    indici_kill = [i for i, r in enumerate(righe) if r == "kill -KILL -1"]
    assert len(indici_kill) >= 3, f"Attesi almeno 3 kill -KILL -1, trovati {len(indici_kill)} in {righe}"

    # Il primo kill è all'inizio del giro, prima del clone del progetto
    idx_primo_clone = next(i for i, r in enumerate(righe) if "git clone" in r)
    assert indici_kill[0] < idx_primo_clone, "Il primo kill deve precedere il primo clone"

    # Il secondo kill è prima del clone dell'oracolo
    idx_clone_oracolo = next(i for i, r in enumerate(righe) if "git clone" in r and "oracolo.bundle" in r)
    assert indici_kill[1] < idx_clone_oracolo, "Il secondo kill deve precedere il clone dell'oracolo"

    # Il terzo kill è dopo l'ultimo comando del giro (l'oracolo o la revisione)
    idx_oracolo = next(i for i, r in enumerate(righe) if "bash -c" in r)
    assert indici_kill[2] > idx_oracolo, "Il terzo kill deve essere dopo l'oracolo"


def test_niente_kill_senza_prefisso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B6-R6: senza prefisso non lancia mai kill -KILL -1 (il runner ucciderebbe se stesso)."""
    import subprocess as sp_mod
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto con successo")

    comandi_lanciati: list[list[str]] = []
    run_originale = sp_mod.run

    def sp_run_spia(cmd, *a, **kw):
        comandi_lanciati.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
        return run_originale(cmd, *a, **kw)

    monkeypatch.setattr(sp_mod, "run", sp_run_spia)

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"

    # Nessun comando deve contenere "kill"
    for c in comandi_lanciati:
        assert "kill" not in c, f"Trovato comando kill senza prefisso: {c}"


def test_kill_niente_se_il_prefisso_resta_noi(tmp_path: Path) -> None:
    """B6-R6: se il prefisso esegue id davvero e l'uid resta il nostro, nessun kill."""
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    _uccidi_processi_esecutore((str(prefisso_sh),))

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert righe == ["id -u"]
    assert not any("kill" in r for r in righe)


def test_kill_niente_come_root(tmp_path: Path) -> None:
    """B6-R6: se il prefisso restituisce uid 0, nessun kill."""
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 0\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    _uccidi_processi_esecutore((str(prefisso_sh),))

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert righe == ["id -u"]
    assert not any("kill" in r for r in righe)


def test_kill_niente_se_id_fallisce(tmp_path: Path) -> None:
    """B6-R6: se id fallisce (codice di uscita diverso da 0), nessun kill."""
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        exit 1\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    _uccidi_processi_esecutore((str(prefisso_sh),))

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert righe == ["id -u"]
    assert not any("kill" in r for r in righe)


def test_kill_niente_se_id_illeggibile(tmp_path: Path) -> None:
    """B6-R6: se id produce un output non numerico, nessun kill."""
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo pippo\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    _uccidi_processi_esecutore((str(prefisso_sh),))

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert righe == ["id -u"]
    assert not any("kill" in r for r in righe)


def test_kill_se_l_utente_e_un_altro(tmp_path: Path) -> None:
    """B6-R6: se l'utente è un altro (uid non zero e diverso dal nostro), kill -KILL -1 dopo id -u."""
    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    _uccidi_processi_esecutore((str(prefisso_sh),))

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert righe == ["id -u", "kill -KILL -1"]


def test_kill_niente_senza_prefisso_diretto(monkeypatch: pytest.MonkeyPatch) -> None:
    """B6-R6: prefisso vuoto non invoca alcun processo."""
    chiamate: list[tuple] = []

    def spia(*args, **kwargs):
        chiamate.append((args, kwargs))

    monkeypatch.setattr(modulo_giro, "_esegui", spia)
    _uccidi_processi_esecutore(())
    assert chiamate == []


def test_fascicolo_del_runner_0750(tmp_path: Path) -> None:
    """B6-R6: dir_giro / 'fascicolo' ha modo 0o750 (chmod esplicito dopo mkdir)."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    modi_fascicolo: list[int] = []

    def callback_porta(cartella, prompt, **kwargs):
        fasc_runner = Path(cartella).parent.parent / "fascicolo"
        if fasc_runner.exists():
            modi_fascicolo.append(fasc_runner.stat().st_mode & 0o777)
        (Path(cartella) / "mod.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "mod.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: mod"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=callback_porta)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    assert len(modi_fascicolo) == 1
    assert modi_fascicolo[0] == 0o750


def test_ci_pericolosa_niente_lancio(tmp_path: Path) -> None:
    """B6-R7: workflow con trigger su push e segreti blocca il lancio e la spinta, avviso aperto."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    # Creiamo un workflow pericoloso nel ramo principale di origin
    clone_wf = tmp_path / "clone_wf"
    subprocess.run(["git", "clone", str(origin), str(clone_wf)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(clone_wf), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(clone_wf), check=True, capture_output=True)

    wf_dir = clone_wf / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        "name: CI\n"
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ${{ secrets.CHIAVE_SEGRETA }}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(clone_wf), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "workflow pericoloso"], cwd=str(clone_wf), check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=str(clone_wf), check=True, capture_output=True)

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    porta_chiamata = False

    def callback_porta(cartella, prompt, **kwargs):
        nonlocal porta_chiamata
        porta_chiamata = True
        return Lancio(esito="fatto", testo="fatto")

    porta = PortaFinta(callback=callback_porta)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    # 1. Esito in_attesa con motivo "ci del progetto"
    assert esito.esito == "in_attesa"
    assert esito.motivo == "ci del progetto"

    # 2. La porta non è mai lanciata
    assert porta_chiamata is False

    # 3. L'origine non ha il ramo del lavoro
    res_ramo = subprocess.run(
        ["git", "rev-parse", "--verify", "bottega/1-compito-uno"],
        cwd=str(origin),
        capture_output=True,
    )
    assert res_ramo.returncode != 0

    # 4. L'avviso ci è aperto
    titolo_atteso = "Avviso della bottega: la CI del progetto parte sui rami bottega/*"
    avvisi_aperti = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta]
    assert len(avvisi_aperti) == 1
    assert avvisi_aperti[0].titolo == titolo_atteso
    assert "ci.yml" in avvisi_aperti[0].corpo
    assert any(r[0] == "avviso" and r[1] == "ci" and r[2] == titolo_atteso and r[3] is not None for r in forgia.registro)

    # 5. Il lavoro è in attesa sulla board con nota
    lav = board.lavoro(1)
    assert lav.stato == "in attesa"
    assert "ci del progetto" in lav.nota


def test_ci_sicura_chiude_l_avviso(tmp_path: Path) -> None:
    """B6-R7: se la CI è sicura, l'avviso ci precedente viene chiuso."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    # Avviso ci aperto in precedenza
    titolo_avviso = "Avviso della bottega: la CI del progetto parte sui rami bottega/*"
    forgia.avviso("ci", titolo_avviso, "avviso vecchio")

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"
    # L'avviso ci deve essere stato chiuso
    avvisi_aperti = [i for i in forgia._issues.values() if "bottega: avviso" in i.etichette and i.aperta and i.titolo == titolo_avviso]
    assert len(avvisi_aperti) == 0
    assert any(r[0] == "avviso" and r[1] == "ci" and r[3] is None for r in forgia.registro)



def test_ci_solo_nell_albero_non_conta(tmp_path: Path) -> None:
    """B6-R7: un workflow pericoloso solo nell'albero di lavoro del clone non blocca il giro."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()

    # Creiamo un workflow pericoloso SOLO nell'albero del clone (non committato né spinto su origin/main)
    wf_dir = clone / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "locale_pericoloso.yml").write_text(
        "name: Locale\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ${{ secrets.X }}\n",
        encoding="utf-8",
    )

    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )
    assert esito.esito == "consegnato"


def test_m3_kill_all_inizio_del_giro(tmp_path: Path) -> None:
    """M3: con prefisso finto (uid 54321), un kill -KILL -1 precede il primo git clone del giro."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    porta = PortaFinta(callback=lambda cartella, prompt, **kw: Lancio(esito="fatto", testo="ok"))
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(str(prefisso_sh),),
        adesso=adesso,
        caso=caso,
    )

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    indici_kill = [i for i, r in enumerate(righe) if r == "kill -KILL -1"]
    assert len(indici_kill) >= 1
    idx_primo_clone = next(i for i, r in enumerate(righe) if "git clone" in r)
    assert indici_kill[0] < idx_primo_clone


def test_m4_cartella_del_giro_imprevedibile(tmp_path: Path) -> None:
    """M4: la cartella del giro creata in spazio ha nome imprevedibile (non lavoro-epoca) e modo 0o2750 con esecutore/ 0o2770."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    cartella_vista: list[Path] = []
    modo_visto: list[int] = []
    cartella_esec_vista: list[Path] = []
    modo_esec_visto: list[int] = []

    def callback_porta(cartella, prompt, **kw):
        p_esec = Path(cartella).parent
        p_giro = p_esec.parent
        cartella_vista.append(p_giro)
        modo_visto.append(p_giro.stat().st_mode & 0o7777)
        cartella_esec_vista.append(p_esec)
        modo_esec_visto.append(p_esec.stat().st_mode & 0o7777)
        return Lancio(esito="fatto", testo="ok")

    porta = PortaFinta(callback=callback_porta)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    caso = random.Random(42)

    giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": porta},
        clone_progetto=clone,
        spazio=spazio,
        prefisso=(),
        adesso=adesso,
        caso=caso,
    )

    assert len(cartella_vista) == 1
    p_giro = cartella_vista[0]
    epoca = str(int(adesso.timestamp()))
    assert p_giro.name != f"1-{epoca}", f"Il nome della cartella del giro non deve essere prevedibile ({p_giro.name})"
    assert p_giro.name.startswith("1-")
    assert modo_visto[0] == 0o2750
    assert len(cartella_esec_vista) == 1
    p_esec = cartella_esec_vista[0]
    assert p_esec.name == "esecutore"
    assert modo_esec_visto[0] == 0o2770


def test_r22_cartella_del_giro_del_runner(tmp_path: Path) -> None:
    """B6-R22: la cartella del giro 0o2750, esecutore/ 0o2770, lavoro e oracolo dentro esecutore/."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    percorsi_lavoro: list[Path] = []
    modi_giro: list[int] = []
    modi_esec: list[int] = []

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        percorsi_lavoro.append(p_lavoro)
        p_esec = p_lavoro.parent
        p_giro = p_esec.parent
        modi_giro.append(p_giro.stat().st_mode & 0o7777)
        modi_esec.append(p_esec.stat().st_mode & 0o7777)
        (p_lavoro / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"
    assert len(percorsi_lavoro) == 1
    p_lavoro = percorsi_lavoro[0]
    p_esec = p_lavoro.parent
    p_giro = p_esec.parent

    assert p_lavoro.name == "lavoro"
    assert p_esec.name == "esecutore"
    assert modi_giro[0] == 0o2750
    assert modi_esec[0] == 0o2770

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    clone_oracolo = next(r for r in righe if "git clone" in r and "oracolo.bundle" in r)
    assert str(p_esec / "oracolo") in clone_oracolo


def test_r22_link_al_posto_della_consegna(tmp_path: Path) -> None:
    """B6-R22: l'esecutore mette un link a sentinella al posto del bundle: giro non consegna, sentinella intatta, nessun push."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    sentinella = tmp_path / "sentinella.txt"
    sentinella.write_text("sentinella_intatta\n", encoding="utf-8")

    commit_iniziali = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'"$@"\n'
        f'esito=$?\n'
        f'if [ $esito -eq 0 ] && [ "$1" = "git" ] && [ "$2" = "bundle" ] && [ "$3" = "create" ]; then\n'
        f'    case "$4" in\n'
        f'        *consegna.bundle)\n'
        f'            rm -f "$4"\n'
        f'            ln -s "{sentinella}" "$4"\n'
        f'            ;;\n'
        f'    esac\n'
        f'fi\n'
        f'exit $esito\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "f.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: f"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito != "consegnato"
    assert sentinella.read_text(encoding="utf-8") == "sentinella_intatta\n"
    commit_finali = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert commit_finali == commit_iniziali
    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert any("git bundle create" in r and "/esecutore/consegna.bundle" in r for r in righe)


def test_r22_fifo_al_posto_della_consegna(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B6-R22: l'esecutore mette una FIFO al posto del bundle: il giro non si appende e non consegna."""
    import bottega.giro as modulo_giro
    import time

    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'"$@"\n'
        f'esito=$?\n'
        f'if [ $esito -eq 0 ] && [ "$1" = "git" ] && [ "$2" = "bundle" ] && [ "$3" = "create" ]; then\n'
        f'    case "$4" in\n'
        f'        *consegna.bundle)\n'
        f'            rm -f "$4"\n'
        f'            mkfifo "$4"\n'
        f'            ;;\n'
        f'    esac\n'
        f'fi\n'
        f'exit $esito\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "f.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: f"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    # In 3ce72c8~1 senza _copia_dall_esecutore, git bundle verify resterebbe appeso a tempo pieno
    monkeypatch.setattr(modulo_giro, "TEMPO_GIT", 5.0)

    t0 = time.monotonic()
    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    durata = time.monotonic() - t0

    assert esito.esito != "consegnato"
    # Un giro appeso aspetta il tetto di git (5 s), uno sano finisce prima anche con la macchina carica.
    assert durata < 4.0, f"Il giro si è appeso per {durata}s"
    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert any("git bundle create" in r and "/esecutore/consegna.bundle" in r for r in righe)


def test_r22_revisione_creata_dall_esecutore(tmp_path: Path) -> None:
    """B6-R22: la cartella di revisione è creata dall'esecutore con mkdir -p attraverso il prefisso."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "f.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: f"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"
    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert any(r.startswith("mkdir -p -- ") and r.endswith("/esecutore/revisione") for r in righe), (
        f"Atteso mkdir -p -- <...>/esecutore/revisione nel prefisso, trovati: {righe}"
    )


def test_r22_comandi_col_prefisso_hanno_cwd(tmp_path: Path) -> None:
    """B6-R22: nessun comando col prefisso gira nel clone del progetto né nella cwd del processo di prova."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntrue\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    registro = tmp_path / "prefisso_cwd.log"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'printf "%s | %s\\n" "$(pwd)" "$*" >> "{registro}"\n'
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"    id)\n"
        f"        echo 54321\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "f.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: f"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    cwd_processo = os.getcwd()
    clone_str = str(clone.resolve())

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert len(righe) > 0
    cwd_viste: set[str] = set()
    for r in righe:
        cwd_cmd = r.split(" | ", 1)[0].strip()
        cwd_viste.add(str(Path(cwd_cmd).resolve()))

    assert cwd_processo not in cwd_viste, f"Comandi girati nella cartella del processo ({cwd_processo}): {righe}"
    assert clone_str not in cwd_viste, f"Comandi girati nel clone del progetto ({clone_str}): {righe}"



def test_r22_il_runner_non_scrive_in_esecutore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B6-R22: nessun comando che il runner lancia da sé (senza prefisso) scrive in `esecutore/`, e il fascicolo del
    runner sta fuori: un link piantato lì dall'esecutore porterebbe la scrittura del runner fuori dal giro."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        "#!/bin/sh\n"
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
    prefisso = (str(prefisso_sh),)

    comandi_del_runner: list[list[str]] = []
    esegui_vero = modulo_giro._esegui

    def spia(cmd, **kw):
        if list(cmd[: len(prefisso)]) != list(prefisso):
            comandi_del_runner.append(list(cmd))
        return esegui_vero(cmd, **kw)

    monkeypatch.setattr(modulo_giro, "_esegui", spia)

    def committa(cartella, prompt, **kw):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(cartella), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(cartella), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=committa)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=prefisso,
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"
    bundle_del_runner = [c for c in comandi_del_runner if "bundle" in c and "create" in c]
    assert len(bundle_del_runner) >= 2, comandi_del_runner
    for cmd in comandi_del_runner:
        assert not any("/esecutore/" in arg or arg.endswith("/esecutore") for arg in cmd), cmd


def test_c3_setgid_sulle_cartelle(tmp_path: Path) -> None:
    """C3: prepara_cartelle_del_giro dà 0o2750 e 0o2770; prepara_cartella_del_fascicolo dà 0o2750."""
    spazio = tmp_path / "spazio"
    spazio.mkdir()
    d_giro, d_esec = modulo_giro.prepara_cartelle_del_giro(spazio, 1)
    assert (d_giro.stat().st_mode & 0o7777) == 0o2750
    assert (d_esec.stat().st_mode & 0o7777) == 0o2770

    f_dir = d_giro / "fascicolo"
    modulo_giro.prepara_cartella_del_fascicolo(f_dir)
    assert (f_dir.stat().st_mode & 0o7777) == 0o2750


def test_c3_file_del_runner_0640(tmp_path: Path) -> None:
    """C3: dopo un giro consegnato, visto durante il lancio: ramo.bundle e file di fascicolo/ sono 0o640 anche con umask 0o077."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    modi_visti: dict[str, int] = {}

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        p_esec = p_lavoro.parent
        p_giro = p_esec.parent
        for b in p_giro.glob("*.bundle"):
            modi_visti[b.name] = b.stat().st_mode & 0o7777
        p_fasc = p_giro / "fascicolo"
        for f in p_fasc.iterdir():
            if f.is_file():
                modi_visti[f.name] = f.stat().st_mode & 0o7777
        (p_lavoro / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    vecchia_umask = os.umask(0o077)
    try:
        esito = giro(
            lavoro=1,
            bottega="principale",
            configurazione=cfg,
            forgia=forgia,
            board=board,
            porte={"finta": PortaFinta(callback=callback_porta)},
            clone_progetto=clone,
            spazio=tmp_path / "spazio",
            prefisso=(),
            adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
            caso=random.Random(42),
        )
    finally:
        os.umask(vecchia_umask)

    assert esito.esito == "consegnato"
    assert any(k.endswith(".bundle") for k in modi_visti)
    assert "brief.md" in modi_visti
    for nome, modo in modi_visti.items():
        assert modo == 0o640, f"{nome} ha modo {oct(modo)}, atteso 0o640"


def test_c3_errore_delle_cartelle_non_lascia_in_corso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """C3: monkeypatch di prepara_cartelle_del_giro che solleva OSError: il giro non esce con eccezione e lavoro non resta in corso."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    iss = Issue(numero=1, titolo="Compito Uno", corpo="Brief", autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    def fallisci_prepara(spazio, lavoro):
        raise OSError("impossibile creare la cartella del giro")

    monkeypatch.setattr(modulo_giro, "prepara_cartelle_del_giro", fallisci_prepara)

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta()},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    assert esito.esito != "consegnato"
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato != "in corso"


def test_c3_l_esecutore_toglie_il_suo(tmp_path: Path) -> None:
    """C3: nel registro del prefisso, alla fine del giro, chmod -R u+rwX -- <…>/esecutore e poi rm -rf -- <…>/esecutore."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

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

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(str(prefisso_sh),),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )
    assert esito.esito == "consegnato"

    righe = [r.strip() for r in registro.read_text(encoding="utf-8").splitlines() if r.strip()]
    idx_chmod = next(i for i, r in enumerate(righe) if "chmod -R u+rwX --" in r and r.endswith("/esecutore"))
    idx_rm = next(i for i, r in enumerate(righe) if "rm -rf --" in r and r.endswith("/esecutore"))
    assert idx_chmod < idx_rm


def test_c3_tetto_della_copia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """C3: monkeypatch di giro.TETTO_COPIA a pochi byte: il giro non consegna e non c'è spinta."""
    origin, clone = _crea_ambiente_git(tmp_path)
    cfg = _crea_configurazione()
    corpo = "Brief compito 1\n\n## Fatto quando\n```bash\ntest -f file.txt\n```\n"
    iss = Issue(numero=1, titolo="Compito Uno", corpo=corpo, autore="maestro")
    forgia = ForgiaFinta(issues=[iss])
    board = BoardFinta(lavori=[Lavoro(numero=1, titolo="Compito Uno", stato="pronto")])

    commit_iniziali = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    monkeypatch.setattr(modulo_giro, "TETTO_COPIA", 10)

    def callback_porta(cartella, prompt, **kw):
        p_lavoro = Path(cartella)
        (p_lavoro / "file.txt").write_text("modifica consistente\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(p_lavoro), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: file"], cwd=str(p_lavoro), check=True, capture_output=True)
        return Lancio(esito="fatto", testo="fatto")

    esito = giro(
        lavoro=1,
        bottega="principale",
        configurazione=cfg,
        forgia=forgia,
        board=board,
        porte={"finta": PortaFinta(callback=callback_porta)},
        clone_progetto=clone,
        spazio=tmp_path / "spazio",
        prefisso=(),
        adesso=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        caso=random.Random(42),
    )

    assert esito.esito != "consegnato"
    commit_finali = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(origin),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert commit_finali == commit_iniziali
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato != "consegnato"



def test_c4_cartella_a_meta_non_resta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se la preparazione delle cartelle del giro cade a metà, la cartella creata da mkdtemp non resta nello spazio."""
    spazio = tmp_path / "spazio"
    chmod_vero = Path.chmod

    def chmod_che_cade(self: Path, modo: int, *a, **kw) -> None:
        if self.name == "esecutore":
            raise OSError("chmod rifiutato")
        chmod_vero(self, modo, *a, **kw)

    monkeypatch.setattr(Path, "chmod", chmod_che_cade)
    with pytest.raises(OSError):
        modulo_giro.prepara_cartelle_del_giro(spazio, 7)
    monkeypatch.undo()
    assert list(spazio.iterdir()) == []
