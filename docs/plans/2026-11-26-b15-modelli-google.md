# B15: i modelli di novembre — scala, ritmo, categorie e piani di notte — piano

> **Per chi esegue:** si esegue col metodo della bottega (`plugin/skills/bottega/SKILL.md`), un compito alla volta o
> in parallelo dove i file sono disgiunti (tabella sotto). Nessuna scelta resta aperta: ogni valore, firma ed errore
> sta nei Ruling. I passi usano le caselle (`- [ ]`).

**Scopo:** usare la quota del fornitore abbondante al massimo senza sprechi e riservare la quota scarsa a chi decide:
piani in bozza di notte, scala automatica sui fallimenti, ritmo della quota sui riempitivi, passo finale «pronta per
l'unione» con categorie di rischio, e gli stessi controlli come comandi CLI usabili dagli script locali di sessione.

**Architettura:** nessun campo nuovo nel Project, nessun cambio al contratto dell'adattatore (`docs/adattatore.md`),
nessun cambio ai workflow di GitHub Actions (`.github/workflows/` e `progetto.py` restano intatti: `distributore.yml`
passa già tutte le variabili `vars` in `BOTTEGA_VARIABILI`, `esecutore.yml` può già scrivere variabili via `gh`, e
`Esito` ha già l'opzione `pronta per l'unione`). La logica vive in moduli puri e comandi CLI (`bottega categoria`,
`bottega ritmo`, `bottega scala`) condivisi tra sessione (Parte A) e plugin automatico (Parte B).

**Strumenti:** Python ≥ 3.11, sola libreria standard nel pacchetto; `pytest` e Hypothesis nelle prove.

**Disegno:** `docs/specs/2026-11-26-b15-modelli-google-design.md` (incluso §5.8). Parte da B14 (`v0.2.8`).

## Vincoli di tutta la tappa

- Costituzione del repo (`docs/costituzione.md`): italiano, righe fino a 120 colonne, niente di personale o di un
  progetto specifico nei file del repo (nessun percorso `/home/<utente>` reale, nessun nome di persona, casa, servizio
  o macchina).
- **Retrocompatibilità:** una configurazione scritta prima di B15 (senza `scala`, `aree_non_delicate`, `bozze_piano`,
  `[categorie]`, `[ritmo]` né funzione `pianificare`) resta valida e si comporta esattamente come in B14.
- `plugin/skills/bottega/SKILL.md`, le pagine `plugin/skills/bottega/porte/*.md` e i `modelli/*.md` **non contengono
  mai nomi di modello** (`attrezzi/tests/test_plugin.py`); i quaderni (`quaderni/*.md`) nominano il loro modello.
- `.github/` non si tocca. La pubblicazione (cambio versione, tag, spinta) **non** è un compito di questo piano.
- Le prove dei file toccati si lanciano in primo piano: `uv run pytest -q <file>…`.

## Le decisioni (Ruling)

- **B15-R1 Configurazione: `pianificare`, `scala`, `aree_non_delicate`, `bozze_piano` (`configurazione.py`).**
  - `FUNZIONI` diventa `("decidere", "eseguire", "rivedere", "consigliare", "pianificare")`.
  - `_CHIAVI_TOP` diventa `("versione", "progetto", "botteghe", "candidati", "categorie", "ritmo")`.
  - `_CHIAVI_PROGETTO` aggiunge `"scala"`, `"aree_non_delicate"`, `"bozze_piano"`.
  - Campi nuovi in coda a `Progetto` (con valori di serie per non rompere le costruzioni esistenti):
    `scala: tuple[str, ...] = ()`, `aree_non_delicate: tuple[str, ...] = ()`, `bozze_piano: int = 3`.
  - Costanti nuove: `BOZZE_PIANO_PREDEFINITE = 3`, `BOZZE_PIANO_MASSIME = 10`.
  - Validazione di `progetto.bozze_piano`: intero (`type(v) is int`, no `bool`) tra `0` e `10` compresi (`0` disattiva
    le bozze di piano notturne); errori su `progetto.bozze_piano` (`tipo sbagliato: serve un numero intero` oppure
    `fuori intervallo: <v> (serve da 0 a 10)`).
  - Validazione di `progetto.aree_non_delicate`: identica a `progetto.liberi` (lista di stringhe non vuote, senza
    duplicati case-insensitive; lista vuota valida).
  - Validazione di `progetto.scala` (eseguita in `_valida` dopo `_candidati`): facoltativa, lista di stringhe non
    vuote senza duplicati (lista vuota valida). Per ogni `scala[i]`: se l'id non è in `candidati` → errore su
    `progetto.scala[i]`: `candidato inesistente: «<id>»`; se presente ma `"eseguire"` non è nelle sue `funzioni` →
    errore su `progetto.scala[i]`: `il candidato «<id>» non ha la funzione «eseguire»`. Candidati con `riserva = true`
    o `su_richiesta = true` sono **ammessi** in `scala`.

- **B15-R2 Configurazione e classificazione `[categorie]` (`configurazione.py`, `categorie.py`).**
  - Sezione top-level facoltativa `[categorie]` in `bottega.toml`: mappa `<id_categoria> = ["<glob>", ...]`.
    Campo nuovo in coda a `Configurazione`: `categorie: dict[str, tuple[str, ...]] = field(default_factory=dict)`.
  - Validazione: `categorie` è una tabella; ogni chiave rispetta `_id` (`a-z`, `0-9`, `-`); ogni valore è una lista
    non vuota di stringhe non vuote, senza duplicati. Ogni modello glob: max 200 caratteri, non inizia con `/` né `-`,
    non contiene `..` tra i segmenti, non è `"**"` né `"**/*"` (errore `modello troppo largo: «<v>»`), solo caratteri
    in `[A-Za-z0-9._/*?-]`.
  - **Corrispondenza glob POSIX (`corrisponde_glob(percorso: str, modello: str) -> bool`):** normalizza `./` iniziali
    e separatori `/`; converte il glob in regex ancorata (`^…$`): `/**/` → `(?:/.*)?/` (zero o più cartelle), `**/` in
    testa → `(?:[^/]+/)*`, `/**` in coda → `/.*`, `**` residuo → `.*`, `*` → `[^/]*`, `?` → `[^/]`, resto `re.escape`.
    Esempio: `docs/**` prende `docs/a.md` e `docs/x/b.md`, mai `docs-altro/a.md` né `sub/docs/a.md`; `*.md` prende
    `LEGGIMI.md`, mai `docs/a.md`.
  - **Pavimento protetto (sempre delicato, anche se un glob lo coprisse):** ogni percorso il cui segmento/prefisso
    normalizzato tocca `.github/`, `.bottega/`, `.gitleaksignore`, `.gitleaks.toml` (o finisce con tali nomi) rende
    sempre la PR **delicata**.
  - **Classificazione (`classifica_diff`):**
    - Elenco `percorsi` vuoto → `delicata = True`, motivo `"nessun file nel diff"`.
    - Etichette PR che contengono (case-insensitive) `"bottega: prove cambiate"` o `"bottega: segreti"` → `delicata =
      True`, motivo con le etichette trovate.
    - Flag `sicurezza=True` (da `Verdetto.sicurezza`) → `delicata = True`, motivo `"segnalazione di sicurezza nella
      revisione"`.
    - Ogni percorso deve corrispondere ad almeno un glob di `categorie` e non ricadere nel pavimento protetto; basta
      un solo percorso fuori elenco per avere `delicata = True`, con `fuori_elenco` ordinato.
    - Se tutti i percorsi rientrano in `categorie` e nessun vincolo scatta → `delicata = False`, `categorie_toccate` è
      la tupla ordinata delle categorie colpite (es. `("documenti", "prove")`).

- **B15-R3 Tabella `[ritmo]`, formato punti di quota e soglie esatte (`configurazione.py`, `quota.py`, `ritmo.py`).**
  - Sezione top-level facoltativa `[ritmo]` in `bottega.toml`, rappresentata da:
    `Ritmo(gruppo: str | None = None, ritardo: int = 15, riserva_5h: int = 30, riserva_settimana: int = 15)`.
    Campo nuovo in coda a `Configurazione`: `ritmo: Ritmo = field(default_factory=Ritmo)`.
  - Validazione: `ritmo` è una tabella con chiavi ammesse `("gruppo", "ritardo", "riserva_5h", "riserva_settimana")`.
    `gruppo`: stringa non vuota facoltativa; `ritardo`: intero `1..99` (di serie `15`); `riserva_5h`: intero `0..100`
    (di serie `30`); `riserva_settimana`: intero `0..100` (di serie `15`). Booleani rifiutati.
  - **Soglie esatte di serie:**
    - `SOGLIA_RITARDO = 15` (punti percentuali di quota settimanale spesi in meno rispetto al tempo trascorso).
    - `RISERVA_CINQUE_ORE = 30` (punti percentuali minimi residui nella finestra di 5 ore per lanciare un riempitivo).
    - `RISERVA_SETTIMANA = 15` (punti percentuali minimi residui nella finestra settimanale).
    - `DURATA_SETTIMANA_S = 7 * 24 * 3600` (`604800`).
  - **Parser di `agy -p /quota` (`quota.py`):** accetta il formato non-TTY (TSV a 4 colonne):
    `<gruppo>\t<Weekly Limit Remaining|Five Hour Limit Remaining>\t<N>%\t<ISO 8601 UTC>`
    (es. `Gemini Models\tWeekly Limit Remaining\t86%\t2026-12-02T15:21:03Z`). Ignora righe vuote o d'intestazione
    (`Quota:`). Supporta anche righe separate da due o più spazi se la quarta colonna è data ISO/locale leggibile, ma
    il formato canonico salvato e letto è TSV.
  - **Variabile Actions per i punti (`quota.py`):** `nome_variabile_punti(id_bottega: str) -> str` restituisce
    `BOTTEGA_PUNTI_<BOTTEGA>` (es. `BOTTEGA_PUNTI_GOOGLE`). Valore JSON compatto:
    `{"rilevato": "<ISO UTC>", "gruppi": {"<gruppo>": {"settimana": 86, "rinnovo_settimana": "<ISO>", "cinque_ore": 47,
    "rinnovo_cinque_ore": "<ISO>"}}}`.
  - **Formula del ritmo (`valuta_ritmo` in `ritmo.py`):**
    - `EPOCH_SOGLIA = datetime(1970, 1, 2, tzinfo=timezone.utc)`: se `rinnovo_settimana <= EPOCH_SOGLIA` → finestra non
      ancora avviata (`lancia = False`, `ritardo = 0.0`, `motivo = "finestra settimanale non ancora avviata"`).
    - Se `adesso >= rinnovo_settimana` → `lancia = False`, `motivo = "rilevazione scaduta (rinnovo settimanale
      superato)"`.
    - `inizio_settimana = rinnovo_settimana - timedelta(days=7)`;
      `frazione_passata = max(0.0, min(1.0, (adesso - inizio_settimana).total_seconds() / 604800.0))`;
      `atteso_speso = frazione_passata * 100.0`; `speso = 100 - punto.settimana`;
      `ritardo = atteso_speso - speso`.
    - Finestra 5 ore effettiva: se `rinnovo_cinque_ore > EPOCH_SOGLIA` e `adesso >= rinnovo_cinque_ore` →
      `cinque_ore_effettiva = 100` (già rinnovata dopo la rilevazione); altrimenti `punto.cinque_ore`.
    - `lancia = (ritardo >= soglia_ritardo) and (cinque_ore_effettiva >= riserva_5h) and
      (punto.settimana >= riserva_settimana)`.
    - Motivi espliciti per ogni caso di stop: `"riserva cinque ore (<n>% < <soglia>%)"`,
      `"riserva settimanale (<n>% < <soglia>%)"`, `"quota in passo (ritardo <r> < <soglia>)"`.

- **B15-R4 Ordine e filtri dei riempitivi (`ritmo.py`).**
  - Etichette di esclusione fisse (case-insensitive): `ETICHETTE_ESCLUSE_RIEMPITIVI = frozenset({"attesa utente",
    "design", "delicato", "bottega: sospeso", "bottega: bozza di piano"})`.
  - Un lavoro è eleggibile come riempitivo solo se: aperto, `stato == "pronto"` (o `esito == "correzioni"` e
    `stato != "in corso"`), autore comandante (o proprietario), ha `## Fatto quando` valido, non ha alcuna etichetta
    in `ETICHETTE_ESCLUSE_RIEMPITIVI`, non ha `bottega: fuori` né `esegue:` (quelli vanno già come lavori ordinari), e
    ha almeno un'etichetta in `progetto.aree_non_delicate` (confronto case-insensitive). Se `aree_non_delicate` è vuota
    nessun riempitivo viene mai scelto.
  - **Quattro fasce di priorità** (`fascia_riempitivo(etichette) -> int`, 0 più alta):
    - Fascia `0` (debiti e bug): etichetta in `{"debito", "bug", "debt"}`.
    - Fascia `1` (prove mancanti): etichetta in `{"prove", "test", "tests", "copertura"}`.
    - Fascia `2` (documenti): etichetta in `{"docs", "documenti", "documentazione", "guida"}`.
    - Fascia `3` (altre aree non delicate configurate).
  - A parità di fascia vince il numero di issue più basso (`lav.numero` crescente).

- **B15-R5 Formato del verdetto del revisore (`categorie.py`).**
  - Il prompt di rilettura e di revisione finale chiede al modello di aprire la risposta con tre righe esatte:
    ```text
    VERDETTO: APPROVATO | RILIEVI_GRAVI | SICUREZZA
    GRAVI: <intero >= 0>
    MINORI: <intero >= 0>
    ```
  - `analizza_verdetto(testo: str) -> Verdetto` ignora righe dentro blocchi recintati (```` ``` ```` / `~~~`), toglie
    spazi e marcatori markdown in testa (`-`, `*`, `#`, `>`, `_`), confronta le chiavi senza badare alle maiuscole,
    accetta sia `RILIEVI_GRAVI` sia `RILIEVI GRAVI`.
  - Regole di coerenza (fail-closed):
    - Manca `VERDETTO:` o stato sconosciuto → `Verdetto(stato="non_valido", gravi=0, minori=0, sicurezza=False,
      valido=False)`.
    - `VERDETTO: APPROVATO` con `GRAVI > 0` → normalizzato a `stato="RILIEVI_GRAVI"`, `valido=True` (bloccante).
    - `VERDETTO: RILIEVI_GRAVI` senza riga `GRAVI:` → `gravi = 1`.
    - `VERDETTO: SICUREZZA` → `sicurezza = True`, `gravi = max(gravi_letti, 1)`.
  - Proprietà di `Verdetto`:
    - `approvato`: `valido and stato == "APPROVATO" and gravi == 0 and not sicurezza` (richiesto per `pronta per
      l'unione` e per `bottega categoria --verdetto`).
    - `bloccante`: `valido and (stato in ("RILIEVI_GRAVI", "SICUREZZA") or gravi > 0)` (usato nella rilettura di
      compito nel giro: non rompe i vecchi test con risposte a testo libero senza `VERDETTO:`, ma blocca sempre su
      rilievi gravi o sicurezza espliciti).

- **B15-R6 La scala sui fallimenti (`scelta.py`, `distributore.py`, `giro.py`).**
  - `EsitoScala(candidato: str | None, gradino: int | None, totale: int, aspetta: bool, esaurita: bool, perche: str)`.
  - `prossimo_gradino(scala: Sequence[str], indice: int, configurazione: Configurazione, quote: Mapping[str,
    str | None], adesso: datetime, *, fuori: bool = True) -> EsitoScala`:
    - Se `not scala` → `EsitoScala(None, None, 0, False, False, "nessuna scala configurata")`.
    - Se `indice < 0` → `ValueError`.
    - Cerca a partire da `indice` il primo `i` tale che `c = candidati[scala[i]]` rispetti `not fuori or c.runner`
      (ammette sia `c.riserva` sia `c.su_richiesta`). Se nessuno → `EsitoScala(None, None, len(scala), False, True,
      f"scala esaurita ({len(scala)} gradini): torna a chi decide")`.
    - Se `_ha_quota(c, quote, adesso)[0]` è falso → `EsitoScala(None, i, len(scala), True, False,
      f"aspetta: gradino {i + 1}/{len(scala)} («{c.id}») senza quota")`.
    - Altrimenti → `EsitoScala(c.id, i, len(scala), False, False, f"gradino {i + 1}/{len(scala)}: «{c.id}»")`.
  - **Interazione con `esegue:` e con la nota del giro:**
    - La nota porta `gradino=<intero 0-based>` (assente = 0).
    - Se il lavoro ha un'etichetta `esegue: <nome>`, `esegue:` vince sempre e la scala **non** scatta (restano i 3
      tentativi sul candidato forzato).
    - Senza `esegue:`, con `scala` configurata: al primo giro (`gradino` assente o `0`) la scelta viva sceglie come
      oggi (tipicamente `scala[0]`, unico normale); per `gradino > 0` il distributore usa `prossimo_gradino` invece
      di `precedente` e della scelta viva.
    - Nel giro, quando `scala` è configurata e il lavoro non ha `esegue:`, **un** tentativo per gradino sui fallimenti
      del modello (oracolo rosso, rilettura con `verdetto.bloccante`, esito modello diverso da `fatto`/`quota`, nessun
      commit, commit vuoto, eccezione nel giro): calcola `indice_corrente` (`int(d_nota["gradino"])` se presente,
      altrimenti `scala.index(candidato.id)` se `candidato.id in scala`, altrimenti `0`), pone `prossimo =
      indice_corrente + 1`. Se `prossimo >= len(scala)` → `bloccato` (`motivo = f"scala esaurita: {motivo}"`) con
      commento che rimanda a chi decide; altrimenti `d_nota["gradino"] = str(prossimo)`, rimuove `precedente`,
      `conversazione`, `consegnato` (lascia `rosso` se oracolo rosso), rimette `pronto` e rilancia il distributore.
    - Una quota esaurita (`esito == "quota"`) **non** sale di gradino; un errore prima del giro resta sui 3 tentativi.
    - `gradino` si azzera su `/bottega riprova`, al cambio sotto-issue e alla chiusura riuscita di una sotto-issue non
      ultima.

- **B15-R7 Nuovi comandi CLI (`__main__.py`, Parte A).**
  1. `bottega categoria [--file TOML] [--base RIF] [--ramo RIF] [--percorsi FILE] [--etichetta E ...] [--verdetto FILE]
     [--json]`:
     - Predefiniti: `--file .github/bottega/bottega.toml`, `--base origin/main`, `--ramo HEAD`.
     - `--percorsi FILE` (o `-` da stdin) è alternativo a `--base`/`--ramo`; senza `--percorsi` legge
       `git diff --raw -z -M --no-ext-diff <base>...<ramo>`.
     - Codici d'uscita: `0` = non delicata (e verdetto `APPROVATO` se `--verdetto` è dato); `1` = delicata (incluso
       `SICUREZZA` nel verdetto); `3` = non delicata ma `--verdetto` non approvato (`RILIEVI_GRAVI` o `non_valido`);
       `2` = errore di uso, configurazione, file mancante o git.
  2. `bottega ritmo [--file TOML] [--gruppo NOME] [--soglia-ritardo N] [--riserva-5h N] [--riserva-settimana N]
     [--da-quota FILE] [--proponi] [--repo REPO] [--json]`:
     - Senza `--da-quota`, lancia `agy -p /quota` con tetto 60 s; con `--da-quota -` legge stdin.
     - Codici d'uscita: `0` = quota indietro e sopra le riserve (lancia riempitivo; con `--proponi` stampa anche il
       primo riempitivo ammissibile `#N <titolo> [fascia <k>]` o `nessun riempitivo pronto`); `1` = quota in passo o
       sotto riserva o finestra non avviata/scaduta; `2` = errore (configurazione, porta, uscita illeggibile).
  3. `bottega scala [--file TOML] [--gradino N | --dopo ID] [--fuori] [--quote FILE] [--json]`:
     - `--gradino N` (predefinito `0`) e `--dopo ID` (cerca `scala.index(ID) + 1`, errore `2` se `ID` non è in `scala`)
       sono mutuamente esclusivi.
     - Codici d'uscita: `0` = candidato pronto (`<id>\t<modello>\t<perche>`); `1` = scala esaurita o nessuna scala
       (`esaurita\t\t<perche>`); `3` = aspetta quota (`aspetta\t\t<perche>`); `2` = errore di uso o configurazione.

