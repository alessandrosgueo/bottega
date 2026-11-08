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
