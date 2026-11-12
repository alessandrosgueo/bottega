# Claude Sonnet 5.5

Modello di Anthropic, usato come capobottega in sessione (effort `high`) e come rilettore stretto dal 2026-11-08.

- Il brief gli lascia esplicitamente il fermo davanti a una contraddizione fra brief e vincoli del progetto: lo usa
  prima di scrivere codice, con le opzioni e il loro costo (CICLO-26, dal vivo 2026-11-12).
- Davanti a un divieto del brief che impedisce la correzione scrive le prove ferme e una bozza invece di rompere il
  divieto: chi decide controlla prima dove vive il codice (CICLO-25, dal vivo 2026-11-12).
- Se la riga rossa prima del codice conta, il brief la chiede per nome: senza, può scrivere il codice prima delle prove
  e compensare con mutanti (dal vivo 2026-11-12).
- Aggiunge regole più prudenti del piano e le scrive come Ruling: la revisione le legge una per una (dal vivo
  2026-11-12).
- Come rilettore stretto del diff delle correzioni trova i difetti introdotti dalle correzioni stesse: dopo ogni giro
  di correzioni una rilettura sua (B4, B5, B6, B9).
