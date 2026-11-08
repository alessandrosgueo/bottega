# La bottega a più botteghe: design del metodo

Stato: design, da approvare. Scritto l'8 novembre 2026 da un brainstorming con l'utente che ha fondato il metodo.

## Perché

Chi lavora con le CLI di programmazione ha più abbonamenti e più modelli, e una risorsa sola davvero scarsa: la quota
del modello più forte, quello che decide. La bottega nasce per spendere quella quota solo dove serve. Il maestro prende
tutte le decisioni prima, per iscritto, nel piano e nel brief; a chi esegue resta il *come*, non il *cosa*. Così
l'esecuzione può andare a modelli più economici.

Il metodo esiste già in una versione a una bottega (maestro, capobottega e garzoni dello stesso fornitore). Questo
design lo allarga in tre direzioni:

1. **Più botteghe.** Una bottega è una CLI con la sua quota. Una quota abbondante di un altro fornitore diventa una
   bottega «di fronte», con un suo maestro e un suo lavorante, che esegue tutto ciò che può aspettare una revisione.
2. **Un metodo da regalare.** Una cartella (un repo pubblico) che si passa a un amico: lui la dà alla sua CLI, scrive
   «installa la bottega», e la CLI fa tutto da sola.
3. **Un metodo che impara.** Le lezioni sui modelli, i precedenti e le misure crescono col lavoro vero.

Questa versione non è compatibile all'indietro con quella a una bottega: è un nuovo inizio.

## Obiettivi

- Spendere la quota del maestro solo per decisioni e revisioni.
- Usare le quote abbondanti di altri fornitori senza che un esecutore confuso possa fare danni.
- Installare tutto con una frase alla propria CLI, nel modo più automatico possibile.
- Imparare dal lavoro: lezioni per modello, casistica, misure di tutto.

## Non obiettivi

- Windows senza WSL e macOS: questa versione gira su **Linux e su Windows con WSL**.
- Non è un framework né un servizio: sono una skill, dei modelli di documento e pochi attrezzi da riga di comando.
- Non sostituisce le skill di processo che la CLI ha già (brainstorming, piani, prove): ci si appoggia.

## Anti-obiettivi

