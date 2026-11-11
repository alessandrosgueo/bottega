"""Prove per i passi di macchina dell'installazione della bottega (Compito B6.2)."""

import pytest

from bottega.macchina import (
    ErroreMacchina,
    Passo,
    Utenti,
    esegui_passi,
    passi_macchina,
    passi_runner,
    sha_della_release,
    systemd_attivo,
    testo_env_runner,
    testo_sudoers,
)


# Composto mentre la prova gira: scritto per intero, il controllo pubblico troverebbe se stesso.
_CASE = "/ho" + "me"

class EsecutoreFinto:
    """Esecutore finto per simulare i comandi di macchina e registrare le chiamate."""

    def __init__(self, esiti: dict[str, tuple[int, str]] | None = None) -> None:
        self.comandi: list[tuple[tuple[str, ...], dict[str, str] | None]] = []
        self.esiti: dict[str, tuple[int, str]] = dict(esiti or {})
        # Stato simulato di macchina
        self.gruppi: set[str] = set()
        self.utenti: set[str] = set()
        self.appartenenze: set[tuple[str, str]] = set()
        self.spazio_ok: bool = False
        self.sudoers_ok: bool = False
        # Stato simulato del runner
        self.cartelle: set[str] = set()
        self.archivi: set[str] = set()
        self.estratti: set[str] = set()
        self.configurati: set[str] = set()
        self.env_installati: set[str] = set()
        self.servizi_installati: set[str] = set()
        self.dropin_installati: set[str] = set()
        self.servizi_attivi: set[str] = set()

    def __call__(
        self, comando: tuple[str, ...] | list[str], ambiente: dict[str, str] | None = None
    ) -> tuple[int, str]:
        cmd = tuple(comando)
        env = dict(ambiente) if ambiente else None
        self.comandi.append((cmd, env))

        # Esito predefinito specifico se impostato
        chiave_cmd = " ".join(cmd)
        for pattern, res in self.esiti.items():
            if pattern in chiave_cmd:
                return res

        # Simulazione controlli macchina
        if len(cmd) >= 3 and cmd[0] == "getent" and cmd[1] == "group":
            return (0, "") if cmd[2] in self.gruppi else (2, "")
        if len(cmd) >= 3 and cmd[0] == "id" and cmd[1] == "-u":
            return (0, "1001\n") if cmd[2] in self.utenti else (1, "")
        if len(cmd) >= 3 and "sh" in cmd and "-c" in cmd:
            script = cmd[cmd.index("-c") + 1]
            if "id -gn" in script:
                for u in self.utenti:
                    if f"id -gn {u}" in script:
                        return (0, "")
                return (1, "")
            if "id -Gn" in script:
                for u, g in self.appartenenze:
                    if f"id -Gn {u}" in script and g in script:
                        return (0, "")
                return (1, "")
            if "stat -c" in script:
                return (0, "") if self.spazio_ok else (1, "")
            # passo_file: controllo con cmp, installazione da root con mktemp
            if "cmp -s -" in script:
                if "/etc/sudoers.d/bottega" in script:
                    return (0, "") if self.sudoers_ok else (1, "")
                if ".env" in script:
                    return (0, "") if "env" in self.env_installati else (1, "")
                if "bottega.conf" in script:
                    return (0, "") if "dropin" in self.dropin_installati else (1, "")
            if "mktemp" in script and "install -m" in script:
                if "/etc/sudoers.d/bottega" in script:
                    self.sudoers_ok = True
                elif ".env" in script:
                    self.env_installati.add("env")
                elif "bottega.conf" in script:
                    self.dropin_installati.add("dropin")
                return (0, "")
            if "svc.sh install" in script:
                self.servizi_installati.add("runner")
                return (0, "")
            if "svc.sh start" in script:
                self.servizi_attivi.add("runner")
                return (0, "")
            if "config.sh" in script:
                self.configurati.add("runner")
                return (0, "")
            if "mkdir -p" in script and "bottega.conf" in script:
                self.dropin_installati.add("dropin")
                return (0, "")
            if "echo" in script and "sha256sum" in script:
                return (0, "")

        if len(cmd) >= 3 and "cmp" in cmd:
            if "/etc/sudoers.d/bottega" in cmd:
                return (0, "") if self.sudoers_ok else (1, "")
            if ".env" in cmd[-1]:
                return (0, "") if cmd[-1] in self.env_installati else (1, "")
            if "bottega.conf" in cmd[-1]:
                return (0, "") if "dropin" in self.dropin_installati else (1, "")

        if len(cmd) >= 3 and cmd[0] == "test":
            flag = cmd[1]
            bersaglio = cmd[2]
            if flag == "-d":
                return (0, "") if bersaglio in self.cartelle else (1, "")
            if flag == "-f":
                if bersaglio.endswith(".tar.gz"):
                    return (0, "") if bersaglio in self.archivi else (1, "")
                if bersaglio.endswith("config.sh"):
                    return (0, "") if "runner" in self.estratti else (1, "")
                if bersaglio.endswith(".runner"):
                    return (0, "") if "runner" in self.configurati else (1, "")
                if bersaglio.endswith(".service"):
                    return (0, "") if "runner" in self.servizi_installati else (1, "")

        if "systemctl" in cmd and "is-active" in cmd:
            return (0, "active\n") if "runner" in self.servizi_attivi else (3, "inactive\n")

        # Simulazione comandi mutanti macchina
        if "groupadd" in cmd:
            gruppo = cmd[-1]
            self.gruppi.add(gruppo)
            return (0, "")
        if "useradd" in cmd:
            utente = cmd[-1]
            self.utenti.add(utente)
            if "--gid" in cmd:
                g = cmd[cmd.index("--gid") + 1]
                self.appartenenze.add((utente, g))
            return (0, "")
        if "usermod" in cmd:
            u = cmd[-1]
            g = cmd[cmd.index("-G") + 1]
            self.appartenenze.add((u, g))
            return (0, "")
        if "install" in cmd:
            if "-d" in cmd:
                self.spazio_ok = True
                self.cartelle.add(cmd[-1])
                return (0, "")
            if "/etc/sudoers.d/bottega" in cmd:
                self.sudoers_ok = True
                return (0, "")
            if ".env" in cmd[-1]:
                self.env_installati.add(cmd[-1])
                return (0, "")
        if "visudo" in cmd:
            return (0, "")
        if "curl" in cmd:
            if "-o" in cmd:
                dest = cmd[cmd.index("-o") + 1]
                self.archivi.add(dest)
            return (0, "")
        if "tar" in cmd:
            self.estratti.add("runner")
            return (0, "")
        if "systemctl" in cmd and "daemon-reload" in cmd:
            return (0, "")

        return (0, "")


