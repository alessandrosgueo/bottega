# B12: secchi di quota, candidati di riserva, livello per compito

Data: 2026-11-14. Disegno breve, nato dal brainstorming col signore dopo l'arrivo di Gemini 4 Hydrogen e di
Orchestrator (Argon) in Antigravity. Il secondo progetto (le tappe intere con l'Orchestrator) viene dopo questo.

## Il perché

Un abbonamento può avere più quote separate: Antigravity ne ha tre («Gemini Models», «Gemini 4 Argon», «Claude and GPT
models»). La bottega ne conosce una per bottega, quindi un 429 di un modello ferma anche gli altri gruppi: il 2026-11-12
la quota Gemini finita ha spento Flash e Argon e costretto a passare a Sonnet a mano. Insieme a questo il signore vuole
usare il modello nuovo (Hydrogen) come esecutore predefinito, sceglierne il livello compito per compito e imparare dai
numeri, e tenere i modelli di scorta solo come riserva.

## Obiettivi

- Una quota finita ferma solo i candidati del suo secchio; la bottega va avanti con gli altri.
- Un candidato può stare in configurazione solo come riserva: mai scelto per esplorare.
- Chi decide sceglie il livello dell'esecutore per un compito; le misure dicono com'è andato ogni livello.
- La configurazione di Jarvis passa a Hydrogen, coi ruoli decisi.

## Non obiettivi

- Le tappe intere con l'Orchestrator (progetto 2).
- Un concetto di «livello» dentro la bottega (strada A, scartata).
- Leggere la data di rinnovo vera della quota (oggi un 429 vale un'ora): resta com'è.

## Vincoli

- Sola libreria standard; il repo è pubblico (costituzione); la skill non nomina modelli né fornitori, le pagine per
  porta sì.
- Una configurazione scritta prima di B12 resta valida e si comporta come oggi.

## Le strade considerate

- **Quote separate.** Tre botteghe (una per quota, solo configurazione: la PR Jarvis #632, già pronta), una bottega con
  i secchi (codice nuovo), oppure una bottega spegnendo i candidati a mano. **Scelta del signore: i secchi**, perché una
  bottega resta un abbonamento e un lavoro alla volta per abbonamento.
- **Livello per compito.** A: il livello come concetto della bottega (livelli ammessi sul candidato, «Livello:» nel
  corpo del compito, ogni porta lo traduce, campo nuovo nel Project). B: un candidato per livello, i livelli diversi
  dal predefinito di riserva, scelti da chi decide con l'etichetta `esegue:` che esiste già. **Scelta del signore: B**:
  nessun concetto nuovo, misure e conti già divisi per esecutore.

## Le decisioni

1. **Secchi** (proposta di chi decide, non discussa nel dettaglio). Una bottega può avere
   `quote = { <secchio> = "scarsa|normale|abbondante", … }` al posto di `quota = "<peso>"`; con `quote` ogni candidato
   della bottega dice `quota = "<secchio>"`. La variabile della quota di un secchio è
   `BOTTEGA_QUOTA_<BOTTEGA>__<SECCHIO>` (due trattini bassi, perché non si scontri con una bottega dal nome composto);
   la bottega col vecchio `quota = "<peso>"` è un secchio solo, con la variabile di oggi `BOTTEGA_QUOTA_<BOTTEGA>`. Il
   peso nella scelta viva è quello del secchio del candidato. Un 429 (dell'esecutore o del consigliere) segna il
   secchio del candidato che l'ha preso.
2. **Riserva.** `riserva = true` su un candidato: la scelta viva lo considera solo se nessun candidato normale della
   stessa funzione ha quota; l'etichetta `esegue:` lo sceglie sempre.
3. **Livello** (strada B). Un candidato per livello; il livello predefinito è un candidato normale, gli altri sono di
   riserva; chi decide sceglie con `esegue: <nome>`. Il nome dice il livello («Lavorante Hydrogen xhigh»).
4. **Quaderno in comune.** Chiave facoltativa `quaderno = "<nome>"` sul candidato; senza, vale lo slug del modello come
   oggi.
5. **Jarvis** (scelte del signore). Bottega `google` coi secchi `gemini` (abbondante), `argon` (scarsa), `claude`
   (scarsa). Eseguono Lavorante Hydrogen (high, normale) e i livelli low, medium, xhigh (riserva); Flash esce (il suo
   quaderno resta); Sonnet 5.5 a `low` di riserva. Rivedono e consigliano Maestro Argon (normale) e Opus 5.5 via
   Antigravity (riserva). Un solo workflow dell'esecutore, `bottega-esecutore-google.yml`. La PR #632 (tre botteghe) si
   chiude senza unire; il Task #631 passa a questo lavoro.
6. **Documenti.** Il commit `ff77d4a` («una bottega per quota») si corregge: skill, `INSTALLA.md`, modello di
   configurazione e pagina della porta Antigravity parlano di secchi. La pagina della porta tiene i fatti nuovi (modelli
   della 1.5.8, ordine di `-p`, `/quota` senza mani).
7. **Rilascio.** Versione `0.2.4` della bottega e `bottega aggiorna` in Jarvis (i workflow sono fissati allo SHA del
   tag). Il `lavorante.sh` locale di chi decide passa a `gemini-4-hydrogen-high` di serie.
8. **Esecuzione con la bottega**, coi compiti al Lavorante Hydrogen; il livello di ogni compito lo sceglie chi decide e
   va nelle misure del piano.

## Lasciato a chi costruisce

Nomi interni, testo dei messaggi d'errore della configurazione, ordine dei controlli, forma delle prove.
