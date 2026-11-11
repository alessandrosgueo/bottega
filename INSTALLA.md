# Installare la bottega

Questa guida è per la CLI che installa (Claude Code, Antigravity, Pi, GitHub Copilot CLI): l'utente le dice
«installa la bottega» e lei segue questi passi. Leggila tutta prima di cominciare. Fai da sola tutto ciò che puoi,
chiedi solo ciò che non puoi sapere, e mostra sempre la prova a vuoto (`--prova`) prima di un passo che cambia la
macchina o il progetto.

Il comando è `python3 -m bottega` con `PYTHONPATH=<clone>/attrezzi` (qui sotto: `bottega`).

## 0. Cosa serve

- Linux, oppure Windows con WSL 2. Per l'esecutore fuori serve systemd (su WSL: `[boot]` `systemd=true` in
  `/etc/wsl.conf`, poi `wsl --shutdown` da Windows: quel passo lo fa l'utente).
- `git`, `python3` 3.11 o più, `gh` collegato all'account dell'utente (`gh auth status`). Va bene anche il `gh` dei
  pacchetti di Ubuntu (2.46): dove mancano i comandi nuovi la bottega usa l'API REST.
- `sudo`, solo per l'esecutore fuori: si chiede una volta.

## 1. Il clone e il plugin

1. Clona il repo `bottega` in una cartella stabile; gli aggiornamenti arrivano con `git pull`.
2. Per ogni porta presente sulla macchina, installa il plugin dal clone come dice la sezione «Installare dal clone e
   aggiornare» di `plugin/skills/bottega/porte/<porta>.md`.

## 2. Le domande

Chiedi, una alla volta, e solo queste:

1. come l'utente vuole essere chiamato;
2. il progetto: il repo su GitHub (`owner/repo`) e la cartella del suo clone su questa macchina;
3. quali abbonamenti si possono usare su quel progetto (un progetto di lavoro può avere regole su dove va il codice);
4. se vuole l'**esecutore fuori** (un runner su questa macchina che lavora da GitHub, anche di notte) e a che ora la
   notte.

Il resto lo proponi tu e l'utente conferma: le botteghe (una per abbonamento), i candidati (porte e modelli che
trovi: `<porta> --version` e la sezione «I modelli» delle pagine delle porte), le funzioni (`decidere`, `eseguire`,
`rivedere`, `consigliare`) e i nomi, «titolo + modello».

## 3. La configurazione

Scrivi `.github/bottega/bottega.toml` nel clone del progetto, partendo da
`plugin/skills/bottega/modelli/bottega.toml`, coi valori decisi. Controlla con
`bottega configurazione --file .github/bottega/bottega.toml`: dice gli errori e i **rischi della CI** del progetto.

**La CI del progetto e i rami `bottega/*`.** Se il controllo segnala un workflow che parte sui rami `bottega/*` e ha
segreti o un runner self-hosted, fermati: i rami `bottega/*` li scrive un modello, e quel workflow eseguirebbe il suo
codice con quei segreti o su quella macchina. Proponi all'utente la correzione in una PR a parte (di solito
`branches-ignore: ['bottega/**']` sotto `push`, e per `pull_request` una guardia
`if: ${{ !startsWith(github.head_ref, 'bottega/') }}` in ogni job), e vai avanti solo quando è unita.

## 4. La firma

`bottega firma prepara` (nel clone del progetto): crea la chiave di firma dell'utente se manca, configura git per
firmare le unioni e scrive la sua riga in `.github/bottega/firme-ammesse`, che entra nella PR d'installazione.

## 5. L'esecutore fuori (solo se l'utente l'ha voluto)

1. **La macchina:** `bottega installa macchina --prova`, mostra le righe, poi `bottega installa macchina`. Crea due
   utenti di sistema (`bottega-runner` con le chiavi di GitHub, `bottega-esecutore` per i modelli, senza chiavi), un
   gruppo, lo spazio dei giri e il solo `sudo` che serve: il runner può diventare l'esecutore, mai root.
