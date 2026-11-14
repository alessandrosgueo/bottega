# B13: le tappe intere

Data: 2026-11-14. Disegno breve del secondo progetto deciso col signore il 2026-11-14: l'**Orchestrator (Argon)** di
Antigravity, che sta al livello di Argon, riceve una tappa intera dal piano di chi decide. Il signore ha dato
l'autonomia fino alla fine dei due progetti: le scelte di questo disegno sono di chi decide, segnate come tali.

## Il perché

Oggi chi decide scrive il piano e poi un brief per ogni compito: è lavoro della sua quota, la più cara. Un esecutore
che pianifica da sé (l'Orchestrator: Argon divide il piano in passi e lo ripianifica quando qualcosa non torna, Hydrogen
esegue, Argon controlla i progressi) può ricevere il piano intero e consegnare la tappa in un giro solo. Chi decide
rivede alla fine, come sempre. La prova del 2026-11-14 (stesso bug: Orchestrator 56 s e 48k token contro Hydrogen 33 s e
27k, stessa correzione) dice che sui compiti piccoli non conviene: conviene sulla tappa, dove risparmia i brief.

## Obiettivi

- Chi decide può dare una tappa intera a un esecutore scelto, con un lavoro senza sotto-issue.
- Un esecutore riservato alle tappe intere non viene mai preso dalla scelta viva per un compito qualsiasi.
- Un giro può durare quanto serve a una tappa, entro il tempo del job.

## Non obiettivi

- Un tipo di lavoro nuovo con un suo flusso (Argon che divide nel distributore): l'Orchestrator lo fa già dentro di sé.
- Cambiare la rilettura del consigliere o la revisione di chi decide.

## Le strade considerate (scelta di chi decide)

- **A. Nessun tipo nuovo:** la tappa intera è un lavoro senza sotto-issue (il giro lo tratta già come compito
  singolo, `giro.py:1036-1047`) col piano come brief e l'etichetta `esegue:`. Servono due chiavi del candidato
  (`su_richiesta`, `tempo`). **Scelta**: è la più piccola e usa ciò che c'è.
- B. Un tipo «tappa» con un flusso suo nel distributore: rifà quello che l'Orchestrator fa da sé.
- C. Solo in sessione (`lavorante.sh` col modello dell'Orchestrator): niente lavori fuori né notte.

## Le decisioni (di chi decide)

1. **`su_richiesta = true`** sul candidato (booleano, di serie falso): la scelta viva non lo considera mai, né per
   esplorare né come riserva; lo sceglie solo l'etichetta `esegue:`. Insieme a `riserva = true` è un errore di
   configurazione (non avrebbe senso).
2. **`tempo = <minuti>`** sul candidato (intero da 5 a 270, di serie 60): il tempo massimo di un lancio dell'esecutore.
   Il job dell'esecutore ha `timeout-minutes: 300`: 270 lascia mezz'ora all'oracolo e alla consegna.
3. **Il brief della tappa intera** è il corpo del lavoro: il percorso del piano nel repo, le sezioni da eseguire, il
   «Fatto quando» della tappa. Un modello del corpo sta nella skill.
4. **Documenti**: la skill spiega la tappa intera (senza nomi di modelli); la pagina della porta Antigravity spiega
   l'Orchestrator (che cosa fa, quota di Argon, niente `--effort`); `quaderni/` nulla finché non ci sono lezioni.
5. **Jarvis**: candidato `orchestratore` (`gemini-pro-orchestrator-g1-pro`, secchio `argon`, `su_richiesta = true`,
   `tempo = 240`, funzione `eseguire`).
6. **Collaudo**: il codice di B13 lo esegue l'Orchestrator stesso, in sessione, come tappa intera dal piano B13; poi un
   lavoro fuori vero in Jarvis, piccolo e con un oracolo meccanico, lanciato con `esegue: Orchestratore Argon`.

## Lasciato a chi costruisce

Nomi interni, messaggi d'errore, forma delle prove.