- **B15-R8 Bozze di piano di notte (`distributore.py`, `giro.py`).**
  - Costante `ETICHETTA_BOZZA_PIANO = "bottega: bozza di piano"`.
  - Solo con `notte=True`, `cfg.progetto.bozze_piano > 0`, e almeno un candidato con `"pianificare"` e `runner`.
  - **Conteggio tetto:** lavori aperti in `lavori_elenco` con `ETICHETTA_BOZZA_PIANO` fra le etichette (senza badare
    alle maiuscole) OPPURE `nota(lav.nota).get("modo") == "pianifica"` e `lav.stato in ("in corso", "consegnato")`.
    Se il conteggio è `>= cfg.progetto.bozze_piano`, nessuna nuova pianificazione parte e si stampa
    `bozze di piano al tetto (<n>/<tetto>): nessuna nuova pianificazione`.
  - **Selezione nel distributore:** per un lavoro pronto (con `bottega: fuori` o etichetta in `liberi`), autore
    comandante, privo di `## Fatto quando`, senza sotto-issue aperte, senza `esegue:`, senza `attesa utente` e senza
    `ETICHETTA_BOZZA_PIANO`, in **qualsiasi** area (anche delicata): sceglie con `Compito(funzione="pianificare",
    fuori=True, etichette=...)`, prende il lavoro con `modo=pianifica` nella nota e avvia
    `bottega-esecutore-<bottega>.yml`.
  - **Esecuzione nel giro (`d_nota.get("modo") == "pianifica"`):**
    - Non richiede `## Fatto quando`.
    - Prompt dedicato: produrre solo la bozza di piano in `docs/plans/<YYYY-MM-DD>-issue-<numero>-bozza.md` (Scopo,
      Ruling proposti, Review Focus, Compiti con File/Interfacce/Prove/Fatto quando, righe ≤ 120), nessun file di
      codice.
    - **Controllo meccanico sul diff:** ogni percorso (`old_path` e `new_path`) di `entries` e `entries_storia` deve
      soddisfare `p.startswith("docs/plans/") and p.endswith(".md")`; se anche un solo file esce da `docs/plans/*.md`
      la consegna viene rifiutata (`bloccato`, `motivo = "bozza di piano fuori da docs/plans/"`).
    - Nessun oracolo e nessun passo finale «pronta per l'unione».
    - Apre (o aggiorna) la PR in bozza `Bozza di piano: <titolo>`, mette `ETICHETTA_BOZZA_PIANO` su PR e issue madre,
      segna `board.consegna(lavoro, pr=pr_num)` (lasciando `Esito` vuoto) e rilancia il distributore.

