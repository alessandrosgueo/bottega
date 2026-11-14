# Ricognizione B14.0 — Misure da sole

## D1 — `bottega lancia` e `bottega segui` (`attrezzi/bottega/lancio.py`)

- **Argomenti di `lancia`** (`argomenti_lancia`, `attrezzi/bottega/lancio.py:147-164`): `numero` (`int`),
  `--repo`, `--attesa` (`int`, default `180`), `--tetto` (`int`, default `900`). Non riceve `--configurazione`
  ne `board`.
- **Operazioni di `comando_lancia`** (`attrezzi/bottega/lancio.py:191-359`): esegue solo comandi `gh` tramite
  `esecutore_gh`; non legge `bottega.toml` e non tocca `Board`. Legge `gh issue view <numero> --json labels`
  (`:211-213`); se `"bottega: fuori"` e presente lancia `gh workflow run bottega-distributore.yml` (`:228-229`),
  altrimenti aggiunge l'etichetta (`:231-240`). Fa polling su `gh run list --workflow bottega-distributore.yml`
  (`:253-264`), `gh run view <id_giro> --json status,conclusion` (`:298-306`) e `gh run view <id_giro> --log`
  (`:336-337`), poi estrae l'esito con `esito_del_lavoro` (`:60-88,343`).
- **Codici di uscita di `comando_lancia`**: `ESITI_LANCIO` (`:28-34`) mappa `avviato -> 0`, `manutenzione -> 2`,
  `occupata -> 3`, `rosso -> 4`, `assente -> 1`. Ritorna `ESITI_LANCIO[esito]` se `esito != "assente"` (`:345-347`),
  altrimenti `1` (errori `gh`/JSON, `--tetto` superato, run assente entro `--attesa`, `esito == "assente"`).
- **Argomenti di `segui`** (`argomenti_segui`, `attrezzi/bottega/lancio.py:362-391`): `numero` (`int`),
  `--repo`, `--intervallo` (`300`), `--fermo` (`1200.0`), `--tetto` (`18000.0`),
  `--configurazione` (`PERCORSO_PREDEFINITO`).
- **Operazioni e codici di `comando_segui`** (`attrezzi/bottega/lancio.py:451-646`): costruisce `BoardComando` o
  `BoardProject` se `board is None` (`:463-489`). Sulla board legge soltanto `board.lavoro(numero)` (`:510`),
  senza scrivere nulla. Interroga `gh api repos/.../issues/{numero}/sub_issues` (`:517-525`),
  `gh workflow list --all` filtrando `bottega-esecutore` (`:545-553`), `gh run list` (`:575-586`) e i commenti
  via `_avvisi_misure_perse` (`:406-408,624`). Ritorna `1` su errore di configurazione (`:472,488`), `6` se
  supera `--tetto` (`:503-505`), altrimenti `verdetto` (`:91-129,633-644`): `0` (`finito`),
  `2` (`in attesa: una domanda per chi decide`), `3` (`bloccato`), `4` (`fermo dal ...`).
- **Aggancio di `segno.inizio` senza cambiare codici di uscita**:
  - In `comando_lancia`: al termine del lancio prima di `return ESITI_LANCIO[esito]` (`:347`, ad esempio quando
    `esito == "avviato"`), oppure subito dopo il comando di avvio (`:245`), gestendo eventuali eccezioni; oggi
    mancano `board` e `--configurazione`, che andrebbero aggiunti come in `comando_segui` (`:463-489`).
  - In `comando_segui`: ha gia `board` (`:463-489`), quindi potrebbe chiamare `segno.inizio` prima dei ritorni
    (`:641-644` o `:505`), ma `segui` gira a lancio gia avviato e non all'istante del lancio.

## D2 — `bottega dividi` (`attrezzi/bottega/dividi.py`)

- **`dividi`** (`attrezzi/bottega/dividi.py:201-308`): crea la issue madre con
  `f_effettiva.crea_issue(titolo=madre_titolo, corpo=madre_corpo, madre=None)` (`:294`), poi per ciascun elemento
  in `dati["compiti"]` chiama `f_effettiva.crea_issue(titolo=c_titolo, corpo=c_corpo, madre=num_madre)` (`:297-301`)
  raccogliendo tutti gli ID in `numeri_creati` (`[num_madre, num_compito_1, ...]`).
