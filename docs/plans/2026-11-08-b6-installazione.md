# B6 L'installazione: piano dettagliato

> **Per chi esegue:** metodo Bottega; i passi usano le caselle (`- [ ]`). Vale il piano delle tappe
> (`docs/plans/2026-11-08-tappe.md`) e la costituzione del repo (`docs/costituzione.md`).

**Obiettivo:** chi riceve la bottega dice alla sua CLI «installa la bottega» e la CLI, seguendo `INSTALLA.md`, prepara
la macchina (due utenti, il runner, il `sudo` stretto), il progetto (campi del Project, configurazione, costituzione,
workflow, segreto) e le porte, chiedendo solo ciò che non può sapere. Più ciò che B3 ha rimandato qui: l'esecutore come
utente diverso e il controllo della CI del progetto sui rami `bottega/*`.

**Architettura:** quattro moduli nuovi, ognuno con i suoi passi come dati (descrizione, comando, controllo «già
fatto»), così ogni installazione si rifà senza danni e si può mostrare a vuoto (`--prova`):
`attrezzi/bottega/ci.py` (la CI del progetto), `macchina.py` (utenti, gruppo, cartelle, `sudoers`, runner),
`progetto.py` (Project, PR d'installazione, segreto, `ferma`/`riparti`/`aggiorna`), e il sottocomando
`bottega installa`. `INSTALLA.md` alla radice guida la CLI.

**Design:** `docs/specs/2026-11-08-metodo-design.md`, «L'esecutore fuori» e «Il repo, il plugin e l'installazione»;
ricognizione `docs/ricognizioni/2026-11-08-installazione.md`.

## Ruling

- **B6-R1. La macchina.** Due utenti di sistema senza login: `bottega-runner` (il runner, le chiavi di GitHub) e
  `bottega-esecutore` (le porte, nessuna chiave di GitHub), un gruppo `bottega` con tutti e due. Lo spazio dei giri è
  `/var/lib/bottega/spazio`, di `bottega-runner:bottega`, `2770`. I nomi si cambiano con le opzioni di `installa`.
- **B6-R2. Il `sudo` stretto,** in `/etc/sudoers.d/bottega` (`0440`, `root:root`, controllato con
  `visudo -c -f` su un file temporaneo prima di spostarlo):
  `Defaults:bottega-runner umask=0007, umask_override` e
  `bottega-runner ALL=(bottega-esecutore) NOPASSWD: ALL`. Il runner diventa solo l'esecutore, mai root; l'esecutore
  non ha nessun `sudo`.
- **B6-R3. Il runner,** per ogni progetto, in `/var/lib/bottega/runner-<owner>-<repo>` (fuori dalle case): l'archivio della
  versione scelta con lo SHA-256 letto dal corpo della release (`<!-- BEGIN SHA linux-<arch> -->`), `config.sh
  --unattended --url --token --name <host>-bottega --labels <etichetta> --work _work --replace` col token di
  registrazione di `gh api -X POST repos/<repo>/actions/runners/registration-token`, il servizio con `svc.sh install
  bottega-runner`, e un drop-in systemd `bottega.conf` con `UMask=0007`. Il file `.env` del runner porta
  `BOTTEGA_PREFISSO_ESECUTORE=sudo -n -H -u bottega-esecutore --`, `BOTTEGA_SPAZIO`, `BOTTEGA_RUNNER=<etichetta>` e
  `BOTTEGA_PORTA_<NOME>=<percorso assoluto>` per ogni porta dell'esecutore (B6-R5). Senza systemd (WSL senza
  `systemd=true`): l'installazione si ferma e dice come accenderlo.