Il metodo è fallito, anche se funziona, se:
- diventa un recinto di regole: le barriere stanno solo dove un errore farebbe un danno vero (segreti, dati veri,
  cancellazioni, azioni irreversibili o verso l'esterno), il resto è giudizio di chi lavora, controllato dal diff;
- un esecutore esterno può unire nel ramo principale, chiudere lavoro, toccare segreti, dati veri o produzione;
- rivedere il lavoro di un esecutore costa al maestro più di quanto gli risparmia;
- nel repo pubblico finisce qualcosa di personale o di un progetto.

## I concetti

**Bottega:** una CLI con la sua quota. La bottega **di casa** è quella del maestro; le altre sono **di fronte**.

**I ruoli.** Un ruolo si nomina col titolo e col nome del modello che lo ricopre («Lavorante Gemini 3.8», «Maestro
Argon»): quando il fornitore cambia modello, cambia solo il nome.

| Ruolo | Dove | Fa |
|---|---|---|
| Maestro | casa | brainstorming con l'utente, design, piano, brief, revisione, unione, rilascio |
| Capobottega | casa | i compiti di giudizio che non si possono scrivere prima; revisione finale dei rami piccoli |
| Garzone | casa | i compiti in sessione, da un brief su file, in TDD |
| Revisore | casa | revisione finale dei rami grandi o delicati, a contesto fresco |
| Maestro esterno | di fronte | consulente del maestro, arbitro, controlli su tutto il repo, capo del lavorante |
| Lavorante | di fronte | esegue tutto ciò che può aspettare una PR, anche da solo di notte |

**Due modi di eseguire un compito:**
- **in casa:** un garzone (o il capobottega) nel worktree del maestro; il consulto è immediato; il commit è del
  maestro, ed è il suo sigillo;
- **fuori:** il lavorante nel suo clone, coi suoi commit, su un ramo suo, consegnato come PR in bozza; il sigillo del
  maestro è l'unione `--no-ff` dopo la revisione.

**Il predefinito:** va fuori tutto ciò che può aspettare una PR. In casa resta ciò che serve al maestro durante la
sessione. Il compito va al capobottega solo se il suo giudizio non si può scrivere nel piano.

**Il consulto.** In casa, il garzone bloccato chiede al maestro, che risponde allo stesso agente. Fuori, il lavorante
chiede prima al maestro esterno; se il maestro esterno non basta, non ha quota o la risposta cambierebbe il piano, la
domanda resta nella PR per il maestro e il lavorante passa ad altro.

## Il ciclo

Resta quello della bottega a una bottega, con tre cambi.

1. **Prima del codice:** brainstorming, design, piano coi Ruling, la costituzione del progetto. Il maestro esterno
   critica design e piani importanti prima che arrivino all'utente; il maestro risponde punto per punto nel documento.
2. **Per ogni compito:** il piano dice chi lo esegue e dove (in casa o fuori). Un compito fuori è un lavoro sulla
   board del progetto, con la riga «Esegue: Lavorante <modello>», il suo piano o brief e il suo «fatto quando»
   (l'oracolo).
3. **Chiusura:** la revisione finale del maestro (o del revisore) resta; per le PR del lavorante il maestro esterno
   può rileggere prima, ma il suo «visto» è un aiuto, non un permesso.

## Il maestro esterno

- **Compiti, in ordine di valore**, perché la sua quota finisce presto: consulente del maestro su design e piani;
  arbitro quando il maestro ha un dubbio o non è d'accordo col lavorante; controlli su tutto il repo in una passata
  (ogni segnalazione con file, riga e testo citato, che uno script verifica prima che il maestro la legga); capo del
  lavorante (spezza i lavori grandi in compiti e rilegge le PR prima del maestro).
- **Senza quota si va avanti senza di lui:** il lavorante continua, il maestro rivede come prima.
- **I disaccordi** li decide il maestro, scritti col perché; quelli che cambiano cosa si costruisce vanno all'utente.

## Il lavorante

- **Fiducia larga da subito**, anche sul codice delicato quando il piano dà firme e valori.
- **Cosa fa:** prima i lavori che il maestro gli assegna; finiti quelli, sceglie lui fra i debiti e i bug della board
  che hanno un oracolo, e lo annuncia sulla board prima di cominciare. Non sceglie mai da solo: decisioni dell'utente,
  design e specifiche, lavori che aspettano l'utente o già presi da altri, ciò che tocca segreti, dati veri,
  cancellazioni o azioni irreversibili o verso l'esterno; più ciò che la costituzione del progetto aggiunge.
- **Le sue PR restano vive:** risolve i conflitti col ramo principale e corregge ciò che il maestro chiede nei commenti.
- **La notte:** un timer lo lancia da solo, un lavoro alla volta, fuori dalla finestra di manutenzione del progetto.
  Un lavoro che fallisce in una notte (tre tentativi) diventa «bloccato» e passa al maestro. Se il ramo principale è
  rosso non prende lavori nuovi. A quota esaurita aspetta il rinnovo e lo annota.
- **Di giorno** lavora solo se lo chiamano l'utente o il maestro.
- **Il resoconto** va solo al maestro, sulla board; il maestro fa da filtro e dice all'utente ciò che serve.

## L'isolamento del lavorante (Linux e WSL)

- **Un utente Unix suo**, con la sua cartella chiusa: non vede la cartella dell'utente, i segreti del progetto, le
  chiavi ssh, gli archivi di password, la memoria delle altre CLI.
- **Le credenziali che servono, e basta:** l'accesso alla CLI del suo fornitore e un `gh` con l'account dell'utente.
  La rete è libera.
- **`sudo` solo per i comandi** che la costituzione del progetto elenca (per esempio quelli che lanciano le prove in
  una gabbia).
- **Tre guardie locali:** un `gh` che rifiuta di unire e di chiudere PR e issue; un controllo di git che rifiuta il
  push sui rami protetti (il principale e quello di produzione); un controllo di git che rifiuta il push di un ramo che
  tocca `.github/` (una pipeline lo eseguirebbe prima della revisione). Un lavorante confuso si ferma; il confine vero
  resta la revisione.
- **Un interruttore:** `bottega ferma` ferma timer e lavorante in corso, `bottega riparti` li riaccende.

## Come impara

- **Una skill sola**, generica, nel repo: la leggono tutte le CLI supportate. Le differenze fra le CLI stanno in una
  pagina per CLI.
- **I quaderni, uno per modello:** le lezioni sul modello (per esempio «indebolisce le prove per farle passare»),
  ognuna come regola breve con la PR da cui viene. Le scrive il maestro durante la revisione. Quando il fornitore
  cambia modello, il quaderno si rilegge. Le lezioni sul progetto vanno nella costituzione del progetto.
- **La casistica:** riparte da zero con questa versione. Raccoglie precedenti (scenario, domanda, risposta presa,
  esito), mai regole: vince sempre la skill. Cresce col lavoro vero.
- **Il banco di prova:** quando la skill cambia, il maestro esterno risponde a 100-200 casi a caso con la skill nuova e
  senza le risposte; uno script confronta; il maestro guarda solo le divergenze.
- **Le misure: tutto.** Per ogni compito: chi l'ha fatto, dove, con che modello; la quota del maestro spesa per brief e
  revisione (il numero che decide); le quote delle altre CLI e le durate, se la CLI le dà; giri, consulti; l'esito
  della revisione (unito com'era, corretto, rifiutato); i rilievi gravi e da dove venivano. Per il maestro esterno, i
  consigli accolti, respinti e, col tempo, giusti o sbagliati. Il maestro dice all'utente solo ciò che cambia la strada.

## Il repo e l'installazione

- **Il repo `bottega`**, pubblico, licenza MIT, in italiano. Dentro: `LEGGIMI.md` per le persone (come si regala e
  come si installa, in poche righe), `INSTALLA.md` per la CLI (installare, aggiornare, disinstallare; ogni passo
  rifacibile senza danni), la skill con le pagine per CLI e per sistema, i quaderni, la casistica, i modelli di brief,
  costituzione e registro, gli attrezzi.
- **Le CLI:** Claude Code, Antigravity, GitHub Copilot CLI. Una CLI con più famiglie di modelli (come Copilot) può
  coprire più ruoli dentro una sola bottega.
- **L'installazione fa da sola tutto ciò che può:** riconosce CLI e sistema; collega (o copia, dove i collegamenti non
  funzionano) la skill nel posto che la CLI legge; legge i modelli disponibili e propone i ruoli; chiede solo ciò che
  non può sapere: come l'utente vuole essere chiamato, il progetto, se vuole il lavorante di notte, se vuole la board.
  Poi scrive: la configurazione dei ruoli fuori dal progetto, la prima costituzione del progetto (guardando il suo
  repo, da rivedere con l'utente) e un `AGENTS.md` alla radice che rimanda alla costituzione; se richiesti, la gabbia
  del lavorante con le guardie e il timer (chiede `sudo` una volta) e una board su GitHub.
- **Il comando `bottega`:** `stato`, `ferma`, `riparti`, `aggiorna` (dopo un `git pull` ricollega o ricopia), più gli
  attrezzi del lavorante.
- **Il repo è pubblico:** prima di ogni push un controllo cerca segreti, nomi e percorsi personali.

## Lasciato al costruttore

Il linguaggio degli attrezzi e del comando `bottega`; la disposizione esatta dei file; i nomi delle opzioni; come si
leggono i modelli di ogni CLI; il formato del registro; i campi della board oltre a Status, «Esegue» e al legame fra
PR e lavoro; come lo script della notte sceglie fra più lavori pronti.

## Le scelte del maestro

Fatte durante il brainstorming, non dall'utente, e quindi rivedibili: la licenza MIT; il controllo prima del push del
repo pubblico; l'ordine di valore dei compiti del maestro esterno; «senza quota si va avanti»; la regola che una
lezione sul progetto va nella costituzione e non nel quaderno; i tre tentativi per notte; il rinvio a `AGENTS.md`.
