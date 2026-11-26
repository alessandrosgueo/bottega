# Gemini 4 Neon (high)

Modello di Google, usato da Antigravity (`gemini-4-neon-high`) per piani, brief, critiche e revisioni sullo stesso
secchio Gemini (pesa circa il doppio di Hydrogen per token) dalla tappa B15 (2026-11-26).

- Nelle revisioni di compito e finali apre la risposta con le tre righe `VERDETTO:`, `GRAVI:`, `MINORI:` per rendere
  leggibile l'esito in automatico (B15).
- Nelle bozze di piano di notte tocca solo file in `docs/plans/*.md` e nessun file di codice: il controllo meccanico
  sul diff rifiuta qualsiasi modifica fuori da quella cartella (B15).
- Nel ruolo di revisore/costruttore completa un controllo in circa 2 minuti e 161k token (B15).