- Se `board is not None`, esegue `board.aggiungi(n)` per ogni numero in `numeri_creati` (`:303-305`).
- **`dividi` restituisce `numeri_creati: list[int]`** (`:307`); `comando_dividi` (`:385-387`) stampa un numero per
  riga su stdout e restituisce `0`.

## D3 — `segno.inizio`, `segno.fine` e lettura token (`attrezzi/bottega/segno.py`, `attrezzi/bottega/porte/`)

- **Individuazione di porta e sessione**:
  - `porta_della_sessione(env)` (`attrezzi/bottega/segno.py:30-49`) controlla in ordine:
    `CLAUDE_CODE_SESSION_ID` -> `"claude-code"`, `ANTIGRAVITY_CONVERSATION_ID` -> `"antigravity"`,
    `PI_SESSION_FILE` -> `("pi", Path(pi).name)`, `COPILOT_AGENT_SESSION_ID` -> `"copilot-cli"`, else `None`.
  - `comando_segno` per `inizio` (`:270-325`): usa `--porta`/`--sessione` se passati; altrimenti
    `porta_della_sessione(env)`; se assente scansiona `configurazione.PORTE` chiamando
    `p_obj.trascrizione(env, cartella, sessione=None)` e sceglie il file con `st_mtime` piu recente (`:300-310`),
    ricavando `sessione` (`pi`: `tr.name`, `copilot-cli`: `tr.parent.name`, `antigravity`:
    `tr.parent.parent.parent.name`, `claude-code`: `tr.stem`, `:285-292,311-320`). Poi chiama
    `inizio(board, numero, p_nome, s_id, adesso)` (`:322`), che salva `Segno` (`porta`, `sessione`, `inizio` ISO,
    `:87-92`).
  - `comando_segno` per `fine` (`:327-363`): raccoglie `porte_e_sessioni` da `--porta`/`--sessione` oppure
    `porta_della_sessione(env)` (`:328-356`) e chiama `fine(...)` (`:358`).
- **Come `fine` chiude il segno** (`attrezzi/bottega/segno.py:96-202`):
  - Legge `Segno` (`porta_segno`, `sessione_segno`, `inizio_str`, `:113-138`) e costruisce
    `tutte = [(p_segno, sessione_segno)] + list(porte_e_sessioni)` (`:140`).
  - Per ogni `(p_obj, s_id)` chiama `p_obj.trascrizione(env, cartella, sessione=s_id)` (`:150`); se manca torna
    `(None, ...)` (`:154-155`). Deduplica i percorsi risolti con `file_visti: set[Path]` (`:157-160`).
  - Chiama `p_obj.token(tr_risolto, dopo, fino, visti=messaggi_visti)` (`:163`) condividendo `messaggi_visti`,
    somma `totale_token` e `totale_messaggi`, e imposta `ha_parziale = True` se un `tok.parziale` e vero (`:167-170`).
  - Se `totale_messaggi == 0`, torna `(None, ...)` lasciando `Segno` aperto (`:174-175`).
  - Azzera `Segno` (`board.campo(numero, "Segno", None)`, `:179`), somma su `"Token di chi decide"` (`:182`) e
    aggiorna `"Misure parziali"` se `ha_parziale` (`:189-195`).
- **Firme su `Porta`** (`attrezzi/bottega/porte/__init__.py:91-108`):
  - `trascrizione(self, env: Mapping[str, str], cartella: Path, sessione: str | None = None) -> Path | None`
  - `token(self, percorso: Path, dopo: datetime, fino: datetime, visti: set[str] | None = None) -> Token`
