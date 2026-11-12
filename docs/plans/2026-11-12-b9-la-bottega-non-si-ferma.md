# B9 La bottega non si ferma: piano

> **Per chi esegue:** metodo Bottega; vale la costituzione del repo (`docs/costituzione.md`). Ogni compito ha il suo
> worktree e il suo ramo (`b9-<nome>`); chi decide li unisce nel ramo `b9`.

**Obiettivo:** chiudere i fermi silenziosi visti il 2026-11-12 sul primo progetto che usa la bottega dal vivo. Un
lavoro non deve restare fermo senza che nessuno lo sappia, e un compito rosso non deve diventare la base del seguente.

**Perché (dal vivo, 2026-11-12):**

1. Un giro dell'esecutore è caduto prima di cominciare per un `HTTP 503` di GitHub («No server is currently
   available»). Il lavoro è rimasto `pronto`, ma la catena dei giri si è fermata: `giro()` affida la ripresa «al giro
   programmato», e il modello del distributore ne ha uno solo, di notte.
2. Un lavoro chiuso, con l'etichetta ancora sopra ed `Esito` = `correzioni`, è stato preso come pronto, riaperto e
   rimandato all'esecutore; il lavoro nuovo è stato saltato.
3. Un lavoro lanciato dentro la finestra di manutenzione ha ricevuto «nessun lavoro avviato», e nessuno l'ha saputo
   per tre ore: chi aspettava guardava solo errori e domande.
4. Il giro di notte pianificato al minuto 0 non è mai partito (GitHub salta o ritarda gli eventi pianificati al minuto
   0, i più carichi).
5. L'oracolo di un compito era ROSSO; il giro ha chiuso il compito e ha passato il seguente, che ha trovato la suite
   rossa sul ramo (B3-R12: «un oracolo rosso non blocca la consegna»; vale per un compito solo, non per una tappa).
6. L'esecutore ha scritto `DOMANDA PER CHI DECIDE:` in **testa** al rapporto: il giro la riconosce solo nell'ultima
   riga, quindi ha contato «nessun commit» e ha rilanciato lo stesso compito.

## Ruling

- **B9-R1. Gli errori passeggeri di GitHub si ritentano** (`attrezzi/bottega/ritenta.py`, nuovo, puro tranne
  `ritenta`):
  - `ATTESE_S: tuple[float, ...] = (10.0, 30.0)`: al più tre tentativi.
  - `passeggero(testo: str) -> bool`, senza maiuscole: `HTTP 50[0234]`, `no server is currently available`,
    `connection reset`, `connection refused`, `timeout`, `timed out`, `tls handshake`, `unexpected eof`,
    `could not resolve host`, `temporary failure in name resolution`, `non ha risposto in`.
  - `non_consegnato(testo: str) -> bool`: la richiesta non è arrivata a GitHub: `no server is currently available`,
    `connection refused`, `could not resolve host`, `temporary failure in name resolution`.
  - `di_sola_lettura(argomenti: Sequence[str]) -> bool`: `issue|pr|run|repo|label|release|workflow|project|search`
    seguiti da `view|list|status|diff|checks`; `api graphql` senza la parola `mutation` in nessun argomento; `api`
    su un altro percorso senza `-X`/`--method` diversi da `GET` e senza `-f`, `-F`, `--field`, `--raw-field`,
    `--input` (con un campo `gh api` usa `POST`).
  - `ritenta(prova: Callable[[], tuple[int, str, str]], argomenti, *, dormi=time.sleep) -> tuple[int, str, str]`
    (codice, stdout, stderr): ripete solo se `passeggero(stderr)` e (`di_sola_lettura(argomenti)` o
    `non_consegnato(stderr)`); prima di ogni attesa scrive su stderr una riga che comincia con `avviso:` e nomina i
    primi due argomenti e i secondi d'attesa; restituisce l'ultimo risultato.
  - Si usa in `ForgiaGh._esegui_di_serie` (che guadagna `timeout=120`, codice `124` e il testo
    `gh non ha risposto in 120 secondi`), in `BoardProject._esegui_di_serie` e in `BoardComando._esegui` per le sole
    letture dell'adattatore (`pronti`, `in-corso`, `elenco`). Con un `esegui` iniettato (le prove) niente ritentativi.
- **B9-R2. I giri pianificati del distributore** (modello `plugin/skills/bottega/modelli/workflows/
  bottega-distributore.yml`, `attrezzi/bottega/progetto.py`):
  - il giro di notte non sta mai al minuto 0: con l'ora della notte a `HH:00` il cron usa il minuto `17` e il commento
    lo dice (`minuto_sicuro(minuto: int) -> int`, `0 → 17`, gli altri invariati);
  - un **giro di riserva** ogni ora, `'<M> * * * *'` con `M` = `minuto_sicuro((minuto della notte + 30) mod 60)`, oppure `47` senza
    notte (`cron_di_riserva(cron_notte: str | None) -> str`): riprende entro un'ora un lavoro rimasto pronto, e dopo
    la finestra di manutenzione ciò che vi era caduto. A bottega occupata non fa nulla;
  - `notte:` vale solo per il cron della notte: `${{ (github.event_name == 'schedule' && github.event.schedule ==
    '<cron della notte>') || inputs.notte == true }}`; senza notte `${{ inputs.notte == true }}` e nessuna riga del
    cron di notte;
  - `bottega aggiorna` non cambia i cron dei progetti già installati: l'`INSTALLA.md` dice come aggiungerli a mano.
- **B9-R3. Un lavoro chiuso non è mai pronto:** `Lavoro` guadagna `aperta: bool = True`; `BoardProject` legge lo
  `state` delle issue e delle PR (`aperta` = `OPEN`), e `pronti()` e `prendi()` saltano i chiusi; il JSON
  dell'adattatore può portare `"aperta": false` (`_dati_a_lavoro` lo legge, di serie `True`). Il protocollo
  dell'adattatore lo dice.
