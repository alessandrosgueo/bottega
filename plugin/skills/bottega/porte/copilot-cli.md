# Porta: GitHub Copilot CLI

Comando `copilot`. Fatti della ricognizione del 2026-11-08
(`<clone>/docs/ricognizioni/2026-11-08-porte.md`, capitolo D). `<clone>` è la cartella del repo clonato;
`~` è la cartella personale.

## Installare dal clone e aggiornare

- Installare: `copilot plugin marketplace add <clone>` (la cartella del clone è il marketplace), poi
  `copilot plugin install bottega@bottega`.
- Non si installa il plugin da percorso diretto (`copilot plugin install <clone>/plugin`): la 1.0.32 avvisa che
  questa via è deprecata. Si passa dal marketplace.
- Aggiornare: `git pull` nel clone, poi `copilot plugin marketplace update bottega` e
  `copilot plugin update bottega`. Le modifiche valgono dopo `/restart` o in una sessione nuova.
- Togliere: `copilot plugin uninstall bottega`, poi `copilot plugin marketplace remove bottega`. Il marketplace non
  si toglie se ci sono plugin installati, salvo con `--force`.

## Lavorare senza mani

- Prompt: `copilot -p "<prompt>"`. Con `-s` o `--silent` stampa solo la risposta.
- Cartella: quella corrente. `--add-dir <cartella>` dà accesso e carica anche skill e agenti di `.github/`,
  `.agents/` e `.claude/`.
- Modello: `--model <id>`.
- Permessi: in modo non interattivo serve `--allow-all-tools`. Si usano `--allow-tool` e `--deny-tool`,
  `--available-tools=<elenco>` (solo quegli strumenti), `--excluded-tools` e `--no-ask-user`. Sola lettura:
  `--available-tools='view,grep,glob'`. `--yolo` o `--allow-all` attivano tutto.
- Modo: `--mode interactive|plan|autopilot`, oppure `--plan`.
- Uscita leggibile da programmi: `--output-format json` (JSONL, un oggetto per riga).
- Ripresa: `--continue` (ultima sessione) o `--resume[=ID]`.
- Identificativo: l'evento `session.start` ha `data.sessionId`. Il riepilogo di `-p` suggerisce
  `copilot --resume=<SESSION-ID>`.

## I modelli

- Si scelgono con `--model <id>`.
- Elenco: `/model` in sessione interattiva (`copilot help commands`). Fuori dalla sessione: vedi «Da verificare in B3».

## Trascrizioni e contatori

- Trascrizione: `~/.copilot/session-state/<uuid>/events.jsonl`, accanto a `workspace.yaml`. I log stanno in
  `~/.copilot/logs/`. La cartella si cambia con `COPILOT_HOME` o `--config-dir`.
- Contatori nell'evento `session.shutdown`: `data.totalPremiumRequests`, `data.conversationTokens`,
  `data.currentTokens`, `data.systemTokens`, `data.toolDefinitionsTokens`, `data.totalApiDurationMs`. Per modello,
  in `data.modelMetrics.<modello>.usage`: `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`,
  `reasoningTokens`.
- Facoltativo, con OpenTelemetry: `COPILOT_OTEL_FILE_EXPORTER_PATH` scrive JSON-lines con la metrica
  `gen_ai.client.token.usage`.

## Quota esaurita

Dal sorgente della 1.0.32, non verificato in una sessione reale:

- `Quota exceeded. Upgrade to increase your limit: …` (il link porta alla pagina dell'abbonamento);
- HTTP 402 in un job: `No remaining quota for premium requests`;
- limite di frequenza: `You've hit your global rate limit.`, seguito da `Please wait for your limit to reset`;
- avvisi quando la quota scende al 10% o meno: `weekly usage limit` e `session usage limit`.

## Versione e accesso

- Versione: `copilot --version` (alla ricognizione: `GitHub Copilot CLI 1.0.32.`); anche `copilot version`.
- Accesso senza quota: non c'è un comando Copilot dedicato (vedi «Da verificare in B3»). La documentazione indica
  `gh auth status` per il login GitHub, e le variabili `COPILOT_GITHUB_TOKEN`, `GH_TOKEN` e `GITHUB_TOKEN`.
  `copilot login` autentica; non è stato eseguito.

## Sotto-agenti

- Sì. Agenti integrati: `task`, `explore`, `research`, `code-review`, `configure-copilot` e `rubber-duck`.
- Agenti propri: file `.agent.md` con i campi `model`, `model-policy` e `tools`.
- Comandi: `/fleet` (sotto-agenti in parallelo) e `/tasks` (compiti in background).

## Istruzioni e skill del progetto

- Istruzioni: `.github/copilot-instructions.md`; `AGENTS.md` nella radice; `CLAUDE.md` nella radice o in
  `.claude/CLAUDE.md`; `GEMINI.md` nella radice; `~/.copilot/copilot-instructions.md` per tutto l'utente.
  `--no-custom-instructions` le disattiva.
- Skill personali: `~/.copilot/skills/`, `~/.agents/skills/`, `~/.claude/skills/`. Di progetto: `.github/skills/`,
  `.agents/skills/`, `.claude/skills/`. In sessione: `/skills add <cartella>`.

## Da verificare in B3

- `-C <cartella>` e `--session-id`: nella documentazione, non nell'aiuto della 1.0.32.
- Il sottocomando `copilot skill`: non compare nell'aiuto della 1.0.32.
- Testo della quota: dal sorgente, non verificato in una sessione reale.
- Controllo di accesso senza quota: non trovato un comando dedicato.
- Elenco dei modelli fuori dalla sessione interattiva: non verificato.
- Installazione da percorso diretto: deprecata nella 1.0.32, valida nella documentazione corrente. Qui non si usa.
- Versione: il registro dava la 1.0.107 alla ricognizione; l'aiuto e i sorgenti letti sono della 1.0.32.
- Che `copilot plugin marketplace add <clone>` legga `.claude-plugin/marketplace.json` del clone: è una scelta di
  B1 fatta sulla documentazione, mai provata (Copilot CLI senza crediti alla tappa B1).
- `copilot plugin marketplace update bottega`: visto in `copilot plugin marketplace --help`, non nella ricognizione.