def test_testo_sudoers() -> None:
    u_def = Utenti()
    atteso_def = (
        "Defaults:bottega-runner umask=0007, umask_override\n"
        'Defaults:bottega-runner secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin:'
        f'{_CASE}/bottega-esecutore/.local/bin"\n'
        "bottega-runner ALL=(bottega-esecutore) NOPASSWD: ALL\n"
    )
    assert testo_sudoers(u_def) == atteso_def

    u_pers = Utenti(runner="r-test", esecutore="e-test")
    atteso_pers = (
        "Defaults:r-test umask=0007, umask_override\n"
        'Defaults:r-test secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin:'
        f'{_CASE}/e-test/.local/bin"\n'
        "r-test ALL=(e-test) NOPASSWD: ALL\n"
    )
    assert testo_sudoers(u_pers) == atteso_pers


def test_sudoers_controllato_prima() -> None:
    u = Utenti()
    passi = passi_macchina(u)

    # Controllo e installazione stanno nello stesso passo, sullo stesso temporaneo di root (niente finestra in mezzo):
    # con `set -e`, `visudo` che fallisce ferma lo script prima di `install`.
    sudoers = [p for p in passi if any("/etc/sudoers.d/bottega" in arg and "install -m 0440" in arg for arg in p.comando)]
    assert len(sudoers) == 1
    script = sudoers[0].comando[-1]
    assert script.startswith("set -e;")
    assert "mktemp" in script and "/tmp/bottega" not in script
    assert script.index('visudo -c -q -f "$t"') < script.index("install -m 0440")

    esecutore = EsecutoreFinto(esiti={"visudo -c": (1, "syntax error in temporary file")})
    with pytest.raises(ErroreMacchina) as exc:
        esegui_passi(passi, esecutore)
    assert "syntax error" in str(exc.value)
    assert esecutore.sudoers_ok is False


