# Ricognizione B12.0: quote, riserva e livelli

Data: 2026-11-14.
Scopo: fotografare lo stato attuale di quote per bottega, scelta viva, passaggio del modello e del livello alle porte, misure, quaderni, comportamento della CLI `agy`, prove e documenti prima di scrivere il piano per B12.

---

## A. La configurazione (`attrezzi/bottega/configurazione.py`)

### 1. `Bottega`, `Candidato`, chiavi ammesse e chiavi sconosciute

- `attrezzi/bottega/configurazione.py:48-55` — `Bottega` è una `dataclass` con tre campi: `id: str`, `quota: str`, `porte: tuple[str, ...]`.
- `attrezzi/bottega/configurazione.py:57-68` — `Candidato` è una `dataclass` con sette campi: `id: str`, `nome: str`, `bottega: str`, `porta: str`, `modello: str`, `funzioni: tuple[str, ...]`, `runner: str | None`.
- `attrezzi/bottega/configurazione.py:24-27` — le chiavi ammesse sono costanti di modulo:
  - `_CHIAVI_TOP = ("versione", "progetto", "botteghe", "candidati")` (`configurazione.py:24`);
  - `_CHIAVI_PROGETTO = ("comandanti", "adattatore", "fuso", "notte", "manutenzione", "project", "liberi", "costituzione")` (`configurazione.py:25`);
  - `_CHIAVI_BOTTEGA = ("quota", "porte")` (`configurazione.py:26`);
  - `_CHIAVI_CANDIDATO = ("nome", "bottega", "porta", "modello", "funzioni", "runner")` (`configurazione.py:27`).
- `attrezzi/bottega/configurazione.py:20-22` — i valori ammessi per porte, funzioni e quote sono `PORTE = ("claude-code", "antigravity", "pi", "copilot-cli")`, `FUNZIONI = ("decidere", "eseguire", "rivedere", "consigliare")`, `QUOTE = ("scarsa", "normale", "abbondante")`.
- `attrezzi/bottega/configurazione.py:520-523` — `_sconosciute(tabella, ammesse, percorso, errori)` scorre le chiavi di `tabella` e per ciascuna chiave assente da `ammesse` chiama `_errore(errori, _completa(percorso, chiave), "chiave sconosciuta")`.
- `attrezzi/bottega/configurazione.py:189,233,269,295` — `_sconosciute` è chiamata a livello radice in `_valida` (`:189`), su `[progetto]` in `_progetto` (`:233`), su ogni `[botteghe.<id>]` in `_botteghe` (`:269`) e su ogni `[candidati.<id>]` in `_candidati` (`:295`).
- `attrezzi/bottega/configurazione.py:18,542-543` — `_errore` aggiunge stringhe nel formato `f"{PREFISSO}: {percorso}: {motivo}"` con `PREFISSO = "bottega.toml"`.

### 2. Validazione di `Bottega.quota` e suoi usi nel pacchetto

- `attrezzi/bottega/configurazione.py:22,259-274` — in `_botteghe`, la riga `:270` valida `quota` chiamando `_scelta(corpo, "quota", percorso, QUOTE, "quota", errori)`.
- `attrezzi/bottega/configurazione.py:432-445` — `_scelta` richiede che la chiave sia presente come stringa non vuota appartenente a `QUOTE = ("scarsa", "normale", "abbondante")`.
- `attrezzi/bottega/scelta.py:424-425` — unico uso di `Bottega.quota` in tutto `attrezzi/bottega/`: dentro `_scegli_per_costo_atteso`, legge `bottega = configurazione.botteghe[c.bottega]` e ricava `peso_quota = PESI_QUOTA.get(bottega.quota, 1.0)`.

---

## B. La quota (`attrezzi/bottega/quota.py` e chi lo usa)

### 3. Chiamate a `nome_variabile`, `disponibile`, `valore_esaurita`, `imposta_variabile` in `attrezzi/bottega/`

