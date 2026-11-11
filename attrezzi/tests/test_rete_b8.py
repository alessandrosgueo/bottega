"""Prove per la configurazione di rete nftables dell'esecutore (Compito B8-2)."""

import ipaddress
from collections.abc import Mapping, Sequence


def test_b8_resolv_legge_i_server() -> None:
    """nameserver_da_resolv estrae solo gli indirizzi validi in ordine e senza doppioni."""
    from bottega.macchina import nameserver_da_resolv

    testo = (
        "# File resolv.conf di prova\n"
        "search lan\n"
        "options edns0 trust-ad\n"
        "nameserver 127.0.0.53\n"
        "nameserver 2001:db8::1\n"
        "nameserver 127.0.0.53\n"
        "nameserver fe80::1%eth0\n"
        "nameserver pippo\n"
    )
    assert nameserver_da_resolv(testo) == ("127.0.0.53", "2001:db8::1")


def test_b8_resolv_vuoto() -> None:
    """nameserver_da_resolv su testo vuoto o privo di nameserver validi restituisce 127.0.0.1."""
    from bottega.macchina import nameserver_da_resolv

    assert nameserver_da_resolv("") == ("127.0.0.1",)
    assert nameserver_da_resolv("search lan\n") == ("127.0.0.1",)


def test_b8_tabella_e_segno() -> None:
    """tabella_rete normalizza il nome e segno_rete assegna un bit fisso per esecutore."""
    from bottega.macchina import Utenti, segno_rete, tabella_rete

    u = Utenti(esecutore="bottega-esecutore")
    assert tabella_rete(u) == "rete_bottega_esecutore"

    u_due = Utenti(esecutore="esecutore-due")
    assert tabella_rete(u_due) == "rete_esecutore_due"

    segno1 = segno_rete(u)
    segno2 = segno_rete(u)
    assert segno1 == segno2
    assert (1 << 24) <= segno1 <= (1 << 31)
    # È una singola potenza di due
    assert segno1 > 0 and (segno1 & (segno1 - 1)) == 0


def test_b8_rete_ricarica_atomica() -> None:
    """Il file nftables comincia con table inet <t> e delete table inet <t> per ricarica atomica."""
    from bottega.macchina import Utenti, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_rete_esecutore(u, ["192.0.2.53"])
    righe_utili = [
        riga.strip()
        for riga in testo.splitlines()
        if riga.strip() and not riga.strip().startswith("#")
    ]
    assert len(righe_utili) >= 2
    assert righe_utili[0] == "table inet rete_bottega_esecutore"
    assert righe_utili[1] == "delete table inet rete_bottega_esecutore"


def test_b8_rete_chiude_la_lan() -> None:
    """Il file nftables chiude i set di indirizzi privati e scarta il traffico dopo il DNS."""
    from bottega.macchina import Utenti, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_rete_esecutore(u, ["192.0.2.53"])

    assert 'meta skuid "bottega-esecutore" jump esecutore' in testo

    # In esadecimale, come in pubblico.py: il controllo pubblico prende le reti private scritte per esteso.
    indirizzi_chiusi = [
        str(ipaddress.ip_network((indirizzo, bit)))
        for indirizzo, bit in (
            (0x0A000000, 8),
            (0x64400000, 10),
            (0x7F000000, 8),
            (0xA9FE0000, 16),
            (0xAC100000, 12),
            (0xC0A80000, 16),
            (0xE0000000, 4),
        )
    ]
    for cidr in indirizzi_chiusi:
        assert cidr in testo

    assert "ip daddr @chiuse4 reject" in testo
    assert "meta nfproto ipv6 reject" in testo

    righe = [r.strip() for r in testo.splitlines()]
    indici_dns = [i for i, r in enumerate(righe) if "192.0.2.53" in r]
    indici_chiuse = [i for i, r in enumerate(righe) if "ip daddr @chiuse4 reject" in r]

    assert indici_dns, "mancano righe DNS"
    assert indici_chiuse, "manca riga ip daddr @chiuse4 reject"
    assert min(indici_chiuse) > max(indici_dns)


