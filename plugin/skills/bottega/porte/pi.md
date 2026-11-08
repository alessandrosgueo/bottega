# Porta: Pi

Comando `pi`. Fatti della ricognizione del 2026-11-08 (`<clone>/docs/ricognizioni/2026-11-08-porte.md`, capitolo C).
Pi non era installato alla ricognizione: i fatti vengono dalla sua documentazione (pacchetto 1.5.0).
`<clone>` è la cartella del repo clonato; `~` è la cartella personale.

## Installare dal clone e aggiornare

- Installare, dal clone: `cd <clone>` e poi `pi install ./plugin`. Le installazioni personali vanno in
  `~/.pi/agent/settings.json`; con `-l` vanno in `.pi/settings.json` del progetto, e solo dopo la fiducia nel progetto.
- Aggiornare: il percorso locale si carica senza copiare. Basta `git pull` nel clone.
- Togliere: `pi remove ./plugin` dal clone (`pi uninstall` è un alias).

## Lavorare senza mani

- Prompt: `pi -p "<prompt>"` (o `--print`): scrive il testo finale su stdout ed esce. `pi --mode json "<prompt>"`
  scrive JSONL su stdout ed esce.
- Cartella: quella corrente; i percorsi relativi partono da lì.
- Modello: `--model <provider/id>[:thinking]`, `--provider <nome>`,
  `--thinking off|minimal|low|medium|high|xhigh|max`.
- Sola lettura: `--tools read,grep,find,ls`; `-nt` o `--no-tools` spegne tutti gli strumenti.
- Permessi: Pi non chiede conferma per ogni chiamata a uno strumento, e approvare tutto è il comportamento
  predefinito. `-a` o `--approve` si fida dei file di progetto; `-na` o `--no-approve` li ignora.
- Uscita leggibile da programmi: `--mode json` (JSONL).
- Ripresa: `-c` o `--continue` (ultima sessione della cartella), `-r` o `--resume` (selettore),
  `--session <percorso|id>`, `--fork <percorso|id>`, `--session-id <id>` (apre la sessione con quell'ID o la crea).
- Identificativo: la prima riga di `--mode json` è un record `{"type":"session", … "id": …}`. In modalità RPC si
  usa il comando `get_state`.

## I modelli

- Si scelgono con `--model <provider/id>[:thinking]`, e con `--provider <nome>` per il fornitore.
- Elenco: `pi --list-models [ricerca]` elenca e termina. L'ultimo elenco scaricato si usa anche offline e con `pi -p`.

## Trascrizioni e contatori

- Trascrizione: `~/.pi/agent/sessions/--<percorso-cartella>--/<timestamp>_<session-id>.jsonl`. Nel percorso si toglie
  il separatore iniziale, e `/`, `\` e `:` diventano `-`. La cartella si cambia con `PI_CODING_AGENT_SESSION_DIR`
  o con `--session-dir`.
- Contatori: nel campo `usage` dei messaggi `assistant`: `input`, `output`, `cacheRead`, `cacheWrite`,
  `cacheWrite1h` (facoltativo), `totalTokens`, e `cost` con i suoi campi.
- Esistono anche record `usage` separati, con un campo `kind`.

## Quota esaurita

- Testo della quota: non trovato nella documentazione: vedi «Da verificare in B3».
- Gli errori del fornitore finiscono in `errorMessage`, in un messaggio con `stopReason: "error"`.
- I tentativi automatici sono eventi `auto_retry_start`, con `errorMessage`.

## Versione e accesso

- Versione: `pi --version`. Non è stato eseguito alla ricognizione, perché Pi non era installato.
- Accesso: non c'è un comando non interattivo di verifica (vedi «Da verificare in B3»). `/login [provider]` in
  sessione interattiva salva la credenziale in `~/.pi/agent/auth.json`.

## Sotto-agenti

- No nel nucleo: la documentazione dice che Pi non include sotto-agenti né modo piano.
- Un pacchetto esterno, `pi-subagents`, è citato in un documento di un altro plugin: non verificato (vedi B3).

## Istruzioni e skill del progetto

- Istruzioni: `AGENTS.md`, `AGENTS.override.md` o `CLAUDE.md` nella cartella `~/.pi/agent`, nella cartella di lavoro e
  nelle superiori. `-nc` o `--no-context-files` le disattiva. `GEMINI.md` non è citato: non viene letto.
- Skill: con il pacchetto, vedi «Installare dal clone e aggiornare». Senza pacchetto: `~/.pi/agent/skills/`,
  `.pi/skills/`, `~/.agents/skills/` e `.agents/skills/` (risalendo fino alla radice del repo). `--skill <percorso>`
  le carica per un solo lancio.

## Da verificare in B3

- Versione, `pi --list-models` e un lancio con `-p`: non eseguiti, perché Pi non era installato.
- Testo della quota: non trovato nella documentazione.
- Controllo di accesso senza quota: non trovato un comando non interattivo di verifica.
- Pacchetto `pi-subagents`: non verificato.