Definizioni e firme in `attrezzi/bottega/quota.py`:
- `attrezzi/bottega/quota.py:10-16` — `PREFISSO_QUOTA = "BOTTEGA_QUOTA_"` e `nome_variabile(id_bottega)` restituisce `f"{PREFISSO_QUOTA}{id_bottega.upper().replace('-', '_')}"`.
- `attrezzi/bottega/quota.py:11,19-23` — `TESTO_ESAURITA = "esaurita fino a "` e `valore_esaurita(fino_a)` (richiede `tzinfo`) restituisce `f"{TESTO_ESAURITA}{fino_a.isoformat()}"`.
- `attrezzi/bottega/quota.py:26-52` — `disponibile(valore, adesso)` (richiede `tzinfo` su `adesso`) restituisce `(True, None)` se `valore` è `None`/vuoto o `adesso >= fino_a`, `(False, None)` se `adesso < fino_a`, `(True, avviso)` su valore non stringa, prefisso ignoto, data non ISO o senza fuso.

Chi legge e chi scrive:
- `attrezzi/bottega/scelta.py:257-263` (`comando_scegli`) — legge `quote_map` passato da CLI (`--quote`), cercando per `b_id` o `nome_variabile(b_id)` per ogni `b_id` di `configurazione.botteghe`, e chiama `disponibile(valore, adesso)` per stampare eventuali avvisi su stderr.
- `attrezzi/bottega/scelta.py:358-364` (`_avvisi_quote`) — legge `quote.get(b_id)` o `quote.get(nome_variabile(b_id))` per ogni bottega di `configurazione.botteghe` e chiama `disponibile(valore, adesso)`.
- `attrezzi/bottega/scelta.py:483-487` (`_ha_quota`) — legge `quote.get(c.bottega)` o `quote.get(nome_variabile(c.bottega))` per la bottega del candidato `c` e chiama `disponibile(valore, adesso)`.
- `attrezzi/bottega/distributore.py:611-617` (`comando_distribuisci`) — legge l'intero JSON da `os.environ.get("BOTTEGA_VARIABILI")` (passato dai workflow GitHub Actions come `${{ toJSON(vars) }}`, `.github/workflows/distributore.yml:63`) e passa il dizionario come `variabili` a `distribuisci`, che lo gira come `quote` a `_gestisci_evento_commento` (`distributore.py:402` → `:257`) e a `scegli` (`distributore.py:531`).
- `attrezzi/bottega/dividi.py:245-251` (`dividi`) — legge per ogni `b_id` in `cfg.botteghe` `forgia.variabile(nome_variabile(b_id))` (con ripiego su `os.environ.get(var_quota)`) e passa la mappa a `scegli` (`:260`).
- `attrezzi/bottega/giro.py:1345` (consulto nel giro) — legge per ogni `b_id` in `configurazione.botteghe` `forgia.variabile(nome_variabile(b_id))` e lo passa a `scegli` (`:1351`).
- `attrezzi/bottega/giro.py:1743` (rilettura del consigliere nel giro) — legge per ogni `b_id` in `configurazione.botteghe` `forgia.variabile(nome_variabile(b_id))` e lo passa a `scegli` (`:1749`).
- `attrezzi/bottega/giro.py:1399` (consulto fallito per quota) — **scrive** `forgia.imposta_variabile(nome_variabile(cand_cons.bottega), valore_esaurita(rinnovo_cons))` usando l'id della bottega del consigliere scelto (`cand_cons.bottega`).
- `attrezzi/bottega/giro.py:1441-1442` (esecutore uscito con `esito == "quota"`) — **scrive** `var_quota = nome_variabile(bottega_cfg.id)` e `forgia.imposta_variabile(var_quota, valore_esaurita(rinnovo))` usando `bottega_cfg.id` (la bottega dell'esecutore).
- `attrezzi/bottega/forgia.py:68,223` — definisce il protocollo `Forgia.imposta_variabile` e l'attuazione su `gh variable set` (`ForgiaGh.imposta_variabile`).
- `attrezzi/bottega/finta.py:114-116` — attuazione in memoria `ForgiaFinta.imposta_variabile`.

### 4. Comportamento in `giro.py` su esito `quota` dell'esecutore e del consigliere

**Esecutore con `lancio.esito == "quota"` (`attrezzi/bottega/giro.py:1434-1498`):**
- `attrezzi/bottega/giro.py:1434` — `_committa_lavoro_pendente` committa prima eventuali modifiche rimaste non committate nella cartella di lavoro.
- `attrezzi/bottega/giro.py:1438-1440` — durata dell'esaurimento: `rinnovo = lancio.rinnovo or (adesso + timedelta(hours=1))` (un'ora di default quando la porta lascia `rinnovo=None`, come fanno `antigravity.py:119`, `pi.py:119`, `copilot_cli.py:147`).
- `attrezzi/bottega/giro.py:1441-1442` — scrive la variabile `BOTTEGA_QUOTA_<ID>` (`nome_variabile(bottega_cfg.id)`) con `valore_esaurita(rinnovo)`.
- `attrezzi/bottega/giro.py:1453-1482` — se ci sono commit oltre `base_commit`, consegna il bundle con `_verifica_e_consegna_bundle` e apre una PR in bozza se non esiste (`"Salvataggio parziale per quota esaurita."`).
- `attrezzi/bottega/giro.py:1484-1498` — non tocca `attese` né `tentativi`; salva `d_nota["conversazione"] = lancio.conversazione` se presente e incrementa `d_nota["quote"]` (`:1489-1490`).
  - Se `quote >= 3`: imposta `d_nota["motivo"] = "quota ripetuta"`, porta il lavoro a `"bloccato"`, chiama `_rilancia_distributore` e torna `EsitoGiro("bloccato", motivo="quota ripetuta")` (`:1491-1494`).
  - Altrimenti (`quote < 3`): riporta il lavoro a `"pronto"`, chiama `_rilancia_distributore` e torna `EsitoGiro("quota", motivo="quota esaurita")` (`:1495-1498`).
