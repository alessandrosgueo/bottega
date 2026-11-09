"""Prove del giro B6: esecutore come utente diverso, kill dei processi, fascicolo 0750 e CI del progetto."""

from datetime import datetime, timezone
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
    assert len(indici_kill) >= 2, f"Attesi almeno 2 kill -KILL -1, trovati {len(indici_kill)} in {righe}"

    # Il primo kill è prima del clone dell'oracolo
    idx_clone_oracolo = next(i for i, r in enumerate(righe) if "git clone" in r and "oracolo.bundle" in r)
    assert indici_kill[0] < idx_clone_oracolo, "Il primo kill deve precedere il clone dell'oracolo"

    # Il secondo kill è dopo l'ultimo comando del giro (l'oracolo o la revisione)
    idx_oracolo = next(i for i, r in enumerate(righe) if "bash -c" in r)
    assert indici_kill[1] > idx_oracolo, "Il secondo kill deve essere dopo l'oracolo"


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
        fasc_runner = Path(cartella).parent / "fascicolo"
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
