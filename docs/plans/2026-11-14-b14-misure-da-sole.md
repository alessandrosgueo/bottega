# B14 — Le misure che si scrivono da sole

Disegno e piano in un solo documento. Le scelte sono di chi decide (l'utente ha detto «procedi in autonomia» dopo la
revisione del metodo del 2026-11-14); ognuna è un'ipotesi rivedibile.

## Perché

La revisione del metodo, sui conti di un progetto vero (45 compiti fuori), ha trovato:

- «Token di chi decide»: 0 compiti su 45 col numero. La spia del metodo è vuota: non si sa se il metodo risparmia.
- «Esito del compito»: 5 su 45. La scelta viva impara solo da lì.
- «Consigli accolti» e «respinti»: 0. 42 compiti su 44 sono passati col commento «compito senza rilettura», che non
  dice il motivo.

I tre numeri che mancano dipendono da tre gesti a mano (`bottega segno inizio|fine`, `bottega misura --esito`, i
consigli). Un gesto che serve solo a misurare si dimentica. **Il principio di B14: nessun gesto fatto solo per
misurare; la misura la lascia il gesto che fa il lavoro.**

## Il disegno

1. **La correzione ha un comando, e il comando scrive l'esito.** Chiedere una correzione è già il giudizio «corretto».
   `bottega correggi <N>` crea il compito di correzione sotto il lavoro, rimette il lavoro in `correzioni` e scrive
   sul compito `N` «Esito del compito» = `corretto`, più il rilievo per origine se chi decide lo dice (`--origine`) e
   il consiglio accolto se la correzione viene dal consigliere (`--consiglio`). Oggi gli stessi tre passi si fanno a
   mano e l'esito resta vuoto.
2. **Alla chiusura del lavoro gli esiti che mancano li scrive il distributore.** A ogni giro guarda i lavori chiusi che
   non ha ancora spazzato: i compiti senza esito prendono `unito com'era` se il lavoro è chiuso come fatto, `rifiutato`
   se è chiuso come «non pianificato». Un esito già scritto non si tocca mai.
3. **Il segno si apre e si chiude da solo.** I comandi che chi decide lancia già su un lavoro (`lancia`, `segui`,
   `correggi`) aprono il segno sulla sessione; una sessione ha un solo lavoro aperto alla volta (toccarne un altro
   chiude il primo); un segno rimasto aperto su un lavoro chiuso si chiude all'ora della chiusura, al primo comando
   che passa (`lancia`, `segui`, `correggi`, `conti`). I token vanno divisi in parti uguali fra i compiti del lavoro.
   Resta fuori il tempo del piano, prima del primo comando: la misura è «brief, attese, revisione, correzioni,
   unione». `bottega segno inizio|fine` resta per chi lavora in sessione.
4. **«Compito senza rilettura» dice perché** (nessun consigliere con quota, nessuno sul runner, lancio non riuscito).