- **B15-R9 Passo finale «pronta per l'unione» e `Forgia.etichette_pr` (`forgia.py`, `finta.py`, `giro.py`).**
  - Nuovo metodo in `Forgia` (implementato in `ForgiaGh` con `gh pr view <n> --repo <repo> --json labels` e in
    `ForgiaFinta` su `self._pr[n].get("etichette", [])`): `etichette_pr(self, n: int) -> list[str]`.
  - Nel giro, quando `oracolo_ok` è vero, `ultima_sotto_issue` è vero, `modo != "pianifica"`, la rilettura di compito
    non ha bloccato, ed esiste almeno un candidato con `"rivedere"` sullo stesso `candidato.runner`:
    1. Calcola `merge_base` fra `refs/remotes/origin/<ramo_principale>` e `refs/heads/<nome_ramo>`, estrae tutti i
       percorsi toccati dal diff dell'intero ramo (`git diff --raw -z -M --no-ext-diff <merge_base> refs/heads/<ramo>`)
       e il diff testuale (troncato a 60 000 caratteri).
    2. Sceglie il revisore con `Compito(funzione="rivedere", fuori=True)` su `_solo_runner(cfg, candidato.runner)`.
       Se assente o `aspetta`: commenta sulla PR `revisione finale saltata: <perche>`, consegna senza `Esito`.
    3. **Riuso senza doppio costo:** se la rilettura di compito appena fatta ha usato esattamente lo stesso candidato
       (`cand_cons.id == cand_rev.id`) e `base_consegna == merge_base` (un solo compito sul ramo), riusa quel testo
       e quel `Verdetto` senza rilanciare il modello; altrimenti lancia `porta_rev.lancia(..., sola_lettura=True)` con
       il prompt col formato `VERDETTO:` / `GRAVI:` / `MINORI:`.
    4. Classifica il ramo con `classifica_diff(percorsi_ramo, cfg.categorie, etichette_pr=forgia.etichette_pr(pr_num),
       sicurezza=verdetto.sicurezza)`.
    5. Scrive il commento sulla PR con ruolo `"revisore"` riportando revisore, verdetto, conteggi gravi/minori,
       categoria (`non delicata (<cat…>)` o `delicata (<motivo>)`) e testo recintato.
    6. **Esiti:**
       - `verdetto.approvato`: chiude sotto-issue se presente, `board.consegna(lavoro, pr=pr_num)`,
         `board.campo(lavoro, "Esito", "pronta per l'unione")`, salva `categoria=non-delicata|delicata` e
         `revisore=<cand_rev.id>` in `Nota del giro`, aggiunge alla PR `bottega: non delicata` o `bottega: delicata`
         (rimuovendo l'opposta se presente).
       - `verdetto.sicurezza`: chiude sotto-issue se presente, `board.consegna(lavoro, pr=pr_num)` **senza** `Esito`,
         salva `categoria=delicata` e `motivo=sicurezza nella revisione finale`, mette `bottega: delicata` sulla PR.
       - `verdetto.bloccante` (non sicurezza): su lavoro a compito singolo (`not sotto_issues`) **non** consegna e
         applica la scala (`B15-R6`, `motivo = "rilievi gravi nella revisione"`); su lavoro a più sotto-issue consegna
         senza `Esito` con `motivo = "rilievi gravi nella revisione finale"`.
       - `not verdetto.valido`: fail-closed, consegna **senza** `Esito` e commenta
         `revisione finale con verdetto non leggibile: Esito non impostato`.

- **B15-R10 Punti di quota e misure per gradino (`porte/antigravity.py`, `misure.py`, `conti.py`, `giro.py`).**
  - `Antigravity.leggi_quota(self, prefisso: Sequence[str] = (), tempo: int | float = 60) -> dict[str, PuntoQuota] |
    None`: lancia `agy -p /quota` con `esegui_porta`, analizza con `quota.analizza_uscita_quota`; su errore dà `None`
    senza mai sollevare.
  - Nel giro (quando la porta ha `leggi_quota`): legge `punti_prima` prima del lancio e `punti_dopo` nel `finally`
    (prima della chiusura); se `punti_dopo` c'è, aggiorna `forgia.imposta_variabile(nome_variabile_punti(bottega),
    formatta_punti(punti_dopo, adesso))` catturando eventuali errori su stderr.
  - Stampa su stdout a fine giro la riga:
    `misura gradino: candidato=<id>; gradino=<k>/<n>; durata=<s>; token=<t>; punti_settimana=<ds>; punti_5h=<d5>;
    oracolo=<ok|rosso|->; rilievi_gravi=<g>; rilievi_minori=<m>; esito=<esito>`
    e aggiunge una riga di riepilogo nel commento di consegna sulla PR (o sul compito se manca la PR).
  - **Misure per gradino senza campi nuovi nel Project (`misure.py`, `conti.py`, `giro.py`):**
    - Quando `cfg.progetto.scala` è non vuota e `candidato.id in cfg.progetto.scala`, `_scrivi_misure` registra nel
      campo `Misure parziali` una voce `gradino:<id>:<esito_gradino>:<token>:<durata>` (dove `esito_gradino` è `ok`,
      `fallito` o `quota`) senza aggiungere `più esecutori`. Quando `scala` è vuota, resta intatto il comportamento
      B5/B14 (`più esecutori`).
    - `MisuraGradino(candidato_id: str, esito: str, token: int, durata: int)` e `gradini(lavoro: Lavoro) ->
      list[MisuraGradino]` in `misure.py`.
    - `misure.risultati(lavori, cfg)`: se un lavoro ha voci `gradino:` e `Esito del compito` è in `OPZIONI_ESITO`, ogni
      gradino con `esito == "fallito"` somma `1` a `corretti` del suo `candidato_id` (su `"*"` e sulle etichette), e
      l'ultimo gradino con `esito == "ok"` riceve l'esito finale del compito (`unito com'era` / `corretto` /
      `rifiutato`). I lavori con `più esecutori` senza voci `gradino:` restano esclusi come oggi.
    - `misure.costi_propri(lavori, cfg)`: se un lavoro ha voci `gradino:`, somma i `token` per ciascun `candidato_id`
      con `token > 0` (aggregando più giri dello stesso gradino sullo stesso compito in una sola osservazione).
    - `conti.conti(lavori)`: per i compiti con voci `gradino:`, conteggia ciascun gradino sotto il proprio candidato
      in `per_candidato` (durata, token, esiti).