- **Formula dei token** (`attrezzi/bottega/porte/__init__.py:43-55`): `PESO_CACHE_LETTA = 0.1`; `somma_pesata`
  moltiplica la chiave `cache_letta` per `0.1` e le altre per `1`, arrotondando con `round(totale)`.
  - `ClaudeCode` (`claude_code.py:183-282`): da `CLAUDE_CONFIG_DIR` o `.claude/projects`; deduplica con
    `message.id`/`requestId`/`{percorso}:{n_riga}` e `visti`; chiavi `input_tokens`,
    `cache_creation_input_tokens`, `cache_read_input_tokens` (`cache_letta`), `output_tokens`; `parziale=False`.
  - `Antigravity` (`antigravity.py:123-199`): da `ANTIGRAVITY_APP_DATA_DIR` o `.gemini/antigravity-cli/brain`;
    righe `source == "MODEL"` e `type == "PLANNER_RESPONSE"`, ignora `visti`; chiavi `input_tokens`,
    `output_tokens`, `cache_read_tokens` (`cache_letta`); `parziale=True`.
  - `Pi` (`pi.py:123-264`): da `PI_CODING_AGENT_SESSION_DIR` o `.pi/agent/sessions`; righe `type == "message"`
    (`role == "assistant"`) o `type in ("usage", "compaction", "branch_summary")`, ignora `visti`; chiavi
    `input`, `output`, `cacheRead` (`cache_letta`), `cacheWrite` (o `totalTokens` peso `1`); `parziale=False`.
  - `CopilotCli` (`copilot_cli.py:151-261`): da `COPILOT_HOME` o `.copilot/session-state`; `assistant.usage`
    (`inputTokens`, `outputTokens`, `cacheReadTokens` come `cache_letta`, `cacheWriteTokens`) e
    `subagent.completed` (`totalTokens` peso `1`), ignora `visti`; `parziale=False`.

## D4 — Chi scrive e chi legge «Esito del compito»

- **Definizione**: `SINGLE_SELECT` con opzioni `OPZIONI_ESITO = ("unito com'era", "corretto", "rifiutato")`
  (`attrezzi/bottega/misure.py:29,37`; `attrezzi/bottega/progetto.py:28-29`).
- **Chi lo scrive**: soltanto `attrezzi/bottega/misura.py:37-41,165-171` (`comando_misura`), che mappa `--esito`
  (`unito|corretto|rifiutato`) con `MAPPA_ESITO` e chiama `board.campo(numero, "Esito del compito", valore_esito)`.
  Ne `giro.py`, ne `distributore.py`, ne `scelta.py`, ne `board.py` lo scrivono.
- **Chi lo legge**:
  - `attrezzi/bottega/misure.py:108-126` (`risultati`): legge `lav.campi.get("Esito del compito")` e incrementa i
    contatori `uniti`, `corretti`, `rifiutati` di `Risultati`.
  - `attrezzi/bottega/conti.py:30,71-75`: `_ha_misura` include tutti i `CAMPI`; `_statistiche_gruppo` legge
    `l.campi.get("Esito del compito")` per i conteggi del gruppo.
  - `attrezzi/bottega/distributore.py:389` e `attrezzi/bottega/giro.py:987` passano `board.elenco()` a
    `misure.risultati(...)`; `scelta.py:38-43,449-451,487-500` consuma `Risultati` senza leggere il campo;
    `board.py:422-444,579-585` carica `lav.campi` in modo generico (`lav.esito` legge `"Esito"`, non
    `"Esito del compito"`).

## D5 — Correzioni dopo revisione («Esito» = `"correzioni"`)