**Limite noto, scritto nella skill:** una correzione fatta da chi decide con le sue mani, senza `correggi`, lascia al
compito l'esito `unito com'era`. Per quel caso resta `bottega misura <N> --esito corretto`.

## Ruling

- **R1.** `Forgia` ha due metodi nuovi, anche in `ForgiaGh` e `ForgiaFinta`:
  - `madre_di(n: int) -> int | None`: il numero dell'issue madre; `None` se non ne ha. In `ForgiaGh`:
    `gh api repos/<repo>/issues/<n>/parent` (campo `number`); una risposta 404 è `None`, ogni altro errore è
    `ErroreForgia`. Un 404 non si ritenta.
  - `chiusura(n: int) -> tuple[str, datetime] | None`: `None` se l'issue è aperta; altrimenti il motivo come lo dà
    GitHub (`state_reason`: `completed`, `not_planned`, `duplicate`; stringa vuota se manca) e l'ora di chiusura
    (`closed_at`, con fuso). In `ForgiaGh`: `gh api repos/<repo>/issues/<n>` (campi `state`, `state_reason`,
    `closed_at`).
  - `ForgiaFinta`: `crea_issue(..., madre=M)` ricorda la madre; `chiudi_issue(n)` registra l'ora (un orologio
    iniettabile, di serie `datetime.now(timezone.utc)`) e il motivo `completed`; un metodo di sola prova
    `chiudi_come(n, motivo, quando)` per gli altri casi.
- **R2.** `bottega correggi <N>` (modulo nuovo `attrezzi/bottega/correggi.py`, funzione pura `correggi(...)` più
  `argomenti_correggi` e `comando_correggi`, registrati in `__main__.py`):
  - argomenti: `numero`; il testo con `--brief FILE` oppure `--testo "…"` (uno dei due, obbligatorio); `--titolo`
    (di serie `Correzione di #<N>: <prima riga del testo, fino a 60 caratteri>`); `--origine piano|brief|esecuzione`;
    `--consiglio`; `--configurazione`; `--repo`.
  - **il lavoro `M`:** se `board.lavoro(N)` ha uno stato della bottega (campo «Bottega» non vuoto), `M = N`;
    altrimenti `M = forgia.madre_di(N)`, e `M` deve avere uno stato della bottega. Se no: errore, uscita 1, niente
    scritto. Un lavoro `M` chiuso è un errore (uscita 1).
  - **il corpo:** con `--brief` il file com'è; deve avere il suo «Fatto quando» (`brief.fatto_quando`), se no uscita
    2 e niente scritto. Con `--testo` il corpo è il testo, una riga `Corregge: #<N>`, e la sezione «Fatto quando»
    copiata dal corpo di `N`; se `N` non ha un «Fatto quando», uscita 2 con un messaggio che chiede `--brief`.
  - **l'ordine delle scritture:** (1) `forgia.crea_issue(titolo, corpo, madre=M)`; (2) `board.aggiungi(nuovo)`;
    (3) `board.campo(N, "Esito del compito", "corretto")`; (4) con `--origine`, `misure.somma(board, N, "Rilievi del
    piano|del brief|dell'esecuzione", 1)`; con `--consiglio`, `misure.somma(board, N, "Consigli accolti", 1)`;
    (5) `board.campo(M, "Esito", "correzioni")`. Stampa il numero del compito nuovo e la riga
    `poi: bottega lancia <M>`. Uscita 0. Se un passo dopo il primo fallisce: uscita 1, e il messaggio dice che cosa è
    già stato scritto e che cosa manca.
  - Se `N` è `M` (lavoro senza compiti, o tappa intera) l'esito `corretto` va su `N`.
