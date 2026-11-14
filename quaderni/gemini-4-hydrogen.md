# Gemini 4 Hydrogen

Modello di Google, Lavorante da Antigravity (`agy -p`, senza mani) dalla tappa B12 (2026-11-14), al posto di Gemini 3.8
Flash. Un candidato per livello (`low`, `medium`, `high`, `xhigh`), tutti con questo quaderno (`quaderno =
"gemini-4-hydrogen"`).

- Il livello si sceglie per compito, partendo da `medium`: `low` basta per una correzione dettata riga per riga (52k
  token, B12-RV), `medium` per documenti e correzioni piccole (86-98k, B12.3 e B12.2-C1), `high` per una ricognizione
  o un modulo nuovo (140-407k, B12.0 e B12.1), `xhigh` solo per il codice più delicato (455k, B12.2). Circa 100k token
  costano un punto della finestra di cinque ore della quota Gemini (B12).
- Lancia le prove come attività in sottofondo e scrive «attendo l'esito»: in B12 le ha aspettate davvero, ma il brief
  continua a chiedere le prove in primo piano (B12.1, B12.2).
- Davanti a una prova che dice la regola superata non la cambia e si ferma con `DOMANDA PER CHI DECIDE:` (B12.2-C1): il
  brief dice quali prove può toccare.
- Una ricognizione esatta (17 domande su 17, righe giuste) ma con righe oltre le 120 colonne: il brief dà il comando
  per controllarle (`awk 'length > 120' <file>`) (B12.0).
- A `medium` porta a termine al primo giro un compito dettato dai Ruling su uno o due moduli, con le sue prove
  (74-117k token, 2-4 minuti: B14.K1-K4); `high` per un compito che tocca quattro moduli o un file di duemila righe
  (237-267k token, 5-8 minuti: B14.K5, K7). Tre compiti `medium` su file diversi, in parallelo in tre worktree, si
  sono uniti senza rompersi (B14).
- Non pensa al costo di ciò che chiama: in B14.K5 leggeva tre volte l'elenco della board per comando. Se una chiamata
  è lenta nel mondo vero, il brief lo dice col numero («una lettura dell'elenco dura secondi: una sola») (B14.K5).