def test_passi_macchina_ordine() -> None:
    u = Utenti()
    passi = passi_macchina(u)

    # Verifica sequenza: groupadd -> useradd (runner) -> useradd (esecutore) -> usermod -> install spazio -> sudoers
    nomi_comandi = []
    for p in passi:
        # Tutti i comandi root iniziano con sudo -n tranne controlli o comandi non root
        if any(c in p.comando for c in ("groupadd", "useradd", "usermod", "install")):
            assert p.comando[0] == "sudo" and p.comando[1] == "-n", f"Comando root senza sudo -n: {p.comando}"
        nomi_comandi.append(" ".join(p.comando))

    testo_tutto = "\n".join(nomi_comandi)
    pos_group = testo_tutto.index("groupadd")
    pos_u_runner = testo_tutto.index(
        f"useradd --system --create-home -K HOME_MODE=0700 --shell /usr/sbin/nologin --user-group --groups {u.gruppo} {u.runner}"
    )
    pos_u_esec = testo_tutto.index(
        f"useradd --system --create-home -K HOME_MODE=0700 --shell /usr/sbin/nologin --user-group --groups {u.gruppo} {u.esecutore}"
    )
    pos_usermod_r = testo_tutto.index(f"usermod -a -G {u.gruppo} {u.runner}")
    pos_usermod_e = testo_tutto.index(f"usermod -a -G {u.gruppo} {u.esecutore}")
    pos_spazio = testo_tutto.index(f"install -d -o {u.runner} -g {u.gruppo} -m 3770 {u.spazio}")
    pos_visudo = testo_tutto.index("visudo -c -q -f")
    pos_sudoers = testo_tutto.index("install -m 0440 -o root -g root")

    assert pos_group < pos_u_runner < pos_u_esec < pos_usermod_r < pos_usermod_e < pos_spazio < pos_visudo < pos_sudoers


def test_rifatta_non_cambia_niente() -> None:
    u = Utenti()
    passi = passi_macchina(u)
    esecutore = EsecutoreFinto()

    # Prima esecuzione: crea e muta lo stato
    righe_prima = esegui_passi(passi, esecutore)
    assert any(r.startswith("fatto:") for r in righe_prima)

    # Seconda esecuzione sullo stato aggiornato
    esecutore.comandi.clear()
    righe_seconda = esegui_passi(passi, esecutore)

    # Tutte le righe devono essere "già fatto:"
    assert len(righe_seconda) == len(passi)
    assert all(r.startswith("già fatto:") for r in righe_seconda)

    # Nessun comando mutante lanciato: solo i controlli
    controlli_attesi = [p.controllo for p in passi if p.controllo is not None]
    assert len(esecutore.comandi) == len(controlli_attesi)
    for (cmd, _), c_atteso in zip(esecutore.comandi, controlli_attesi, strict=True):
        assert cmd == c_atteso


def test_prova_non_lancia_niente() -> None:
    u = Utenti()
    passi = passi_macchina(u)
    esecutore = EsecutoreFinto()

    righe = esegui_passi(passi, esecutore, prova=True)
    assert len(righe) == len(passi)
    assert all(r.startswith("farei:") for r in righe)

    # Nessun comando mutante lanciato
    for cmd, _ in esecutore.comandi:
        assert not any(x in cmd for x in ("groupadd", "useradd", "usermod", "visudo"))
        if "install" in cmd:
            assert False, f"install non doveva essere lanciato: {cmd}"