def test_b8_rete_dns() -> None:
    """Le regole di accettazione porte DNS (IPv4 e IPv6) precedono qualsiasi regola reject."""
    from bottega.macchina import Utenti, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_rete_esecutore(u, ("192.0.2.53", "2001:db8::53"))
    righe = [r.strip() for r in testo.splitlines()]

    indici_reject = [i for i, r in enumerate(righe) if "reject" in r]
    assert indici_reject, "nessuna riga reject trovata"
    primo_reject = indici_reject[0]

    indici_v4 = [
        i
        for i, r in enumerate(righe)
        if "ip daddr 192.0.2.53" in r and "53" in r and "accept" in r
    ]
    assert indici_v4, "manca riga DNS IPv4 per 192.0.2.53"
    assert any(i < primo_reject for i in indici_v4)

    indici_v6 = [
        i
        for i, r in enumerate(righe)
        if "ip6 daddr 2001:db8::53" in r and "53" in r and "accept" in r
    ]
    assert indici_v6, "manca riga DNS IPv6 per 2001:db8::53"
    assert any(i < primo_reject for i in indici_v6)


def test_b8_rete_dns_storto() -> None:
    """Indirizzi DNS non letterali o con caratteri malevoli sollevano ValueError."""
    import pytest
    from bottega.macchina import Utenti, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    for dns_non_valido in [
        ("192.0.2.1; flush ruleset",),
        ("pippo",),
        ("fe80::1%eth0",),
    ]:
        with pytest.raises(ValueError):
            testo_rete_esecutore(u, dns_non_valido)


def test_b8_rete_loopback_solo_dall_esecutore() -> None:
    """Le connessioni di loopback sono marcate e autorizzate solo se dell'esecutore."""
    from bottega.macchina import Utenti, segno_rete, testo_rete_esecutore

    u = Utenti(esecutore="bottega-esecutore")
    segno_hex = hex(segno_rete(u))
    testo = testo_rete_esecutore(u, ["192.0.2.53"])
    righe = [r.strip() for r in testo.splitlines()]

    assert any(
        "lo" in r and "ct mark set" in r and segno_hex.lower() in r.lower()
        for r in righe
    ), "manca marcatura connessioni loopback"

    assert any(
        "ct direction reply" in r and segno_hex.lower() in r.lower() and "risposta" in r
        for r in righe
    ), "manca salto a risposta per risposte marcate"

    indici_catena_risposta = [i for i, r in enumerate(righe) if "chain risposta" in r]
    assert indici_catena_risposta, "manca catena risposta"
    inizio_risposta = indici_catena_risposta[0]

    indici_skuid = [
        i
        for i, r in enumerate(righe)
        if i > inizio_risposta and 'meta skuid "bottega-esecutore" accept' in r
    ]
    assert indici_skuid, (
        'manca meta skuid "bottega-esecutore" accept nella catena risposta'
    )

    indici_syn_drop = [
        i
        for i, r in enumerate(righe)
        if i > inizio_risposta and "syn" in r.lower() and "drop" in r.lower()
    ]
    assert indici_syn_drop, "manca drop dei SYN-ACK altrui nella catena risposta"

    assert indici_skuid[0] < indici_syn_drop[0]


def test_b8_rete_due_esecutori() -> None:
    """Due esecutori diversi generano tabelle e regole nftables separate e isolate."""
    from bottega.macchina import Utenti, testo_rete_esecutore

    u1 = Utenti(esecutore="bottega-esecutore")
    u2 = Utenti(esecutore="esecutore-due")

    t1 = testo_rete_esecutore(u1, ["192.0.2.53"])
    t2 = testo_rete_esecutore(u2, ["192.0.2.53"])

    assert t1 != t2
    assert "rete_bottega_esecutore" in t1
    assert "rete_esecutore_due" in t2
    assert "bottega-esecutore" in t1
    assert "esecutore-due" not in t1
    assert "esecutore-due" in t2
    assert "bottega-esecutore" not in t2


def test_b8_unita_rete() -> None:
    """testo_unita_rete definisce un'unità systemd oneshot con dipendenze e percorso nft corretti."""
    from bottega.macchina import Utenti, testo_unita_rete

    u = Utenti(esecutore="bottega-esecutore")
    testo = testo_unita_rete(u)

    assert "Type=oneshot" in testo
    assert "RemainAfterExit=yes" in testo
    assert "ExecStart=/usr/sbin/nft -f /etc/nftables.d/bottega-esecutore.nft" in testo
    assert "DefaultDependencies=no" in testo
    assert "Before=network-pre.target" in testo
    assert "WantedBy=sysinit.target" in testo