- **R3.** Lo spazzino degli esiti, nel distributore (`distributore.py`, funzione `_scrivi_esiti_dei_chiusi(lavori,
  forgia, board, adesso) -> list[str]`, chiamata in `distribuisci` subito dopo la lettura dell'elenco e prima di
  `_gestisci_evento_commento`; se l'elenco non si è letto, non gira):
  - **candidati:** i lavori dell'elenco con `aperta` falso, uno stato della bottega non vuoto, e la nota senza la
    chiave `esiti`. Al più 10 per giro, dal numero più alto.
  - per ogni candidato: `forgia.chiusura(n)`. `None` (riaperto nel frattempo): salto. Chiuso da più di 7 giorni
    rispetto ad `adesso`: scrive solo la nota `esiti=vecchi`, nessun esito. Motivo `completed` → `unito com'era`;
    `not_planned` → `rifiutato`; ogni altro motivo → nota `esiti=saltati`, nessun esito.
  - **i compiti:** `forgia.sotto_issue(n)`; se non ce ne sono, il compito è il lavoro stesso. L'esito si scrive solo
    ai compiti che nell'elenco hanno «Giri» maggiore di 0 e «Esito del compito» vuoto.
  - alla fine la nota del lavoro prende `esiti=scritti` (le altre chiavi della nota restano: `segni.nota` e
    `segni.scrivi_nota`), e la funzione dà una riga per lavoro: `lavoro <n>: esiti scritti (<k> uniti com'erano, <j>
    già scritti)`.
  - Un errore di forgia o board su un candidato: una riga su stderr, niente nota, si riprova al giro dopo. Non ferma
    mai la distribuzione.
- **R4.** Il segno da solo (`segno.py`):
  - `tocca(board, forgia, numero, env, cartella, adesso) -> list[str]`: se `porta_della_sessione(env)` non dà una
    sessione, non fa niente. Altrimenti: (a) chiude i segni dei lavori chiusi (R5); (b) chiude con `fine` ogni segno
    aperto **da questa sessione** su un lavoro diverso da `numero`; (c) se `numero` non ha un segno, lo apre con
    `inizio`. Un segno aperto da un'altra sessione sullo stesso `numero` resta com'è. Restituisce le righe da
    stampare su stderr. **Non solleva mai:** ogni errore diventa una riga `segno: …` e il comando che l'ha chiamata
    esce come sarebbe uscito.
  - chi la chiama: `comando_lancia` (dopo il lancio riuscito, esito `avviato`; `lancia` prende `--configurazione` e
    costruisce la board come `comando_segui`), `comando_segui` (all'inizio), `comando_correggi` (alla fine, sul lavoro
    `M`). Il numero è sempre quello del **lavoro**, non del compito.
  - `fine` prende un argomento in più, `fino: datetime | None = None` (di serie `adesso`), e **divide**: se
    `compiti` (argomento nuovo, `Sequence[int]`, di serie vuoto) non è vuoto, i token vanno in parti uguali
    (divisione intera, il resto al primo) su «Token di chi decide» dei compiti invece che sul lavoro.
- **R5.** `chiudi_segni_dei_chiusi(board, forgia, env, cartella, adesso) -> list[str]`: per ogni lavoro dell'elenco
  con «Segno» non vuoto e `aperta` falso: `forgia.chiusura(n)` dà l'ora; `fine(..., fino=<ora di chiusura>,
  compiti=<le sotto-issue del lavoro; vuoto se non ne ha>)` con la porta e la sessione scritte nel segno. Se la
  trascrizione non si trova (un'altra macchina) il segno resta aperto e la riga lo dice una volta. Se fra l'inizio
  del segno e l'ora di chiusura non c'è nessun messaggio, il segno si chiude senza numero. La chiamano
  `tocca` e `comando_conti` (prima di leggere i conti; `conti` non scrive nient'altro).
- **R6.** `giro.py`: il commento `compito senza rilettura` diventa `compito senza rilettura: <motivo>`, dove il motivo
  è il perché della scelta quando nessun candidato è scelto (`scelta.perche`), oppure `il lancio del consigliere è
  finito con «<esito>»`.
- **R7.** Nessun campo nuovo nel Project, nessun cambio al contratto dell'adattatore, nessun cambio ai workflow.
- **R9.** Il giro dice dove va il tempo (`giro.py`). Su 55 giri di un progetto vero il passo del giro dura 13 minuti
  di mediana e il log non dice niente fra l'inizio e la fine; da fuori si misura solo che ogni chiamata alla board
  passa dall'adattatore e dura 9-10 secondi, e un giro ne fa una ventina.
  - A fine di ogni fase il giro stampa su stdout `fase <nome>: <secondi> s`, coi nomi fissi `preparazione` (dall'inizio
    al primo lancio dell'esecutore), `esecutore` (i lanci del modello, consulti compresi), `consegna` (patch, controlli,
    spinta, PR), `oracolo`, `rilettura`, `chiusura` (misure, stato, commenti). Una fase che non c'è stata non si stampa.
  - Alla fine, anche su errore, una riga sola: `tempi del giro: totale <s> s; <fase> <s> s, …; board <n> chiamate
    <s> s; forgia <n> chiamate <s> s`.
  - Board e forgia si contano con un involucro che cronometra ogni metodo chiamato, messo all'ingresso del giro: nessun
    cambio ai punti che le chiamano. L'orologio è `time.monotonic`, iniettabile nelle prove.
  - Niente campi nuovi e niente commenti nuovi: solo il log. Il flusso del giro non cambia (stessi esiti, stesse
    scritture, stesso ordine).
- **R10.** Il fascicolo entra nel prompt (`giro.py`). Le misure su 46 giri riusciti di un progetto vero, incrociati
  con le trascrizioni del modello: il 75% del tempo è il modello (mediana 698 s e 69 passi a giro), il 18% il dopo
  (consegna, oracolo, rilettura, misure), il 7% la preparazione. Un passo dura 8,9 s di media qualunque strumento usi
  (una lettura di file 6,8 s): il tempo è la latenza del passo, non il comando. L'85% dei passi è esplorazione (letture
  e ricerche). Oggi il fascicolo sono sei file da leggere, almeno sei passi a giro.
  - Il prompt porta, dopo le istruzioni, i pezzi del fascicolo **per intero**, ognuno sotto un titolo `### <nome del
    file>` e dentro un recinto: nell'ordine `brief.md`, `stato.md`, `costituzione.md`, `quaderno.md`, `lavoro.md`,
    `commenti.md`. I file nella cartella del fascicolo si scrivono come oggi.
  - **I file del brief.** Se il brief ha una sezione `## File` (un elenco puntato di percorsi fra apici inversi,
    relativi alla radice del repo), il giro aggiunge quei file dalla copia dell'esecutore, nell'ordine, dopo i pezzi
    del fascicolo. Entra solo un file regolare, UTF-8, fino a 40 KiB, il cui percorso risolto sta sotto la copia
    risolta e non sotto `.git/` né `.bottega/`. Ogni altro percorso si salta, e il prompt lo dice su una riga
    (`saltato <percorso>: <motivo>`), senza mai il contenuto.
  - **Il tetto:** tutto il prompt sta in 96 KiB (byte UTF-8). I pezzi entrano nell'ordine finché ci stanno; quello
    che non ci sta resta fuori per intero (mai un pezzo troncato) e il prompt lo elenca sotto «Da leggere nel
    fascicolo» (o «Da leggere nel repo» per i file del brief).
  - Il prompt di ripresa dopo un consulto usa la stessa composizione.
  - Il modello del brief (`modelli/brief.md`) prende la sezione `## File`, facoltativa: i file che chi esegue dovrà
    leggere per intero (quelli da cambiare e quelli da imitare); ognuno risparmia almeno un passo.