- **B15-R11 Documenti, quaderni, pagina porta e guardia modelli (`plugin/`, `quaderni/`, `casistica/`).**
  - `quaderni/gemini-4-neon-high.md` e `quaderni/orchestrator-neon.md` nuovi, nel formato di `quaderni/LEGGIMI.md`.
    `quaderni/gemini-4-argon-high.md` e `quaderni/orchestrator-argon.md` portano già l'intestazione `**Uscito:**`
    (verificare soltanto che restino intatti).
  - `plugin/skills/bottega/porte/antigravity.md`: mantiene esattamente le 9 sezioni `## ` nell'ordine di
    `test_plugin.py`, senza alcun nome di modello; documenta il formato TSV di `agy -p /quota`, l'epoch zero per
    finestre non avviate, la variabile `BOTTEGA_PUNTI_<BOTTEGA>` e il comportamento dell'Orchestrator su secchio unico.
  - `attrezzi/tests/test_plugin.py`: aggiunge `neon` alla regex `NOMI_DI_MODELLO` e ai casi parametrizzati di
    `test_il_controllo_dei_modelli_prende_le_forme_senza_numero`.
  - `plugin/skills/bottega/SKILL.md`: senza nomi di modello né fornitori; aggiunge `pianificare`, la scala sui
    fallimenti, il ritmo della quota sui riempitivi, le bozze di piano di notte, l'unione per categorie e le misure
    per gradino.
  - `plugin/skills/bottega/modelli/bottega.toml`: mostra tutte le chiavi nuove (`pianificare`, `scala`,
    `aree_non_delicate`, `bozze_piano`, `[categorie]`, `[ritmo]`) con segnaposto generici; passa `bottega
    configurazione` e `test_esempio_*`.
  - `casistica/ciclo.md`: aggiunge `CICLO-43` (scala sui fallimenti), `CICLO-44` (unione per categorie), `CICLO-45`
    (ritmo della quota con riserva), tutti con `Fonte: deciso dall'utente`.

## Review Focus

Casi che le prove unitarie non coprono del tutto e che vanno verificati a mano in revisione:

1. **Fail-closed sulle categorie e sui percorsi strani:** rinominazioni (`R100` in `git diff --raw -z -M`: sia
   `old_path` sia `new_path` controllati!), file con spazi o prefisso `./`, glob `docs/**` che non deve mai prendere
   `docs2/x.md`, e pavimento `.github/` / `.gitleaksignore` che resta delicato anche se `[categorie]` provasse a
   includerlo.
2. **Stato reale di `agy -p /quota`:** finestra non avviata (`1970-01-01T00:00:00Z`, `100%`) non deve mai far partire
   riempitivi; finestra di 5 ore già rinnovata rispetto a una rilevazione vecchia di ore deve risultare `100%` (non
   restare bloccata al valore vecchio); rilevazione con `rinnovo_settimana` passato deve risultare scaduta.
3. **Nessun codice nelle bozze di piano di notte:** un modello che modifica un file Python insieme a
   `docs/plans/…-bozza.md` (o lo aggiunge in un commit e lo toglie nel successivo!) deve essere rifiutato guardando
   sia `entries` sia `entries_storia`; il tetto di 3 bozze deve contare sia quelle `in corso` sia quelle già
   `consegnate` con `bottega: bozza di piano`.
4. **Rilettura vs passo finale senza doppia chiamata né bypass:** se il revisore risponde `VERDETTO: APPROVATO` con
   `GRAVI: 1` o senza riga `VERDETTO:`, `pronta per l'unione` NON si scrive mai; su lavoro singolo dove `consigliare`
   e `rivedere` sono lo stesso candidato, il modello gira una volta sola; su lavoro a più compiti, il passo finale
   guarda il diff dell'intero ramo dalla base (`merge-base`), non solo l'ultimo compito.
5. **Scala vs `esegue:` vs quota:** una quota finita (429) non fa mai salire di gradino; un `esegue:` esplicito non
   viene mai scalato su un altro modello; al cambio sotto-issue e dopo `/bottega riprova` il `gradino` torna a `0`;
   senza `scala` in `bottega.toml` restano i 3 tentativi identici a B14.
6. **Retrocompatibilità di `misure` e `più esecutori`:** i compiti senza `scala` toccati da due esecutori dopo un 429
   devono continuare a scrivere `più esecutori` ed essere esclusi da `risultati`/`costi_propri` (`test_c1`, `test_c2`).
7. **Sicurezza negli script locali di Parte A:** `unisci.sh` non unisce mai una PR delicata senza `RIVISTO_MAESTRO=1`
   né una non delicata senza `VERDETTO` valido (o `RIVISTO_MAESTRO=1`); `gitleaks` e controllo salute restano sempre
   attivi dopo l'unione locale.
8. **Nomi vietati e dati personali:** `test_plugin.py` verde con `neon` nella regex; `controlla-pubblico` verde su
   tutti i file aggiunti e modificati.

---

## Quadro dei compiti e parallelismo

| ID | Parte | Compito | Dopo | Parallelo con | Livello |
|---|---|---|---|---|---|
| B15.1 | Base | Schema `bottega.toml` e modello di esempio | — | — | `medium` |
| A1 | A | Categorie del diff e formato del verdetto (`categorie.py`) | B15.1 | A2, A3, B4 | `medium` |
| A2 | A | Parser `/quota`, punti e ritmo (`quota.py`, `ritmo.py`, `antigravity.py`) | B15.1 | A1, A3, B4 | `medium` |
| A3 | A | Prossimo gradino della scala (`scelta.py`) | B15.1 | A1, A2, B4 | `medium` |
| A4 | A | Registrazione CLI (`__main__.py`) + patch script locali (fuori git) | A1, A2, A3 | B4 | `low` |
| B1 | B | `Forgia.etichette_pr` e misure per gradino (`forgia`, `misure`, `conti`) | A4 | B2, B4 | `medium` |
| B2 | B | Distributore: scala, ritmo sui riempitivi, bozze di piano di notte | A4 | B1, B4 | `high` |
| B3 | B | Giro: scala, bozze di piano, passo finale, punti e misure per gradino | B1, B2 | B4 | `high` |
| B4 | B | Quaderni, `antigravity.md`, `SKILL.md`, casistica, `test_plugin.py` | B15.1 | A1..A4, B1..B3 | `medium` |
| B5 | B | Verifica completa del ramo intero | B3, B4 | — | `low` |

---

## Base: configurazione

### B15.1 — Schema `bottega.toml` e modello di esempio

**File:**
- `attrezzi/bottega/configurazione.py`
- `attrezzi/tests/test_configurazione.py`
- `plugin/skills/bottega/modelli/bottega.toml`

**Interfacce (B15-R1, B15-R2, B15-R3):**
- Costanti in `configurazione.py`:
  - `FUNZIONI = ("decidere", "eseguire", "rivedere", "consigliare", "pianificare")`
  - `BOZZE_PIANO_PREDEFINITE = 3`, `BOZZE_PIANO_MASSIME = 10`
  - `RITMO_RITARDO_PREDEFINITO = 15`, `RITMO_RISERVA_5H_PREDEFINITA = 30`, `RITMO_RISERVA_SETTIMANA_PREDEFINITA = 15`
- Dataclass:
  - `Progetto`: in coda `scala: tuple[str, ...] = ()`, `aree_non_delicate: tuple[str, ...] = ()`,
    `bozze_piano: int = BOZZE_PIANO_PREDEFINITE`.
  - Nuovo `@dataclass(frozen=True) class Ritmo`:
    `gruppo: str | None = None`, `ritardo: int = RITMO_RITARDO_PREDEFINITO`,
    `riserva_5h: int = RITMO_RISERVA_5H_PREDEFINITA`, `riserva_settimana: int = RITMO_RISERVA_SETTIMANA_PREDEFINITA`.
  - `Configurazione`: in coda `categorie: dict[str, tuple[str, ...]] = field(default_factory=dict)`,
    `ritmo: Ritmo = field(default_factory=Ritmo)`.
- `modelli/bottega.toml`: aggiunge un quarto candidato `[candidati.pianificatore]` con `funzioni = ["pianificare"]`,
  aggiunge in `[progetto]` `scala = ["lavorante", "riserva"]`, `aree_non_delicate = ["docs", "prove", "debito"]`,
  `bozze_piano = 3`, aggiunge `[categorie]` (`documenti`, `prove`, `quaderni`) e `[ritmo]` (`gruppo`, `ritardo`,
  `riserva_5h`, `riserva_settimana`).

**Prove in `attrezzi/tests/test_configurazione.py`:**
- Aggiornare `test_elenchi_del_formato`, `funzione-fuori-elenco` in `ERRORI`, `test_esempio_si_legge_per_intero`,
  `test_esempio_ha_ogni_chiave_ammessa`, `test_comando_esempio_esce_0_con_il_conteggio` (`candidati 4`).
- Nuove prove rosse prima del codice:
  - `test_funzione_pianificare_valida`: candidato con `funzioni = ["pianificare"]` accettato.
  - `test_scala_valida_con_riserva_e_su_richiesta`: `scala = ["lavorante", "riserva", "speciale"]` valida anche con
    `riserva = true` e `su_richiesta = true`; `scala = []` valida.
  - `test_scala_errori`: candidato inesistente (`progetto.scala[0]`), candidato senza `eseguire`, duplicato, tipo non
    lista.
  - `test_aree_non_delicate_valide_ed_errori`: lista valida, vuota, duplicati case-insensitive, voce vuota.
  - `test_bozze_piano_valide_ed_errori`: `0`, `3`, `10` validi; `-1`, `11`, `true`, `"3"` errori su
    `progetto.bozze_piano`.
  - `test_categorie_valide_ed_errori`: tabella valida; nome categoria invalido (`Docs`), lista vuota, glob assoluto
    (`/docs/**`), `..`, modello troppo largo (`**`, `**/*`), duplicati.
  - `test_ritmo_valido_ed_errori`: predefiniti senza sezione `[ritmo]`; valori personalizzati validi; `ritardo = 0`,
    `ritardo = 100`, `riserva_5h = -1`, `riserva_5h = 101`, `riserva_settimana = true`, chiave sconosciuta.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_configurazione.py && \
  uv run python -m bottega configurazione --file plugin/skills/bottega/modelli/bottega.toml
