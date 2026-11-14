# L'impianto: il sigillo e la CI dei rami della bottega

Ciò che si prepara una volta, o che serve solo a chi monta una pipeline. La skill lo cita e non lo ripete.

## Il sigillo

- **Che cosa si firma.** Solo le unioni nel ramo principale: chi decide unisce in locale con `git merge --no-ff -S` e
  spinge. Un commit di lavoro non si firma, così non diventa mai una punta da rilasciare.
- **Le chiavi ammesse** sono in `.github/bottega/firme-ammesse`, una riga per chiave. Una chiave si revoca togliendo
  la sua riga, mai con le date.
- **Preparare la macchina di chi decide:** `bottega firma prepara`, una volta. Prepara la chiave SSH e il git che
  firma.
- **Un'unione dal sito di GitHub** è firmata da GitHub e non passa la verifica. Un attrezzo di rilascio che scrive da
  sé sul ramo principale ha la sua chiave, ammessa anch'essa.
- **La pipeline di rilascio** chiama, come primo passo e prima di ogni codice del repo:

  ```bash
  bottega firma verifica --stato <file fuori dal repo> --avvisa
  ```

  su un clone con tutta la storia, e si ferma se la verifica non è buona. Il file di stato tiene lo SHA dell'ultimo
  rilascio verificato (mai un tag: chi ha il token lo può spingere). Il primo rilascio si fa con `--primo`.

## La CI del progetto e i rami `bottega/*`

Quei rami li scrive un modello, e la CI che li prova esegue codice suo.

- **Nessun segreto** ai job che eseguono quel codice. Un controllo che ha bisogno di un segreto prende il suo codice
  dal ramo principale e il ramo del modello solo come dati.
- **Nessun runner self-hosted** per quei job: lì il modello sarebbe l'utente del runner. Se la CI del progetto gira
  su un runner self-hosted, va esclusa per `bottega/**`; il compito è fatto quando il suo «Fatto quando» è verde nel
  giro.
- Il distributore controlla a ogni giro i workflow del progetto che partirebbero su quei rami, e si ferma con un
  avviso se ne trova uno a rischio.