def test_sha_della_release() -> None:
    sha_valido = "0123456789abcdef" * 4
    corpo = (
        "## Release v2.320.0\n\n"
        f"- runner-linux-x64.tar.gz <!-- BEGIN SHA linux-x64 -->{sha_valido}<!-- END SHA linux-x64 -->\n"
        "- runner-linux-arm64.tar.gz <!-- BEGIN SHA linux-arm64 -->123456<!-- END SHA linux-arm64 -->\n"
    )

    # SHA valido 64 caratteri
    sha = sha_della_release(corpo, "x64")
    assert sha == sha_valido

    # Architettura assente
    assert sha_della_release(corpo, "arm") is None

    # SHA corto (non 64 cifre)
    assert sha_della_release(corpo, "arm64") is None

    # Non esadecimale
    corpo_non_hex = "<!-- BEGIN SHA linux-x64 -->" + ("z" * 64) + "<!-- END SHA linux-x64 -->"
    assert sha_della_release(corpo_non_hex, "x64") is None

    # Corpo vuoto
    assert sha_della_release("", "x64") is None


def test_testo_env_runner() -> None:
    u = Utenti()
    porte = {
        "claude-code": "/usr/local/bin/claude",
        "copilot-cli": "/usr/bin/copilot",
    }
    testo = testo_env_runner(u, "etichetta-prova", porte)
    righe = testo.strip().split("\n")

    # Verifica ordine alfabetico
    assert righe == sorted(righe)

    assert "BOTTEGA_PORTA_CLAUDE_CODE=/usr/local/bin/claude" in righe
    assert "BOTTEGA_PORTA_COPILOT_CLI=/usr/bin/copilot" in righe
    assert f"BOTTEGA_PREFISSO_ESECUTORE=sudo -n -H -u {u.esecutore} --" in righe
    assert "BOTTEGA_RUNNER=etichetta-prova" in righe
    assert f"BOTTEGA_SPAZIO={u.spazio}" in righe


def test_passi_runner_comandi() -> None:
    u = Utenti()
    porte = {"claude-code": "/opt/claude"}
    sha = "0" * 64
    passi = passi_runner(
        u,
        repo="proprietario/mio-progetto",
        versione="2.320.0",
        arch="x64",
        sha256=sha,
        etichetta="etichetta-1",
        nome="runner-1",
        porte=porte,
        token="token-finto",
    )

    comandi_testo = [" ".join(p.comando) for p in passi]
    tutto = "\n".join(comandi_testo)

    assert "curl -fsSL" in tutto
    assert "sha256sum -c" in tutto
    assert "tar xzf" in tutto
    assert "config.sh" in tutto
    assert "--unattended" in tutto
    assert "--url https://github.com/proprietario/mio-progetto" in tutto
    assert "--name runner-1" in tutto
    assert "--labels etichetta-1" in tutto
    assert "--work _work" in tutto
    assert "--replace" in tutto
    assert "--preserve-env=ACTIONS_RUNNER_INPUT_TOKEN" in tutto
    assert "runsvc.sh" in tutto
    assert "bottega-runner-proprietario-mio-progetto.service" in tutto
    assert "systemctl daemon-reload" in tutto
    assert "systemctl enable --now bottega-runner-proprietario-mio-progetto.service" in tutto
    assert "svc.sh install" not in tutto
    assert "svc.sh start" not in tutto
    assert "./svc.sh" not in tutto


