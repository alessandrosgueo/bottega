# Ricognizione per la Tappa B6: L'Installazione (Metodo «Bottega»)

Data: 2026-11-08.
Ambito: Tappa B6 del progetto `bottega`.
Obiettivo: raccogliere le specifiche tecniche, i comandi, le API e i requisiti di sistema per automatizzare
l'installazione della bottega su Linux e WSL (runner self-hosted, permessi sudo, systemd, porte CLI, GitHub CLI e Project, CI sicura per rami `bottega/*`).

---

## 1. Il runner self-hosted di GitHub Actions su Linux

Questa sezione descrive come uno script installa, registra e gestisce come servizio un runner self-hosted di GitHub Actions su Linux in modo del tutto non interattivo (senza interfaccia web).

### 1.1 Download e verifica dell'integrità
- **Indirizzo dell'archivio per versione:**
  I pacchetti ufficiali del runner sono ospitati nelle release del repository `actions/runner`:
  ```
  https://github.com/actions/runner/releases/download/v<versione>/actions-runner-linux-<arch>-<versione>.tar.gz
  ```
  dove `<arch>` può essere `x64`, `arm64` o `arm`.
  Esempio per architettura x64 e versione 2.338.2:
  `https://github.com/actions/runner/releases/download/v2.338.2/actions-runner-linux-x64-2.338.2.tar.gz`.
  *Fonte:* https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners

- **Elenco pacchetti via API:**
  L'endpoint REST di GitHub restituisce i file binari scaricabili per la versione corrente:
  ```http
  GET /repos/{owner}/{repo}/actions/runners/downloads
  ```
  oppure per un'organizzazione:
  ```http
  GET /orgs/{org}/actions/runners/downloads
  ```
  Il payload JSON contiene un array di oggetti con i campi `os`, `architecture`, `download_url` e `filename`.
  *Fonte:* https://docs.github.com/en/rest/actions/self-hosted-runners#list-runner-applications-for-a-repository

- **Dove si trova lo SHA-256 ufficiale:**
  L'endpoint API `actions/runners/downloads` non include il checksum SHA-256 nel suo payload JSON.
  Il valore SHA-256 ufficiale per ciascun archivio viene pubblicato direttamente nel testo (body) della release su GitHub (`actions/runner`). Può essere estratto programmaticamente interrogando l'API delle release:
  ```bash
  gh api repos/actions/runner/releases/latest --jq '.body'
  ```
  Nel corpo del testo Markdown, i checksum sono racchiusi in blocchi standard con commenti HTML dedicati:
  `- actions-runner-linux-x64-<versione>.tar.gz <!-- BEGIN SHA linux-x64 --><sha256><!-- END SHA linux-x64 -->`
  La verifica si effettua con il comando:
  ```bash
  echo "<sha256>  actions-runner-linux-<arch>-<versione>.tar.gz" | sha256sum -c -
  ```
  *Fonte:* https://github.com/actions/runner/releases

### 1.2 Token di registrazione via `gh api`
Per registrare un runner senza passare dalla pagina web delle impostazioni di GitHub:
- **Endpoint:** `POST /repos/{owner}/{repo}/actions/runners/registration-token`
- **Metodo HTTP:** `POST`
- **Comando:**
  ```bash
  gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token --jq .token
  ```
- **Durata del token:** 60 minuti (1 ora) dal momento dell'emissione. La risposta contiene il token e il timestamp di scadenza (`expires_at`).
- **Permessi richiesti:** permessi di amministrazione sul repository; con token OAuth/PAT classico serve lo scope `repo`, con fine-grained PAT serve `Administration: write`.
*Fonte:* https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository

### 1.3 Configurazione non interattiva (`config.sh`)
La configurazione iniziale del runner avviene tramite lo script `./config.sh` presente nella radice della cartella scompattata.
Opzioni per lavorare senza domande (`--unattended`):
```bash
./config.sh \
  --unattended \
  --url "https://github.com/<owner>/<repo>" \
  --token "<registration_token>" \
  --name "<nome_runner>" \
  --labels "<etichetta1>,<etichetta2>" \
  --work "<cartella_lavoro>" \
  --replace
```
Significato dei parametri:
- `--unattended`: disabilita i prompt interattivi, adottando i valori predefiniti per qualsiasi opzione non fornita da riga di comando.
- `--url`: l'indirizzo URL del repository o dell'organizzazione GitHub.
- `--token`: il token di registrazione temporaneo ottenuto via API.
- `--name`: nome con cui il runner viene registrato e identificato su GitHub (default: hostname del sistema).
- `--labels`: elenco di etichette personalizzate separate da virgola (default: aggiunge `self-hosted`, `Linux`, `<arch>`).
- `--work`: percorso relativo o assoluto della cartella di lavoro dei job (default: `_work`).
- `--replace`: flag booleano (senza argomenti) che forza la sovrascrittura di un runner registrato con lo stesso nome se già presente.
*Fonti:* https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners; codice sorgente `src/Runner.Listener/CommandSettings.cs` del repo `actions/runner`.