- **R8.** Le prove nuove usano `BoardFinta` e `ForgiaFinta` (`attrezzi/bottega/finta.py`) e una trascrizione finta
  come in `attrezzi/tests/test_segno.py`. Un caso rosso prima del codice per ogni Ruling.

## Review Focus

Ciò che le prove non coprono e la revisione finale deve guardare:

- lo spazzino non deve mai scrivere su un lavoro **aperto** né sovrascrivere un esito; il limite di 10 e la nota
  `esiti` devono impedire che ogni giro rifaccia le stesse chiamate a GitHub;
- `tocca` dentro `lancia` e `segui`: nessun cambio dei codici d'uscita, nemmeno con board rotta o `gh` assente;
- un segno contato due volte (la stessa finestra su lavoro e compiti) o perso (segno chiuso, somma fallita);
- `correggi` a metà (issue creata, campo non scritto): il messaggio deve bastare a finire a mano;
- R10: nessun percorso della sezione «File» deve poter portare nel prompt un file fuori dalla copia dell'esecutore
  (collegamenti simbolici scritti da un compito di prima, `..`, percorsi assoluti); il tetto in byte;
- la forma vera delle risposte di `gh api` (404 della madre, `state_reason` nullo).

## I compiti

| N | Compito | File | Esegue | Livello e perché |
|---|---|---|---|---|
| K1 | R1: `madre_di` e `chiusura` | `forgia.py`, `finta.py`, `tests/test_forgia.py` | fuori dalla sessione | `medium` |
| K2 | R2: `bottega correggi` | `correggi.py` (nuovo), `__main__.py`, `tests/test_correggi.py` (nuovo) | c.s. | `medium` |
| K3 | R3: lo spazzino degli esiti | `distributore.py`, `tests/test_esiti_b14.py` (nuovo) | c.s. | `medium` |
| K4 | R6: il motivo della rilettura mancata | `giro.py`, `tests/test_rilettura_b14.py` (nuovo) | c.s. | `medium` |
| K5 | R4, R5: il segno da solo | `segno.py`, `lancio.py`, `conti.py`, `correggi.py`, `tests/test_segno_b14.py` (nuovo) | c.s. | `high`: tocca quattro moduli e i codici d'uscita di due comandi |
| K7 | R9: il giro dice dove va il tempo | `giro.py`, `tests/test_tempi_b14.py` (nuovo) | c.s. | `high`: un file di duemila righe con un `try/finally` lungo, e il flusso non deve cambiare |
| K8 | R10: il fascicolo nel prompt | `giro.py`, `brief.py`, `modelli/brief.md`, `tests/test_fascicolo_b14.py` (nuovo) | c.s., dopo K7 | `high`: il contenuto dei file va davanti al modello, e un percorso sbagliato porterebbe fuori i file del runner |
| K6 | skill, pagine, casistica, quaderni, versione 0.2.6 | `plugin/`, `casistica/`, `quaderni/`, `LEGGIMI.md` | chi decide | — |