```

---

## Parte A — Attrezzi delle sessioni (CLI con prove vere + script locali)

### A1 — Categorie del diff, verdetto del revisore e `bottega categoria`

*Può girare in parallelo con A2, A3 e B4 (dopo B15.1).*

**File:**
- `attrezzi/bottega/categorie.py` (nuovo)
- `attrezzi/tests/test_categorie.py` (nuovo)

**Interfacce (B15-R2, B15-R5, B15-R7):**
```python
ETICHETTE_DELICATE: frozenset[str] = frozenset({"bottega: prove cambiate", "bottega: segreti"})

@dataclass(frozen=True)
class Verdetto:
    stato: str          # "APPROVATO", "RILIEVI_GRAVI", "SICUREZZA", "non_valido"
    gravi: int
    minori: int
    sicurezza: bool
    valido: bool

    @property
    def approvato(self) -> bool: ...
    @property
    def bloccante(self) -> bool: ...

@dataclass(frozen=True)
class EsitoCategoria:
    delicata: bool
    categorie_toccate: tuple[str, ...]
    fuori_elenco: tuple[str, ...]
    motivi: tuple[str, ...]

def corrisponde_glob(percorso: str, modello: str) -> bool: ...
def percorso_protetto(percorso: str) -> bool: ...
def analizza_verdetto(testo: str) -> Verdetto: ...
def classifica_diff(
    percorsi: Sequence[str],
    categorie: Mapping[str, Sequence[str]],
    *,
    etichette_pr: Sequence[str] = (),
    sicurezza: bool = False,
) -> EsitoCategoria: ...
def file_del_diff(base: str, ramo: str, cartella: Path | None = None) -> list[str]: ...
def argomenti_categoria(parser: argparse.ArgumentParser) -> None: ...
def comando_categoria(args: argparse.Namespace) -> int: ...
```

**Prove in `attrezzi/tests/test_categorie.py`:**
- `test_corrisponde_glob_casi_principali`: `docs/**` (`docs/a.md`, `docs/a/b.md` vero; `docs-2/a.md`, `x/docs/a.md`
  falso), `*.md` (`LEGGIMI.md` vero; `docs/a.md` falso), `**/*.py`, `a/?/b.txt`, prefisso `./` normalizzato.
- `test_percorso_protetto`: `.github/workflows/x.yml`, `.bottega/a`, `.gitleaksignore`, `sub/.gitleaks.toml` veri;
  `docs/github.md` falso.
- `test_classifica_diff_non_delicata`: file solo in `documenti` e `prove` → `delicata is False`,
  `categorie_toccate == ("documenti", "prove")`, `fuori_elenco == ()`.
- `test_classifica_diff_file_fuori_elenco`: anche un solo file non coperto → `delicata is True`, presente in
  `fuori_elenco`.
- `test_classifica_diff_pavimento_protetto_vince`: `.github/x.md` delicato anche con `documenti = ["**/*.md"]`.
- `test_classifica_diff_vuoto_e_delicato`: `percorsi = []` → `delicata is True`.
- `test_classifica_diff_etichette_e_sicurezza`: `bottega: prove cambiate`, `bottega: segreti` (anche maiuscole) e
  `sicurezza=True` rendono `delicata is True`.
- `test_analizza_verdetto_approvato_gravi_sicurezza`: formati validi, con grassetto markdown (`**VERDETTO:**`),
  spazio in `RILIEVI GRAVI`, `VERDETTO:` dentro blocco recintato ignorato.
- `test_analizza_verdetto_fail_closed`: `VERDETTO: APPROVATO` + `GRAVI: 2` → `stato == "RILIEVI_GRAVI"`,
  `approvato is False`, `bloccante is True`; testo senza `VERDETTO:` → `valido is False`, `approvato is False`,
  `bloccante is False`.
- `test_file_del_diff_con_rinomina_e_spazi`: repo git reale in `tmp_path` con rinomina `docs/a.md -> src/a.md` e file
  con spazio; verifica che entrambi `old_path` e `new_path` tornino nella lista.
- `test_comando_categoria_codici_uscita`: esce `0` (non delicata + verdetto approvato), `1` (delicata o `SICUREZZA`),
  `3` (non delicata ma verdetto `RILIEVI_GRAVI` o non valido), `2` (configurazione mancante o file verdetto assente);
  verifica `--json`.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_categorie.py
```

---

### A2 — Parser `/quota`, variabile `BOTTEGA_PUNTI_*`, porta Antigravity e `bottega ritmo`

*Può girare in parallelo con A1, A3 e B4 (dopo B15.1).*

**File:**
- `attrezzi/bottega/quota.py`
- `attrezzi/bottega/porte/antigravity.py`
- `attrezzi/bottega/ritmo.py` (nuovo)
- `attrezzi/tests/test_quota.py`
- `attrezzi/tests/test_ritmo.py` (nuovo)

**Interfacce (B15-R3, B15-R4, B15-R7):**
- In `attrezzi/bottega/quota.py`:
  ```python
  PREFISSO_PUNTI = "BOTTEGA_PUNTI_"

  @dataclass(frozen=True)
  class PuntoQuota:
      gruppo: str
      settimana: int
      rinnovo_settimana: datetime
      cinque_ore: int
      rinnovo_cinque_ore: datetime

  def nome_variabile_punti(id_bottega: str) -> str: ...
  def analizza_uscita_quota(testo: str) -> dict[str, PuntoQuota]: ...
  def formatta_punti(punti: Mapping[str, PuntoQuota], rilevato: datetime) -> str: ...
  def leggi_punti(valore: str | None) -> tuple[datetime | None, dict[str, PuntoQuota]]: ...
  def differenza_punti(
      prima: Mapping[str, PuntoQuota] | None,
      dopo: Mapping[str, PuntoQuota] | None,
  ) -> dict[str, tuple[int, int]]: ...  # gruppo -> (delta_settimana, delta_5h)
  ```
- In `attrezzi/bottega/porte/antigravity.py`:
  ```python
  def leggi_quota(
      self,
      prefisso: Sequence[str] = (),
      tempo: int | float = 60,
  ) -> dict[str, PuntoQuota] | None: ...
  ```
- In `attrezzi/bottega/ritmo.py`:
  ```python
  ETICHETTE_ESCLUSE_RIEMPITIVI: frozenset[str] = frozenset({
      "attesa utente", "design", "delicato", "bottega: sospeso", "bottega: bozza di piano",
  })

  @dataclass(frozen=True)
  class EsitoRitmo:
      lancia: bool
      gruppo: str
      settimana_residua: int
      cinque_ore_effettiva: int
      atteso_speso: float
      speso: int
      ritardo: float
      motivo: str

  def valuta_ritmo(
      punto: PuntoQuota,
      adesso: datetime,
      *,
      soglia_ritardo: int = 15,
      riserva_5h: int = 30,
      riserva_settimana: int = 15,
  ) -> EsitoRitmo: ...
  def seleziona_gruppo_punti(
      punti: Mapping[str, PuntoQuota],
      cfg: Configurazione,
      id_bottega: str,
  ) -> PuntoQuota | None: ...
  def fascia_riempitivo(etichette: Sequence[str]) -> int: ...
  def scegli_riempitivo(
      lavori: Sequence[Lavoro],
      *,
      aree_non_delicate: Sequence[str],
      ha_fatto_quando: Callable[[int], bool],
      autore_valido: Callable[[int], bool],
  ) -> tuple[Lavoro, int] | None: ...
  def argomenti_ritmo(parser: argparse.ArgumentParser) -> None: ...
  def comando_ritmo(args: argparse.Namespace) -> int: ...
  ```

**Prove in `attrezzi/tests/test_quota.py` e `attrezzi/tests/test_ritmo.py`:**
- In `test_quota.py`:
  - `test_nome_variabile_punti`: `nome_variabile_punti("google") == "BOTTEGA_PUNTI_GOOGLE"`,
    `nome_variabile_punti("google-pro") == "BOTTEGA_PUNTI_GOOGLE_PRO"`.
  - `test_analizza_uscita_quota_tsv`: analizza output reale TSV a 2 gruppi (`Gemini Models` e `Claude and GPT models`,
    con `1970-01-01T00:00:00Z`), verifica percentuali e timestamp UTC aware.
  - `test_formatta_e_leggi_punti_roundtrip`: andata e ritorno JSON identico; JSON rotto o `None` restituisce
    `(None, {})` senza eccezioni.
  - `test_differenza_punti`: calcola delta settimana e 5h positivi, omette gruppi senza variazione o mancanti.
- In `test_ritmo.py`:
  - `test_valuta_ritmo_indietro_lancia`: 3,5 giorni passati (`50%` atteso), `80%` residuo (`20%` speso, ritardo `30`),
    5h a `60%` → `lancia is True`.
  - `test_valuta_ritmo_in_passo_non_lancia`: ritardo `14.9` (< `15`) → `lancia is False`.
  - `test_valuta_ritmo_riserva_5h_ferma`: ritardo `30`, ma 5h a `29%` → `lancia is False` (`riserva cinque ore`).
  - `test_valuta_ritmo_5h_rinnovata_dopo_rilevazione`: rilevazione con 5h a `10%` ma `adesso > rinnovo_cinque_ore` →
    `cinque_ore_effettiva == 100`, `lancia is True`.
  - `test_valuta_ritmo_riserva_settimanale_ferma`: `settimana == 14`, ritardo `16` → `lancia is False`.
  - `test_valuta_ritmo_epoch_zero_e_scaduta`: `rinnovo_settimana == 1970-01-01T00:00:00Z` → `lancia is False`;
    `adesso >= rinnovo_settimana` → `lancia is False` (`rilevazione scaduta`).
  - `test_fascia_e_scegli_riempitivo_ordine`: debiti/bug (0) prima di prove (1) prima di docs (2) prima di altre aree
    (3); a parità vince numero minore; esclude `attesa utente`, `design`, `delicato`, `bottega: fuori`, `esegue:`,
    lavori senza `## Fatto quando` o autore non comandante, e restituisce `None` se `aree_non_delicate` è vuota.
  - `test_antigravity_leggi_quota_con_finto_eseguibile`: script finto che stampa TSV di `/quota` → dizionario valido;
    eseguibile rotto → `None`.
  - `test_comando_ritmo_da_file_e_json`: esce `0` quando lancia, `1` quando fermo, `2` su file/formato errato.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_quota.py attrezzi/tests/test_ritmo.py attrezzi/tests/test_porte.py