### 1.4 Servizio systemd (`svc.sh`)
Dopo la configurazione con `config.sh`, nella cartella del runner viene generato lo script `svc.sh` (basato sul template `src/Misc/layoutbin/systemd.svc.sh.template`).
- **Installazione come servizio per un utente specifico:**
  ```bash
  sudo ./svc.sh install <utente_runner>
  ```
  Lo script genera il file di unità `/etc/systemd/system/actions.runner.<owner>-<repo>.<nome_runner>.service`, impostando `User=<utente_runner>`, imposta i permessi `664`, copia `runsvc.sh` impostandone la proprietà a `<utente_runner>` con permessi `755`, esegue `systemctl daemon-reload` e `systemctl enable`.
- **Avvio del servizio:**
  ```bash
  sudo ./svc.sh start
  ```
- **Stato del servizio:**
  ```bash
  sudo ./svc.sh status
  ```
- **Arresto del servizio:**
  ```bash
  sudo ./svc.sh stop
  ```
- **Disinstallazione del servizio:**
  ```bash
  sudo ./svc.sh uninstall
  ```
  Arresta il servizio, esegue `systemctl disable`, rimuove il file di unità da `/etc/systemd/system/`, elimina il file `.service` locale ed esegue `systemctl daemon-reload`.
*Fonte:* https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service

### 1.5 Deregistrazione (`config.sh remove`)
Per rimuovere il runner da GitHub ed eliminare la configurazione locale:
1. Si richiede un token di rimozione temporaneo via API:
   - **Endpoint:** `POST /repos/{owner}/{repo}/actions/runners/remove-token`
   - **Metodo HTTP:** `POST`
   - **Durata:** 60 minuti.
   - **Comando:**
     ```bash
     gh api -X POST repos/<owner>/<repo>/actions/runners/remove-token --jq .token
     ```
2. Si esegue la rimozione locale:
   ```bash
   ./config.sh remove --token "<remove_token>"
   ```
*Fonte:* https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-remove-token-for-a-repository

---

## 2. systemd su WSL

Il runner self-hosted della bottega richiede un sistema init attivo per gestire il demone del runner tramite `svc.sh`.

### 2.1 Come rilevare se systemd è attivo
1. **Verifica del processo init (PID 1):**
   ```bash
   ps -p 1 -o comm=
   ```
   - Se restituisce `systemd`, systemd è attivo come init principale.
   - Se restituisce `init`, WSL sta eseguendo il processo di avvio proprietario Microsoft anziché systemd.

