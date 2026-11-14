# L'adattatore della board

Un progetto che ha già un suo comando per la board lo dichiara in `[progetto].adattatore` della configurazione. I
workflow della bottega allora non scrivono sul Project da soli: lanciano quel comando, con `bottega` e un
sottocomando in coda (se il comando non finisce già con `bottega`, la bottega lo aggiunge). Un percorso relativo vale
dalla radice del ramo principale.

Questa pagina è il contratto. Un adattatore che lo rispetta solo in parte non fa cadere niente subito, ma fa perdere
dati in silenzio: il 2026-11-12 un `elenco` che dava solo i lavori madre ha tenuto le misure dei compiti fuori dalla
board per giorni, e il distributore ha scelto sempre «su 0 risultati» (B10).

## I sottocomandi

| Sottocomando | Fa | Esce |
|---|---|---|
| `pronti` | stampa i **lavori** pronti a partire | JSON: una lista di elementi |
| `in-corso` | stampa i **lavori** con stato `in corso` | JSON: una lista di elementi |
| `elenco` | stampa **tutti gli elementi che la bottega legge** (sotto) | JSON: una lista di elementi |
| `prendi N --esecutore E --nota T` | prende il lavoro N se è pronto: stato `in corso`, `Esito` vuoto, `Esecutore` = E, la nota | 0 preso, 1 non pronto, altro = errore |
| `stato N S [--nota T]` | scrive lo stato S (e la nota) | 0, altro = errore |
| `consegna N --pr P` | segna il lavoro N `consegnato` | 0, altro = errore |
| `campo N NOME VALORE` | scrive un campo del Project; un valore vuoto lo svuota; un campo numerico vuole un numero | 0, altro = errore |
| `aggiungi N` | mette l'issue N nel Project (se c'è già, non fa niente) | 0, altro = errore |

Gli errori vanno su stderr: la bottega li riporta come sono.

## Chi sta in quale elenco

- **`pronti` e `in-corso` danno solo lavori**: le issue con l'etichetta `bottega: fuori` (o un'etichetta libera della
  configurazione). Un lavoro è pronto se è aperto e il suo stato è `pronto`, oppure se il suo `Esito` è `correzioni` e
  non è `in corso`. Un compito non sta mai qui: un compito in `Todo` partirebbe come un lavoro.
- **`elenco` dà tutto ciò che la bottega rilegge**, aperto o chiuso:
  - i lavori;
  - i loro compiti, cioè le sub-issue di un lavoro: il giro ci scrive le misure (`Durata`, `Giri`, `Consulti`,
    `Token esecutore`, `Misurato da`, `Esecutore`, `Porta`, `Dove`) e le rilegge per sommarle;
  - ogni elemento che porta già un campo della bottega (per esempio `Misurato da`), anche dopo che il lavoro ha perso
    l'etichetta: il distributore e `bottega conti` calcolano risultati e costi da lì.

## L'elemento

Ogni elemento delle tre liste è un oggetto JSON:

| Chiave | Tipo | Cosa |
|---|---|---|
| `numero` | intero | il numero dell'issue |
| `titolo` | testo | il titolo |
| `etichette` | lista di testi | le etichette |
| `stato` | testo | il campo `Bottega` (vuoto se non c'è) |
| `esito` | testo o `null` | il campo `Esito` |
| `esecutore` | testo o `null` | il campo `Esecutore` |
| `nota` | testo | il campo `Nota del giro` |
| `repo` | testo o `null` | il repo, se il Project ne tiene più d'uno |
| `campi` | oggetto | tutti i campi con un valore, nome → testo; un numero intero senza `.0` |
| `aperta` | booleano | l'issue è aperta (se manca vale vero: allora gli esiti e i segni non si chiudono da soli) |

Le chiavi in più si ignorano.

## Quando le misure non entrano

Se una misura non si scrive, il giro lo dice sul lavoro madre con un commento che comincia con «Misure non scritte
sulla board», col motivo e i valori, e `bottega segui` lo riporta come avviso. I valori del commento si possono
ricopiare a mano con `campo` quando l'adattatore è corretto.
