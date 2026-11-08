# La casistica

Precedenti, non regole: casi veri o pensati, con la scelta presa e il perché. La skill vince sempre; quando un caso e
la skill non vanno d'accordo, chi decide corregge l'uno o l'altro.

## Il formato

Un file per area: `casistica/<area>.md` (l'area in minuscolo). Ogni caso è una sezione così:

```markdown
### CICLO-1. Titolo breve

**Scenario:** che cosa succede, in due o tre frasi.
**Domanda:** che cosa si fa?
**Opzioni:**
- A) prima opzione
- B) seconda opzione
- C) terza opzione
**Scelta:** B
**Perché:** la ragione, in una o due frasi.
**Esito:** com'è andata, o «da vedere».
**Fonte:** dal vivo AAAA-MM-GG
```

- L'identificativo comincia con l'area del file in maiuscolo e prosegue la numerazione dell'area.
- La **scelta** è una lettera fra le opzioni: così il banco di prova confronta senza modello.
- La **fonte** è `deciso dall'utente`, `dal vivo AAAA-MM-GG` o `di chi decide`.
- Un caso che parla di un progetto resta nel progetto, non qui.

`python3 -m bottega casi` controlla il formato; `python3 -m bottega casi --domande` stampa i casi senza scelta, perché
ed esito: è il foglio del banco di prova.

## Quando si aggiunge un caso

A fine tappa, per ogni caso che la skill e la casistica non coprivano: un Ruling rifiutato, un rilievo grave, un
esecutore che ha fallito, una scelta fatta a giudizio. Si aggiunge con una PR.
