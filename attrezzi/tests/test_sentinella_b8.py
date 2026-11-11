"""Prove per la sentinella di rete e la sicurezza dell'esecutore (Compito B8-3)."""

import random
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import bottega.giro
import pytest
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


def test_b8_sentinella_senza_prefisso() -> None:
    """1. rete_dell_esecutore_chiusa con prefisso vuoto restituisce True."""
    from bottega.giro import rete_dell_esecutore_chiusa

    assert rete_dell_esecutore_chiusa(()) is True


def test_b8_sentinella_rete_aperta(tmp_path: Path) -> None:
    """2. Con prefisso finto che lancia il comando com'è (stesso utente), la sonda si connette: False."""
    from bottega.giro import rete_dell_esecutore_chiusa

    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "    kill|pkill|killall)\n"
        "        exit 0\n"
        "        ;;\n"
        "esac\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    assert rete_dell_esecutore_chiusa((str(prefisso_sh),)) is False


def test_b8_sentinella_rete_chiusa(tmp_path: Path) -> None:
    """3. Con prefisso finto che esce subito 3 su python3 (rete chiusa simulata): True."""
    from bottega.giro import rete_dell_esecutore_chiusa

    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "    kill|pkill|killall)\n"
        "        exit 0\n"
        "        ;;\n"
        "    python3)\n"
        "        exit 3\n"
        "        ;;\n"
        "esac\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    assert rete_dell_esecutore_chiusa((str(prefisso_sh),)) is True


def test_b8_sentinella_sonda_storta(tmp_path: Path) -> None:
    """4. Prefisso che esce 1 o 0 senza connettersi: restituisce False per entrambi (solo 3 vale chiuso)."""
    from bottega.giro import rete_dell_esecutore_chiusa

    prefisso_esce_1 = tmp_path / "prefisso_1.sh"
    prefisso_esce_1.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "    kill|pkill|killall)\n"
        "        exit 0\n"
        "        ;;\n"
        "    python3)\n"
        "        exit 1\n"
        "        ;;\n"
        "esac\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_esce_1.chmod(0o755)

    prefisso_esce_0 = tmp_path / "prefisso_0.sh"
    prefisso_esce_0.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "    kill|pkill|killall)\n"
        "        exit 0\n"
        "        ;;\n"
        "    python3)\n"
        "        exit 0\n"
        "        ;;\n"
        "esac\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_esce_0.chmod(0o755)

    assert rete_dell_esecutore_chiusa((str(prefisso_esce_1),)) is False
    assert rete_dell_esecutore_chiusa((str(prefisso_esce_0),)) is False


