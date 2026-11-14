# Modello del brief

Il brief è il corpo dell'issue del compito, in sessione come fuori. Riempi le parti fra `<…>` e togli le sezioni che
non servono, mai «Cosa conta di più», «Fatto quando» e «Rapporto finale». Ciò che sta nella costituzione del progetto
non si ripete: la si cita.

---

Sei l'esecutore del **compito <N>** della tappa <tappa> (per un lavoro sciolto: **del lavoro #<N>**): <cosa produce,
in una frase>. <Chi lo userà dopo,
in una frase.> Lavora in TDD: prima le prove, poi la prova rossa vista, poi il codice, poi la prova verde. Il
metodo vuole il massimo risultato col minimo di quota: lavora in pochi passi, ognuno costa.

## Da leggere prima

1. La costituzione del progetto: `docs/costituzione.md`. Valgono le sue regole su dove si lavora, prove e stile.
2. Il piano, se c'è: `<percorso>`, sezioni <per nome: «Ruling» (R…), «Review Focus», «Compito N»>.
   <I compiti fatti: «Il compito 1 è fatto (commit `abc1234`) e ti dà `modulo.funzione`.»>
3. Il codice da imitare: `<funzione>` in `<file>` (<perché>).

## Cosa conta di più

<Le trappole che chi decide vede e chi esegue non vedrebbe, al massimo cinque, dalla più costosa. Ognuna in
grassetto, col suo perché. Per esempio:>

- **<Una scrittura che ne cancella un'altra.>** <«`salva` cancella tutto il gruppo: il dato nuovo deve passare dal
  suo campo, altrimenti il ricalcolo lo cancella.»>
- **<Una chiave che sembra ovvia e non lo è.>** <«Il giorno viene dalla colonna `giorno`, non dall'istante.»>

Dove il piano lascia spazio decidi tu e lo scrivi come Ruling. Se sei bloccato, o se la scelta contraddice il piano o
tocca segreti, dati veri, cancellazioni, azioni irreversibili o verso l'esterno, fermati e chiudi con `DOMANDA PER CHI DECIDE:` e una domanda precisa,
con le opzioni che vedi. Ti rispondono e riprendi da dove eri.

## Fatto quando

```
<il comando che esce 0 solo se il compito è fatto, per esempio: uv run pytest -q tests/test_x.py>
```

## Rapporto finale

- I file toccati.
- L'ultima riga della prova rossa e di quella verde, col comando esatto.
- Ogni scelta presa dove il piano lasciava spazio: `Ruling: <cosa> — <perché> — <costo se sbagliato>`.
- Cosa non hai verificato.