- **B6-R4. L'accesso `gh` del runner** è suo: `sudo -u bottega-runner -H gh auth login --web --git-protocol https -s
  repo,workflow,project` (chi installa mette il codice nel browser, una volta). Il segreto `BOTTEGA_TOKEN` del
  progetto si scrive con `sudo -u bottega-runner -H gh auth token | gh secret set BOTTEGA_TOKEN --repo <repo>`, mai
  stampato né scritto su file.
- **B6-R5. Le porte dell'esecutore** si installano per `bottega-esecutore` con gli installatori ufficiali e i login
  si fanno come quell'utente (`sudo -u bottega-esecutore -H <porta> …`; chi installa completa il codice nel browser).
  Le credenziali di chi installa **non si copiano** (i token si rinnovano e la copia può invalidare l'originale). Il
  `sudo` del runner azzera il `PATH`: la porta si lancia col percorso assoluto, che la fabbrica delle porte legge da
  `BOTTEGA_PORTA_<NOME>` (nome in maiuscolo, `-` → `_`), se c'è.
- **B6-R6. L'esecutore separato a tempo di giro** (i rimandi di B3): con `BOTTEGA_PREFISSO_ESECUTORE` il giro, prima
  dell'oracolo e a fine giro, uccide tutti i processi dell'esecutore con `[*prefisso, "kill", "-KILL", "-1"]` (il
  runner non può: `EPERM`); il fascicolo del runner sta in una cartella `0750` del runner (l'esecutore legge, non
  scrive); le cartelle temporanee del consulto stanno nello spazio con `0770`.
- **B6-R7. La CI del progetto sui rami `bottega/*`** (il grave rimandato da B3): `ci.rischi(testi: Mapping[str, str])
  -> list[Rischio]` legge i workflow come testo (solo libreria standard) e segnala un workflow che parte su `push`
  senza escludere `bottega/**` (o su `pull_request` senza una guardia `!startsWith(github.head_ref, 'bottega/')` in
  ogni job), e che usa `secrets.` (anche `secrets: inherit`) o un runner self-hosted (`self-hosted` o un'etichetta che
  non è di GitHub) o chiama un workflow riusabile (`uses:` verso `.github/workflows/`, locale o di un altro repo: il
  chiamato non si vede, quindi nel dubbio è un rischio; è il caso di `sviluppo.yml` di Jarvis). Lo usano: `bottega configurazione` (avviso), `bottega installa progetto` (si ferma e propone la
  correzione nella PR) e il giro, che **non spinge** se il ramo principale del progetto ha un rischio (avviso con
  chiave `ci`, lavoro `in attesa`). Nel dubbio (una forma che il lettore non capisce) è un rischio.
- **B6-R8. Il progetto,** con una PR sul ramo `bottega/installazione`: `.github/bottega/bottega.toml` (dalle risposte),
  la costituzione se manca, un `AGENTS.md` alla radice che rimanda a lei, i due workflow chiamanti col `uses:` fissato
  allo SHA del tag della bottega e il `cron` dalla `notte` e dal `fuso` della configurazione (in UTC). I campi del
  Project (quelli di B3 e `misure.CAMPI`) si creano se mancano, con `createProjectV2Field` (opzioni con `color` e
  `description` obbligatori); se manca lo scope `project`, `gh auth refresh -s project`.
- **B6-R9. `bottega ferma|riparti`:** `gh workflow disable|enable` dei workflow `bottega-*.yml` del progetto.
  **`bottega aggiorna`:** una PR che porta i chiamanti allo SHA del tag nuovo.
- **B6-R10. Il cancello, rivisto:** l'installazione vera da zero (runner registrato, login delle porte) si fa in B7
  sulla palestra, col signore per i codici nel browser. In B6: i passi di macchina girano davvero in un contenitore
  Ubuntu pulito (utenti, gruppo, cartelle, `sudoers`), due volte, e la seconda non cambia niente; i passi verso GitHub
  girano a vuoto (`--prova`) e con forge e board finte.

- **B6-R11. I file di sistema** (`sudoers`, `.env` del runner, drop-in systemd) si installano con `passo_file`: un
  passo solo, in una shell di root, col contenuto quotato nel comando, scritto in un `mktemp` di root, controllato con
  `visudo -c -f` se è un sudoers, e installato con `install`. Nessun file temporaneo dal nome prevedibile e nessuna
  finestra fra controllo e installazione (dalla revisione di B6.2: il primo codice scriveva in `/tmp` con un nome
  fisso già mentre preparava i passi, e un altro utente poteva cambiare il sudoers prima dell'installazione). Il
  `.env` è di `root:bottega`, `0640`: il runner lo legge, nessuno dei due utenti lo cambia.

## Review Focus

1. **`sudoers` sbagliato** che chiude fuori chi installa: si controlla con `visudo -c -f` su un temporaneo, mai
   scritto direttamente (`test_sudoers_controllato_prima`).
2. **Una seconda installazione** sopra la prima: niente utenti doppi, niente runner registrato due volte, nessun
   file riscritto se uguale (`test_rifatta_non_cambia_niente`, nel cancello).
3. **Un workflow del progetto pericoloso** in una forma insolita (`on: [push]`, `on:\n  push:` senza filtri,
   `branches: ['**']`, `branches-ignore` senza `bottega/**`, `runs-on: [self-hosted, linux]`, `secrets: inherit`):
   segnalato (una prova per forma).
4. **Il token** del runner che finisce in un log, in un file o nell'output: mai (`test_token_mai_stampato`).
5. **L'esecutore che sopravvive al giro** con un processo staccato: ucciso prima dell'oracolo e a fine giro
   (`test_kill_prima_dell_oracolo`).

## Compiti

| Compito | Chi | File | Dipende da |
|---|---|---|---|
| B6.1 la CI del progetto | Lavorante | `ci.py`, `configurazione.py` (il comando), prove | — |
| B6.2 la macchina | Lavorante | `macchina.py`, prove (comandi finti) | — |
| B6.3 il progetto | Lavorante | `progetto.py`, prove (forgia e `gh` finti) | — |
| B6.4 l'esecutore separato | Lavorante | `giro.py`, `porte/__init__.py` (`BOTTEGA_PORTA_*`), `distributore.py`, prove | B6.1 |
| B6.5 `installa` e `INSTALLA.md` | Lavorante + maestro | `installa.py`, `__main__.py`, `INSTALLA.md`, skill | B6.1-B6.4 |
| B6.6 il cancello | maestro | il contenitore, la prova a vuoto | B6.5 |

**Fatto quando** (per ogni compito):

```
uv run pytest -q
```

## Misure

| Compito | Chi | Token | Durata | Giri | Consulti | Rilievi dopo |
|---|---|---|---|---|---|---|
| ricognizione installazione | Lavorante Gemini 3.8 Flash | 300 648 (Google) | 8 min 52 s | 0 | 0 | |
