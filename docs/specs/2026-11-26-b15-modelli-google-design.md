# B15 — La bottega coi modelli Google di novembre (design)

## 1. Perché

A novembre 2026 Antigravity ha cambiato la famiglia Gemini 4. **Hydrogen** (12/11) è l'esecutore veloce. **Neon**
(18/11) sta sugli indici indipendenti alla pari di Opus 5.5 o sopra, a circa un terzo del costo per prova. **Carbon**
(10/11) è il più forte sul codice a lungo orizzonte, ma è lento e dal 1/12 costa il doppio. **Argon** esce il 30/11.
L'**Orchestrator** mette un pianificatore a scelta (Neon, Carbon od Opus) sopra un esecutore (Hydrogen). Tutti i
Gemini pescano da un solo secchio di quota, a tariffe API: Neon pesa circa il doppio di Hydrogen per token.

Il signore (26/11, notte): «non dobbiamo solo sostituire. hanno aggiunto carbon e neon, dobbiamo capire e migliorare
il sistema di conseguenza»; poi, nel modulo: Neon scrive e Opus firma, «ma comunque dobbiamo usare al massimo anche la
quota di gemini»; per i lavori non delicati bastano prove verdi e revisione di Neon, per categorie; si fanno sia gli
attrezzi della sessione (A) sia la tappa nel plugin (B) («a e b»).

Il dato che pesa: decidere costa più che eseguire (B14: 4,0 milioni di token contro 2,4). La notte del 25/11 i
quattro piani scritti da agenti Opus sono costati circa 2 milioni di token di quota Claude.

## 2. Obiettivi, non obiettivi, anti-obiettivi

**Obiettivi**
- La quota Claude, scarsa, si spende solo dove serve Opus: domande al signore, decisioni, firme, revisioni delicate.
- La quota Gemini, abbondante, si usa fino in fondo: ciò che non si spende entro il rinnovo settimanale è perso.
- La qualità di ciò che entra nel ramo principale non scende: lo dicono le misure, non le impressioni.