- **Cambio esecutore al giro dopo:** `giro.py:1437-1498` non imposta `d_nota["precedente"]` (`precedente` viene scritto solo a `giro.py:1811` quando una sotto-issue finisce e ne resta un'altra). Quindi su un compito singolo o alla prima sotto-issue (`precedente is None`), il giro successivo di `distribuisci` (`distributore.py:513-535`) sceglie subito un altro candidato idoneo con quota tramite `_scegli_per_costo_atteso`. Se `precedente` era già nella nota da una sotto-issue precedente, `_scegli_per_precedente` (`scelta.py:384-406`) al primo passaggio (`giri_in_attesa < 1`) restituisce attesa e `distributore.py:538-541` incrementa `attese`; al passaggio dopo (`giri_in_attesa >= 1`), `scelta.py:123-125` scarta `compito.precedente` e assegna un altro esecutore con quota.

**Consigliere con `esito == "quota"`:**
- **Consulto (`attrezzi/bottega/giro.py:1395-1403`):** calcola `rinnovo_cons = lancio_cons.rinnovo or (adesso + timedelta(hours=1))`, scrive `forgia.imposta_variabile(nome_variabile(cand_cons.bottega), valore_esaurita(rinnovo_cons))`, imposta `d_nota["motivo"] = "quota"`, mette il lavoro in `"in attesa"` sulla board, chiama `_rilancia_distributore` e torna `EsitoGiro("in_attesa", motivo="quota")`. Non incrementa `quote` né `tentativi`.
- **Rilettura a fine compito (`attrezzi/bottega/giro.py:1764-1775`):** per qualsiasi `lancio_rev.esito != "fatto"` (incluso `"quota"`), non scrive alcuna variabile di quota e non blocca la consegna: aggiunge solo il commento `"compito senza rilettura"` sulla PR (`:1774-1775`).
- **`/bottega consulta` in `distributore.py:333-360`:** su `lancio.esito != "fatto"` scrive il commento `"Errore consulto ({lancio.esito}): ..."` senza aggiornare variabili di quota.

### 5. Variabili della quota in `installa.py`, `progetto.py`, `lancio.py`, `conti.py`, `distributore.py`

- `installa.py`, `progetto.py`, `lancio.py`, `conti.py` — nessuno di questi moduli crea, legge o mostra le variabili `BOTTEGA_QUOTA_*`.
- `attrezzi/bottega/distributore.py:611-617` (`comando_distribuisci`) — non crea né mostra variabili di quota; legge `BOTTEGA_VARIABILI` dall'ambiente (JSON delle variabili repository) e le passa a `distribuisci` per l'uso in `scegli` (`:402`, `:531`).

---

## C. La scelta viva (`attrezzi/bottega/scelta.py`)

### 6. Percorso passo per passo di `scegli`

- `attrezzi/bottega/scelta.py:27-31` — pesi di quota: `PESI_QUOTA = {"scarsa": 1.0, "normale": 0.25, "abbondante": 0.0}`.
- `attrezzi/bottega/scelta.py:64-85` — `scegli(...)` delega a `_scegli_senza_avvisi` (`:78`) e poi appende gli avvisi di quota tramite `_con_avvisi` (`:85` → `:368-381` → `_avvisi_quote` `:352-365`).

Sequenza in `_scegli_senza_avvisi` (`attrezzi/bottega/scelta.py:88-145`):
1. **Ricerca etichetta `esegue` (`:101-109`):** chiama `_ricava_esegue(compito)` (`:286-308`), che guarda `compito.esegue` e le etichette `esegue:<nome>`. Conflitto tra valori diversi → `Scelta(None, False, ...)` (`:102-107`). Se c'è `nome_esegue`, delega a `_scegli_per_etichetta_esegue` (`:311-349`): cerca il candidato per `id` o per `nome`, verifica `_elegibile` e `_ha_quota`; se non c'è o non è idoneo dà `aspetta=False`, se non ha quota dà `aspetta=True`, altrimenti restituisce subito quel candidato.
2. **Precedente di sotto-issue (`:112-115`):** se `compito.precedente` è valorizzato e esiste in `configurazione.candidati`, chiama `_scegli_per_precedente` (`:384-406`): se `_elegibile` e `_ha_quota`, lo sceglie subito; se è idoneo ma senza quota e `compito.giri_in_attesa < 1`, restituisce `Scelta(None, True, ...)` (aspetta 1 giro).
3. **Filtro di eligibilità (`:118-121`):** costruisce `elegibili = [c for c in tutti if _elegibile(c, compito)]` (`_elegibile` a `:475-480`: `compito.funzione in c.funzioni` e, se `compito.fuori`, `c.runner is not None`). Se `elegibili` è vuota → `Scelta(None, False, ...)`.
4. **Esclusione di `precedente` dopo attesa (`:123-125`):** se `compito.precedente is not None and compito.giri_in_attesa >= 1`, toglie da `elegibili` il candidato `compito.precedente`.
5. **Filtro della quota (`:128-134`):** costruisce `con_quota = [c for c in elegibili if _ha_quota(c, quote, adesso)[0]]` (`_ha_quota` a `:483-487`). Se `con_quota` è vuota → `Scelta(None, True, ...)`.
6. **Campionamento e costo atteso (`:137-145` → `_scegli_per_costo_atteso` `:409-456`):** per ogni candidato in `con_quota`:
   - `_conteggia_risultati` (`:459-472`) somma i contatori `(u, cr, rf)` sulle etichette di `compito.etichette`, o su `"*"` se nessuna ha storia;
   - campiona `p = max(caso.betavariate(1.0 + u, 1.0 + cr + rf), 1e-9)` (`:421-423`);
   - calcola `peso_quota = PESI_QUOTA.get(bottega.quota, 1.0)` (`:424-425`), `c_proprio = costi_propri.get(c.id, 1.0)` (`:426`), `numeratore = costo_decisore + peso_quota * c_proprio` (`:427`), `costo = numeratore / p` (`:428`);
   - sceglie il candidato con `costo` minimo (`:435-445`).

### 7. Dove si colloca un filtro «riserva»

- `attrezzi/bottega/scelta.py:128-137` — subito **dopo** la costruzione e il controllo di non-vuotezza di `con_quota` (`:128-134`, filtro quota) e **prima** della chiamata a `_scegli_per_costo_atteso` (`:137`, campionamento e costo atteso).
- Restano a monte i due rami diretti dell'etichetta `esegue` (`:101-109`, `_scegli_per_etichetta_esegue`) e del `precedente` di sotto-issue (`:112-115`, `_scegli_per_precedente`).

### 8. Scelta del consigliere nel giro (`giro.py`)

- `attrezzi/bottega/giro.py:1344-1354` (consulto su richiesta dell'esecutore) — costruisce `Compito(funzione="consigliare", fuori=True)` e chiama `scegli(..., configurazione=_solo_runner(configurazione, candidato.runner), ...)` leggendo le quote di tutte le botteghe (`:1345`).
- `attrezzi/bottega/giro.py:1742-1752` (rilettura a fine esecuzione) — costruisce `Compito(funzione="consigliare", fuori=True)` e chiama `scegli(..., configurazione=_solo_runner(configurazione, candidato.runner), ...)`.
- `attrezzi/bottega/giro.py:332-335` — `_solo_runner(configurazione, runner)` restituisce una copia di `Configurazione` con i soli candidati per cui `runner is not None and c.runner == runner`, cioè sulla stessa macchina/runner dell'esecutore.

---

## D. Il modello e il livello

### 9. Come il giro (e gli altri comandi) passa `modello` alla porta

- `attrezzi/bottega/giro.py:312-329,981` — `_trova_candidato(lavoro, bottega, configurazione, board)` cerca tra i candidati di `bottega_id` con `"eseguire"` nelle `funzioni` quello che corrisponde per `id` o `nome` a `lav.esecutore` (con ripiego al primo candidato `"eseguire"` della bottega).
- `attrezzi/bottega/giro.py:1323` — lancia l'esecutore con `porta_esecutore.lancia(..., modello=candidato.modello, ...)`.
- `attrezzi/bottega/giro.py:1386,1767` — nei due lanci del consigliere (consulto e rilettura) prende `cand_cons = configurazione.candidati[scelta_cons.candidato]` e passa `modello=cand_cons.modello`.
- `attrezzi/bottega/distributore.py:336` (`/bottega consulta`) e `attrezzi/bottega/dividi.py:274` (`dividi`) — passano analogamente `modello=cand.modello` dal candidato scelto con `scegli`.

### 10. Comando costruito dalle quattro porte e concetto di livello/`effort`

- `attrezzi/bottega/porte/__init__.py:77-89` — l'interfaccia `Porta.lancia` non ha nessun parametro per livello o `effort`. Nessun file in `attrezzi/bottega/porte/*.py` contiene riferimenti a livello, `effort` o `thinking` (nel pacchetto `thinking_tokens` compare solo in `attrezzi/bottega/misure.py:181` per il conteggio dei token Antigravity).
- `attrezzi/bottega/porte/antigravity.py:40-46` — costruisce `[self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]` più `--conversation <id>` oppure `--mode plan` (sola lettura) / `--dangerously-skip-permissions`.
- `attrezzi/bottega/porte/claude_code.py:96-102` — costruisce `[self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]` più `--resume <id>` oppure `--permission-mode plan` / `--dangerously-skip-permissions`.
- `attrezzi/bottega/porte/copilot_cli.py:41-47` — costruisce `[self.eseguibile, "-p", prompt, "--model", modello, "--output-format", "json"]` più `--resume <id>` oppure `--available-tools view,grep,glob --allow-tool view,grep,glob` / `--allow-all-tools`.
- `attrezzi/bottega/porte/pi.py:41-45` — costruisce `[self.eseguibile, "--mode", "json", prompt, "--model", modello]` più `--session <id>` oppure `--tools read,grep,find,ls` (sola lettura).

### 11. Lettura di etichette e campi del corpo dell'issue; dove leggere un «livello»

- `attrezzi/bottega/board.py:413-414` — `BoardProject` legge le prime 20 etichette GraphQL (`labels(first: 20)`) in `Lavoro.etichette`.
- `attrezzi/bottega/forgia.py:129,159` — `ForgiaGh` popola `Issue.etichette` quando legge un'issue o una sotto-issue.
- `attrezzi/bottega/distributore.py:110-121,470-482,522` — `distribuisci` controlla `lav.etichette` per le etichette note (`bottega: fuori`), estrae `fatto_quando(iss.corpo)` e passa `etichette=frozenset(lav.etichette)` dentro `Compito` a `scegli` (`scelta.py:290-294` legge `esegue:`).
- `attrezzi/bottega/brief.py:6-45` — contiene i lettori di sezioni del corpo (`fatto_quando(corpo)` legge `## Fatto quando`).
- `attrezzi/bottega/giro.py:1029,1043,1046,1087` — `giro` legge `iss_madre` (`:1029`), individua `compito` con le sue etichette e corpo (`:1043` / `:1046`) ed estrae `cmd_fatto_quando = fatto_quando(compito.corpo)` (`:1087`), prima di `_prepara_fascicolo` (`:1243`) e `porta_esecutore.lancia` (`:1320`), per poi scrivere i campi a fine giro in `_scrivi_misure` (`:1847`).
- **Dove può essere letto un «livello»:**
  - come parser di sezione del corpo in `attrezzi/bottega/brief.py` (accanto a `fatto_quando`, `:6-45`);
  - nel giro in `attrezzi/bottega/giro.py` dopo l'individuazione di `compito` (`:1043-1047`) / accanto a `fatto_quando(compito.corpo)` (`:1087`), prima di `porta_esecutore.lancia` (`:1320`) e di `_scrivi_misure` (`:1847`).

### 12. Misure: campi attuali, scrittura di esecutore e modello

- `attrezzi/bottega/misure.py:18-35` — `CAMPI` definisce oggi 16 campi di misura: `Porta`, `Dove`, `Durata`, `Giri`, `Consulti`, `Token esecutore`, `Token di chi decide`, `Segno`, `Misure parziali`, `Misurato da`, `Esito del compito`, `Rilievi del piano`, `Rilievi del brief`, `Rilievi dell'esecuzione`, `Consigli accolti`, `Consigli respinti`.
- `attrezzi/bottega/progetto.py:19-32` — `CAMPI_DEL_PROJECT` aggiunge a quelli i 4 campi base di `_CAMPI_B3` (`Bottega`, `Esito`, `Esecutore`, `Nota del giro`), per un totale di 20 campi nel Project (`board.py:384` verifica i 4 campi base obbligatori, `:438,441` popola `Lavoro.esecutore` e `Lavoro.campi`).
- Scrittura di `Esecutore` e `Misurato da`:
  - `attrezzi/bottega/board.py:484` — `BoardProject.prendi` scrive il campo `"Esecutore"` (`cand.nome`, passato da `distributore.py:568`);
  - `attrezzi/bottega/giro.py:585,600` — `_scrivi_misure` scrive `"Misurato da"` (`candidato.id`, `:585`), `"Esecutore"` (`candidato.nome`), `"Porta"` (`candidato.porta`) e `"Dove"` (`"fuori"`, `:600`).
  - `attrezzi/bottega/misure.py:112,147` e `attrezzi/bottega/conti.py:111` — leggono il campo `"Esecutore"` (con ripiego a `lavoro.esecutore`) per attribuire risultati e conti per candidato.
- Scrittura del modello: **non esiste** nessun campo `"Modello"` (né in `misure.py`, né in `misura.py`, né in `progetto.py`, né in `board.py`, né in `conti.py`).

### 13. Il quaderno del modello (`giro.py`)

- `attrezzi/bottega/giro.py:689-709` — `_prepara_fascicolo` calcola `modello_slug = re.sub(r"[^a-z0-9]+", "-", candidato.modello.lower()).strip("-")` e cerca il quaderno in due posti: `BOTTEGA_CLONE / "quaderni" / f"{modello_slug}.md"` (nel repo centrale) o via `git show origin/<ramo_principale>:.github/bottega/quaderni/{modello_slug}.md` (nel repo del progetto).
- `quaderni/` nel repo oggi contiene: `LEGGIMI.md`, `claude-haiku-5-5.md`, `claude-sonnet-5-5.md`, `gemini-3-8-flash-high.md`, `gemini-4-argon-high.md`.
- Con un modello il cui nome cambia col livello (es. `gemini-4-hydrogen-high` contro `gemini-4-hydrogen-xhigh`), `modello_slug` produce due file distinti (`gemini-4-hydrogen-high.md` vs `gemini-4-hydrogen-xhigh.md`), quindi non condivide il quaderno se il campo `candidato.modello` incorpora il suffisso del livello; con il nome senza livello (`gemini-4-hydrogen`), `modello_slug` punta invece sempre a `gemini-4-hydrogen.md` e ignora eventuali quaderni già salvati col suffisso del livello.

---

## E. La CLI di Antigravity (comando `agy`)

### 14. Output di `agy --help` (su `--model` ed `--effort`) e `agy models`

Righe di `agy --help`:
```text
  --effort                        Reasoning effort for the current CLI session (low|medium|high|xhigh|max)
  --model                         Model for the current CLI session
```

Elenco completo restituito da `agy models` (18 voci):
```text
gemini-4-argon-medium           Gemini 4 Argon (Medium)
gemini-4-argon-high             Gemini 4 Argon (High)
gemini-4-argon-low              Gemini 4 Argon (Low)
gemini-4-hydrogen-high          Gemini 4 Hydrogen (High)
gemini-4-hydrogen-xhigh         Gemini 4 Hydrogen (XHigh)
gemini-4-hydrogen-medium        Gemini 4 Hydrogen (Medium)
gemini-4-hydrogen-low           Gemini 4 Hydrogen (Low)
gemini-pro-orchestrator-g1-pro  Orchestrator (Argon)
gemini-3.8-flash-high           Gemini 3.8 Flash (High)
gemini-3.8-flash-medium         Gemini 3.8 Flash (Medium)
gemini-3.8-flash-low            Gemini 3.8 Flash (Low)
claude-opus-5-5-low             Claude Opus 5.5 (Low)
claude-opus-5-5-medium          Claude Opus 5.5 (Medium)
claude-opus-5-5-high            Claude Opus 5.5 (High)
claude-sonnet-5-5-low           Claude Sonnet 5.5 (Low)
claude-sonnet-5-5-medium        Claude Sonnet 5.5 (Medium)
claude-sonnet-5-5-high          Claude Sonnet 5.5 (High)
gpt-oss-120b-medium             GPT-OSS 120B (Medium)
```

### 15. Esito delle tre prove con `agy`

1. `agy -p "Rispondi solo: ok" --model gemini-4-hydrogen-high --effort xhigh --output-format json` (exit code `1`):
   - `status`: `"ERROR"`
   - `error`: `"invalid model selection (--model \"gemini-4-hydrogen-high\" --effort \"xhigh\"): --model gemini-4-hydrogen-high conflicts with --effort=xhigh"`
   - token: `input_tokens: 0`, `output_tokens: 0`, `thinking_tokens: 0`, `cache_read_tokens: 0`, `total_tokens: 0`
   - Esito: `--model` con livello nel nome è rifiutato se `--effort` specifica un livello diverso; fallisce prima di chiamare il modello.
2. `agy -p "Rispondi solo: ok" --model gemini-4-hydrogen --effort xhigh --output-format json` (exit code `0`):
   - `status`: `"SUCCESS"`, nessun `error`, `response`: `"ok\n"`
   - token: `input_tokens: 13305`, `output_tokens: 708`, `thinking_tokens: 703`, `cache_read_tokens: 0`, `total_tokens: 14013`
3. `agy -p "Rispondi solo: ok" --model gemini-4-hydrogen --output-format json` (exit code `0`):
   - `status`: `"SUCCESS"`, nessun `error`, `response`: `"ok\n"`
   - token: `input_tokens: 13302`, `output_tokens: 36`, `thinking_tokens: 31`, `cache_read_tokens: 0`, `total_tokens: 13338`
   - Conclusione dalle prove 2 e 3: il nome base `gemini-4-hydrogen` (pur non comparendo in `agy models`) è accettato sia da solo sia con `--effort xhigh`, e `--effort xhigh` alza `thinking_tokens` (703 contro 31).

---

## F. Le prove e i documenti

### 16. Copertura in `attrezzi/tests/`, finti per le porte e simulazione di un 429

File di test per area:
- **Configurazione:** `attrezzi/tests/test_configurazione.py`.
- **Quota:** `attrezzi/tests/test_quota.py` (copre `nome_variabile`, `valore_esaurita`, `disponibile`).
- **Scelta viva:** `attrezzi/tests/test_scelta.py` (proprietà Hypothesis, `precedente` senza quota, `PESI_QUOTA`, CLI `scegli`); integrazione in `attrezzi/tests/test_distributore.py:312-405,1221-1245` (`BOTTEGA_QUOTA_*` e azzeramento `quote` su `/bottega riprova`).
- **Giro con esito `quota`:** `attrezzi/tests/test_giro.py:289-335,1205-1239,1945-1985,2685-2718,3163-3233` (`BOTTEGA_QUOTA_PRINCIPALE`, commit pendente, PR in bozza, 3× quota → `motivo="quota ripetuta"`), `attrezzi/tests/test_giro_completo.py:447-468`, `attrezzi/tests/test_giro_misure.py:205-297`.
- **Porte:** `attrezzi/tests/test_porte.py`.
- **Misure e conti:** `attrezzi/tests/test_misura.py`, `attrezzi/tests/test_misure.py`, `attrezzi/tests/test_misure_completo.py`, `attrezzi/tests/test_misure_perse_b10.py`, `attrezzi/tests/test_giro_misure.py`, `attrezzi/tests/test_conti.py`.

Finti per le porte e simulazione di un 429:
- `attrezzi/bottega/finta.py` — contiene solo `ForgiaFinta` e `BoardFinta`; **non esiste nessuna `PortaFinta` condivisa**.
- Classi locali `PortaFinta`, `PortaFintaCompleta` o `PortaFintaCons` sono ridefinite in ciascun file di test: `test_giro.py:20`, `test_giro_b6.py:21`, `test_giro_b9.py:24`, `test_giro_completo.py:34`, `test_giro_misure.py:19`, `test_pulizia_b7.py:19`, `test_sentinella_b8.py:18`, `test_b8_punti.py:45`, `test_banco.py:21`, `test_dividi.py:14`, `test_misure_completo.py:38`, `test_distributore.py:764,1014,...`. Tutte restituiscono direttamente `Lancio(esito="quota", ...)` da callback o configurazione (senza passare da stdout CLI).
- `attrezzi/tests/test_porte.py:384-390,533-539,644-650,755-761,917-992` — usa finti eseguibili Python generati con `_crea_script_finto` e passati tramite `eseguibile=str(script)` per simulare le risposte CLI reali:
  - Antigravity: stringa `"RESOURCE_EXHAUSTED: rate limit exceeded (429)"` (`test_porte.py:533`), campo intero `{"code": 429, "message": "Too Many Requests"}` (`test_porte.py:926`), o messaggio crediti AI (`test_porte.py:947`);
  - Pi: stringa `"Rate limit exceeded (429 quota)"` (`test_porte.py:644`) o intero `{"type": "error", "code": 429, "errorMessage": "Rate limit exceeded"}` (`test_porte.py:986`);
  - Claude Code: `"You've hit your session limit · resets 3:45pm"` (`test_porte.py:384`);
  - Copilot CLI: `"Quota exceeded..."` (`test_porte.py:755`).

### 17. Righe dei documenti su quota di una bottega, «una bottega per quota/gruppo» e modello del candidato

- `LEGGIMI.md:11-12` — definisce le **botteghe** come gli abbonamenti (`quante ne ha l'utente`); `LEGGIMI.md:14` parla della **scelta viva** sulla «quota del momento»; `LEGGIMI.md:24` cita «un quaderno per modello».
- `INSTALLA.md:34-36` — descrive cosa raccogliere in installazione: «le botteghe (una per abbonamento, o una per quota se l'abbonamento ne ha più d'una), i candidati (porte e modelli ...)» e gli annunci `«titolo + modello»`.
- `plugin/skills/bottega/SKILL.md:9` — definisce le botteghe come «gli **abbonamenti** dell'utente, ognuno con la sua quota».
- `plugin/skills/bottega/SKILL.md:25-27` — «Un abbonamento con più quote separate (Antigravity: una per gruppo di modelli) diventa una bottega per quota, con la stessa porta».
- `plugin/skills/bottega/SKILL.md:40-41` — definisce il candidato (porta + modello di una bottega; la skill non conosce alcun modello).
- `plugin/skills/bottega/SKILL.md:67-76` — spiega i valori di `quota` (`abbondante` ecc.) e la «quota del momento» salvata nelle variabili di GitHub Actions.
- `plugin/skills/bottega/SKILL.md:185` — vincola l'esecutore a usare sotto-agenti solo col suo modello.
- `plugin/skills/bottega/SKILL.md:219-221` — spiega i quaderni «uno per modello».
- `plugin/skills/bottega/porte/antigravity.md:18,33-38` — documenta `--model <nome>`, `--effort low|medium|high|xhigh|max`, e precisa che alla 1.5.8 «il livello sta nel nome: `gemini-3.8-flash-high`, `gemini-4-hydrogen-xhigh`, ecc.».
- `plugin/skills/bottega/porte/antigravity.md:53-58` — sezione Quote: spiega che Antigravity ha gruppi di quota separati e prescrive «Quindi in configurazione fai una bottega per gruppo, tutte con la porta `antigravity`: con una bottega sola, un 429 di un modello ferma anche i modelli degli altri gruppi».
- `plugin/skills/bottega/porte/claude-code.md:19,33` — documenta `--model <nome>`.
- `plugin/skills/bottega/porte/pi.md:19-20,32` — documenta `--model <provider/id>[:thinking]` e `--thinking off|minimal|low|medium|high|xhigh|max`.
- `plugin/skills/bottega/porte/copilot-cli.md:23,35` — documenta `--model <id>`.
- `plugin/skills/bottega/modelli/bottega.toml:17-20` — commento `# Un abbonamento con più quote separate (Antigravity: una per gruppo di modelli) si divide in una bottega per quota.` ed esempio `quota = "scarsa"`.
- `plugin/skills/bottega/modelli/bottega.toml:29,32,36,39` — esempi di `modello = "<modello forte>"` e `modello = "<modello economico>"` nei candidati.
- `docs/adattatore.md` — nessun riferimento alla quota di una bottega, a una bottega per quota/gruppo o al modello del candidato (`docs/adattatore.md:34-37` elenca solo i campi di misura del Project).