```

---

### A3 — Prossimo gradino della scala (`scelta.py`, `bottega scala`)

*Può girare in parallelo con A1, A2 e B4 (dopo B15.1).*

**File:**
- `attrezzi/bottega/scelta.py`
- `attrezzi/tests/test_scelta.py`

**Interfacce (B15-R6, B15-R7):**
```python
@dataclass(frozen=True)
class EsitoScala:
    candidato: str | None
    gradino: int | None
    totale: int
    aspetta: bool
    esaurita: bool
    perche: str

def prossimo_gradino(
    scala: Sequence[str],
    indice: int,
    configurazione: Configurazione,
    quote: Mapping[str, str | None],
    adesso: datetime,
    *,
    fuori: bool = True,
) -> EsitoScala: ...
def argomenti_scala(parser: argparse.ArgumentParser) -> None: ...
def comando_scala(args: argparse.Namespace) -> int: ...
```

**Prove in `attrezzi/tests/test_scelta.py`:**
- `test_prossimo_gradino_percorre_tutta_la_scala`: scala di 4 candidati (normale, `riserva=True`, `riserva=True`,
  `su_richiesta=True`): indici `0..3` danno ciascun candidato in ordine, indice `4` dà `esaurita is True`.
- `test_prossimo_gradino_senza_quota_aspetta`: secchio del gradino esaurito → `aspetta is True`, `candidato is None`,
  `esaurita is False`.
- `test_prossimo_gradino_fuori_salta_candidato_senza_runner`: se `fuori=True` e `scala[1]` non ha `runner`, salta a
  `scala[2]`; se `fuori=False` (sessione) sceglie `scala[1]`.
- `test_prossimo_gradino_scala_vuota`: `esaurita is False`, `aspetta is False`, `candidato is None`.
- `test_prossimo_gradino_indice_negativo_errore`: solleva `ValueError`.
- `test_comando_scala_codici_uscita`: `--gradino 0` e `--dopo <id>` escono `0` con `<id>\t<modello>\t<perche>`,
  ultimo gradino esce `1`, quota esaurita esce `3`, `--dopo` inesistente o `--gradino` e `--dopo` insieme escono `2`;
  verifica `--json`.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_scelta.py
```

---

### A4 — Registrazione CLI (`__main__.py`) e righe esatte per gli script locali

*Gira dopo A1, A2 e A3.*

**File nel repo:**
- `attrezzi/bottega/__main__.py`
- `attrezzi/tests/test_comando.py`

**Interfacce (B15-R7):**
- Registra in `COMANDI` e `ARGOMENTI` di `__main__.py`:
  - `"categoria": comando_categoria` / `argomenti_categoria`
  - `"ritmo": comando_ritmo` / `argomenti_ritmo`
  - `"scala": comando_scala` / `argomenti_scala`

**Prove in `attrezzi/tests/test_comando.py`:**
- `test_comandi_b15_registrati`: `{"categoria", "ritmo", "scala"} <= set(COMANDI)` e `<= set(ARGOMENTI)`;
  `main(["categoria", "--help"])`, `main(["ritmo", "--help"])`, `main(["scala", "--help"])` escono `0`.

**Fatto quando:**
- [ ] Tutte le prove di Parte A verdi:
```bash
uv run pytest -q \
  attrezzi/tests/test_comando.py attrezzi/tests/test_configurazione.py \
  attrezzi/tests/test_categorie.py attrezzi/tests/test_quota.py \
  attrezzi/tests/test_ritmo.py attrezzi/tests/test_scelta.py
```

#### Patch esatte degli script locali (fuori da git — le applica chi decide a mano)

1. **`~/.cache/bottega-maestro/lavorante.sh`** (estensione per Neon in sola lettura, salvataggio risposta per
   `unisci.sh` e riga del ritmo):
   - Sotto la riga `w="$1"; brief="$2"; nome="$3"`, aggiungere:
     ```bash
     BOTTEGA_CLONE="${BOTTEGA_CLONE:-$HOME/bottega}"
     SOLA_LETTURA="${SOLA_LETTURA:-0}"
     MODO_FLAGS=()
     PROMPT_EXTRA=""
     if [ "$SOLA_LETTURA" = "1" ]; then
       MODO_FLAGS=(--mode plan)
       PROMPT_EXTRA=" Lavora in sola lettura: non modificare file."
     fi
     ```
   - Nel comando `agy -p ...`: appendere `"$PROMPT_EXTRA"` al prompt e `"${MODO_FLAGS[@]}"` subito dopo
     `--model "${MODELLO:-gemini-4-hydrogen-high}"`.
   - Nel blocco `python3 - "$o/uscita.json"`, salvare la risposta pulita in `"$o/risposta.md"` (così `unisci.sh`
     riceve `VERDETTO="$o/risposta.md"`):
     ```python
     testo = re.sub(r"\(file:///[^)]*\)", "", d.get("response") or "")
     open(sys.argv[2], "w", encoding="utf-8").write(testo + "\n")
     print(testo)
     ```
     (passando `"$o/risposta.md"` come secondo argomento dello script Python).
   - Dopo `q_dopo=...` e il blocco `quota spesa:`, stampare il ritmo se il progetto ha `bottega.toml`:
     ```bash
     if [ -f "$w/.github/bottega/bottega.toml" ] && [ -n "$q_dopo" ]; then
       ritmo_out=$(printf '%s\n' "$q_dopo" | PYTHONPATH="$BOTTEGA_CLONE/attrezzi" \
         python3 -m bottega ritmo --file "$w/.github/bottega/bottega.toml" --da-quota - 2>/dev/null || true)
       [ -n "$ritmo_out" ] && echo "ritmo: $ritmo_out"
     fi
     ```

2. **`~/.cache/bottega-maestro/sera/unisci.sh`** (controllo categorie e verdetto del revisore prima del merge):
   - Sotto `RAMO=$1; DESCR=$2; RISOLVI=${3:-}`, aggiungere:
     ```bash
     BOTTEGA_CLONE="${BOTTEGA_CLONE:-$HOME/bottega}"
     VERDETTO="${VERDETTO:-}"
     RIVISTO_MAESTRO="${RIVISTO_MAESTRO:-0}"
     ```
   - Subito dopo `git checkout -q --detach origin/main || exit 2` e **prima** di `git merge --no-ff -S`:
     ```bash
     CAT_ARGS=(--file .github/bottega/bottega.toml --base origin/main --ramo "origin/$RAMO")
     [ -n "$VERDETTO" ] && CAT_ARGS+=(--verdetto "$VERDETTO")
     cat_out=$(PYTHONPATH="$BOTTEGA_CLONE/attrezzi" python3 -m bottega categoria "${CAT_ARGS[@]}")
     cat_rc=$?
     echo "categoria: $cat_out"
     if [ "$cat_rc" -eq 0 ]; then
       if [ -z "$VERDETTO" ] && [ "$RIVISTO_MAESTRO" != "1" ]; then
         echo "non delicata ma manca VERDETTO=<file> (o RIVISTO_MAESTRO=1): fermo"; exit 7
       fi
     elif [ "$cat_rc" -eq 1 ]; then
       if [ "$RIVISTO_MAESTRO" != "1" ]; then
         echo "PR delicata: serve rilettura di chi decide (RIVISTO_MAESTRO=1): fermo"; exit 7
       fi
     else
       echo "controllo categoria/verdetto fallito (rc=$cat_rc): fermo"; exit 7
     fi
     ```
   - Uso pratico:
     - PR non delicata:
       `VERDETTO=~/.cache/bottega-maestro/uscite/lavorante-rev-<nome>/risposta.md unisci.sh <ramo> "<descr>"`
     - PR delicata (dopo rilettura del diff): `RIVISTO_MAESTRO=1 unisci.sh <ramo> "<descr>"`
   - Per il passo di scala in sessione:
     `PYTHONPATH="$HOME/bottega/attrezzi" python3 -m bottega scala --file .github/bottega/bottega.toml --dopo <id>`

---

## Parte B — Il plugin

### B1 — `Forgia.etichette_pr` e misure per gradino (`misure.py`, `conti.py`)

*Può girare in parallelo con B2 e B4 (dopo A4).*

**File:**
- `attrezzi/bottega/forgia.py`
- `attrezzi/bottega/finta.py`
- `attrezzi/bottega/misure.py`
- `attrezzi/bottega/conti.py`
- `attrezzi/tests/test_forgia.py`
- `attrezzi/tests/test_misure.py`
- `attrezzi/tests/test_conti.py`

**Interfacce (B15-R9, B15-R10):**
- In `forgia.py` (`Forgia`, `ForgiaGh`) e `finta.py` (`ForgiaFinta`):
  ```python
  def etichette_pr(self, n: int) -> list[str]: ...
  ```