K1 per primo. K2, K3 e K4 toccano file diversi e partono insieme, ognuno nel suo worktree; si uniscono al ramo della
tappa e si rilancia la prova completa. Poi K5, poi K6.

**Fatto quando** (ogni compito il suo file di prove; la tappa):

```bash
uv run pytest -q
```

## K6: che cosa cambia nei testi

- **Skill, «Le misure»:** il principio di B14, `correggi`, lo spazzino, il segno da solo, il limite noto.
- **Skill, «Come si rivede»:** le correzioni passano da `bottega correggi`.
- **Skill, «Fine della tappa»:** dopo ogni giro di correzioni, una rilettura stretta del solo diff delle correzioni
  da chi non le ha scritte (la lezione più confermata: B4, B5, B6, B8, CICLO-12).
- **Skill, «Quando sì e quando no»** (sezione nuova, dalle decisioni dell'utente che la skill vecchia aveva e questa
  no): manca il piano; causa ignota; il gusto è il prodotto; le modifiche piccole le scrive chi decide quando il brief
  costerebbe più della modifica; due giri del candidato più forte senza soluzione = si torna al piano.
- **Skill, il manuale d'impianto fuori:** i dettagli del sigillo e della CI dei rami `bottega/*` in una pagina
  `impianto.md`, citata; nella skill resta una riga per uno.
- **Pagina della porta Claude Code, «Sotto-agenti»:** come si lavora in sessione (lancio in sottofondo, il prompt di
  tre righe, il consulto allo stesso agente, gli strumenti ereditati che scrivono su sistemi veri).
- **Casistica:** i casi di B12 e B14 (la spinta nel ramo principale senza prove; i compiti in parallelo che si rompono
  a vicenda; il gesto fatto solo per misurare; la rilettura che non gira e nessuno lo sa).
- **Quaderni:** nel quaderno dell'esecutore che pianifica, i token contano anche il giro fallito.
- **Il banco di prova** sulla skill nuova prima dell'unione (sulla 0.2.5: accordo 35 su 35).
