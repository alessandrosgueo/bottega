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
- **B6-R2. Il `sudo` stretto,** in `/etc/sudoers.d/<utente dell'esecutore>` (un file per esecutore, B6-R12; `0440`, `root:root`, controllato con
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

- **B6-R12. Un utente dell'esecutore per runner** (cioè per progetto): `kill -KILL -1` come quell'utente uccide tutti
  i suoi processi, e due giri dello stesso utente potrebbero comunque toccarsi i file a vicenda. Il primo progetto su
  una macchina usa `bottega-esecutore`; un secondo progetto riceve un utente suo (`bottega-esecutore-<repo>`), col
  suo `sudoers` e il suo `.env`. Il runner resta uno per progetto (B6-R3). Il sudoers di ogni esecutore sta nel suo
  file, `/etc/sudoers.d/<esecutore>`: un file solo per tutti avrebbe tolto al primo progetto il suo permesso alla
  seconda installazione. I nomi di utenti e gruppo passano da `[a-z_][a-z0-9_-]{0,31}` (sudo salta in silenzio i file
  con un punto nel nome).

- **B6-R13. I workflow chiamanti puntano alla bottega, mai al progetto** (dalla revisione di B6.5: il primo codice
  inventava il tag `v1.0.0` e prendeva lo SHA dal `HEAD` del progetto, o 40 zeri). `installa progetto` vuole
  `--tag T` (facoltativo solo con `--solo-sessione`) e prende il repo della bottega da `--bottega OWNER/REPO` o
  dall'`origin` del clone della bottega da cui gira, mai dalla cartella del progetto; il nome del repo è `bottega`
  (i modelli dicono `<proprietario>/bottega`); lo SHA viene da `gh api repos/<bottega>/commits/<tag>`, 40
  esadecimali, altrimenti si ferma. `--valore` non può dare `proprietario`, `tag` né `sha`. Il tag passa da
  `[0-9A-Za-z][0-9A-Za-z._-]{0,99}`: finisce nell'indirizzo dell'API, nel nome di un ramo e nel YAML. `aggiorna`
  trova la bottega allo stesso modo.
- **B6-R14. `kill -1` solo verso un altro utente** (dalla revisione di B6.4, dopo due crash): il giro chiede `id -u`
  attraverso il prefisso e lancia `kill -KILL -1` solo se l'uid è diverso dal suo e diverso da 0; ogni dubbio vuol
  dire non uccidere (`_uccidi_processi_esecutore`).

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


## Correzioni della revisione finale

La revisione finale (Opus high, a contesto fresco) ha trovato 8 gravi e 13 minori. Il maestro ha scritto le correzioni
di root, sudo, token e pin (B6.C1, `d31de1d`); il Lavorante ha scritto le prove, ognuna vista rossa sul codice di prima
(C1-prove), e le correzioni di `ci.rischi` e di `riparti` (C1-ci).

- **B6-R15 (G1). L'esecutore non scrive mai dove scrive il runner.** Ognuno dei due utenti ha il suo gruppo
  principale (`useradd --user-group --groups bottega`); il servizio del runner non ha `UMask` (prima `0007`: tutto ciò
  che il runner creava, hook e configurazione git dei cloni, codice della bottega in `_work`, nasceva scrivibile
  all'esecutore, che poteva così far girare codice suo come runner, col token). La cartella del runner è sua, `0750`.
  Il gruppo `bottega` vale solo nello spazio (`2770`) e nelle cartelle del giro e del consulto (`2770`, mkdtemp): il
  bit setgid tiene il gruppo su ciò che crea l'esecutore (con la sua umask `0007` del sudoers), così il runner lo
  legge e lo toglie.
- **B6-R16 (G2).** Lo spazio del giro è quello del `.env` del runner: il workflow `esecutore.yml` lo esporta solo
  come ripiego (`${BOTTEGA_SPAZIO:-$RUNNER_TEMP/bottega-spazio}`).
- **B6-R17 (G3, M1, M2). Il codice che gira è quello del commit fissato.** `bottega_ref:` è lo SHA del tag, il tag
  resta solo nel commento `@<sha> # <tag>`; lo SHA viene da `refs/tags/<tag>` (un tag annotato si segue fino al
  commit; mai `commits/<x>`, che risolve anche rami e commit dei fork); `aggiorna` riscrive solo le chiamate ai
  workflow della bottega, col repo della bottega.
- **B6-R18 (G4). Il token di registrazione nell'ambiente, attraverso sudo.** `config.sh` lo riceve come
  `ACTIONS_RUNNER_INPUT_TOKEN` con `sudo --preserve-env=ACTIONS_RUNNER_INPUT_TOKEN`: sudo azzera l'ambiente
  (`env_reset`), e il token del primo codice arrivava vuoto. Mai in un argomento (`ps` lo mostrerebbe a tutti).
- **B6-R19 (G7, M8). Root non esegue file del runner.** L'unità `bottega-runner-<owner>-<repo>.service` la scriviamo
  noi con `passo_file` (`User=` il runner, `ExecStart=<cartella>/runsvc.sh`); `svc.sh` non si usa.
- **B6-R20 (G8).** Il repo della bottega si ricava solo da un origin di GitHub (https o ssh, sempre verso `github.com`); altrimenti serve `--bottega`.
- **B6-R21 (G5, G6).** `riparti` vede i workflow disabilitati (`gh workflow list --all`), e un elenco vuoto è un
  errore. `ci.rischi` legge le chiavi fra apici, ogni forma di `secrets` in un'espressione, `runs-on` a mappa o con
  un'espressione come dubbio, le sole etichette esatte dei runner di GitHub, e la guardia `bottega/` solo intera o in
  `&&`.
- **Minori corretti:** M3 (processi dell'esecutore uccisi anche all'inizio del giro e dopo ogni consulto), M4
  (cartella del giro con mkdtemp), M5 (con la G1 i file del fascicolo nascono `0644` in una cartella `0750`: l'esecutore
  li legge e non li cambia), M9 (archivio scaricato in un temporaneo e rinominato dopo la verifica), M10 (pulizia del
  consulto con `ignore_cleanup_errors`), M13 (argomenti del runner controllati prima del token).
- **Minori aperti** (da rivedere col signore o dopo la palestra di B7):
  - M6: gli esecutori di progetti diversi condividono gruppo e spazio. Il runner (`bottega-runner`) è comunque uno
    solo per la macchina, quindi i progetti di una macchina sono un solo dominio di fiducia.
  - M7: il `.env` sta nella cartella del runner, che il runner può cambiare; non apre nulla all'esecutore.
  - M11: `BOTTEGA_TOKEN` è l'accesso OAuth di chi installa (`repo`, `workflow`, `project`) e vale su tutti i suoi
    repo; un token a grana fine o una GitHub App per il solo progetto è la scelta da proporre al signore.
  - M12: `bottega-esecutore-<repo>` sta nei 32 caratteri solo con nomi corti; `INSTALLA.md` consiglia un suffisso
    breve.
- **B6-R22 (dalla rilettura delle correzioni). Il runner non scrive dove scrive l'esecutore.** La cartella del giro è
  del runner, `0750`: lì stanno solo ciò che il runner prepara (`ramo.bundle`, `fascicolo`, `oracolo.bundle`) e le
  copie dei bundle dell'esecutore. Tutto ciò che crea l'esecutore sta in `esecutore/` (`2770`, setgid): il clone di
  lavoro, le copie del consigliere, la revisione, l'oracolo, i bundle di consegna e di salvataggio. Il runner non
  scrive mai in `esecutore/`, e i bundle che ne legge li copia prima nella sua cartella senza seguire link
  (`O_NOFOLLOW`, solo file normali). Prima la cartella del giro era `2770`, e un link piantato dall'esecutore al posto di
  `oracolo.bundle` faceva sovrascrivere al runner un suo file. Lo spazio è `3770` (sticky): l'esecutore non rinomina
  le cartelle dei giri. Il consulto apre la sua cartella all'esecutore solo dopo averci scritto. Ogni comando col
  prefisso ha una cartella di lavoro sua (quella del processo è nel runner, chiusa all'esecutore). Le case degli utenti
  sono `0700` (`HOME_MODE`). `ci.rischi` legge anche `runs-on` in flusso o fra apici e `secrets` in maiuscolo;
  `ferma` e `riparti` toccano solo i workflow nello stato da cambiare (`--limit 200`).
- **Minori aperti della rilettura:**
  - il passo «ricarica configurazione systemd» risulta già fatto alla prima installazione (`NeedDaemonReload` è `no`
    per un'unità mai caricata); `systemctl enable --now` ricarica da sé, quindi non fa danni;
  - `_uccidi_processi_esecutore` uccide anche i processi di un secondo progetto che usasse lo stesso utente
    dell'esecutore: `INSTALLA.md` lo sconsiglia (B6-R12);
  - lo spazio non ha una pulizia dei giri rimasti per un errore: la palestra di B7 dirà se serve.
- **B6-R23 (dalla seconda rilettura). Il setgid si scrive.** Il `chmod` di Python mette esattamente il modo dato e
  toglie il setgid se il modo non lo nomina (quello di coreutils lo conserva): la prima versione di B6-R22 dava
  `0750` alla cartella del giro, `fascicolo/` nasceva col gruppo del runner e l'esecutore non poteva copiarlo, quindi
  ogni giro moriva. Ora le cartelle del runner nel giro sono `2750` (giro, fascicolo), `esecutore/` `2770`, i file del
  runner che l'esecutore legge `0640`: nessuno dipende dall'umask del runner. Le cartelle le preparano
  `prepara_cartelle_del_giro` e `prepara_cartella_del_fascicolo`, che il cancello lancia come runner nel contenitore: con
  `0750` il cancello va ROSSO. La creazione sta dentro il `try` del giro; l'esecutore toglie ciò che ha creato, anche
  le sue cartelle chiuse (`togli_come_esecutore`), prima della pulizia del runner, nel giro e nel consulto; una pulizia
  del consulto che non riesce non fa perdere la risposta; la copia di un bundle dell'esecutore ha un tetto di 1 GiB.
  `ci.rischi` legge `runs-on` in maiuscolo e fa un dubbio di ogni chiave fra doppi apici con un escape; `ferma` spegne
  anche uno stato mancante, `riparti` riaccende solo i `disabled_*`; le case degli utenti si chiudono a `0700` anche
  se c'erano già.
- **B6-R24 (dalla terza rilettura). I workflow della bottega non sono mai un rischio.** `ci.rischi` toglie le
  espressioni `${{ … }}` anche quando vanno a capo prima di cercare i flussi `{…}`: il distributore installato ne ha
  una su più righe, e contarla come una graffa aperta faceva di ogni progetto installato un rischio, quindi ogni giro
  restava in attesa («ci del progetto») e un secondo `installa progetto` si fermava. La prova
  `test_c4_i_workflow_dell_installazione_non_sono_rischi` lo tiene. Una cartella del giro preparata a metà non resta
  nello spazio; il cancello prova lo sticky su una cartella del runner aperta al gruppo (`2770`), che senza sticky
  l'esecutore potrebbe togliere.

## Misure

| Compito | Chi | Token | Durata | Giri | Consulti | Rilievi dopo |
|---|---|---|---|---|---|---|
| ricognizione installazione | Lavorante Gemini 3.8 Flash | 300 648 (Google) | 8 min 52 s | 0 | 0 | |
| B6.1 la CI del progetto | Lavorante Gemini 3.8 Flash | 315 720 (Google) | 14 min 5 s | 0 | 0 | un `uses:` verso un workflow riusabile del repo non era un rischio (corretto dal maestro) |
| B6.2 i passi di macchina | Lavorante Gemini 3.8 Flash | 323 902 (Google) | 12 min 14 s | 0 | 0 | stato ERROR coi file a posto; percorso della casa offuscato per il controllo pubblico, file di sistema in `/tmp` con nomi fissi già a tempo di piano, finto troppo stretto (corretti dal maestro, B6-R11) |
| B6.3 i passi del progetto | Lavorante Gemini 3.8 Flash | 303 851 (Google) | 9 min 37 s | 0 | 0 | |
| B6.6 il cancello in un contenitore | maestro | | | | | verde |
| B6.4 l'esecutore a tempo di giro | Lavorante Gemini 3.8 Flash | (perso nel crash) | | 1 | 0 | `kill -KILL -1` passato da un prefisso finto con `exec "$@"`: ha ucciso tutti i processi dell'utente due volte, la seconda dalla suite del maestro (brief: il maestro non aveva previsto il finto; B6-R14, prove in un namespace PID) |
| B6.4 bis le prove del blocco | Lavorante Gemini 3.8 Flash, in gabbia | 185 099 (Google) | 8 min 33 s | 0 | 0 | 7 mutazioni del maestro uccise |
| B6.5 i comandi | Lavorante Gemini 3.8 Flash, in gabbia | 340 871 (Google) | 22 min 53 s | 0 | 0 | tag inventato e SHA del progetto nei workflow, pipe del segreto spezzata in due comandi, bottega cercata nell'origin del progetto (brief: non diceva da dove venissero; corretti dal maestro, B6-R13) |
| B6.5 bis prove e aggiunte | Lavorante Gemini 3.8 Flash, in gabbia | 473 736 (Google) | 14 min 41 s | 0 | 0 | 9 prove d'attacco rosse sul codice di prima; mutazione dello SHA uccisa |
| B6 sudoers per esecutore | maestro | | | | | un file solo per tutti gli esecutori: la seconda installazione toglieva il permesso al primo progetto (piano, B6-R12) |
| revisione finale | revisore Opus high | 173 592 | 8 min 5 s | | | 8 gravi + 13 minori (B6-R15…R21) |
| B6.C1 correzioni di root, sudo, token e pin | maestro | | | | | il cancello in contenitore prova G1 e G4 dal vero |
| B6.C1-ci `ci.rischi` e `riparti` | Lavorante Gemini 3.8 Flash, in gabbia | 363 832 (Google) | 11 min 33 s | 0 | 0 | 8 prove rosse sul codice di prima |
| B6.C1-prove | Lavorante Gemini 3.8 Flash, in gabbia | 710 009 (Google) | 23 min 8 s | 0 | 0 | 17 prove rimesse al passo, 21 d'attacco rosse sul codice di prima |
| rilettura delle correzioni | capobottega Sonnet high | 212 445 | 8 min 41 s | | | 1 grave (link piantato nella cartella del giro, B6-R22) + 8 minori |
| B6.C2 correzioni | maestro | | | | | il cancello in contenitore prova link, sticky e case dal vero |
| B6.C2 prove e `ci.rischi` | Lavorante Gemini 3.8 Flash, in gabbia | 620 952 (Google) | 21 min 32 s | 0 | 0 | 14 prove rosse sul codice di prima; `ferma` due volte di fila dava errore (corretto dal maestro); nessuna prova vedeva il runner scrivere in `esecutore/` (aggiunta dal maestro, mutazione uccisa) |
| seconda rilettura (C2) | capobottega Sonnet high | 160 712 | 5 min 31 s | | | 1 grave (il `chmod` di Python toglieva il setgid: ogni giro moriva, B6-R23) + 8 minori, corretti |
| B6.C3 correzioni | maestro | | | | | il cancello ora usa le funzioni vere del giro: con `0750` va ROSSO |
| B6.C3 prove | Lavorante Gemini 3.8 Flash, in gabbia | 394 484 (Google) | 10 min 43 s | 0 | 0 | 12 prove rosse sul codice di prima |
| terza rilettura (C3) | capobottega Sonnet high | 176 873 | 7 min 24 s | | | nessun grave; 5 minori, fra cui il falso rischio sui workflow della bottega che il maestro ha pesato come grave (B6-R24), corretti |
| B6.C4 correzioni e prove | maestro | | | | | la prova dei modelli rossa sul codice di prima |