- In `misure.py`:
  ```python
  PREFISSO_GRADINO = "gradino:"

  @dataclass(frozen=True)
  class MisuraGradino:
      candidato_id: str
      esito: str     # "ok", "fallito", "quota"
      token: int
      durata: int

  def formatta_gradino(candidato_id: str, esito: str, token: int, durata: int) -> str: ...
  def gradini(lavoro: Lavoro) -> list[MisuraGradino]: ...
  ```
  - `risultati(lavori, cfg)` e `costi_propri(lavori, cfg)` applicano B15-R10: se `gradini(lav)` è non vuota,
    attribuiscono ogni gradino fallito (`corretti += 1`) e il gradino vincente (l'`Esito del compito` finale), e i
    token per ciascun `candidato_id`; altrimenti restano identici a B14 (`_di_piu_esecutori` continua a escludere).
- In `conti.py`:
  - `conti(lavori)` riconosce i lavori con `gradini(lav)` e costruisce una voce per ciascun `candidato_id` presente nei
    gradini (durata, token, giri, esito del gradino) invece di scartarli.

**Prove:**
- In `test_forgia.py`: `test_etichette_pr_gh` (mock `gh pr view <n> --repo ... --json labels`) e
  `test_etichette_pr_finta` (aggiungi/rimuovi etichette sulla PR in `ForgiaFinta`).
- In `test_misure.py`:
  - `test_formatta_e_leggi_gradini`: roundtrip con più gradini in `Misure parziali`; voci malformate ignorate.
  - `test_risultati_per_gradino`: compito con `gradino:cand-a:fallito:100:60, gradino:cand-b:ok:200:90` ed esito
    `unito com'era` → `cand-a` ha `Risultati(0, 1, 0)` e `cand-b` ha `Risultati(1, 0, 0)` (sia su `"*"` sia sulle
    etichette).
  - `test_costi_propri_per_gradino`: `cand-a` riceve media `100`, `cand-b` riceve media `200`, relativi `2/3` e `4/3`.
  - `test_piu_esecutori_senza_gradini_resta_escluso`: regressione esplicita per B5/B14.
- In `test_conti.py`:
  - `test_conti_attribuisce_compito_per_gradino`: `conti([lav])["per_candidato"]` contiene sia `cand-a` sia `cand-b`
    con i rispettivi token e durate.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_forgia.py attrezzi/tests/test_misure.py attrezzi/tests/test_conti.py
```

---

### B2 — Distributore: scala, ritmo sui riempitivi e bozze di piano di notte

*Può girare in parallelo con B1 e B4 (dopo A4).*

**File:**
- `attrezzi/bottega/distributore.py`
- `attrezzi/tests/test_distributore_b15.py` (nuovo)

**Interfacce e logica (B15-R4, B15-R6, B15-R8):**
- Costante `ETICHETTA_BOZZA_PIANO = "bottega: bozza di piano"`.
- In `_gestisci_evento_commento` (`riprova`): rimuovere anche `"gradino"` e `"modo"` da `d_riprova`.
- Nel ciclo dei lavori pronti (`distribuisci`):
  1. Se `fq is None` (manca `## Fatto quando`):
     - Di giorno (`not notte`) o con `bozze_piano == 0` o senza candidati `pianificare` fuori o con `esegue:` o
       `ETICHETTA_BOZZA_PIANO` o `attesa utente` o sotto-issue aperte: salta come oggi.
     - Altrimenti (notte, sotto tetto `bozze_piano`, issue senza sotto-issue aperte): sceglie con
       `Compito(funzione="pianificare", fuori=True, etichette=frozenset(lav.etichette))`; se scelto e bottega libera,
       `nuovi["modo"] = "pianifica"`, `nuovi["inizio"] = adesso_fuso.isoformat()`, prende e avvia
       `bottega-esecutore-<bottega>.yml`, incrementa il contatore locale delle bozze avviate nel giro.
  2. Se `fq` è presente:
     - Legge `gradino_raw = valori_nota.get("gradino")`; `gradino = int(gradino_raw)` se cifra, altrimenti `0`.
     - Se `gradino > 0` senza `esegue:` e `cfg.progetto.scala` non è vuota: chiama
       `prossimo_gradino(cfg.progetto.scala, gradino, cfg, variabili, adesso_fuso, fuori=True)`.
       - `esaurita` → blocca il lavoro (`motivo = esito.perche`), commenta e passa al seguente.
       - `aspetta` → logga in attesa e passa al seguente.
       - Altrimenti usa `esito.candidato` (aggiornando `nuovi["gradino"] = str(esito.gradino)`).
     - Altrimenti usa `scegli(...)` come oggi; se `cfg.progetto.scala` non è vuota e il candidato scelto è in `scala`
       e non c'è `esegue:`, scrive `nuovi["gradino"] = str(cfg.progetto.scala.index(scelta.candidato))`.
- **Dopo il ciclo dei lavori ordinari — fase riempitivi del ritmo (giorno e notte):**
  - Se `cfg.progetto.aree_non_delicate` è non vuota, per ogni bottega `b_id` non in `botteghe_occupate` che ha
    variabile `nome_variabile_punti(b_id)` in `variabili`:
    1. Legge `leggi_punti(variabili.get(nome_variabile_punti(b_id)))` e trova il gruppo con `seleziona_gruppo_punti`.
    2. Valuta `valuta_ritmo(punto, adesso_fuso, soglia_ritardo=cfg.ritmo.ritardo, riserva_5h=cfg.ritmo.riserva_5h,
       riserva_settimana=cfg.ritmo.riserva_settimana)`.
    3. Se `esito_ritmo.lancia`: chiama `scegli_riempitivo` sui `lavori_pronti` non ancora presi nel giro; se ne trova
       uno, sceglie il candidato con `prossimo_gradino(cfg.progetto.scala, 0, ...)` (se `scala` configurata e il primo
       gradino appartiene a `b_id`) oppure `scegli(...)` sui soli candidati di `b_id`, prende il lavoro (con
       `nuovi["riempitivo"] = "1"` e `gradino=0` se `scala`), commenta il perché (incluso il ritardo e la fascia del
       riempitivo) e avvia `bottega-esecutore-<b_id>.yml`.

**Prove in `attrezzi/tests/test_distributore_b15.py`:**
- `test_distributore_usa_prossimo_gradino_dopo_salita`: lavoro con `nota="gradino=1"` prende il candidato di riserva
  al gradino 1; con `gradino=2` prende `su_richiesta=True`; con `gradino=len(scala)` blocca il lavoro.
- `test_distributore_esegue_vince_su_gradino`: lavoro con `esegue:` e `gradino=1` usa il candidato di `esegue:`.
- `test_riprova_azzera_gradino_e_modo`: `/bottega riprova` rimuove `gradino` e `modo` dalla nota.
- `test_distributore_riempitivo_quando_ritmo_indietro`: senza lavori ordinari, `BOTTEGA_PUNTI_*` indietro di 25 punti
  e 5h al 60% → prende il debito prima delle prove e dei docs, con il primo gradino della scala.
- `test_distributore_riempitivo_fermo_sotto_riserva_5h`: 5h al 20% → nessun riempitivo avviato.
- `test_distributore_riempitivo_non_scavalca_lavoro_ordinario`: con un lavoro `bottega: fuori`, parte solo quello.
- `test_distributore_bozza_di_piano_di_notte_anche_nel_delicato`: `notte=True`, issue senza `## Fatto quando` con
  etichetta `cuore` → assegnata al candidato `pianificare` con `modo=pianifica` nella nota; di giorno (`notte=False`)
  resta saltata.
- `test_distributore_tetto_tre_bozze_di_piano`: con 3 lavori aperti con `bottega: bozza di piano` (o `modo=pianifica`
  in corso/consegnato), il quarto non parte e il log riporta `bozze di piano al tetto (3/3)`.

**Fatto quando:**
- [ ] Tutte le prove verdi:
```bash
uv run pytest -q attrezzi/tests/test_distributore.py attrezzi/tests/test_distributore_b15.py
```

---

### B3 — Giro: scala sui fallimenti, bozze di piano, passo finale «pronta per l'unione», punti e misure gradino

*Gira dopo B1 e B2; può girare in parallelo con B4.*

**File:**
- `attrezzi/bottega/giro.py`
- `attrezzi/tests/test_giro_b15.py` (nuovo)

**Interfacce e logica (B15-R5, B15-R6, B15-R8, B15-R9, B15-R10):**
- `_trova_candidato(lavoro_numero, bottega_id, configurazione, board, *, funzione: str = "eseguire") -> Candidato`:
  il ripiego cerca `funzione in cand.funzioni` (così funziona anche per `pianificare`).
- Helpers interni puliti in `giro.py`:
  - `_ha_etichetta_esegue(etichette: Sequence[str]) -> bool`
  - `_scala_attiva(cfg: Configurazione, iss_madre: Issue) -> bool`: `bool(cfg.progetto.scala) and not
    _ha_etichetta_esegue(iss_madre.etichette)`
  - `_avanza_gradino_o_blocca(d_nota, cfg, candidato, motivo, board, forgia, lavoro, compito_numero, *,
    iss_madre) -> tuple[str, str]`: gestisce la salita di 1 gradino (se `_scala_attiva`) oppure i 3 tentativi classici
    (se `scala` vuota o `esegue:`); restituisce `(esito_giro, stato_board)`.
  - `_controlla_diff_bozza_piano(entries_tutte) -> str | None`: verifica che ogni `old_path` e `new_path` stia in
    `docs/plans/` e finisca con `.md`.
  - `_passo_finale_pronta(...)`: esegue B15-R9 sull'intero diff da `merge-base` con `origin/<ramo_principale>`.
  - `_aggiorna_punti_quota(...)`: legge `leggi_quota` prima/dopo se presente sulla porta, salva
    `BOTTEGA_PUNTI_<BOTTEGA>` e calcola i delta per log e commento.
- Aggiornamenti ai punti chiave di `_giro`:
  1. **Modalità `modo=pianifica` (B15-R8):** se `d_nota.get("modo") == "pianifica"`, salta il controllo
     `fatto_quando`, usa il prompt di bozza di piano, controlla `_controlla_diff_bozza_piano(entries_storia + entries)`,
     salta oracolo e passo finale, apre/aggiorna PR in bozza `Bozza di piano: <titolo>`, mette
     `bottega: bozza di piano` su PR e `iss_madre`, consegna senza `Esito`.
  2. **Rilettura del consigliere nel giro (B15-R5, B15-R6):** il prompt di rilettura chiede il formato `VERDETTO:` /
     `GRAVI:` / `MINORI:`; si analizza con `analizza_verdetto`. Se `verdetto_cons.bloccante`: il compito **non** si
     chiude; entra in `_avanza_gradino_o_blocca` con `motivo = "rilievi gravi nella rilettura"` (e `consegnato` viene
     tolto dalla nota così il gradino dopo può committare le correzioni sopra il ramo).
  3. **Fallimenti del giro con `scala` (B15-R6):** oracolo rosso, `lancio.esito != "fatto"` (escluso `quota`), nessun
     commit, commit vuoto ed eccezione nel giro chiamano `_avanza_gradino_o_blocca`. Un `lancio.esito == "quota"`
     mantiene intatto `d_nota["gradino"]`.
  4. **Azzeramento `gradino`:** al cambio `compito_salvato != str(compito.numero)` e dopo chiusura di sotto-issue non
     ultima (`d_nota.pop("gradino", None)`).
  5. **Passo finale «pronta per l'unione» (B15-R9):** chiamato prima della consegna finale su `ultima_sotto_issue` con
     `oracolo_ok=True` e `modo != "pianifica"`; riusa il verdetto della rilettura se `cand_cons.id == cand_rev.id` e
     `base_consegna == merge_base`.
  6. **Punti di quota e misure per gradino (B15-R10):** `_scrivi_misure` accetta `scala_attiva: bool = False` ed
     `esito_gradino: str = "ok"`; con `scala_attiva=True` appende `misure.formatta_gradino(...)` a `Misure parziali`
     senza scrivere `più esecutori`. A fine giro stampa `misura gradino: ...` su stdout e la riga breve nel commento
     di consegna.

**Prove in `attrezzi/tests/test_giro_b15.py`:**
- `test_oracolo_rosso_sale_di_gradino_e_poi_blocca_a_scala_esaurita`: scala di 2 gradini; primo rosso mette
  `gradino=1` e `stato=pronto` (tolto `precedente` e `conversazione`); secondo rosso mette `stato=bloccato` e
  `motivo` con `scala esaurita`.
- `test_rilettura_con_rilievi_gravi_blocca_compito_e_sale_di_gradino`: oracolo verde ma consigliere risponde
  `VERDETTO: RILIEVI_GRAVI\nGRAVI: 1\nMINORI: 0` → sotto-issue resta aperta, lavoro torna `pronto` con `gradino=1`.
- `test_quota_esaurita_non_sale_di_gradino`: `esito == "quota"` con `gradino=0` mantiene `gradino=0`.
- `test_esegue_non_usa_scala`: etichetta `esegue:` su lavoro con scala configurata usa ancora i 3 tentativi.
- `test_bozza_di_piano_valida_apre_pr_in_bozza_senza_oracolo`: `modo=pianifica`, modello scrive solo
  `docs/plans/2026-11-26-issue-1-bozza.md` → PR in bozza con etichetta `bottega: bozza di piano`, `Esito` vuoto,
  oracolo non eseguito.
- `test_bozza_di_piano_con_codice_rifiutata`: modello tocca `app.py` (anche aggiunto e poi rimosso in un secondo
  commit) → consegna rifiutata, `stato=bloccato`, niente push.
- `test_passo_finale_pronta_non_delicata`: diff solo `docs/guida.md`, revisore risponde `VERDETTO: APPROVATO\nGRAVI:
  0\nMINORI: 0` → `Esito == "pronta per l'unione"`, `categoria=non-delicata` nella nota, etichetta PR
  `bottega: non delicata`, commento `revisore`.
- `test_passo_finale_riuso_verdetto_stesso_candidato_compito_singolo`: stesso candidato per `consigliare` e `rivedere`
  su lavoro singolo → la porta in sola lettura viene invocata **1 volta**, non 2.
- `test_passo_finale_delicata_per_file_o_etichetta_o_sicurezza`: file fuori `[categorie]`, oppure `bottega: prove
  cambiate`, oppure `VERDETTO: SICUREZZA` → `categoria=delicata`, etichetta `bottega: delicata` (con `SICUREZZA`
  `Esito` resta vuoto!).
- `test_passo_finale_verdetto_non_valido_fail_closed`: revisore senza riga `VERDETTO:` → consegna senza `Esito`.
- `test_punti_quota_salvati_in_variabile_e_misura_gradino_registrata`: porta finta con `leggi_quota` → aggiorna
  `BOTTEGA_PUNTI_<BOTTEGA>`, stampa `misura gradino:` su stdout, scrive `gradino:<id>:...` in `Misure parziali` senza
  `più esecutori`.

**Fatto quando:**
- [ ] Tutte le prove verdi (incluse le prove esistenti del giro e delle misure):
```bash
uv run pytest -q \
  attrezzi/tests/test_giro_b15.py attrezzi/tests/test_giro.py \
  attrezzi/tests/test_giro_misure.py attrezzi/tests/test_rilettura_b14.py \
  attrezzi/tests/test_giro_b9.py attrezzi/tests/test_ripresa_dal_rosso.py
```

---

### B4 — Quaderni, pagina della porta, skill, casistica e guardia `test_plugin.py`

*Può girare in parallelo con A1..A4 e B1..B3 (dopo B15.1).*

**File:**
- `quaderni/gemini-4-neon-high.md` (nuovo)
- `quaderni/orchestrator-neon.md` (nuovo)
- `plugin/skills/bottega/porte/antigravity.md`
- `plugin/skills/bottega/SKILL.md`
- `casistica/ciclo.md`
- `attrezzi/tests/test_plugin.py`

**Contenuti (B15-R11):**
- `quaderni/gemini-4-neon-high.md`: fornitore Google, porta Antigravity (`gemini-4-neon-high`), usato da B15 per
  piani, brief, critiche e revisioni sullo stesso secchio Gemini (pesa circa il doppio di Hydrogen per token);
  lezioni: formato del verdetto `VERDETTO:` / `GRAVI:` / `MINORI:` nelle revisioni, divieto di toccare file fuori da
  `docs/plans/*.md` nelle bozze di piano di notte, controllo del costruttore in ~2 min / 161k token.
- `quaderni/orchestrator-neon.md`: modalità `gemini-pro-orchestrator-neon` (Neon pianifica e controlla, Hydrogen
  esegue), livello fisso senza `--effort`, stesso secchio Gemini, usato per tappe intere dal piano con
  `su_richiesta = true` e `tempo` lungo, al posto di `orchestrator-argon` (uscito).
- Verificare che `quaderni/gemini-4-argon-high.md` e `quaderni/orchestrator-argon.md` conservino il blocco
  `**Uscito:**` già presente (nessuna modifica se già aggiornati).
- `plugin/skills/bottega/porte/antigravity.md`: stesse 9 sezioni `## `, **zero nomi di modello**; aggiunge in «Quota
  esaurita» il formato TSV di `agy -p /quota` (4 colonne, `1970-01-01T00:00:00Z` a riposo) e `BOTTEGA_PUNTI_<BOTTEGA>`;
  in «I modelli» chiarisce l'Orchestrator su secchio condiviso.
- `plugin/skills/bottega/SKILL.md`: **zero nomi di modello o fornitore**; aggiorna la tabella delle funzioni (5
  funzioni, con `pianificare`), documenta scala sui fallimenti, ritmo della quota con riempitivi e riserve, bozze di
  piano di notte (tetto 3), passo finale «pronta per l'unione» con categorie strette di progetto e misure per gradino.
- `casistica/ciclo.md`: aggiunge `CICLO-43` (scala sui fallimenti), `CICLO-44` (unione per categorie), `CICLO-45`
  (ritmo della quota con riserva), `Fonte: deciso dall'utente`.
- `attrezzi/tests/test_plugin.py`: aggiunge `neon` a `NOMI_DI_MODELLO` e al test parametrizzato delle forme senza
  numero.

**Fatto quando:**
- [ ] Prove plugin, casi e lunghezza righe verdi:
```bash
uv run pytest -q attrezzi/tests/test_plugin.py attrezzi/tests/test_casi.py && \
  uv run python -m bottega casi && \
  awk 'length > 120 {print FILENAME ":" NR ":" length; f=1} END {exit f}' \
    plugin/skills/bottega/SKILL.md plugin/skills/bottega/porte/antigravity.md \
    quaderni/gemini-4-neon-high.md quaderni/orchestrator-neon.md casistica/ciclo.md
```

---

### B5 — Verifica finale del ramo intero

*Gira dopo B3 e B4.*

**Fatto quando:**
- [ ] Suite completa in namespace PID, controllo configurazione modello, controllo casi, controllo righe ≤ 120 e
  controllo pubblico (regole fisse) tutti verdi:
```bash
unshare --user --map-user="$(id -u)" --map-group="$(id -g)" --pid --fork --kill-child \
  uv run pytest -q && \
  uv run python -m bottega configurazione --file plugin/skills/bottega/modelli/bottega.toml && \
  uv run python -m bottega casi && \
  uv run python -m bottega controlla-pubblico
```

---

## Dopo il piano (fuori tappa, a cura di chi decide)

- Applicare le due patch di Parte A agli script locali (`~/.cache/bottega-maestro/lavorante.sh` e
  `~/.cache/bottega-maestro/sera/unisci.sh`).
- Configurare `bottega.toml` nei progetti che usano la bottega (inclusi `[categorie]`, `scala`, `aree_non_delicate` e
  i candidati della nuova famiglia).
- Dopo le prime misure con Parte A e revisione finale del ramo `b15`: controllo pubblico con `PAROLE_VIETATE`,
  aggiornamento della versione (`0.3.0`) solo al momento del rilascio approvato dall'utente, unione firmata `--no-ff`
  in `main`, tag e spinta.