2. **L'accesso a GitHub del runner:** `sudo -u bottega-runner -H gh auth login --web --git-protocol https -s
   repo,workflow,project`. È l'account dell'utente (un solo account): l'utente mette il codice nel browser, una volta. Di' all'utente che questo
   accesso vale per tutti i suoi repo: se preferisce, può usare un account o un token limitato al solo progetto.
3. **Le porte dell'esecutore:** per ogni porta di un candidato che esegue fuori, installala per `bottega-esecutore`
   con l'installatore ufficiale e fai il suo login come quell'utente (`sudo -u bottega-esecutore -H <porta> …`;
   l'utente completa nel browser). **Non copiare le credenziali dell'utente**: i token si rinnovano e la copia può
   rompere l'originale. Annota il percorso assoluto di ogni porta (`sudo` azzera il `PATH`).
4. **Il runner:** `bottega installa runner --repo <owner>/<repo> --etichetta <etichetta> --nome <nome> --porta
   <porta>=<percorso assoluto> … --prova`, poi senza `--prova`. L'etichetta è quella del `runner` dei candidati
   nella configurazione.
   Su una macchina che fa anche altro, `--tetto 6G` (o quanto vuole l'utente) dà al servizio del runner un tetto di
   memoria senza swap: l'esecutore, le sue porte e le sue prove ci stanno dentro.
   Se chi installa non ha `gh` collegato su questa macchina (un server), `--gh-del-runner` fa passare la richiesta
   della release e del token di registrazione dall'accesso del runner del passo 2: niente secondo login.
   L'adattatore della board del progetto gira come runner, col PATH di sistema (il `.path` del runner): gli strumenti
   che usa (per esempio `uv`) vanno in `/usr/local/bin`, non nella casa di un utente.

Un secondo progetto sulla stessa macchina vuole un suo utente dell'esecutore: `bottega installa macchina --esecutore
bottega-esecutore-<repo>` (aggiunge l'utente e il suo file in `/etc/sudoers.d/`, il primo resta com'era) e lo stesso
`--esecutore` a `installa runner`. Due giri dello stesso utente potrebbero toccarsi a vicenda. Il nome di un utente sta in 32 caratteri,
minuscoli, cifre, `-` e `_`: per un repo dal nome lungo scegli un suffisso breve (`bottega-esecutore-sito`).

## 6. Il progetto

1. Il Project: se il progetto non ne ha uno, `gh project create --owner <owner> --title "<repo>"`; il numero va in
   `[progetto].project`. Se `gh` non ha lo scope `project`: `gh auth refresh -s project` (browser, una volta).
2. `bottega installa progetto --repo <owner>/<repo> --project <numero> --configurazione .github/bottega/bottega.toml
   --tag <tag della bottega> --prova`, mostra all'utente i file e i campi, poi senza `--prova`. Il tag è quello della
   bottega a cui fissare i workflow (l'ultimo rilascio del repo `bottega`); il repo della bottega lo prende
   dall'`origin` del clone, oppure `--bottega <owner>/bottega`. Il comando controlla di nuovo la CI del progetto (anche
   sul ramo principale), crea i campi del Project che mancano e l'etichetta `bottega: fuori`, apre una PR in bozza sul
   ramo `bottega/installazione` (configurazione, `AGENTS.md` e `docs/costituzione.md` se mancano, i workflow della
   bottega per le botteghe con un runner fissati allo SHA del tag, `.github/bottega/firme-ammesse` se c'è) e mette il
   segreto `BOTTEGA_TOKEN` dall'accesso del runner. Lascia il clone
   sul ramo `bottega/installazione`. Senza esecutore fuori: `--solo-sessione` (solo la configurazione e le firme,
   niente workflow, niente segreto, niente tag). Se chi installa non è sulla macchina del runner, `--senza-segreto` salta il
   segreto e stampa il comando da lanciare lì (il token passa dall'accesso del runner a `gh secret set`, mai a video).
3. L'utente rivede la PR; chi decide la unisce **in locale e firmata** (`git merge --no-ff -S`) e spinge.

## 7. Il primo giro

Un'issue piccola dell'utente, col suo «Fatto quando» (un blocco di codice dopo il titolo `## Fatto quando`), e
l'etichetta `bottega: fuori`. Il distributore la prende, l'esecutore apre una PR in bozza.

Le viste del Project (per esecutore, per esito, per tappa) l'API non le crea: dai all'utente l'elenco dei campi, se
le vuole le fa una volta a mano.

## Fermare, ripartire, aggiornare, togliere

- `bottega ferma --repo <owner>/<repo>` spegne i workflow della bottega del progetto; `bottega riparti` li riaccende.
- `bottega aggiorna --repo <owner>/<repo> --tag <tag>`, nel clone del progetto: una PR che porta i workflow al
  commit del tag nuovo della bottega.
- Togliere (a mano, in quest'ordine): `sudo systemctl disable --now bottega-runner-<owner>-<repo>.service` e
  `sudo rm /etc/systemd/system/bottega-runner-<owner>-<repo>.service`; poi la registrazione, col token di rimozione
  solo nell'ambiente (mai scritto né in un argomento): `export ACTIONS_RUNNER_INPUT_TOKEN="$(gh api -X POST
  repos/<owner>/<repo>/actions/runners/remove-token --jq .token)"` e `sudo --preserve-env=ACTIONS_RUNNER_INPUT_TOKEN
  -u bottega-runner -H sh -c 'cd /var/lib/bottega/runner-<owner>-<repo> && ./config.sh remove'`; infine la cartella
  del runner, il file dell'esecutore in `/etc/sudoers.d/`, i due utenti e il gruppo.
