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
        "bottega-runner ALL=(bottega-esecutore) NOPASSWD: ALL\n"
    )
    assert testo_sudoers(u_def) == atteso_def

    u_pers = Utenti(runner="r-test", esecutore="e-test")
    atteso_pers = (
        "Defaults:r-test umask=0007, umask_override\n"
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
        f"useradd --system --create-home --shell /usr/sbin/nologin --gid {u.gruppo} {u.runner}"
    )
    pos_u_esec = testo_tutto.index(
        f"useradd --system --create-home --shell /usr/sbin/nologin --gid {u.gruppo} {u.esecutore}"
    )
    pos_usermod_r = testo_tutto.index(f"usermod -a -G {u.gruppo} {u.runner}")
    pos_usermod_e = testo_tutto.index(f"usermod -a -G {u.gruppo} {u.esecutore}")
    pos_spazio = testo_tutto.index(f"install -d -o {u.runner} -g {u.gruppo} -m 2770 {u.spazio}")
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
    assert "svc.sh install" in tutto
    assert "actions.runner.proprietario-mio-progetto.runner-1.service.d/bottega.conf" in tutto
    assert "systemctl daemon-reload" in tutto
    assert "svc.sh start" in tutto


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
    assert dict(passo_config.ambiente).get("BOTTEGA_TOKEN_REGISTRAZIONE") == token_segreto


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