- **Quando «Esito» vale `"correzioni"`**:
  - `BoardProject.pronti` (`attrezzi/bottega/board.py:454`) e `BoardProject.prendi` (`:479`), cosi come
    `BoardFinta` (`attrezzi/bottega/finta.py:300,329`), includono i lavori aperti con
    `lav.stato == "pronto" or (lav.esito == "correzioni" and lav.stato != "in corso")`. (`BoardComando.pronti`
    delega all'adattatore e verifica `.aperta`, `board.py:647-650`; `docs/adattatore.md:30-31`).
  - `prendi` (`board.py:482-486`, `finta.py:332-341`) imposta `Bottega = "in corso"` e azzera `Esito` (`None`).
  - `distribuisci` (`attrezzi/bottega/distributore.py:468-581`) non legge `lav.esito`: tratta il lavoro come ogni
    altro elemento di `board.pronti()` (`_ricava_fatto_quando` alla `:493`, `scegli`, `board.prendi` alla `:568`).
  - `giro` (`attrezzi/bottega/giro.py`) non legge `"Esito"`. Sceglie `compito = aperte[0]` tra le sotto-issue
    aperte o `iss_madre` se non ce ne sono (`:1030-1048`); se `compito` cambia rispetto alla nota azzera
    `tentativi`, `attese` e `quote` (`:1056-1061`). Aggiorna `Nota del giro`, `Bottega`, commenti e somma `+1`
    a `"Giri"` su `compito.numero` tramite `_scrivi_misure` (`:610-618,1849-1858`).
- **Campo o nota che dice "questo compito e stato corretto dopo la revisione"**: **non c'è** (esiste solo
  `"Esito del compito"` = `"corretto"`, scritto manualmente via `bottega misura`).
- **Distinguere da codice una sotto-issue di correzione da un compito del piano**: **non c'è** (`forgia.sotto_issue`
  restituisce `Issue` semplici e `giro.py:1031-1044` prende sempre `aperte[0]`; solo un commento in
  `distributore.py:114-115` cita il caso di una sotto-issue aggiunta a mano senza `Fatto quando`).

## D6 — `Board.elenco()`, `Lavoro` e PR in `forgia.py`

- **Cosa restituisce `Board.elenco()`**:
  - `BoardProject.elenco()` (`attrezzi/bottega/board.py:334-446,462-464`) restituisce tutti gli item del Project
    (`Issue` e `PullRequest` con `number`, filtrati solo per `self.repo` se impostato), indipendentemente da
    `state` (`OPEN`/`CLOSED`/`MERGED`), stato `Bottega` o relazione madre/figlio: quindi aperti e chiusi, madri,
    compiti (sotto-issue) e PR se presenti nel Project.
  - `BoardComando.elenco()` (`board.py:657-660`) esegue `<adattatore> bottega elenco`; `docs/adattatore.md:32-37`
    richiede tutti i lavori aperti o chiusi, i rispettivi compiti e ogni voce con un campo bottega.
- **Attributi di `Lavoro`** (`attrezzi/bottega/board.py:14-27`, `docs/adattatore.md:43-54`): `numero: int`,
  `titolo: str`, `etichette: list[str]`, `stato: str`, `esito: str | None`, `esecutore: str | None`, `nota: str`,
  `repo: str | None`, `campi: dict[str, str]`, `aperta: bool` (`content.get("state", "OPEN") == "OPEN"` in
  `board.py:431`; default `True` se mancante/non booleano in `_dati_a_lavoro` a `:574-578`). Attributi `madre`
  o `PR` su `Lavoro`: **non c'è**. (`BoardProject.consegna` a `:494-495` ignora il parametro `pr` e imposta solo
  `Bottega = "consegnato"`).
- **Sapere in `forgia.py` se una PR e stata unita o chiusa senza unione**: **non c'è**. `Forgia.pr_del_ramo`
  (`attrezzi/bottega/forgia.py:62,192-202`) esegue `gh pr list --head <ramo> --state open --json number --limit 1`
  e vede solo PR aperte; nessun metodo di `Forgia` interroga PR chiuse o unite (`BoardProject` inoltre comprime
  `MERGED` e `CLOSED` entrambi in `aperta = False` a `board.py:431`).

## D7 — Sequenza di `distribuisci` e lavori chiusi (`attrezzi/bottega/distributore.py`)