2. **Verifica dello stato del gestore di sistema:**
   ```bash
   systemctl is-system-running
   ```
   - Restituisce `running` (codice d'uscita 0) quando tutti i servizi essenziali sono operativi.
   - Restituisce `degraded` (codice d'uscita > 0) quando systemd è attivo ed esegue i servizi, ma una o più unità di sistema non critiche sono fallite (situazione frequente in ambiente WSL per la mancanza di hardware reale). Anche con stato `degraded`, i servizi utente e i demoni come il runner di GitHub funzionano regolarmente.
   - Se systemd non è attivo, il comando fallisce con errore:
     `System has not been booted with systemd as init system (PID 1). Can't operate.` oppure restituisce `offline`.

3. **Verifica del file di configurazione WSL:**
   Verificare la presenza della direttiva `systemd=true` in `/etc/wsl.conf`:
   ```ini
   [boot]
   systemd=true
   ```

### 2.2 Cosa fare se systemd non è attivo
Se systemd non risulta attivo su WSL:
1. Modificare o creare `/etc/wsl.conf` con privilegi di root (`sudo`):
   ```bash
   sudo tee -a /etc/wsl.conf << 'EOF'
   [boot]
   systemd=true
   EOF
   ```
2. Arrestare completamente l'istanza WSL da Windows (aprendo PowerShell o Prompt dei comandi su Windows):
   ```powershell
   wsl.exe --shutdown
   ```
   *(oppure `wsl.exe --terminate <nome_distro>`)*
3. Requisiti di sistema:
   È necessario WSL versione ≥ 0.67.6 su Windows 10/11 con architettura WSL 2 (verificabile da Windows con `wsl --version`; se inferiore, aggiornare con `wsl --update`).
4. Riaprire la shell della distribuzione Linux e confermare con `systemctl is-system-running` o `ps -p 1 -o comm=`.

*Fonti:*
- https://learn.microsoft.com/en-us/windows/wsl/systemd
- https://learn.microsoft.com/en-us/windows/wsl/wsl-config#boot-settings
- `man systemctl`

---

## 3. Due utenti Unix e `sudo`

La bottega separa nettamente le responsabilità: l'utente del runner (`<utente_runner>`) possiede le chiavi di GitHub e gestisce il ciclo di vita del job, mentre l'utente dell'esecutore (`<utente_esecutore>`) esegue il modello AI e il codice senza alcuna chiave di GitHub.

### 3.1 Configurazione `sudoers` restrittiva
L'utente del runner deve poter lanciare comandi come l'utente dell'esecutore senza password, ma **non deve poter diventare root** né eseguire comandi come altri utenti.

- **File dedicato:** `/etc/sudoers.d/bottega` (senza estensioni o caratteri speciali).
- **Permessi obbligatori del file:** `0440` (`r--r-----`, proprietario `root:root`).
- **Riga di configurazione più stretta:**
  ```sudoers
  <utente_runner> ALL=(<utente_esecutore>) NOPASSWD: ALL
  ```
  *Spiegazione della sintassi:*
  - `<utente_runner>`: l'utente che invoca `sudo`.
  - `ALL=`: applicabile su qualsiasi host.
  - `(<utente_esecutore>)`: specifica che il comando può essere eseguito **solo ed esclusivamente** con l'identità di `<utente_esecutore>`. È categoricamente escluso `root` (che richiederebbe `(root)` o `(ALL)`).
  - `NOPASSWD: ALL`: non richiede inserimento di password per i comandi eseguiti con l'identità specificata.
- **Validazione prima di applicare:**
  ```bash
  visudo -c -f /etc/sudoers.d/bottega
  ```
  Verifica la correttezza della sintassi del file isolato prevenendo blocchi accidentali di sudo.

- **Significato dei flag di `sudo` (`-n -H -u`):**
  - `-n` (`--non-interactive`): modalità non interattiva. Se l'azione richiede l'inserimento di una password, fallisce immediatamente restituendo errore anziché bloccare il processo su un prompt interattivo.
  - `-H` (`--set-home`): imposta la variabile d'ambiente `HOME` alla home directory dell'utente di destinazione (`/home/<utente_esecutore>/`), impedendo che i file temporanei, le cache e le configurazioni delle porte vengano cercati o scritti nella home del runner.
  - `-u <utente>` (`--user <utente>`): esegue il comando con i privilegi dell'utente specificato (`<utente_esecutore>`) anziché con quelli di root.
  Prefisso risultante: `sudo -n -H -u <utente_esecutore> --`

*Fonti:* `man sudo`, `man sudoers`, `man visudo`

### 3.2 Gruppo comune, cartella `2770` (setgid) e `umask`
I due utenti collaborano scambiandosi file nella cartella dello spazio di lavoro (`BOTTEGA_SPAZIO`).
1. **Gruppo comune:**
   Si crea un gruppo dedicato (es. `<gruppo_comune>`) e vi si iscrivono entrambi gli utenti:
   ```bash
   sudo groupadd <gruppo_comune>
   sudo usermod -a -G <gruppo_comune> <utente_runner>
   sudo usermod -a -G <gruppo_comune> <utente_esecutore>
   ```
2. **Permessi cartella `2770` (setgid):**
   ```bash
   sudo chown <utente_runner>:<gruppo_comune> <cartella_spazio>
   sudo chmod 2770 <cartella_spazio>
   ```
   - Il bit `2` (setgid): in una directory, fa sì che ogni nuovo file o sottocartella creato all'interno erediti automaticamente il gruppo proprietario della cartella (`<gruppo_comune>`), anziché il gruppo primario dell'utente creatore.
   - I permessi `770` (`rwxrwx---`): proprietario e gruppo hanno pieni permessi di lettura, scrittura ed esecuzione/accesso; gli altri utenti (`others`, 0) sono completamente esclusi.
3. **Impostazione della `umask`:**
   La umask predefinita di Linux (`022`) revoca i permessi di scrittura al gruppo (creando file `644` e cartelle `755`).
   Affinché i file creati da un utente possano essere modificati o cancellati dall'altro membro del gruppo, i processi di entrambi gli utenti devono essere eseguiti con:
   ```bash
   umask 002
   ```
   *(oppure `umask 007` per negare qualunque accesso a chiunque non appartenga al gruppo)*.
   In questo modo i nuovi file nascono con permessi `664` (o `660`) e le cartelle con `775` (o `770`).

*Fonti:* `man chmod`, `man umask`

### 3.3 Terminazione dei processi dell'esecutore e problema di `killpg` con `EPERM`
- **Come il runner uccide tutti i processi dell'esecutore senza essere root:**
  Poiché il runner non ha privilegi di root ma può eseguire comandi come `<utente_esecutore>` tramite `sudo`, la pulizia a fine giro (o prima dell'oracolo) si ottiene eseguendo `pkill` o `kill` con l'identità dell'esecutore stesso:
  ```bash
  sudo -n -u <utente_esecutore> -- pkill -KILL -u <utente_esecutore>
  ```
  oppure:
  ```bash
  sudo -n -u <utente_esecutore> -- kill -KILL -1
  ```
  - `pkill -KILL -u <utente_esecutore>`: individua tutti i processi il cui UID effettivo è `<utente_esecutore>` e invia `SIGKILL`. Per specifica di `procps-ng`, `pkill` esclude se stesso dai processi destinatari del segnale, terminando tutti i processi orfani o residui e uscendo in modo pulito.
  - `kill -KILL -1`: in conformità allo standard POSIX e a Linux `kill(2)`, quando PID = -1 il segnale viene inviato a tutti i processi per cui il chiamante ha il permesso di invio (escluso PID 1). Eseguito come `<utente_esecutore>`, invia `SIGKILL` a tutti i processi di `<utente_esecutore>`. Colpisce anche il processo `kill` stesso, causando l'uscita immediata con stato di terminazione per segnale.

- **Perché `killpg` dà `EPERM` se chiamato dall'utente del runner:**
  1. *Regola dei permessi sui segnali POSIX/Linux:* un processo non privilegiato può inviare segnali esclusivamente a processi che possiedono lo stesso UID reale o effettivo. Se l'utente `<utente_runner>` chiama `os.killpg(pgrp, signal.SIGTERM)` su un gruppo di processi in cui sono presenti processi appartenenti a `<utente_esecutore>`, il kernel verifica i permessi: poiché `<utente_runner> != <utente_esecutore>` e il chiamante non dispone della capability `CAP_KILL` (riservata a root), la chiamata di sistema fallisce sollevando l'errore `EPERM` (Operation not permitted).
  2. *Effetto di `use_pty` in sudoers:* se `/etc/sudoers` ha attiva la direttiva `Defaults use_pty` (standard in molte distribuzioni Linux per isolare l'I/O dai terminali dell'utente chiamante), `sudo` alloca uno pseudo-terminale separato ed esegue il comando in una nuova sessione e in un gruppo di processi disgiunto. I segnali inviati dal chiamante non si propagano al gruppo della pty, e qualunque tentativo diretto di segnalare il gruppo dall'esterno genera `EPERM`.
  *Conclusione:* l'utente del runner non può usare `killpg` direttamente, ma deve sempre demandare la terminazione a `sudo -n -u <utente_esecutore> -- pkill -KILL -u <utente_esecutore>`.

*Fonti:* `man 2 kill`, `man 1 pkill`, `man sudoers`

---

## 4. I login delle porte per un altro utente

Questa sezione analizza dove risiedono le credenziali delle quattro porte (Claude Code, Antigravity, Pi, Copilot CLI), se sono trasferibili copiando i file verso un nuovo utente e quali modalità di login senza browser esistono.

### 4.1 Claude Code (`claude`)
- **Posizione dei file di credenziali:**
  - `~/.claude/.credentials.json` (contiene l'oggetto `claudeAiOauth` con `accessToken`, `refreshToken`, `expiresAt`, `refreshTokenExpiresAt`, `scopes`, `subscriptionType`).
  - `~/.claude.json` (configurazione utente, ID installazione e impostazioni globali).
- **Copia tra utenti:**
  Sì, è possibile copiare `~/.claude/.credentials.json` e `~/.claude.json` da un utente all'altro:
  ```bash
  sudo cp -r /home/<utente1>/.claude/.credentials.json /home/<utente2>/.claude/
  sudo chown -R <utente2>:<utente2> /home/<utente2>/.claude
  sudo chmod 600 /home/<utente2>/.claude/.credentials.json
  ```
  I token OAuth memorizzati in chiaro sono validi e vengono caricati dal nuovo utente senza richiedere un nuovo browser login.
- **Login senza browser:**
  1. *Token OAuth a lunga durata (abbonamento Claude Pro/Team/Enterprise):*
     Eseguendo una volta su una macchina provvista di browser il comando:
     ```bash
     claude setup-token
     ```
     si ottiene un token OAuth valido 1 anno. Questo token può essere passato all'utente tramite variabile d'ambiente:
     ```bash
     export CLAUDE_CODE_OAUTH_TOKEN="<token>"
     ```
  2. *Chiave API Anthropic Console:*
     Se l'utente usa la fatturazione a consumo di Anthropic Console:
     ```bash
     export ANTHROPIC_API_KEY="sk-ant-..."
     ```
*Fonti:* `claude --help`, `claude auth login --help`, https://code.claude.com/docs/en/cli-reference.md

### 4.2 Antigravity (`agy`)
- **Posizione dei file di credenziali:**
  - `~/.gemini/antigravity-cli/antigravity-oauth-token` (file JSON contenente `token`, `auth_method`, `id_token_email`).
  - `~/.gemini/antigravity-cli/settings.json` (configurazione CLI).
- **Copia tra utenti:**
  Sì. Copiando il file `antigravity-oauth-token` nella home directory del secondo utente con permessi `0600` e ownership appropriata:
  ```bash
  sudo cp /home/<utente1>/.gemini/antigravity-cli/antigravity-oauth-token /home/<utente2>/.gemini/antigravity-cli/
  sudo chown <utente2>:<utente2> /home/<utente2>/.gemini/antigravity-cli/antigravity-oauth-token
  sudo chmod 600 /home/<utente2>/.gemini/antigravity-cli/antigravity-oauth-token
  ```
  la CLI riconosce la sessione autenticata senza avviare il flusso interattivo.
- **Login senza browser:**
  1. *Flusso URL e codice di verifica:* al primo avvio in una sessione priva di display (es. SSH o headless senza desktop), la CLI stampa l'URL di autenticazione e richiede di incollare nel terminale il codice di autorizzazione generato dal browser.
  2. *API Key:* per ambienti programmatici / headless supportati, esportando:
     ```bash
     export GEMINI_API_KEY="<api_key>"
     ```
  3. *Enterprise:* autenticazione tramite Application Default Credentials (ADC) di Google Cloud o Single Sign-On aziendale.
*Fonti:* `agy --help`, `~/.gemini/antigravity-cli/builtin/skills/antigravity_guide/references/cli.md`, https://antigravity.google/docs/cli/reference

### 4.3 Pi (`pi` / `@earendil-works/pi-coding-agent`)
- **Posizione dei file di credenziali:**
  - `~/.pi/agent/auth.json` (nella cartella dell'agente, convenzionalmente `<agent-dir> = ~/.pi/agent`).
- **Copia tra utenti:**
  Sì. Il file `auth.json` contiene la mappatura chiave-valore dei provider configurati (`{"anthropic": "...", "openai": "..."}`). È un file puramente testuale trasferibile con copia diretta e permessi `0600`:
  ```bash
  sudo cp /home/<utente1>/.pi/agent/auth.json /home/<utente2>/.pi/agent/
  sudo chown <utente2>:<utente2> /home/<utente2>/.pi/agent/auth.json
  sudo chmod 600 /home/<utente2>/.pi/agent/auth.json
  ```
- **Login senza browser:**
  Pi supporta nativamente la configurazione dell'autenticazione tramite le variabili d'ambiente standard dei provider:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
  - `MISTRAL_API_KEY`
  - `GROQ_API_KEY`
  Se le variabili sono impostate nell'ambiente di esecuzione, Pi non richiede alcun login né interazione browser.
*Fonti:* `docs/ricognizioni/2026-11-08-porte.md`, documentazione pacchetto npm `@earendil-works/pi-coding-agent`

### 4.4 GitHub Copilot CLI (`copilot`)
- **Posizione dei file di credenziali:**
  - `~/.copilot/config.json` (memorizza `copilotTokens`, `lastLoggedInUser`, `loggedInUsers`).
  - In alternativa, fa leva sull'autenticazione di `gh` in `~/.config/gh/hosts.yml` o sul credential store di sistema.
- **Copia tra utenti:**
  Sì, copiando `~/.copilot/config.json` (oppure `~/.config/gh/hosts.yml` per l'accesso `gh`) e impostando permessi `0600` e ownership del nuovo utente.
- **Login senza browser:**
  1. *Variabili d'ambiente:* Copilot CLI controlla in ordine di priorità:
     ```bash
     export COPILOT_GITHUB_TOKEN="<token>"
     # oppure
     export GH_TOKEN="<token>"
     # oppure
     export GITHUB_TOKEN="<token>"
     ```
     I token supportati includono token OAuth generati da `gh auth login`, token dell'app GitHub Copilot CLI, oppure Fine-grained Personal Access Tokens (PAT v2) con il permesso specifico "Copilot Requests".
  2. *Flusso OAuth Device Flow:*
     ```bash
     copilot login
     ```
     utilizza il device flow: restituisce un codice a 8 caratteri e invita ad aprire `https://github.com/login/device`, senza richiedere un browser sulla macchina locale.
  3. *Provider custom (BYOK):*
     ```bash
     export COPILOT_PROVIDER_BASE_URL="https://..."
     export COPILOT_PROVIDER_API_KEY="<key>"
     ```
*Fonti:* `copilot login --help`, `copilot help environment`, https://docs.github.com/copilot/how-tos/copilot-cli

---

## 5. `gh` per l'utente del runner

L'utente del runner necessita di un accesso proprio alla GitHub CLI (`gh`) per interagire con i Project, salvare segreti e gestire workflow.

### 5.1 Accesso con codice del dispositivo (`gh auth login`)
Per autenticare l'utente del runner su una macchina priva di browser grafico:
```bash
gh auth login --web --git-protocol https -s repo,workflow,project
```
- `--web`: avvia la procedura di autenticazione web. Rilevando l'assenza di browser (o su richiesta), `gh` stampa a video l'URL di verifica (`https://github.com/login/device`) e il codice monouso del dispositivo (Device Code). L'amministratore apre l'URL da qualsiasi dispositivo ed inserisce il codice.
- `--git-protocol https`: imposta HTTPS per le operazioni git (oppure `ssh`).
- `-s, --scopes repo,workflow,project`: richiede gli scope indispensabili per la bottega:
  - `repo`: lettura e scrittura su repository pubblici e privati, commit, rami e segreti.
  - `workflow`: creazione e aggiornamento dei workflow di GitHub Actions.
  - `project`: lettura e aggiornamento dei campi di GitHub Projects (v2).
- `--insecure-storage` (facoltativo): forza il salvataggio del token in formato testo semplice in `~/.config/gh/hosts.yml`, utile su Linux/WSL quando non è configurato un servizio dbus/Secret Service.
*Fonte:* `gh auth login --help`

### 5.2 Estrazione del token (`gh auth token`)
Per estrarre il token di autenticazione attivo (per esempio per passarlo al segreto del repository):
```bash
gh auth token
```
Restituisce su standard output esclusivamente la stringa del token OAuth memorizzato.
*Fonte:* `gh auth token --help`

### 5.3 Aggiornamento degli scope (`gh auth refresh -s project`)
Se le credenziali memorizzate sono sprovviste dello scope `project`:
```bash
gh auth refresh -s project
```
Il comando apre la procedura del dispositivo per consentire l'autorizzazione incrementale dei permessi senza revocare l'accesso esistente.
*Fonte:* `gh auth refresh --help`

### 5.4 Impostazione di un segreto da stdin (`gh secret set`)
Per impostare un segreto di repository leggendo il valore direttamente da standard input (senza scrivere token su file temporanei o nella cronologia della shell):
```bash
gh auth token | gh secret set BOTTEGA_TOKEN --repo <owner>/<repo>
```
oppure passando una variabile da shell:
```bash
printf '%s' "$TOKEN" | gh secret set BOTTEGA_TOKEN --repo <owner>/<repo>
```
- Livello: repository (`--app actions` è il default).
- Cifratura: `gh` recupera la chiave pubblica del repository dall'API e cifra il segreto localmente prima della trasmissione su rete.
*Fonte:* `gh secret set --help`

---

## 6. I campi del Project (GitHub Projects v2)

La bottega memorizza lo stato dei lavori e le metriche sui campi personalizzati di un GitHub Project (v2).

### 6.1 `createProjectV2Field` con `SINGLE_SELECT` e opzioni
La creazione di campi a scelta singola avviene tramite la mutation GraphQL `createProjectV2Field`.

- **Input della mutation (`CreateProjectV2FieldInput`):**
  - `projectId`: `ID!` (obbligatorio, l'ID GraphQL del Project).
  - `dataType`: `ProjectV2CustomFieldType!` (obbligatorio, valore `SINGLE_SELECT`).
  - `name`: `String!` (obbligatorio, es. `"Bottega"` o `"Esito"`).
  - `singleSelectOptions`: `[ProjectV2SingleSelectFieldOptionInput!]` (lista di opzioni).

- **Obbligatorietà dei campi di `singleSelectOptions` (`ProjectV2SingleSelectFieldOptionInput`):**
  Dall'introspezione dello schema GraphQL ufficiale di GitHub:
  - `name`: `String!` -> **OBBLIGATORIO** (non nullo).
  - `color`: `ProjectV2SingleSelectFieldOptionColor!` -> **OBBLIGATORIO** (non nullo).
  - `description`: `String!` -> **OBBLIGATORIO** (non nullo; se l'opzione non ha descrizione va passata una stringa vuota `""`).
  - `id`: `String` -> facoltativo (usato solo per aggiornamenti di opzioni preesistenti).

- **Colori ammessi (`ProjectV2SingleSelectFieldOptionColor`):**
  `GRAY`, `BLUE`, `GREEN`, `YELLOW`, `ORANGE`, `RED`, `PINK`, `PURPLE`.

- **Esempio di mutation GraphQL:**
  ```graphql
  mutation($projectId: ID!) {
    createProjectV2Field(input: {
      projectId: $projectId
      dataType: SINGLE_SELECT
      name: "Bottega"
      singleSelectOptions: [
        { name: "pronto", color: BLUE, description: "" },
        { name: "in corso", color: YELLOW, description: "" },
        { name: "in attesa", color: ORANGE, description: "" },
        { name: "consegnato", color: GREEN, description: "" },
        { name: "bloccato", color: RED, description: "" }
      ]
    }) {
      projectV2Field {
        ... on ProjectV2SingleSelectField {
          id
          name
          options { id name }
        }
      }
    }
  }
  ```

- **Alternativa via CLI (`gh project field-create`):**
  ```bash
  gh project field-create <numero_progetto> --owner "<owner>" --name "Bottega" --data-type "SINGLE_SELECT" --single-select-options "pronto,in corso,in attesa,consegnato,bloccato"
  ```
  *(Nota: la CLI `gh` assegna colori predefiniti alle opzioni create con questo comando)*.

### 6.2 Come verificare se un campo esiste già
Per evitare errori di duplicazione, prima di creare un campo occorre interrogare i campi esistenti:
- **Via GraphQL:**
  ```graphql
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        id
        fields(first: 50) {
          nodes {
            ... on ProjectV2FieldCommon {
              id
              name
              dataType
            }
            ... on ProjectV2SingleSelectField {
              id
              name
              dataType
              options { id name color }
            }
          }
        }
      }
    }
  }
  ```
- **Via CLI (`gh`):**
  ```bash
  gh project field-list <numero_progetto> --owner "<owner>" --format json
  ```
  Restituisce un JSON con la lista `fields`. Lo script filtra per `name`:
  - Se il campo è presente, ne memorizza l'ID e gli ID delle relative opzioni per gli aggiornamenti successivi.
  - Se il campo non esiste, invoca `createProjectV2Field`.

*Fonti:* `gh project field-list --help`, `gh project field-create --help`, schema GraphQL GitHub (`https://docs.github.com/en/graphql/reference/mutations#createprojectv2field`)

---

## 7. La CI di un progetto sui rami `bottega/*`

I rami `bottega/*` contengono codice scritto dal modello dell'esecutore prima della revisione umana.
Se un workflow di CI del progetto si attiva su tali rami eseguendo codice con accesso a runner self-hosted o a segreti di repository, un modello (o una risposta malevola) potrebbe esfiltrare credenziali o compromettere la macchina ospite.

### 7.1 Quando un workflow parte sui rami `bottega/*`
Un workflow è pericoloso se risponde a eventi `push` o `pull_request` senza escludere i rami della bottega.
Le forme sintattiche della chiave `on:` nei file YAML sono:

1. **Forma stringa scalare:**
   ```yaml
   on: push
   ```
   oppure `on: pull_request`.
   *Comportamento:* scatta su **qualsiasi** ramo, inclusi tutti i rami `bottega/*`.

2. **Forma lista scalare (inline o blocco):**
   ```yaml
   on: [push, pull_request]
   ```
   oppure:
   ```yaml
   on:
     - push
     - pull_request
   ```
   *Comportamento:* scatta su qualsiasi ramo per tutti gli eventi elencati.

3. **Forma mappa (dizionario):**
   ```yaml
   on:
     push:
       branches: [...]
     pull_request:
       branches: [...]
   ```
   - *Assenza di filtri sui rami:* se sotto `push:` (o `pull_request:`) non è presente né `branches` né `branches-ignore` (o la chiave è vuota `push:`), il workflow scatta su tutti i rami.
   - *Con `branches-ignore`:*
     ```yaml
     on:
       push:
         branches-ignore:
           - 'bottega/**'
     ```
     Se la lista contiene `'bottega/**'` (o `'bottega/*'`), il workflow **non** scatta su push a rami bottega. Se la voce manca o esclude solo altri rami, scatta sui rami `bottega/*`.
   - *Con `branches`:*
     ```yaml
     on:
       push:
         branches:
           - 'main'
     ```
     Se `branches` elenca solo rami espliciti (es. `main`, `master`) senza caratteri jolly, **non** scatta su `push` ai rami `bottega/*`.
     Se invece include glob come `'*'`, `'**'`, `'bottega/**'` o pattern generici senza un'esclusione negata (`!bottega/**`), il workflow scatta.
   - *Particolarità di `pull_request`:*
     In GitHub Actions, il filtro `branches` dell'evento `pull_request` verifica il ramo di **destinazione** (*base branch*, tipicamente `main`), **non** il ramo sorgente (*head branch*).
     Di conseguenza, quando la bottega apre una PR verso `main`, un workflow con `on: pull_request: branches: [main]` **scatterà comunque**, eseguendo i job nel contesto della PR.
     Per non essere pericoloso, il workflow o i singoli job devono includere una condizione esplicita:
     `if: !startsWith(github.head_ref, 'bottega/')`
     oppure il progetto deve evitare di concedere segreti e runner self-hosted a quel workflow.

### 7.2 Riconoscimento di segreti e runner self-hosted
Un workflow che scatta su `bottega/*` costituisce un rischio se:
1. **Utilizza segreti del repository:**
   - Presenza nel testo del workflow di riferimenti `${{ secrets.<NOME> }}` o `secrets.<NOME>`.
   - Utilizzo di `secrets: inherit` nelle chiamate di workflow riusabili (`workflow_call`).
   *(Nota: `secrets.GITHUB_TOKEN` è un token effimero generato da Actions, ma con permessi write può comunque modificare il repo; i segreti custom come `BOTTEGA_TOKEN`, `API_KEY`, `DEPLOY_KEY` sono ad alto rischio).*
2. **Utilizza runner self-hosted:**
   - Sintassi `runs-on: self-hosted` oppure lista `runs-on: [self-hosted, ...]`.
   - Utilizzo di etichette non gestite da GitHub (qualsiasi valore che non sia riconducibile a immagini standard GitHub come `ubuntu-latest`, `ubuntu-24.04`, `ubuntu-22.04`, `windows-latest`, `macos-latest`, ecc.).

### 7.3 Analisi dei file YAML con sola libreria standard di Python
Il pacchetto `bottega` non include dipendenze di terze parti come `PyYAML`. L'analisi dei file `.github/workflows/*.yml` deve avvenire interamente tramite la libreria standard di Python (≥ 3.11).

Poiché i workflow di GitHub Actions seguono una struttura a blocchi coerente, è possibile implementare uno scanner strutturato in Python basato su indentazione e tokenizzatore lineare:
1. **Pre-elaborazione delle righe:**
   - Rimozione dei commenti (carattere `#` all'esterno di stringhe racchiuse tra apici singoli o doppi).
   - Misurazione dell'indentazione iniziale (numero di spazi).
   - Ignorare righe vuote o di soli spazi.
2. **Identificazione dei blocchi chiave:**
   - Rilevamento della chiave `on:` (a indentazione 0 o all'interno del dizionario radice).
   - Se `on:` è seguito da un valore scalare sulla stessa riga (`on: push` o `on: [push, pull_request]`), viene estratto immediatamente.
   - Se `on:` apre un blocco indentato, si scansionano le sotto-chiavi (`push:`, `pull_request:`):
     - Rilevamento di `branches-ignore:` e raccolta dei pattern della lista.
     - Rilevamento di `branches:` e raccolta dei pattern della lista.
3. **Scansione dei job e dei pericoli:**
   - Nel blocco `jobs:`, per ciascun job si identificano:
     - Le righe con `runs-on:`: estrazione del valore (stringa o lista `[...]` o elementi `- ...` indentati). Se contiene `self-hosted` o un'etichetta non presente nella whitelist dei runner GitHub standard, il runner è contrassegnato come self-hosted.
     - Espressione regolare per i segreti: `re.search(r'\bsecrets\.([A-Za-z0-9_]+)\b', riga)` e `re.search(r'\bsecrets\s*:\s*inherit\b', riga)`.
4. **Valutazione del rischio:**
   Un file `.yml` viene segnalato come violazione di sicurezza se:
   - Viene attivato da `push` senza escludere `'bottega/**'`; OPPURE viene attivato da `pull_request` senza guardie;
   - E contemporaneamente contiene almeno un riferimento a `secrets.` o un runner `self-hosted`.

*Fonti:*
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onpushpull_requestpull_request_targetbranchestags
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idruns-on
- https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions

---

## 8. Abilitare e disabilitare i workflow di un repo

La bottega o l'amministratore possono disabilitare temporaneamente workflow del progetto non conformi per evitare esecuzioni indesiderate.

### 8.1 Comandi CLI (`gh workflow disable` ed `enable`)
- **Disabilitare un workflow:**
  ```bash
  gh workflow disable <file_o_id> --repo <owner>/<repo>
  ```
  Esempio:
  `gh workflow disable ci.yml --repo <owner>/<repo>`
  *(Accetta il nome del file YAML, il nome del workflow o l'ID numerico).*
- **Abilitare un workflow:**
  ```bash
  gh workflow enable <file_o_id> --repo <owner>/<repo>
  ```
  Esempio:
  `gh workflow enable ci.yml --repo <owner>/<repo>`

### 8.2 Endpoint REST API e stato
I comandi CLI richiamano i seguenti endpoint REST di GitHub Actions:
- **Disabilitazione:**
  ```http
  PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/disable
  ```
  - Risposta: `204 No Content`.
  - Effetto: imposta lo stato del workflow a `disabled_manually`. Il workflow non viene più avviato da push, PR o schedule, ma rimane presente nel repository.
- **Abilitazione:**
  ```http
  PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/enable
  ```
  - Risposta: `204 No Content`.
  - Effetto: ripristina lo stato del workflow ad `active`.

### 8.3 Permessi richiesti
- **Token OAuth / Personal Access Token classico:**
  Richiede lo scope **`repo`** (oppure `workflow` per modificare le azioni di Actions).
- **Fine-grained Personal Access Token / GitHub App:**
  Richiede il permesso di repository:
  **`Actions: write`**.
- **Ruolo utente:**
  L'utente deve avere accesso in scrittura (*write* o *admin*) sul repository.

*Fonti:*
- `gh workflow disable --help`
- `gh workflow enable --help`
- https://docs.github.com/en/rest/actions/workflows#disable-a-workflow
- https://docs.github.com/en/rest/actions/workflows#enable-a-workflow

---

## Cosa non ho trovato

1. **SHA-256 diretto nelle API dei download del runner:**
   L'endpoint REST ufficiale `GET /repos/{owner}/{repo}/actions/runners/downloads` restituisce l'URL di download, l'architettura e l'OS, ma non contiene il campo con l'hash SHA-256 dell'archivio. L'hash ufficiale si trova esclusivamente nel corpo testuale Markdown della release su GitHub (`actions/runner/releases`).
2. **Comando di verifica autenticazione senza consumo o sessione per Antigravity (`agy`):**
   Non è stato trovato un sottocomando CLI dedicato (come `auth status`) per verificare validità e scadenza del token di Antigravity senza avviare una sessione o effettuare chiamate.
3. **Verifica non interattiva dello stato di autenticazione in Pi:**
   Pi non dispone di un comando CLI non interattivo per validare le credenziali prima dell'esecuzione: l'autenticazione è delegata alla presenza di `auth.json` o delle variabili d'ambiente dei provider (`*_API_KEY`), con errore sollevato solo alla prima invocazione dell'API.
4. **Verifica quota residua senza chiamate in GitHub Copilot CLI:**
   Copilot CLI non espone un comando di verifica preliminare della quota rimanente per le richieste premium o di sessione; la quota viene rilevata a runtime dagli errori HTTP (es. 402/429) o registrata nelle metriche di chiusura sessione.
5. **Esclusione nativa del ramo sorgente in `on.pull_request`:**
   GitHub Actions non supporta una direttiva a livello di trigger come `head-branches-ignore` per l'evento `pull_request` (il filtro `branches` agisce solo sul ramo di destinazione). L'esclusione di rami sorgente `bottega/*` deve essere implementata tramite guardie condizionali (`if:`) nei singoli job o disabilitando il workflow.