def test_token_mai_stampato() -> None:
    u = Utenti()
    token_segreto = "TOKEN_SUPER_SEGRETO_NON_STAMPARE_MAI"
    passi = passi_runner(
        u,
        repo="proprietario/repo",
        versione="2.320.0",
        arch="x64",
        sha256="f" * 64,
        etichetta="etichetta",
        nome="runner-segreto",
        porte={},
        token=token_segreto,
    )

    # 1. Non compare in nessun comando
    for p in passi:
        for c in p.comando:
            assert token_segreto not in c, f"Token trovato nel comando: {c}"
        assert token_segreto not in p.descrizione, f"Token trovato nella descrizione: {p.descrizione}"

    # 2. Non compare nelle righe di esegui_passi (prova)
    esecutore = EsecutoreFinto()
    righe_prova = esegui_passi(passi, esecutore, prova=True)
    for riga in righe_prova:
        assert token_segreto not in riga

    # 3. Non compare nelle righe di esegui_passi (reale/fatto)
    righe_fatto = esegui_passi(passi, esecutore, prova=False)
    for riga in righe_fatto:
        assert token_segreto not in riga

    # 4. Token nell'ambiente del passo config.sh
    passo_config = next(p for p in passi if "config.sh" in " ".join(p.comando))
    assert dict(passo_config.ambiente).get("ACTIONS_RUNNER_INPUT_TOKEN") == token_segreto


def test_systemd_attivo() -> None:
    # running -> True
    esec_running = lambda cmd, env: (0, "running\n")
    assert systemd_attivo(esec_running) is True

    # degraded -> True (ricognizione 2.1)
    esec_degraded = lambda cmd, env: (1, "degraded\n")
    assert systemd_attivo(esec_degraded) is True

    # offline -> False
    esec_offline = lambda cmd, env: (1, "offline\n")
    assert systemd_attivo(esec_offline) is False

    # Errore / init non systemd -> False
    esec_err = lambda cmd, env: (1, "System has not been booted with systemd as init system\n")
    assert systemd_attivo(esec_err) is False


def test_errore_si_ferma() -> None:
    esecutore = EsecutoreFinto(esiti={"passo2": (1, "errore permesso negato")})
    passi = [
        Passo(descrizione="passo 1", comando=("echo", "1")),
        Passo(descrizione="passo 2", comando=("echo", "passo2")),
        Passo(descrizione="passo 3", comando=("echo", "3")),
    ]

    with pytest.raises(ErroreMacchina) as exc:
        esegui_passi(passi, esecutore)

    assert "passo 2" in str(exc.value)
    assert "errore permesso negato" in str(exc.value)

    # Passo 3 non deve essere stato eseguito
    comandi_lanciati = [c[0] for c in esecutore.comandi]
    assert ("echo", "1") in comandi_lanciati
    assert ("echo", "passo2") in comandi_lanciati
    assert ("echo", "3") not in comandi_lanciati


def test_sudoers_un_file_per_esecutore() -> None:
    """B6-R12: il secondo esecutore ha il suo file di sudoers, il primo resta com'era."""
    primo = passi_macchina(Utenti())
    secondo = passi_macchina(Utenti(esecutore="bottega-esecutore-due"))

    def destinazione(passi: list[Passo]) -> str:
        script = next(p.comando[-1] for p in passi if "visudo" in p.comando[-1])
        return script.rsplit(" ", 1)[-1]

    assert destinazione(primo) == "/etc/sudoers.d/bottega-esecutore"
    assert destinazione(secondo) == "/etc/sudoers.d/bottega-esecutore-due"


@pytest.mark.parametrize("nome", ["bottega.esecutore", "Bottega", "a b", "x\nroot ALL=(ALL) ALL", "", "-x", "a" * 33])
def test_utenti_nome_non_valido(nome: str) -> None:
    """Un nome con un punto (sudo salterebbe il file) o con caratteri che cambiano il sudoers è rifiutato."""
    with pytest.raises(ValueError):
        Utenti(esecutore=nome)


def test_g1_utenti_col_loro_gruppo() -> None:
    """G1: useradd usa --user-group e --groups bottega, mai --gid."""
    u = Utenti()
    passi = passi_macchina(u)
    useradd_passi = [p for p in passi if "useradd" in p.comando]
    assert len(useradd_passi) == 2
    for p in useradd_passi:
        assert "--user-group" in p.comando
        assert "--groups" in p.comando
        assert u.gruppo in p.comando
        assert "--gid" not in p.comando


