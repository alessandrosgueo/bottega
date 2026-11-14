# Casistica: le porte

### PORTE-1. Le istruzioni del repo dentro il plugin

**Scenario:** una porta carica come regola l'`AGENTS.md` alla radice di ogni plugin installato. Alla radice del repo
del plugin c'è un `AGENTS.md` scritto per chi sviluppa il plugin stesso.
**Domanda:** che cosa si fa?
**Opzioni:**
- A) si svuota l'`AGENTS.md` della radice
- B) il plugin va in una sua sottocartella, separato dai file di sviluppo
- C) si toglie l'`AGENTS.md` dal repo
**Scelta:** B
**Perché:** le istruzioni per chi sviluppa servono a chi lavora sul repo; quelle del plugin arrivano in ogni progetto
di chi lo installa. Tenerle in cartelle diverse le serve tutte e due.
**Esito:** il plugin sta in `plugin/`; i marketplace alla radice puntano lì.
**Fonte:** dal vivo 2026-11-08

### PORTE-2. I crediti finiti senza la parola «quota»

**Scenario:** a metà di una revisione la porta Antigravity si ferma: nel JSON `status` è `ERROR` e `error` dice
«Your AI credits balance is too low to continue.»; la parola «quota» e il 429 stanno solo in stderr.
**Domanda:** come la riconosce la porta?
**Opzioni:**
- A) è un errore: tentativo in più
- B) è quota: la bottega aspetta il rinnovo
- C) si cerca «quota» anche nella risposta del modello
**Scelta:** B
**Perché:** sono crediti esauriti, cioè quota; un tentativo in più consumerebbe tre giri per niente. La risposta del
modello resta fuori (RV16): la frase si aggiunge alle parole cercate nei campi d'errore.
**Esito:** «credits balance» fra le parole della quota di Antigravity; la prova usa l'uscita vera.
**Fonte:** dal vivo 2026-11-08

### PORTE-3. Quote separate dentro lo stesso abbonamento

**Scenario:** una porta (Antigravity) divide i modelli in tre gruppi con quote indipendenti. Con una sola quota
per bottega, un 429 su un gruppo ferma anche i modelli degli altri due.
**Domanda:** come si modellano le quote separate nella configurazione?
**Opzioni:**
- A) tre botteghe separate, una per gruppo di modelli
- B) una bottega sola con i secchi (`quote`) e ogni candidato sul suo secchio (`quota`)
- C) una bottega sola, spegnendo a mano i candidati del gruppo esaurito
**Scelta:** B
**Perché:** una bottega resta un abbonamento e tiene un lavoro alla volta per abbonamento, ma un 429 ferma solo i
candidati del secchio esaurito.
**Esito:** da vedere
**Fonte:** deciso dall'utente

### PORTE-4. Il consigliere che risponde vuoto

**Scenario:** alla domanda dell'esecutore risponde il consigliere, in sola lettura. Il modello tenta un comando, che
la sola lettura nega, e chiude con una risposta vuota. Il giro pubblica come risposta l'uscita grezza della porta, il
JSON, e il lavoro va in attesa di chi decide.
**Domanda:** che cosa vale una risposta vuota del consigliere?
**Opzioni:**
- A) un consiglio: l'esecutore riparte
- B) nessuna risposta: la domanda passa a chi decide, e il commento lo dice in chiaro invece di mostrare il JSON
- C) si rilancia il consigliere finché risponde
**Scelta:** B
**Perché:** una risposta vuota non decide niente, e rilanciare spende quota scarsa. Il giro passa già la domanda a chi
decide, perché la risposta non comincia con `RISPOSTA`.
**Esito:** minore aperto: la porta passa al giro l'uscita intera quando la risposta è vuota, e il commento mostra il
JSON.
**Fonte:** dal vivo 2026-11-14
