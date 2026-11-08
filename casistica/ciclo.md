# Casistica: il ciclo

### CICLO-1. Un difetto del compito prima

**Scenario:** chi esegue il compito 2 scopre che il compito 1, già unito, ha un difetto piccolo: l'aiuto dei
sottocomandi ripete una parola. Il brief del compito 2 non ne parla.
**Domanda:** che cosa fa chi esegue?
**Opzioni:**
- A) lo corregge con una prova che lo fissa e lo dice nel rapporto
- B) si ferma e chiede a chi decide prima di toccarlo
- C) lo lascia stare, perché è fuori dal brief
**Scelta:** A
**Perché:** è una modifica fuori brief ma sensata, non irreversibile e non tocca segreti né dati veri; il diff e il
rapporto la mostrano a chi rivede.
**Esito:** tenuta; difetto chiuso con la sua prova.
**Fonte:** dal vivo 2026-11-08

### CICLO-2. Una consegna che tocca `.github/`

**Scenario:** un esecutore fuori consegna una patch che corregge un errore vero, ma cambia anche un file in
`.github/workflows/`.
**Domanda:** che cosa succede alla consegna?
**Opzioni:**
- A) il workflow la rifiuta e non spinge niente
- B) il workflow la spinge, e chi decide la guarda per prima
- C) il workflow toglie il file di `.github/` e spinge il resto
**Scelta:** A
**Perché:** l'esecutore non tocca `.github/` né i rami protetti: la consegna lo rifiuta intera, perché lì stanno la
regia e le chiavi ammesse.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-3. Rivedere un compito

**Scenario:** un compito è consegnato con un rapporto lungo e ordinato e un diff di duecento righe.
**Domanda:** da dove comincia la revisione?
**Opzioni:**
- A) dal rapporto, che riassume le scelte
- B) dal diff, poi il rapporto
- C) dalle prove: se sono verdi basta il rapporto
**Scelta:** B
**Perché:** prima il diff, per non vedere il codice con gli occhi di chi l'ha scritto; poi il rapporto.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-4. Un compito che chiede giudizio

**Scenario:** un compito deve scegliere il formato di una data in un file che altri compiti leggeranno. La scelta si
può fare oggi, ma nessuno l'ha scritta nel piano.
**Domanda:** a chi va il compito?
**Opzioni:**
- A) al candidato più forte, perché c'è giudizio
- B) chi decide scrive il formato nel piano come Ruling e il compito resta all'esecutore economico
- C) all'esecutore economico, che sceglie e lo scrive come Ruling
**Scelta:** B
**Perché:** il giudizio che si può scrivere prima va nel piano: è ciò che rende sufficiente un esecutore economico, e
un'interfaccia che altri compiti usano non si lascia a chi esegue.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-5. Quota finita a metà tappa

**Scenario:** l'esecutore fuori ha fatto due compiti di una tappa di cinque; al terzo la sua bottega dice «quota
esaurita».
**Domanda:** che cosa fa il distributore?
**Opzioni:**
- A) passa subito il terzo compito al candidato seguente
- B) tiene il compito a quell'esecutore per un giro; se la quota manca ancora, passa al candidato seguente
- C) segna il lavoro «bloccato» e lo passa a chi decide
**Scelta:** B
**Perché:** chi ha fatto i primi compiti conosce il ramo; un giro di attesa costa poco. Il seguente, se serve,
riparte dal ramo e dalle note.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-6. L'etichetta contro la scelta viva

**Scenario:** un lavoro porta l'etichetta `esegue: <nome>`, ma i conti dicono che un altro candidato costerebbe meno.
**Domanda:** chi lo esegue?
**Opzioni:**
- A) il candidato dell'etichetta
- B) il candidato che costa meno
- C) il candidato dell'etichetta solo se ha quota abbondante
**Scelta:** A
**Perché:** a mano vince l'etichetta; il risultato conta comunque nei numeri della scelta viva.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-7. Rilievi gravi nati dal piano

**Scenario:** la revisione finale trova tre rilievi gravi. Il codice fa esattamente ciò che il piano chiedeva: era il
piano a non prevedere quei casi.
**Domanda:** a quale origine si contano?
**Opzioni:**
- A) esecuzione, perché il codice è di chi ha eseguito
- B) piano
- C) brief
**Scelta:** B
**Perché:** i rilievi si contano per origine; se l'esecutore ha fatto ciò che il piano diceva, l'errore è del piano, e
il prossimo piano lo corregge lì.
**Esito:** corretti con una prova ciascuno; il controllo della storia rimandato al cancello giusto.
**Fonte:** dal vivo 2026-11-08

### CICLO-8. La quota di chi decide finisce a fine tappa

**Scenario:** la tappa è finita, le prove sono verdi, ma la quota di chi decide è quasi finita e non basta per la
revisione finale.
**Domanda:** che cosa si fa?
**Opzioni:**
- A) si salta la revisione finale e si unisce, visto che le prove sono verdi
- B) la tappa resta aperta; un sostituto con quota può rivedere e segnare l'esito, l'unione aspetta chi decide
- C) il sostituto rivede e unisce
**Scelta:** B
**Perché:** la revisione finale non si taglia; il sostituto rivede ma non unisce: l'unione è il sigillo di chi decide.
**Esito:** da vedere.
**Fonte:** deciso dall'utente

### CICLO-9. Un'issue scritta di getto

**Scenario:** l'utente apre un'issue di una riga, «la pagina delle misure è lenta», e la mette nel Project fra i
lavori pronti.
**Domanda:** che cosa succede?
**Opzioni:**
- A) il distributore la dà a un esecutore fuori, che indaga
- B) nessun esecutore la prende: chi decide la trasforma in un compito con brief e «Fatto quando»
- C) un consigliere scrive il brief e l'esecutore parte subito
**Scelta:** B
**Perché:** le issue senza brief nessun esecutore le prende; chi decide le trasforma prima in compiti.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-10. Le prove secondo il modello

**Scenario:** un esecutore fuori consegna e scrive nel rapporto «tutte le prove verdi». Il «Fatto quando» lanciato dal
workflow esce 1.
**Domanda:** che cosa vale?
**Opzioni:**
- A) il rapporto del modello, se il diff sembra giusto
- B) l'esito del «Fatto quando» lanciato dal workflow
- C) si rilanciano le prove a mano e si decide
**Scelta:** B
**Perché:** l'oracolo lo esegue il workflow, non il modello: ciò che il modello dice delle sue prove non conta.
**Esito:** da vedere.
**Fonte:** di chi decide