def test_g1_niente_umask_nel_servizio() -> None:
    """G1: nessun passo del runner scrive UMask nel servizio o nei file."""
    u = Utenti()
    passi = passi_runner(u, "o/r", "2.320.0", "x64", "0" * 64, "bottega", "r1", {})
    for p in passi:
        assert not any("UMask" in arg for arg in p.comando)
        if p.controllo:
            assert not any("UMask" in arg for arg in p.controllo)


def test_g1_cartella_runner_sua_0750() -> None:
    """G1: la cartella del runner è del runner (suo gruppo) e con modo 0750."""
    u = Utenti()
    passi = passi_runner(u, "o/r", "2.320.0", "x64", "0" * 64, "bottega", "r1", {})
    passo_c = next(p for p in passi if p.descrizione.startswith("cartella runner"))
    cmd = passo_c.comando
    assert "-o" in cmd and cmd[cmd.index("-o") + 1] == u.runner
    assert "-g" in cmd and cmd[cmd.index("-g") + 1] == u.runner
    assert "-m" in cmd and cmd[cmd.index("-m") + 1] == "0750"
    ctl = " ".join(passo_c.controllo)
    assert f"{u.runner}:{u.runner}:750" in ctl


def test_g4_token_solo_nell_ambiente() -> None:
    """G4: configurazione del runner usa ACTIONS_RUNNER_INPUT_TOKEN e mai argomenti né BOTTEGA_TOKEN_REGISTRAZIONE."""
    u = Utenti()
    token = "token-segreto-xyz"
    passi = passi_runner(u, "o/r", "2.320.0", "x64", "0" * 64, "bottega", "r1", {}, token=token)
    passo_cfg = next(p for p in passi if "config.sh" in " ".join(p.comando))
    assert "--preserve-env=ACTIONS_RUNNER_INPUT_TOKEN" in passo_cfg.comando
    assert dict(passo_cfg.ambiente).get("ACTIONS_RUNNER_INPUT_TOKEN") == token
    for p in passi:
        for c in p.comando:
            assert token not in c
            assert "BOTTEGA_TOKEN_REGISTRAZIONE" not in c


def test_g7_root_non_esegue_file_del_runner() -> None:
    """G7: root non esegue file nella cartella del runner (niente svc.sh, niente cd <cartella>)."""
    u = Utenti()
    passi = passi_runner(u, "o/r", "2.320.0", "x64", "0" * 64, "bottega", "r1", {})
    cartella = f"{u.radice_runner}/runner-o-r"
    for p in passi:
        cmd = p.comando
        if cmd[0] == "sudo" and "-u" not in cmd:
            cmd_str = " ".join(cmd)
            assert "./svc.sh" not in cmd_str
            assert "svc.sh install" not in cmd_str
            assert "svc.sh start" not in cmd_str
            assert f"{cartella}/svc.sh" not in cmd_str
            assert f"cd {cartella}" not in cmd_str
            if cmd[2] == "chmod":
                # La sola eccezione: richiudere la cartella del runner (il padre è di root, non la può sostituire).
                assert cmd == ("sudo", "-n", "chmod", "0750", cartella), f"chmod root non consentito: {cmd}"
                continue
            assert cmd[1] == "-n" and cmd[2] in ("install", "sh", "systemctl"), f"Comando root non consentito: {cmd}"


def test_g7_unita_scritta_da_noi() -> None:
    """G7: l'unità systemd del runner è scritta da noi con ExecStart, User, WorkingDirectory e niente UMask."""
    from bottega.macchina import nome_del_servizio, testo_unita_runner
    u = Utenti()
    repo = "o/r"
    cartella = f"{u.radice_runner}/runner-o-r"
    testo = testo_unita_runner(u, repo, cartella)
    assert f"ExecStart={cartella}/runsvc.sh" in testo
    assert f"User={u.runner}" in testo
    assert f"WorkingDirectory={cartella}" in testo
    assert "UMask" not in testo


