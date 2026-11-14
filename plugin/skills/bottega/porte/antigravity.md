# Porta: Antigravity

Comando `agy`. Fatti della ricognizione del 2026-11-08 (`<clone>/docs/ricognizioni/2026-11-08-porte.md`, capitolo B).
`<clone>` è la cartella del repo clonato; `~` è la cartella personale.

## Installare dal clone e aggiornare

- Installare: `agy plugin install <clone>/plugin`.
- Aggiornare: non esiste `agy plugin update`. Si fa `git pull` nel clone, poi `agy plugin uninstall bottega` e di
  nuovo `agy plugin install <clone>/plugin`.
- Sospendere e riattivare: `agy plugin disable bottega` e `agy plugin enable bottega`.
- Togliere: `agy plugin uninstall bottega`.

## Lavorare senza mani

- Prompt: `agy -p "<prompt>"` (o `--print`, `--prompt`). La cartella è quella corrente; `--add-dir <cartella>`
  per le altre. Le conversazioni sono legate alla cartella.
- Modello: `--model <nome>`. Impegno di ragionamento: `--effort low|medium|high|xhigh|max`. Agente: `--agent <nome>`.
- Modo: `--mode accept-edits|auto|plan`. Senza `--mode` vale il modo predefinito («request-review»), che si ferma
  prima di scrivere file. Il modo `plan` aggiunge al prompt l'istruzione `/plan`; la pagina dei modi non lo descrive
  come blocco delle scritture.
- Sola lettura vera: regole `deny` nel blocco `permissions` di `~/.gemini/antigravity-cli/settings.json`, per
  esempio `write_file(*)` e `command(*)`. Non provato.
- Approvare tutto: `--dangerously-skip-permissions`; la documentazione avverte del rischio.
- Uscita leggibile da programmi: `--output-format json` (una busta alla fine) o `stream-json`. Ci sono anche
  `--json-schema` per l'output strutturato e `--print-timeout` (0 = fino alla fine del turno).
- Ripresa: `agy -p --conversation <id>`, oppure `-c` o `--continue` per l'ultima della cartella.
- Identificativo: nella busta JSON è il campo `conversation_id`; nello `stream-json` è in `init.conversation_id`
  e in `result`.

## I modelli

- Si scelgono con `--model <nome>`. Il prompt va subito dopo `-p`: `agy -p "<prompt>" --model <nome>`. Con
  `agy -p --model <nome> "<prompt>"` la CLI prende `--model` per il prompt e si ferma con un errore.
- Elenco: `agy models`. Un modello non riconosciuto dà errore, con l'elenco di quelli disponibili nel campo `error`.
- Alla versione 1.5.8 (2026-11-14) il livello sta nel nome (`gemini-3.8-flash-high`, `gemini-4-hydrogen-xhigh`).
  Un nome col livello rifiuta `--effort` con un livello diverso (`--model ... conflicts with --effort=...`) ed esce
  con errore prima di chiamare il modello. Il nome senza livello `gemini-4-hydrogen` (anche se non compare in
  `agy models`) è accettato sia da solo sia con `--effort <livello>` (es. `--effort xhigh`, che aumenta i
  `thinking_tokens`).
- `gemini-pro-orchestrator-g1-pro` è «Orchestrator (Argon)»: Argon pianifica e rivede, Hydrogen esegue, in un solo
  agente e con un livello fisso. Va senza mani come gli altri, con la stessa busta JSON.

## Trascrizioni e contatori

- Conversazioni: `~/.gemini/antigravity-cli/conversations/<id>.db` (SQLite), accanto alla cartella
  `~/.gemini/antigravity-cli/brain/<id>/`.
- Contatori nell'uscita headless: l'oggetto `usage`, con `input_tokens`, `output_tokens`, `thinking_tokens`,
  `cache_read_tokens` e `total_tokens`. Nello `stream-json` compare in ogni `step_update`.
- Nel database i contatori non sono stati identificati per nome: vedi «Da verificare in B3».

## Quota esaurita

- Testo della quota: non trovato nella documentazione: vedi «Da verificare in B3».
- Esito headless: `status` diverso da `SUCCESS` (`ERROR`, `CANCELED`, `INTERRUPTED`, `INVALID`, `WAITING`), con il
  motivo nel campo `error`.
- Quote: `/usage` (alias `/quota`) mostra le quote per gruppo di modelli, con limite settimanale e limite di cinque
  ore. Va anche senza mani (`agy -p /quota`, `agy -p /credits`) e non spende quota.
- I gruppi sono separati. Alla versione 1.5.8 sono tre: «Gemini Models», «Gemini 4 Argon» (solo settimanale) e
  «Claude and GPT models». Un gruppo esaurito non ferma gli altri (2026-11-12: Gemini a zero, Claude andava). Quindi
  in configurazione usi **una sola bottega** coi tre secchi (es. `quote = { gemini = "abbondante", argon = "scarsa",
  claude = "scarsa" }`) e su ogni candidato indichi il suo secchio (`quota = "gemini"`): un 429 ferma solo i candidati
  di quel secchio.
- Crediti: l'impostazione «Use AI Credits» li usa quando le quote del piano sono esaurite.

## Versione e accesso

- Versione: `agy --version` (alla ricognizione: `1.5.3`).
- Accesso: non c'è un comando di stato. Il lancio headless usa le credenziali in cache e, senza accesso, termina
  con un errore «authentication required».

## Sotto-agenti

- Sì. Lo strumento `invoke_subagent` lancia un sotto-agente di tipo `research` (ricerca nel codice e nei file) o
  `self` (copia dell'agente chiamante).
- Agenti propri: nel frontmatter `subagent: true`, `model`, `tools`, `mcpServers`. `model` accetta `inherit` oppure
  un livello, non un nome di modello.
- Il modello concreto di ogni livello non è stato trovato: vedi «Da verificare in B3».

## Istruzioni e skill del progetto

- Istruzioni: `AGENTS.md` e `GEMINI.md` nella cartella di lavoro e in ciascuna cartella superiore, fino alla radice
  del repo; `~/.gemini/AGENTS.md` e `~/.gemini/GEMINI.md` per tutto l'utente. Ad ogni livello si legge anche la
  cartella `.agents/`, con le regole `rules/*.md`. Le sottocartelle sotto la cartella di lavoro non vengono cercate.
- Il plugin `bottega` non porta regole: non c'è un `AGENTS.md` dentro `plugin/`. `agy plugin list --json` mostra
  l'elenco `rules` di ogni plugin installato.
- Skill: `<progetto>/.agents/skills/<nome>/SKILL.md` e `~/.gemini/config/skills/<nome>/SKILL.md`.

## Da verificare in B3

- Marketplace in cartella: non trovato. Qui si installa la cartella del plugin.
- Testo della quota: non trovato nella documentazione.
- Controllo di accesso senza quota: non trovato. Un lancio di prova spende quota.
- Modelli concreti per ogni livello dei sotto-agenti: non trovato.
- Contatori nel database delle conversazioni: non identificati per nome.
- Identificativo di una conversazione fissato in partenza: non trovato, non esiste un flag.
- Sola lettura con le regole `deny`: non provata.