- **Ordine dei passi di `distribuisci`** (`attrezzi/bottega/distributore.py:365-583`):
  1. (`:387-394`) legge `lavori_elenco = board.elenco()` per `risultati_storici` e `costi_relativi` (in caso
     d'errore li lascia vuoti/`None`).
  2. (`:397-412`) `_gestisci_evento_commento`: gestisce `/bottega riprova|sospendi|consulta` su `issue_comment`
     e ritorna se `not procedi`.
  3. (`:414-419`) finestra di manutenzione (`_in_manutenzione`): esce subito se attiva.
  4. (`:421-432`) CI sul ramo principale (`forgia.ramo_principale()`, `forgia.stato_ci`): apre/aggiorna avviso
     `ci-ramo-principale` ed esce se `"rosso"`; lo chiude se `"verde"`.
  5. (`:434-466`) `board.in_corso()`: fa scadere lavori oltre `7.0` ore (`ORE_SCADENZA_IN_CORSO`), altrimenti
     segna le botteghe occupate.
  6. (`:468-581`) `board.pronti()`: filtra etichette/autore/`Fatto quando`, chiama `scegli`, verifica
     `botteghe_occupate`, chiama `board.prendi` e avvia `bottega-esecutore-{bottega}.yml`.
- **Dove si saltano i lavori chiusi (B9-R3)**: non in `distribuisci`, ma dentro `Board.pronti()` e `Board.prendi()`:
  `BoardProject.pronti` (`board.py:452-453`), `BoardProject.prendi` (`:477-478`), `BoardComando.pronti` (`:650`
  e `docs/adattatore.md:30`). (`BoardFinta` in `finta.py:300,329` non gestisce `aperta`).
- **Dove inserire un passo sui lavori chiusi senza toccare la scelta dei pronti**: usando `lavori_elenco` gia
  letto a `:388` (tenendo conto che in `391-394` un errore di `elenco()` oggi viene ignorato), subito dopo
  `_gestisci_evento_commento` (`:413`), dopo il controllo CI (`:433`, se deve saltare manutenzione e rosso),
  oppure in coda dopo `board.pronti()` (`:582`).

## D8 — Rilettura dello stesso giro e campi dei consigli (`attrezzi/bottega/giro.py`, `attrezzi/bottega/misura.py`)

- **Quando parte e cosa scrive la rilettura del consigliere** (`attrezzi/bottega/giro.py:1743-1780`):
  - Parte nello stesso giro dopo l'oracolo, l'apertura/aggiornamento della PR e i controlli di prove cambiate/
    segreti, prima di `if not oracolo_ok` (`:1785`).
  - Seleziona un candidato con `scegli(..., Compito(funzione="consigliare", fuori=True), ...)` limitato al solo
    runner del candidato esecutore (`_solo_runner`, `:1744-1754`).
  - Se manca quota/runner (`:1755`) o `lancio_rev.esito != "fatto"` (`:1776-1777`), commenta sulla PR
    `"compito senza rilettura"` con `ruolo="consigliere"` (`:1778-1779`) e il giro prosegue.
  - Se `lancio_rev.esito == "fatto"`, commenta sulla PR (`forgia.commenta(pr_num, msg_rev, ruolo="consigliere")`,
    `:1774-1775`) con `Revisione del consigliere ({cand_cons.nome}):\n\n{recinta_testo_modello(...)}`. Non scrive
    nulla su `board` ne su `lavoro` o `compito.numero`.
- **Chi scrive «Consigli accolti» e «Consigli respinti»**: soltanto `attrezzi/bottega/misura.py:196-197,200-204`
  (`--consigli-accolti`, `--consigli-respinti`). Nessun altro modulo li scrive (`conti.py:85-88` li legge,
  `misure.py:33-34` e `progetto.py:27-31` li definiscono).

## D9 — Somma delle misure nel giro (`attrezzi/bottega/giro.py`, `attrezzi/bottega/misure.py`)

- **Somma su piu giri di «Token esecutore», «Durata» e «Giri»**:
  - In `_giro`: `tempo_inizio_lancio` viene preso prima del primo lancio (`giro.py:1318-1319`), `lancio_partito = True`
    (`:1320`), ogni lancio (inclusi gli eventuali riparti dopo un consulto) entra in `lanci_esecutore` (`:1329`).
  - Nel blocco `finally:` (`:1844-1858`), se `lancio_partito` e vero calcola
    `durata_sec = int(time.monotonic() - tempo_inizio_lancio)` (`:1847`) e
    `token_tot = sum(misure.token_dei_contatori(candidato.porta, l.contatori) for l in lanci_esecutore)` (`:1848`),
    poi `_scrivi_misure` (`:556-624`) chiama `misure.somma(board, compito_numero, nome_misura, quanto)` (`:611-618`)
    per `"Durata"`, `("Giri", 1)`, `"Consulti"` e `"Token esecutore"`.
  - `misure.somma` (`attrezzi/bottega/misure.py:66-90`) somma `quanto` al valore numerico gia presente sul
    compito (`numero(lav, nome)`): i valori si accumulano tra giri successivi (se cambia candidato si aggiunge
    `"più esecutori"` a `"Misure parziali"` a `giro.py:591-598`, ma i totali vengono comunque sommati).
- **Giri falliti e timeout**:
  - Se il giro fallisce dopo `lancio_partito = True` (`errore`, `quota`, `accesso`, nessun commit, pacchetto
    rifiutato, oracolo rosso o eccezione), `finally:` esegue `_scrivi_misure`: eventuali contatori estratti dal
    JSON della porta anche in errore (`claude_code.py:124-130`, `antigravity.py:69-73`, `pi.py:78-88`,
    `copilot_cli.py:83-95`) vengono contati e sommati.
  - Se il singolo lancio scade per tetto (`esegui_con_tetto` con `scaduto=True`, `porte/__init__.py:214-229`),
    tutte e quattro le porte restituiscono `contatori={}` (`antigravity.py:49-50`, `claude_code.py:105-106`,
    `copilot_cli.py:50-51`, `pi.py:48-49`), quindi aggiunge `0` token (mentre `"Giri"` +1 e `"Durata"` vengono
    scritti). Se invece viene ucciso il job GitHub Actions dall'esterno, `finally:` non gira.

## D10 — `bottega conti` (`attrezzi/bottega/conti.py`)

- **Quando un lavoro e "misurato"**: `_ha_misura(lav)` (`attrezzi/bottega/conti.py:28-30,105`) vale `True` se
  almeno uno dei campi in `misure.CAMPI` e presente in `lav.campi` con valore non vuoto dopo `.strip()`.
  (`per_candidato` esclude poi `PIU_ESECUTORI` a `:109-110`; `per_dove` no, `:120-121`).
- **Cosa significa `"senza_numero"`**: in `_statistiche_gruppo` (`:53-68,96`), e il numero di compiti del gruppo
  che non hanno un numero finito valido in `"Token di chi decide"` (`senza_numero = n - con_numero`);
  `token_decisore_medi` e `somma_tok_dec / con_numero` (o `None` se `con_numero == 0`).
- **Cosa contiene `"spia"`** (`:120-131`): `{"fuori": stats_dove["fuori"]["token_decisore_medi"],
  "sessione": stats_dove["sessione"]["token_decisore_medi"]}`, raggruppando `lavori_misurati` per
  `l.campi.get("Dove", "").strip().lower() in ("fuori", "sessione")`.
- **Campi letti sui lavori**: tutti i 16 di `misure.CAMPI` in `_ha_misura` (`:30`), piu esplicitamente
  `"Misure parziali"` (`:109`), `"Esecutore"` (`:111`, fallback `l.esecutore`), `"Dove"` (`:120-121`),
  `"Giri"` (`:49`), `"Durata"` (`:50`), `"Token esecutore"` (`:51`), `"Token di chi decide"` (`:57`),
  `"Esito del compito"` (`:73`), `"Rilievi del piano"` (`:79`), `"Rilievi del brief"` (`:80`),
  `"Rilievi dell'esecuzione"` (`:81`), `"Consigli accolti"` (`:86`), `"Consigli respinti"` (`:87`).

## D11 — `bottega banco` (`attrezzi/bottega/banco.py`, `attrezzi/bottega/casi.py`)

- **Argomenti di `banco`** (`argomenti_banco`, `attrezzi/bottega/banco.py:82-136`): `--cartella` (`"casistica"`),
  `--casi` (`int | None`), `--seme` (`int | None`), `--porta`, `--modello`, `--risposte`, `--pr` (`int`),
  `--skill` (`"plugin/skills/bottega/SKILL.md"`), `--repo` (`""`).
- **Scelta di porta e candidato** (`:161-203`): non usa `bottega.toml` ne `scelta.scegli`; richiede `--porta` e
  `--modello` espliciti (salvo `--risposte`), istanziando `porta_fabbrica(nome_porta)` (`:191`) se non iniettata.
- **Formato dell'uscita** (`:76-77,216-232`): stampa una riga per ogni divergenza
  `"{caso.id}: scelta {caso.scelta.strip()}, risposta {risp_str}"` (`"—"` se mancante) e infine
  `f"accordo: {accordi} su {totale}"`. Con `--pr N`, pubblica lo stesso testo come commento sulla PR `#N` con
  `ruolo="consigliere"`.
- **Granularita del lancio** (`banco.py:185-203`, `casi.py:342-354`): **1 solo lancio per l'intero foglio**
  (`_foglio(casi_scelti)` dentro `prompt_del_banco` passato a un unico `p.lancia(..., sola_lettura=True)`).

## D12 — Fake e suite di test (`attrezzi/tests/`)

- **`lancio`**:
  - `attrezzi/tests/test_lancio_b9.py`: board fake `FintaBoard` (`:44`), `BoardCheSbaglia` (`:647`); finti `gh`
    `FintoEsecutore` (`:24`) e helper locali `esegui_rosso` (`:494`), `esegui_errore_passo` (`:653`),
    `esegui` (`:726,:760`); nessuna `ForgiaFinta`.
  - `attrezzi/tests/test_misure_perse_b10.py`: board fake `BoardSequenza` (`:243`), `BoardSenzaElenco` (`:50`),
    `BoardLetturaRotta` (`:68`), `BoardContata` (`:78`), `BoardTokenRotto` (`:90`); finti `gh`/forgia
    `EsecutoreFinto` (`:219`), `ForgiaFinta` (`:42-43`), `ForgiaRotta` (`:99`).
- **`segno`**:
  - `attrezzi/tests/test_segno.py`: `BoardFinta` (`attrezzi/bottega/finta.py:206`), fixture `isola_ambiente`
    (`:24-40`), nessuna forgia.
  - `attrezzi/tests/test_misure_completo.py`: `BoardFinta` (`:27,263`) e `ForgiaFinta` (`:27,260`). (I test di
    `trascrizione`/`token` stanno in `attrezzi/tests/test_trascrizioni.py` con `isola_ambiente`, `:18-35`).
- **`misura`**:
  - `attrezzi/tests/test_misura.py`: `BoardFinta` (`:5,38`); nessuna forgia.
  - `attrezzi/tests/test_misure.py`: `BoardFinta` (`:9,101`), `BoardRotta` (`:117`); nessuna forgia.
  - `attrezzi/tests/test_misure_completo.py`: `BoardFinta` e `ForgiaFinta` (`:27,260,263`). (I test di
    `_scrivi_misure` in `giro.py` stanno in `attrezzi/tests/test_giro_misure.py` con `BoardFinta` e `ForgiaFinta`
    a `:13,146-147`).
- **`distributore`**:
  - `attrezzi/tests/test_distributore.py`: `BoardFinta` (`:14`), `ForgiaFinta` (`:14`), `ForgiaCheCade` (`:1792`);
    `test_rv18_comando_distribuisci_shlex_split` patcha `BoardComando.__init__` (`:891-897`).
  - Richiamato anche in `attrezzi/tests/test_giro_completo.py` (`BoardFinta`, `ForgiaFinta`, `:26`),
    `attrezzi/tests/test_b11_veloce.py` (`BoardFinta`, `ForgiaFinta`, `:15,54,71`) e `test_misure_completo.py`.
    (`attrezzi/tests/test_chiusi_b9.py` usa `BoardProject`/`BoardComando` con `esegui_finto` a `:111,227`).
- **`conti`**:
  - `attrezzi/tests/test_conti.py`: `BoardFinta` (`:12,196`); nessuna forgia.
  - `attrezzi/tests/test_misure_completo.py`: `BoardFinta` e `ForgiaFinta` (`:260,263`).
- **Sentinella globale**: tutti i test usano la fixture autouse `_spegni_sentinella_rete` in
  `attrezzi/tests/conftest.py:7-10`.
