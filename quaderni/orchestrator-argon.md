# Orchestrator (Argon)

Modalità di Antigravity (`agy -p … --model gemini-pro-orchestrator-g1-pro`): Gemini 4 Argon pianifica, ripianifica e
controlla, Gemini 4 Hydrogen esegue, in un solo agente e con un livello fisso. Si usa per le tappe intere dal piano
(candidato `su_richiesta = true`, `tempo` lungo) dalla tappa B13 (2026-11-14).

- Una tappa intera dal piano (B13: due compiti, codice, prove e documenti, 10 file): 14 minuti e mezzo, 624k token,
  5 punti della quota settimanale di Argon e circa 4 della finestra di cinque ore della quota Gemini; nessun rilievo
  grave alla revisione. Il brief della tappa è il corpo del lavoro, poche righe (B13).
- Ha letto da sé le lezioni della tappa prima nel piano e nei documenti (i nomi di modello vietati nelle pagine delle
  porte) senza che il brief le ripetesse (B13): il brief della tappa nomina il piano della tappa prima.
- Sui compiti piccoli non conviene: sullo stesso bug 56 s e 48k token contro 33 s e 27k di Hydrogen da solo (B12).
