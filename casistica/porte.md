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