- **B9-R4. Un oracolo rosso non chiude il compito** (cambia B3-R12): dopo la PR e il commento dell'esito, con
  l'oracolo rosso il giro non chiude il compito né consegna il lavoro: `tentativi` + 1, `motivo=oracolo rosso`, la
  chiave `consegnato` tolta dalla nota (la ripresa B7-2 non deve saltare all'oracolo), stato `pronto` e distributore
  rilanciato; al terzo, `bloccato` col commento «oracolo rosso tre volte: serve chi decide». Il giro dopo trova la
  consegna sul ramo e l'esito dell'oracolo fra i commenti del fascicolo. Vale anche per un lavoro senza sotto-issue.
- **B9-R5. La domanda è una riga, non la coda:** il consulto parte se una riga del testo finale, tolti in testa spazi,
  `-`, `+`, `>`, `#`, `*`, `_` e un numero d'elenco, comincia con `DOMANDA PER CHI DECIDE` (senza maiuscole, la
  formattazione può chiudersi prima dei due punti); la domanda è il testo da quella riga (l'ultima che lo fa) alla fine.
  Una citazione a metà riga e le righe dentro un blocco di codice recintato non contano. *(Allargato dopo la revisione:
  la prima versione toglieva solo spazi e `*`, e perdeva le domande scritte come titolo o come voce d'elenco.)*
- **B9-R6. `bottega lancia N` e `bottega segui N`** (`attrezzi/bottega/lancio.py`, nuovo):
  - `lancia`: mette l'etichetta `bottega: fuori` (se c'è già, avvia il distributore), aspetta il giro del distributore
    nato dopo, ne legge il registro e dice che cosa ha deciso per **quel** lavoro. Esce `0` avviato, `2` finestra di
    manutenzione, `3` bottega occupata, `4` ramo principale rosso, `1` nessuna riga o un guasto.
  - `segui`: guarda il lavoro finché non succede qualcosa per chi decide, ed esce `0` finito (lavoro consegnato o
    tutte le sotto-issue chiuse), `2` in attesa (una domanda), `3` bloccato, `4` fermo (nessun giro dell'esecutore in
    coda o in corso da `--fermo` secondi, di serie 1200, col lavoro pronto o in corso), `6` tempo scaduto (`--tetto`,
    di serie 18000). Un giro dell'esecutore finito male è un avviso, non un'uscita: con B9-R4 la catena va avanti, e se
    si ferma lo dice il fermo. Il verdetto è una funzione pura. I giri si leggono workflow per workflow (quelli che
    cominciano con `bottega-esecutore`); `lancia` legge tutti i giri del distributore nati dopo il lancio, finché uno
    parla di quel lavoro.
- **B9-R7. Un guasto fisso prima del giro si blocca** (dopo la revisione): col giro di riserva un errore prima del giro
  ripartirebbe ogni ora per sempre. Conta un tentativo come gli altri (`motivo=errore prima del giro`) e al terzo il
  lavoro va `bloccato`.

## Compiti

| Compito | Ramo | Chi esegue | File |
|---|---|---|---|
| B9.1 i ritentativi | `b9-ritenta` | Lavorante | `ritenta.py`, `forgia.py`, `board.py` (i soli `_esegui*`), prove |
| B9.2 i giri pianificati | `b9-giri` | Lavorante | modello del distributore, `progetto.py`, `INSTALLA.md`, prove |
| B9.3 i lavori chiusi | `b9-chiusi` | Lavorante | `board.py` (query, `Lavoro`, `pronti`, `prendi`, `_dati_a_lavoro`), prove |
| B9.4 l'oracolo e la domanda (R4, R5) | `b9-giro` | capobottega | `giro.py`, prove |
| B9.5 lancia e segui | `b9-segui` | Lavorante | `lancio.py`, `__main__.py`, prove |

B9.4 va al capobottega: tocca la ripresa del giro (B7-2, `consegnato`, `tentativi`), dove un errore rimanda
all'esecutore lavori già consegnati; il giudizio sta nel leggere tutte le uscite del giro, che il piano non può
elencare.

## Fatto quando

`uv run pytest -q` verde nel ramo `b9`, il controllo pubblico verde, la casistica con i casi nuovi, una revisione e
una rilettura del diff delle correzioni; poi la versione `0.2.1`.

## Misure

| Compito | Chi | Durata | Token | Giri | Note |
|---|---|---|---|---|---|
| B9.1 i ritentativi | Lavorante (Flash high) | 13 min | 329 271 | 1 | Chi decide ha tolto una sentinella attorno a `time.sleep`. |
| B9.2 i giri pianificati | Lavorante (Flash high) | 9 min | 380 999 | 1 | Chi decide: il minuto da evitare è quello in UTC (un fuso a mezz'ora dava minuto 0); prova aggiunta. |
| B9.3 i lavori chiusi | Lavorante (Flash high) | 20 min | 435 263 | 1 | Nessuno. |
| B9.4 l'oracolo e la domanda | capobottega (Sonnet high) | 24 min | 203 130 | 1 | Chi decide: anche il terzo rosso rilancia il distributore, come gli altri blocchi. |
| B9.5 lancia e segui | Lavorante (Flash high) | 26 min | 398 823 | 1 | Chi decide: un esecutore che dà solo lo stdout (gli avvisi di `gh` su stderr rompevano il JSON). |

I quattro Lavoranti e il capobottega hanno girato insieme, su cinque worktree. Ruff non c'è nel repo: la regola dei
brief che lo chiedeva era sbagliata.