**Non obiettivi**
- Cambiare le quattro barriere (segreti, dati veri, cancellazioni, azioni irreversibili o verso l'esterno).
- Usare Sonnet (escluso dal signore) o modelli fuori dal catalogo di Antigravity.
- Spostare il sigillo: firma e unione restano di chi decide (Opus).

**Anti-obiettivi** (fallimento anche se funziona)
- Opus che passa le giornate a rileggere i diff di Gemini: il risparmio si mangia da solo.
- Un difetto nel cuore, nella sicurezza o nella produzione del server entrato con la sola revisione di Neon.
- La quota Gemini finita a metà settimana, senza esecutori per i lavori urgenti.
- Costi che non si vedono: ogni giro deve lasciare token, punti di quota, minuti ed esito.

## 3. Vincoli

- `agy` 1.5.17: i nomi `gemini-4-neon-high` e `gemini-pro-orchestrator-neon` rispondono (provati il 26/11);
  `gemini-pro-orchestrator-g1-pro` (Argon) no. L'Orchestrator ha un livello fisso (niente `--effort`).
- `agy -p /quota` mostra due gruppi: «Gemini Models» (settimana e cinque ore) e «Claude and GPT models».
- Hydrogen a `xhigh` costa per compito quanto Neon e risponde lento: in sessione si usa `high`, nella bottega `medium`.
- Il repo `alessandrosgueo/bottega` è pubblico: pubblicare una versione nuova lo chiede il signore, ogni volta.
- Il Lavorante non ha chiavi di GitHub, non unisce e non tocca il ramo principale né `.github/`.

## 4. Gli approcci

| | Che cosa | Pro | Contro |
|---|---|---|---|
| A | Attrezzi delle sessioni del maestro (`~/.cache/bottega-maestro`) | Subito, nessuna pubblicazione | Vale solo quando c'è il maestro |
| B | Tappa B15 nel plugin: distributore, configurazione, esiti | Lavora anche di notte e per ogni progetto | Più lavoro, pubblicazione da chiedere |
| A e B | A subito, B scritta sulle misure di A | Gemini lavora da oggi, B non nasce alla cieca | Due posti da tenere allineati per qualche giorno |

**Scelta del signore: A e B.** A parte subito; B si pianifica in parallelo e si costruisce dopo le prime misure.

## 5. Il disegno

### 5.1 Chi fa che cosa

| Funzione | Chi | Livello |
|---|---|---|
| Domande al signore, decisioni, firma e unione | Opus (chi decide) | — |
| Piani, brief, critiche dei piani, indagini | Neon | `high` |
| Tappe intere dal piano | Orchestrator Neon | fisso |
| Eseguire | Hydrogen | `medium` di serie (bottega), `high` in sessione |
| Revisione dei lavori non delicati | Neon | `high` |
| Revisione finale del delicato (cuore, sicurezza, produzione del server) | Opus | — |
| Seconda opinione su un lavoro lungo e rischioso | Carbon (Orchestrator) | fisso, solo su richiesta |

Opus legge ogni piano scritto da Neon prima di lanciarlo e ne risponde: Neon scrive, Opus firma (scelta del signore).

### 5.2 La scala sui fallimenti

Un compito il cui «Fatto quando» resta rosso, o la cui revisione trova un difetto grave, sale di un gradino:
Hydrogen `medium` → Hydrogen `high` → Neon `high` → Orchestrator Carbon → chi decide. Ogni gradino ha **un**
tentativo, riparte dal ramo e dalle note del gradino prima, e lascia la sua misura. Al gradino di chi decide il
problema è il piano (regola di oggi: «due giri del candidato più forte non risolvono → si torna al piano»).

### 5.3 Il ritmo della quota Gemini

Il ritmo è la quota settimanale spesa confrontata col tempo passato dal rinnovo. Se la quota spesa resta indietro di
oltre una soglia, la bottega pesca da sola dalla board un lavoro pronto, in quest'ordine (proposta del maestro):
1. debiti e bug con un «Fatto quando» e un'area non delicata;
2. prove mancanti segnate dalle revisioni;
3. documenti confrontati col codice (guide che dicono una cosa che il codice non fa più).

Si ferma quando la quota a cinque ore scende sotto una riserva per i lavori urgenti. Non prende mai lavori che
aspettano il signore, design, o lavori nel delicato.

### 5.4 L'unione per categorie

Una PR è **non delicata** se tocca solo file di categorie ammesse: documenti, prove, strumenti di sviluppo (quelli che
non girano in produzione), quaderni, debiti minori. È **delicata** se tocca anche un solo file del cuore (`tronco/`),
della casa (`homeassistant/`, `servizio/`), della produzione del server (`strumenti/casa/server/`, `prepara.py`), di
`.github/`, o se la revisione la segna come sicurezza.

- **Non delicata:** si unisce con prove verdi, revisione di Neon senza rilievi gravi, gitleaks e salute verdi. Opus
  firma leggendo il verdetto e l'elenco dei file, non il diff.
- **Delicata:** come oggi, Opus rilegge il diff.

L'elenco delle categorie è nella configurazione del progetto, non nel plugin: ogni progetto ha il suo.

### 5.5 Le misure

Ogni giro lascia: modello e livello, token, punti di quota (settimana e cinque ore), minuti, esito del «Fatto
quando», rilievi della revisione per gravità, gradino della scala. La scelta viva ne tiene conto per genere di
compito. Dopo due settimane il maestro rilegge i numeri: se Neon come pianificatore o come revisore fa entrare più
difetti di Opus, si torna indietro su quella funzione.

### 5.6 A: gli attrezzi delle sessioni

In `~/.cache/bottega-maestro`:
- il Lavorante (`lavorante.sh`) usato anche con Neon, per piani, brief, critiche e revisioni in sola lettura;
- un comando del ritmo che legge `agy -p /quota` e dice se lanciare un riempitivo e quale;
- `unisci.sh` con il controllo delle categorie: per una PR non delicata vuole il verdetto di Neon accanto, per una
  delicata la rilettura del maestro.

### 5.7 B: la tappa B15 nel plugin

- Il ruolo «pianificare» nella configurazione: un candidato che scrive piani e brief, e che chi decide approva.
- La scala dei fallimenti e il ritmo della quota nel distributore.
- L'esito «pronta per l'unione» con la categoria, e le categorie nella configurazione del progetto.
- I quaderni di Neon e dell'Orchestrator Neon; Argon segnato come uscito.
- Pubblicazione della versione nuova solo col permesso del signore.

### 5.8 Le scelte dopo il controllo del costruttore

Il controllo del costruttore l'ha fatto Neon (26/11, 2 minuti, 161k token). Le risposte:

1. **Piani di notte (signore, «sì, anche nel delicato»).** Di notte la bottega prende anche le issue senza piano, in
   ogni area, cuore e sicurezza compresi, e Neon ne scrive una bozza di piano in una PR in bozza. Al mattino chi
   decide la legge e la approva o la scarta; nessun codice parte prima dell'approvazione. Tetto proposto dal maestro:
   tre bozze in attesa alla volta.
2. **La scala (maestro).** Si dichiara in `bottega.toml` come elenco ordinato di candidati della funzione `eseguire`
   (per esempio `scala = ["hydrogen", "hydrogen-high", "neon", "orchestratore-carbon"]`): il plugin non nomina modelli.
   La scelta viva sceglie il primo gradino; `esegue:` lo forza; un candidato `su_richiesta` entra nella scala solo se
   la scala lo nomina. Un rilievo grave della rilettura nel giro diventa bloccante: il compito non si chiude e sale di
   gradino. Il tetto di oggi di tre tentativi uguali diventa un tentativo per gradino.
3. **I riempitivi (maestro).** Il ritmo si guarda a ogni giro del distributore, di giorno e di notte. I riempitivi
   sono issue che esistono già, di un comandante, con un «Fatto quando» e l'etichetta di un'area non delicata: la
   bottega non le inventa. L'area è il criterio prima del diff; all'unione conta il diff vero, e se tocca il delicato
   la PR passa a chi decide.
4. **Quota e misure (maestro).** Il giro, dopo ogni compito, scrive i punti di quota letti da `agy -p /quota` in una
   variabile di GitHub Actions, che il distributore legge: il runner non chiama `/quota` a ogni giro. Gradino, punti e
   rilievi per gravità vanno nel commento di consegna e nel registro della bottega, non in campi nuovi del Project,
   così il contratto dell'adattatore non cambia. Le misure contano il compito per gradino: un compito toccato da più
   gradini dà una misura a ciascuno.
5. **«Pronta per l'unione» (maestro).** La scrive un passo finale del giro sull'intero diff del ramo: rilettura di
   Neon (funzione `rivedere`), poi `Esito = pronta per l'unione` con la categoria. Le categorie sono un elenco stretto
   di percorsi ammessi: un file fuori elenco rende la PR delicata; anche le etichette `bottega: prove cambiate` e
   `bottega: segreti` la rendono delicata. Gitleaks e salute restano controlli di chi unisce (`unisci.sh`).
6. **A e B (maestro).** Due consegne separate in un piano unico: A negli attrezzi delle sessioni
   (`lavorante.sh` e `unisci.sh` esistono già e si estendono, più il comando del ritmo), B nel plugin. A non aspetta B.

## 6. Lasciato a chi costruisce

Le soglie esatte del ritmo (quanto indietro, quanta riserva a cinque ore), l'ordine di dettaglio dei riempitivi, il
formato del verdetto di Neon, l'elenco preciso dei percorsi delle categorie per Jarvis, i nomi dei comandi nuovi.