def test_b8_sentinella_porta_vera(tmp_path: Path) -> None:
    """5. Registra gli argomenti della sonda: ultimo argomento porta 1024-65535, sonda contiene 127.0.0.1."""
    from bottega.giro import rete_dell_esecutore_chiusa

    registro = tmp_path / "argomenti.bin"
    prefisso_sh = tmp_path / "prefisso.sh"
    prefisso_sh.write_text(
        f"#!/bin/sh\n"
        f'case "$1" in\n'
        f"    kill|pkill|killall)\n"
        f"        exit 0\n"
        f"        ;;\n"
        f"esac\n"
        f'printf "%s\\0" "$@" > "{registro}"\n'
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    esito = rete_dell_esecutore_chiusa((str(prefisso_sh),))
    assert esito is False
    assert registro.exists()
    pezzi = [p.decode("utf-8") for p in registro.read_bytes().split(b"\0") if p]
    assert len(pezzi) >= 2
    porta = int(pezzi[-1])
    assert 1024 <= porta <= 65535
    assert "127.0.0.1" in pezzi[-2]


def test_b8_giro_fermo_con_la_rete_aperta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6. Giro con SENTINELLA_RETE=True e rete aperta: si blocca senza chiamare la porta."""
    from bottega.giro import giro

    monkeypatch.setattr(bottega.giro, "SENTINELLA_RETE", True)
    _origin, clone = _crea_ambiente_git(tmp_path)
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

    porta = PortaFinta()
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
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
    assert esito.esito == "bloccato"
    assert esito.motivo == "rete aperta"
    assert len(porta.lanci) == 0
    lav = board.lavoro(1)
    assert lav is not None
    assert lav.stato == "bloccato"
    assert "motivo=rete aperta" in lav.nota
    commenti = forgia.commenti(1)
    assert any(
        "rete dell'esecutore" in c.corpo and "installa macchina" in c.corpo
        for c in commenti
    )


def test_b8_giro_va_con_la_rete_chiusa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """7. Giro con SENTINELLA_RETE=True e sonda che esce 3: arriva alla porta."""
    from bottega.giro import giro

    monkeypatch.setattr(bottega.giro, "SENTINELLA_RETE", True)
    _origin, clone = _crea_ambiente_git(tmp_path)
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
        f"    python3)\n"
        f'        for a in "$@"; do\n'
        f'            if [ "$a" = "-c" ]; then\n'
        f"                exit 3\n"
        f"            fi\n"
        f"        done\n"
        f"        ;;\n"
        f"esac\n"
        f'exec "$@"\n',
        encoding="utf-8",
    )
    prefisso_sh.chmod(0o755)

    def committa(cartella, prompt, **kwargs):
        (Path(cartella) / "file.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: file"],
            cwd=str(cartella),
            check=True,
            capture_output=True,
        )
        return Lancio(esito="fatto", testo="fatto con successo")

    porta = PortaFinta(callback=committa)
    spazio = tmp_path / "spazio"
    adesso = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
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
    assert len(porta.lanci) == 1
    assert esito.esito == "consegnato"
    righe = [
        r.strip()
        for r in registro.read_text(encoding="utf-8").splitlines()
        if r.strip()
    ]
    assert any("python3" in r and "-c" in r for r in righe)


def test_b8_costituzione_cartella_o_assente(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """8. Costituzione cartella o assente: fascicolo senza costituzione.md, avviso su stderr per assente."""
    from bottega.giro import _prepara_fascicolo

    _origin, clone = _crea_ambiente_git(tmp_path)
    compito = Issue(numero=1, titolo="Compito", corpo="Brief")
    forgia = ForgiaFinta(issues=[compito])
    candidato = Candidato(
        id="esecutore",
        nome="Esecutore Finto",
        bottega="principale",
        porta="finta",
        modello="finto-1",
        funzioni=("eseguire",),
        runner="linux-x64",
    )

    fascicolo_docs = tmp_path / "fascicolo_docs"
    _prepara_fascicolo(
        fascicolo_docs,
        compito,
        compito,
        forgia,
        clone,
        candidato,
        nome_ramo="bottega/1-compito",
        base_commit="HEAD",
        pr_num=None,
        d_nota={},
        ramo_principale="main",
        comandanti=("maestro",),
        costituzione="docs",
    )
    assert not (fascicolo_docs / "costituzione.md").exists()

    fascicolo_manca = tmp_path / "fascicolo_manca"
    _prepara_fascicolo(
        fascicolo_manca,
        compito,
        compito,
        forgia,
        clone,
        candidato,
        nome_ramo="bottega/1-compito",
        base_commit="HEAD",
        pr_num=None,
        d_nota={},
        ramo_principale="main",
        comandanti=("maestro",),
        costituzione="docs/manca.md",
    )
    assert not (fascicolo_manca / "costituzione.md").exists()
    catturato = capsys.readouterr()
    assert any(
        r.startswith("avviso:") and "docs/manca.md" in r
        for r in catturato.err.splitlines()
    )


def test_b8_rete_untracked() -> None:
    """9. Nel testo di testo_rete_esecutore c'è oifname "lo" ct state untracked reject prima di ct mark set."""
    from bottega.macchina import Utenti, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_rete_esecutore(u, ["192.0.2.53"])

    riga_attesa = 'oifname "lo" ct state untracked reject'
    assert riga_attesa in testo
    righe = [r.strip() for r in testo.splitlines()]
    idx_untracked = next(i for i, r in enumerate(righe) if riga_attesa in r)
    idx_mark = next(i for i, r in enumerate(righe) if "ct mark set" in r)
    assert idx_untracked < idx_mark


def test_b8_unita_dopo_nftables() -> None:
    """10. testo_unita_rete ha After=nftables.service."""
    from bottega.macchina import Utenti, testo_unita_rete

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_unita_rete(u)

    assert "After=nftables.service" in testo


def test_b8_nft_prima_degli_utenti() -> None:
    """11. Se il controllo di nft fallisce, comando_macchina esce 1 senza eseguire useradd o groupadd."""
    import argparse

    from bottega.installa import comando_macchina

    class EsecutoreFintoNftManca:
        def __init__(self) -> None:
            self.comandi: list[tuple[str, ...]] = []

        def __call__(
            self,
            comando: Sequence[str],
            ambiente: Mapping[str, str] | None = None,
        ) -> tuple[int, str]:
            cmd = tuple(comando)
            self.comandi.append(cmd)
            cmd_str = " ".join(cmd)

            if "systemctl is-system-running" in cmd_str:
                return 0, "running\n"
            if "manca nft" in cmd_str:
                return 1, "manca nft: installa il pacchetto nftables\n"

            e_controllo = (
                cmd[:1] == ("getent",)
                or (cmd[:2] == ("sh", "-c") and "manca nft" not in cmd_str)
                or "cmp -s" in cmd_str
                or "command -v nft" in cmd_str
                or "test -x /usr/sbin/nft" in cmd_str
            )
            return (1, "") if e_controllo else (0, "")

    esecutore = EsecutoreFintoNftManca()
    args = argparse.Namespace(prova=False)

    codice = comando_macchina(args, esegui=esecutore, resolv="nameserver 192.0.2.53\n")
    assert codice == 1
    assert not any("useradd" in " ".join(cmd) for cmd in esecutore.comandi)
    assert not any("groupadd" in " ".join(cmd) for cmd in esecutore.comandi)


def test_b8_avviso_interop(capsys: pytest.CaptureFixture[str]) -> None:
    """12. comando_macchina(..., interop=True) stampa riga avviso: con interop su stderr; interop=False nessuna."""
    import argparse

    from bottega.installa import comando_macchina

    class EsecutoreFintoTuttoRiesce:
        def __init__(self) -> None:
            self.comandi: list[tuple[str, ...]] = []

        def __call__(
            self,
            comando: Sequence[str],
            ambiente: Mapping[str, str] | None = None,
        ) -> tuple[int, str]:
            cmd = tuple(comando)
            self.comandi.append(cmd)
            cmd_str = " ".join(cmd)

            if "systemctl is-system-running" in cmd_str:
                return 0, "running\n"

            e_controllo = (
                cmd[:1] == ("getent",)
                or (cmd[:2] == ("sh", "-c") and "manca nft" not in cmd_str)
                or "cmp -s" in cmd_str
                or "command -v nft" in cmd_str
                or "test -x /usr/sbin/nft" in cmd_str
            )
            return (1, "") if e_controllo else (0, "")

    args = argparse.Namespace(prova=False)
    esecutore1 = EsecutoreFintoTuttoRiesce()
    codice1 = comando_macchina(
        args, esegui=esecutore1, resolv="nameserver 192.0.2.53\n", interop=True
    )
    assert codice1 == 0
    catturato1 = capsys.readouterr()
    righe_err1 = catturato1.err.splitlines()
    assert any(r.startswith("avviso:") and "interop" in r for r in righe_err1)

    esecutore2 = EsecutoreFintoTuttoRiesce()
    codice2 = comando_macchina(
        args, esegui=esecutore2, resolv="nameserver 192.0.2.53\n", interop=False
    )
    assert codice2 == 0
    catturato2 = capsys.readouterr()
    righe_err2 = catturato2.err.splitlines()
    assert not any(r.startswith("avviso:") and "interop" in r for r in righe_err2)


def test_b8_sentinella_sonda_che_non_parte(tmp_path: Path) -> None:
    """Un prefisso che non si lancia (programma assente) non vale «chiusa»: la sentinella fallisce chiusa."""
    from bottega.giro import rete_dell_esecutore_chiusa

    assert rete_dell_esecutore_chiusa((str(tmp_path / "prefisso-che-non-c-e"),)) is False
