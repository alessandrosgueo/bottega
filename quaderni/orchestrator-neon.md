# Orchestrator (Neon)

Modalità di Antigravity (`agy -p … --model gemini-pro-orchestrator-neon`): Gemini 4 Neon pianifica, ripianifica e
controlla, Gemini 4 Hydrogen esegue, in un solo agente e con un livello fisso (senza `--effort`), sullo stesso secchio
Gemini. Si usa per le tappe intere dal piano (`su_richiesta = true`, `tempo` lungo) dalla tappa B15 (2026-11-26), al
posto di `orchestrator-argon` (uscito).

- Eredita lo schema di lavoro di `orchestrator-argon` per le tappe intere dal piano: un candidato con
  `su_richiesta = true` e `tempo` lungo, senza `--effort` (B15).
- Condivide lo stesso secchio Gemini del modello che pianifica e di quello che esegue: un esaurimento del secchio ferma
  l'intero gruppo (B15).
