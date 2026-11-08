# Modello della costituzione del progetto

La costituzione è `docs/costituzione.md` nel repo del progetto: ciò che vale per ogni compito, così i brief non lo
ripetono. La scrive chi decide alla prima tappa e la tiene viva: un errore che torna in più compiti finisce qui.
Riempi le parti fra `<…>`; togli le sezioni vuote.

---

# Costituzione di <progetto>

<Il progetto in due righe: che cosa fa e per chi.>

## Dove si lavora e cosa non si tocca

- Si lavora solo nel worktree del compito (o nel clone del giro, fuori). Niente commit sul ramo principale.
- Non si toccano: <file, cartelle, sistemi veri; per esempio la configurazione di produzione, i dati veri>.
- <Strumenti che scrivono su sistemi veri e che nessun esecutore usa, per nome.>

## Le prove

- Si lanciano così: `<comando>`. <Limiti della macchina, per esempio un tetto di memoria.>
- La CI del progetto: <che cosa fa>. Un compito è fatto quando il suo «Fatto quando» e la CI sono verdi.
- <Le prove che vogliono permessi passano da un solo comando di root, stretto: `<comando>`. Niente altri `sudo`.>

## Lo stile

- <Lingua dei testi e dei commenti, nomi, lunghezza delle righe, formattatore e su quali cartelle si lancia.>

## L'accessibilità

- <Che cosa serve, chiesto all'utente quando la costituzione si scrive.>

## La rete

- <Di serie libera. Limiti, se il progetto ne ha.>

## Che cosa l'esecutore fuori non prende

Oltre a ciò che la skill esclude già (decisioni dell'utente, design, segreti, dati veri, cancellazioni, azioni
irreversibili o verso l'esterno): <aggiunte del progetto>.

## Lezioni del progetto

<Una riga per lezione, col riferimento alla PR o alla tappa da cui viene.>

## Stranezze degli strumenti

<Le trappole note degli strumenti del progetto.>