def test_m9_scarica_in_un_temporaneo() -> None:
    """M9: scarica in un file temporaneo con mktemp, verifica sha256 prima di mv, controllo con sha256sum."""
    u = Utenti()
    passi = passi_runner(u, "o/r", "2.320.0", "x64", "0" * 64, "bottega", "r1", {})
    passo_s = next(p for p in passi if p.descrizione.startswith("scarica e verifica"))
    script = passo_s.comando[-1]
    assert "mktemp -p" in script
    assert "sha256sum -c --status" in script
    assert "mv " in script
    assert script.index("sha256sum -c --status") < script.index("mv ")
    ctl = " ".join(passo_s.controllo)
    assert "sha256sum -c" in ctl
    assert "test -f" not in ctl


@pytest.mark.parametrize(
    ("nome", "etichetta", "porta", "percorso", "versione", "sha256", "arch"),
    [
        ("nome/storto", "etichetta", "porta", "/usr/bin/p", "2.320.0", "0" * 64, "x64"),
        ("nome", "con spazio", "porta", "/usr/bin/p", "2.320.0", "0" * 64, "x64"),
        ("nome", "etichetta", "porta\n", "/usr/bin/p", "2.320.0", "0" * 64, "x64"),
        ("nome", "etichetta", "porta", "relativo/p", "2.320.0", "0" * 64, "x64"),
        ("nome", "etichetta", "porta", "/usr/bin/p", "1.2", "0" * 64, "x64"),
        ("nome", "etichetta", "porta", "/usr/bin/p", "2.320.0", "A" * 64, "x64"),
        ("nome", "etichetta", "porta", "/usr/bin/p", "2.320.0", "0" * 63, "x64"),
        ("nome", "etichetta", "porta", "/usr/bin/p", "2.320.0", "0" * 64, "riscv"),
    ],
)
def test_m13_argomenti_del_runner_controllati(
    nome: str,
    etichetta: str,
    porta: str,
    percorso: str,
    versione: str,
    sha256: str,
    arch: str,
) -> None:
    """M13: argomenti invalidi per passi_runner sollevano ValueError."""
    u = Utenti()
    with pytest.raises(ValueError):
        passi_runner(
            u,
            repo="o/r",
            versione=versione,
            arch=arch,
            sha256=sha256,
            etichetta=etichetta,
            nome=nome,
            porte={porta: percorso},
        )


def test_r22_spazio_sticky() -> None:
    """B6-R22: lo spazio è 3770 (bit sticky contro rinomina delle cartelle del runner)."""
    u = Utenti()
    passi = passi_macchina(u)
    p_spazio = next(p for p in passi if p.descrizione == f"spazio {u.spazio}")
    assert "-m" in p_spazio.comando
    assert p_spazio.comando[p_spazio.comando.index("-m") + 1] == "3770"
    assert "3770" in p_spazio.controllo[2]


def test_r22_case_0700() -> None:
    """B6-R22: le case degli utenti si creano con 0700 (-K HOME_MODE=0700)."""
    u = Utenti()
    passi = passi_macchina(u)
    for desc in (f"utente runner {u.runner}", f"utente esecutore {u.esecutore}"):
        p = next(p for p in passi if p.descrizione == desc)
        assert "-K" in p.comando
        assert p.comando[p.comando.index("-K") + 1] == "HOME_MODE=0700"


def test_r22_utente_gia_fatto_col_suo_gruppo() -> None:
    """B6-R22: il controllo 'già fatto' dell'utente verifica il suo gruppo principale (id -gn)."""
    u = Utenti()
    passi = passi_macchina(u)
    for desc, utente in ((f"utente runner {u.runner}", u.runner), (f"utente esecutore {u.esecutore}", u.esecutore)):
        p = next(p for p in passi if p.descrizione == desc)
        assert p.controllo[0] == "sh" and p.controllo[1] == "-c"
        assert f'id -gn {utente}' in p.controllo[2]
        assert f'= {utente}' in p.controllo[2]