def test_b8_passi_rete_in_ordine() -> None:
    """passi_rete genera i passi ordinati; se nft manca, solleva ErroreMacchina citando nftables."""
    import pytest
    from bottega.macchina import ErroreMacchina, Utenti, esegui_passi, passi_rete

    u = Utenti(esecutore="bottega-esecutore")
    passi = passi_rete(u, ["192.0.2.53"])

    # B8-3: dopo i tre file della rete vengono i tre dell'IP pubblico; in fondo l'avvio dell'IP pubblico e il suo timer.
    assert len(passi) == 11
    passi = [*passi[:3], *passi[6:9]]

    # 1. verifica presenza nft
    cmd0 = " ".join(passi[0].comando)
    ctl0 = " ".join(passi[0].controllo) if passi[0].controllo else ""
    assert "nft" in cmd0 or "nft" in ctl0

    # 2. file nftables
    assert "/etc/nftables.d/bottega-esecutore.nft" in " ".join(passi[1].comando)
    assert "0644" in " ".join(passi[1].comando)

    # 3. file unità systemd
    assert "/etc/systemd/system/bottega-esecutore-rete.service" in " ".join(
        passi[2].comando
    )
    assert "0644" in " ".join(passi[2].comando)

    # 4. caricamento regole nftables (senza controllo)
    assert passi[3].controllo is None
    assert passi[3].comando == (
        "sudo",
        "-n",
        "nft",
        "-f",
        "/etc/nftables.d/bottega-esecutore.nft",
    )

    # 5. ricarica configurazione systemd
    assert passi[4].comando == ("sudo", "-n", "systemctl", "daemon-reload")

    # 6. attivazione e avvio del servizio con controllo is-enabled e is-active
    assert passi[5].comando == (
        "sudo",
        "-n",
        "systemctl",
        "enable",
        "--now",
        "bottega-esecutore-rete.service",
    )
    assert passi[5].controllo is not None
    ctl_str = " ".join(passi[5].controllo)
    assert "is-enabled" in ctl_str
    assert "is-active" in ctl_str

    comandi_chiamati: list[tuple[str, ...]] = []

    def esecutore_manca_nft(
        comando: Sequence[str],
        ambiente: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        cmd_t = tuple(comando)
        comandi_chiamati.append(cmd_t)
        cmd_str = " ".join(comando)
        if "nftables" in cmd_str:
            return 1, "pacchetto nftables non trovato\n"
        return 1, ""

    with pytest.raises(ErroreMacchina) as exc_info:
        esegui_passi(passi, esecutore_manca_nft)

    assert "nftables" in str(exc_info.value).lower()
    for c in comandi_chiamati:
        c_str = " ".join(c)
        assert "/etc/nftables.d" not in c_str
        assert "systemctl" not in c_str


def test_b8_comando_macchina_carica_la_rete() -> None:
    """comando_macchina esegue passi_rete con il nameserver fornito dopo i comandi useradd."""
    import argparse

    from bottega.installa import comando_macchina

    class EsecutoreFintoRete:
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

            # I controlli dei passi falliscono («non fatto»), i comandi riescono. Un controllo è un `getent`, uno
            # `sh -c` di prova (non il comando che dice che manca nft), il confronto `cmp` di passo_file o la
            # ricerca di nft.
            e_controllo = (
                cmd[:1] == ("getent",)
                or (cmd[:2] == ("sh", "-c") and "manca nft" not in cmd_str)
                or "cmp -s" in cmd_str
                or "command -v nft" in cmd_str
                or "test -x /usr/sbin/nft" in cmd_str
            )
            return (1, "") if e_controllo else (0, "")

    esecutore = EsecutoreFintoRete()
    args = argparse.Namespace(prova=False)

    codice = comando_macchina(args, esegui=esecutore, resolv="nameserver 192.0.2.53\n")
    assert codice == 0

    indici_nft = [
        i
        for i, cmd in enumerate(esecutore.comandi)
        if any("nft" in arg for arg in cmd)
        and any("-f" in arg for arg in cmd)
        and any("/etc/nftables.d/bottega-esecutore.nft" in arg for arg in cmd)
    ]
    assert indici_nft, "manca il comando nft -f per il file nftables"

    indici_useradd = [
        i
        for i, cmd in enumerate(esecutore.comandi)
        if any("useradd" in arg for arg in cmd)
    ]
    assert indici_useradd, "mancano comandi useradd"
    assert min(indici_nft) > max(indici_useradd), "nft -f deve venire dopo useradd"

    comandi_passo_file = [
        " ".join(cmd)
        for cmd in esecutore.comandi
        if "/etc/nftables.d/bottega-esecutore.nft" in " ".join(cmd)
        and "install" in " ".join(cmd)
    ]
    assert comandi_passo_file, (
        "manca il passo_file per /etc/nftables.d/bottega-esecutore.nft"
    )
    assert any("192.0.2.53" in cmd for cmd in comandi_passo_file), (
        "il contenuto installato per nftables non contiene l'IP DNS 192.0.2.53"
    )
