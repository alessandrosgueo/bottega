# Porta: Claude Code

Comando `claude`. Fatti della ricognizione del 2026-11-08 (`<clone>/docs/ricognizioni/2026-11-08-porte.md`, capitolo A).
`<clone>` è la cartella del repo clonato; `~` è la cartella personale.

## Installare dal clone e aggiornare

- Installare: `claude plugin marketplace add <clone>` (la cartella del clone è il marketplace), poi
  `claude plugin install bottega@bottega --scope user`. Ambiti: `--scope user|project|local`.
- Provare per una sola sessione, senza installare: `claude --plugin-dir <clone>/plugin`.
- Aggiornare: `git pull` nel clone, poi `claude plugin marketplace update bottega` e
  `claude plugin update bottega@bottega`. Serve un riavvio.
- Togliere: `claude plugin uninstall bottega@bottega --scope user`, poi `claude plugin marketplace remove bottega`.

## Lavorare senza mani

- Prompt: `claude -p "<prompt>"` (o `--print`). La cartella è quella da cui si lancia il processo;
  `--add-dir <cartella>` aggiunge accessi.
- Modello: `--model <nome>`.
- Sola lettura: `--permission-mode plan`, oppure, più stretto, `--tools "Read,Grep,Glob"`; `--tools ""` spegne
  tutti gli strumenti.
- Approvare tutto: `--permission-mode bypassPermissions` o `--dangerously-skip-permissions`. La CLI avverte di
  usarli solo in sandbox.
- Regole precise: `--allowedTools "<regole>"` e `--disallowedTools "<regole>"`.
- Uscita leggibile da programmi: `--output-format json` (un oggetto alla fine) o `stream-json` (righe JSON in
  tempo reale).
- Ripresa: `claude -p --resume <session-id>`. Le sessioni create con `-p` restano fuori da `claude --continue`:
  per continuarle serve `claude -p --continue`.
- Identificativo: si fissa con `--session-id <uuid>`, oppure si legge il campo `session_id` del JSON.

## I modelli

- Si scelgono con `--model <nome>` (alias o nome completo).
- Elenco: il comando che li elenca non è stato trovato. In sessione interattiva il selettore `/model` li mostra.

## Trascrizioni e contatori

- Trascrizione: `~/.claude/projects/<progetto>/<session-id>.jsonl`. `<progetto>` è il percorso della cartella con i
  caratteri non alfanumerici sostituiti da `-`; oltre 200 caratteri il nome viene troncato e seguito da un hash.
- Contatori: nel campo `message.usage` dei record `assistant`: `input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`.
- Con OpenTelemetry: la metrica `claude_code.token.usage`, con attributo `type` (`input`, `output`, `cacheRead`,
  `cacheCreation`).

## Quota esaurita

- Messaggi della CLI: `You've hit your session limit · resets 3:45pm`,
  `You've hit your weekly limit · resets Mon 12:00am`, `You've hit your <famiglia> limit · resets <ora>`
  (un limite per famiglia di modelli).
- Limiti di spesa: `You've hit your monthly spend limit`, `You've hit your individual spend limit`,
  `You've hit your org's monthly spend limit`, `You've hit your team's shared budget`.
- Con `stream-json` l'evento `api_retry` ha un campo `error` con categorie come `rate_limit` e `billing_error`.
- Il messaggio `rate limited until …` in `/usage` dice solo che le quote non si leggono per ora: non che il lavoro
  è bloccato.

## Versione e accesso

- Versione: `claude --version` (alla ricognizione: `2.1.319 (Claude Code)`).
- Accesso: `claude auth status` (con `--json`, predefinito, o `--text`); esce con 0 se si è dentro, con 1 se no.
  Non è stato eseguito alla ricognizione.

## Sotto-agenti

- Sì. Lo strumento `Agent` lancia un sotto-agente. Ogni definizione ha un campo `model`: un alias, un nome completo
  o `inherit`, che eredita il modello della conversazione ed è il default.
- Da riga di comando: `--agents '<json>'` definisce agenti per la sola sessione. `CLAUDE_CODE_SUBAGENT_MODEL`
  impone un modello a tutti i sotto-agenti.

## Istruzioni e skill del progetto

- Istruzioni: `./CLAUDE.md` o `./.claude/CLAUDE.md` (progetto), `~/.claude/CLAUDE.md` (utente).
- Claude Code legge `AGENTS.md` solo se non c'è un `CLAUDE.md`: altrimenti serve `@AGENTS.md` dentro il `CLAUDE.md`.
- Skill: `~/.claude/skills/<nome>/SKILL.md`, `.claude/skills/<nome>/SKILL.md` e `<plugin>/skills/<nome>/SKILL.md`.

## Da verificare in B3

- Elenco dei modelli da comando, senza sessione interattiva: non trovato.
- `claude auth status`: non si sa se tocca la rete. Va provato che non spenda quota.
- Con molte skill installate, l'elenco che la sessione riceve può mostrare `bottega:bottega` senza la sua
  descrizione (visto il 2026-11-08): la skill si carica lo stesso, ma il modello può non pensare di usarla da solo.
  Da capire se `AGENTS.md` o `CLAUDE.md` del progetto devono nominarla.