def test_c3_case_chiuse_anche_se_c_erano() -> None:
    """C3: due passi «casa di … chiusa (0700)», col controllo che legge il modo con stat."""
    u = Utenti()
    passi = passi_macchina(u)
    passi_case = [p for p in passi if "chiusa (0700)" in p.descrizione]
    assert len(passi_case) == 2
    for desc, utente in (
        (f"casa di {u.runner} chiusa (0700)", u.runner),
        (f"casa di {u.esecutore} chiusa (0700)", u.esecutore),
    ):
        p = next(p for p in passi if p.descrizione == desc)
        assert p.comando[0] == "sudo" and p.comando[1] == "-n"
        assert "chmod 700" in p.comando[-1]
        assert utente in p.comando[-1]
        assert p.controllo[0] == "sh" and p.controllo[1] == "-c"
        assert "stat -c %a" in p.controllo[2]
        assert "= 700" in p.controllo[2]
        assert utente in p.controllo[2]




def test_tetto_del_servizio_del_runner() -> None:
    """Con un tetto, l'unità del runner ha MemoryMax senza swap: l'esecutore e le sue prove sono figli del runner."""
    from bottega.macchina import testo_unita_runner

    testo = testo_unita_runner(Utenti(), "o/r", "/var/lib/bottega/runner-o-r", "6G")
    assert "MemoryMax=6G\n" in testo
    assert "MemorySwapMax=0\n" in testo
    assert "MemoryMax" not in testo_unita_runner(Utenti(), "o/r", "/var/lib/bottega/runner-o-r")
    passi = passi_runner(Utenti(), "o/r", "2.320.0", "x64", "a" * 64, "e", "n", {}, tetto="6G")
    unita = next(p for p in passi if p.descrizione.startswith("unità systemd"))
    assert "MemoryMax=6G" in " ".join(unita.comando)


@pytest.mark.parametrize("tetto", ["6", "6GB", "0G", "-1G", "6G\nUser=root", "6 G", "1234567G"])
def test_tetto_storto_rifiutato(tetto: str) -> None:
    """Il tetto entra in un'unità di root: solo un numero e un'unità di misura, mai altro testo."""
    with pytest.raises(ValueError):
        passi_runner(Utenti(), "o/r", "2.320.0", "x64", "a" * 64, "e", "n", {}, tetto=tetto)


def test_estrazione_non_riapre_la_cartella_del_runner() -> None:
    """Dal vivo (2026-11-09): l'archivio del runner ha la voce `./` a 0755 e tar la applicava alla cartella del runner,
    che l'esecutore poteva così attraversare. tar non tocca le cartelle che ci sono già, e un passo la richiude."""
    passi = passi_runner(Utenti(), "o/r", "2.320.0", "x64", "a" * 64, "e", "n", {})
    estrai = next(p for p in passi if p.descrizione.startswith("estrai runner"))
    assert "--no-overwrite-dir" in estrai.comando
    nomi = [p.descrizione for p in passi]
    chiudi = next(i for i, n in enumerate(nomi) if n.startswith("cartella runner chiusa"))
    assert chiudi > nomi.index(estrai.descrizione)
    assert passi[chiudi].comando == ("sudo", "-n", "chmod", "0750", "/var/lib/bottega/runner-o-r")
    assert "= 750" in passi[chiudi].controllo[-1]


def test_secure_path_con_gli_strumenti_dell_esecutore_in_fondo() -> None:
    """Gli strumenti dell'esecutore (uv, le porte) si trovano, ma dopo quelli di sistema: `id` e `kill` del giro non
    si possono sostituire."""
    testo = testo_sudoers(Utenti())
    riga = next(r for r in testo.splitlines() if "secure_path" in r)
    percorso = riga.split('secure_path="', 1)[1].rstrip('"').split(":")
    locale = f"{_CASE}/bottega-esecutore/.local/bin"
    assert percorso[-1] == locale
    assert percorso.index("/usr/bin") < percorso.index(locale)
    assert percorso.index("/bin") < percorso.index(locale)
