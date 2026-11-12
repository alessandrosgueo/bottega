# Casistica: il ciclo

### CICLO-1. Un difetto del compito prima

**Scenario:** chi esegue il compito 2 scopre che il compito 1, già unito, ha un difetto piccolo: l'aiuto dei
sottocomandi ripete una parola. Il brief del compito 2 non ne parla.
**Domanda:** che cosa fa chi esegue?
**Opzioni:**
- A) lo corregge con una prova che lo fissa e lo dice nel rapporto
- B) si ferma e chiede a chi decide prima di toccarlo
- C) lo lascia stare, perché è fuori dal brief
**Scelta:** A
**Perché:** è una modifica fuori brief ma sensata, non irreversibile e non tocca segreti né dati veri; il diff e il
rapporto la mostrano a chi rivede.
**Esito:** tenuta; difetto chiuso con la sua prova.
**Fonte:** dal vivo 2026-11-08

### CICLO-2. Una consegna che tocca `.github/`

**Scenario:** un esecutore fuori consegna una patch che corregge un errore vero, ma cambia anche un file in
`.github/workflows/`.
**Domanda:** che cosa succede alla consegna?
**Opzioni:**
- A) il workflow la rifiuta e non spinge niente
- B) il workflow la spinge, e chi decide la guarda per prima
- C) il workflow toglie il file di `.github/` e spinge il resto
**Scelta:** A
**Perché:** l'esecutore non tocca `.github/` né i rami protetti: la consegna lo rifiuta intera, perché lì stanno la
regia e le chiavi ammesse.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-3. Rivedere un compito

**Scenario:** un compito è consegnato con un rapporto lungo e ordinato e un diff di duecento righe.
**Domanda:** da dove comincia la revisione?
**Opzioni:**
- A) dal rapporto, che riassume le scelte
- B) dal diff, poi il rapporto
- C) dalle prove: se sono verdi basta il rapporto
**Scelta:** B
**Perché:** prima il diff, per non vedere il codice con gli occhi di chi l'ha scritto; poi il rapporto.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-4. Un compito che chiede giudizio

**Scenario:** un compito deve scegliere il formato di una data in un file che altri compiti leggeranno. La scelta si
può fare oggi, ma nessuno l'ha scritta nel piano.
**Domanda:** a chi va il compito?
**Opzioni:**
- A) al candidato più forte, perché c'è giudizio
- B) chi decide scrive il formato nel piano come Ruling e il compito resta all'esecutore economico
- C) all'esecutore economico, che sceglie e lo scrive come Ruling
**Scelta:** B
**Perché:** il giudizio che si può scrivere prima va nel piano: è ciò che rende sufficiente un esecutore economico, e
un'interfaccia che altri compiti usano non si lascia a chi esegue.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-5. Quota finita a metà tappa

**Scenario:** l'esecutore fuori ha fatto due compiti di una tappa di cinque; al terzo la sua bottega dice «quota
esaurita».
**Domanda:** che cosa fa il distributore?
**Opzioni:**
- A) passa subito il terzo compito al candidato seguente
- B) tiene il compito a quell'esecutore per un giro; se la quota manca ancora, passa al candidato seguente
- C) segna il lavoro «bloccato» e lo passa a chi decide
**Scelta:** B
**Perché:** chi ha fatto i primi compiti conosce il ramo; un giro di attesa costa poco. Il seguente, se serve,
riparte dal ramo e dalle note.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-6. L'etichetta contro la scelta viva

**Scenario:** un lavoro porta l'etichetta `esegue: <nome>`, ma i conti dicono che un altro candidato costerebbe meno.
**Domanda:** chi lo esegue?
**Opzioni:**
- A) il candidato dell'etichetta
- B) il candidato che costa meno
- C) il candidato dell'etichetta solo se ha quota abbondante
**Scelta:** A
**Perché:** a mano vince l'etichetta; il risultato conta comunque nei numeri della scelta viva.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-7. Rilievi gravi nati dal piano

**Scenario:** la revisione finale trova tre rilievi gravi. Il codice fa esattamente ciò che il piano chiedeva: era il
piano a non prevedere quei casi.
**Domanda:** a quale origine si contano?
**Opzioni:**
- A) esecuzione, perché il codice è di chi ha eseguito
- B) piano
- C) brief
**Scelta:** B
**Perché:** i rilievi si contano per origine; se l'esecutore ha fatto ciò che il piano diceva, l'errore è del piano, e
il prossimo piano lo corregge lì.
**Esito:** corretti con una prova ciascuno; il controllo della storia rimandato al cancello giusto.
**Fonte:** dal vivo 2026-11-08

### CICLO-8. La quota di chi decide finisce a fine tappa

**Scenario:** la tappa è finita, le prove sono verdi, ma la quota di chi decide è quasi finita e non basta per la
revisione finale.
**Domanda:** che cosa si fa?
**Opzioni:**
- A) si salta la revisione finale e si unisce, visto che le prove sono verdi
- B) la tappa resta aperta; un sostituto con quota può rivedere e segnare l'esito, l'unione aspetta chi decide
- C) il sostituto rivede e unisce
**Scelta:** B
**Perché:** la revisione finale non si taglia; il sostituto rivede ma non unisce: l'unione è il sigillo di chi decide.
**Esito:** da vedere.
**Fonte:** deciso dall'utente

### CICLO-9. Un'issue scritta di getto

**Scenario:** l'utente apre un'issue di una riga, «la pagina delle misure è lenta», e la mette nel Project fra i
lavori pronti.
**Domanda:** che cosa succede?
**Opzioni:**
- A) il distributore la dà a un esecutore fuori, che indaga
- B) nessun esecutore la prende: chi decide la trasforma in un compito con brief e «Fatto quando»
- C) un consigliere scrive il brief e l'esecutore parte subito
**Scelta:** B
**Perché:** le issue senza brief nessun esecutore le prende; chi decide le trasforma prima in compiti.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-10. Le prove secondo il modello

**Scenario:** un esecutore fuori consegna e scrive nel rapporto «tutte le prove verdi». Il «Fatto quando» lanciato dal
workflow esce 1.
**Domanda:** che cosa vale?
**Opzioni:**
- A) il rapporto del modello, se il diff sembra giusto
- B) l'esito del «Fatto quando» lanciato dal workflow
- C) si rilanciano le prove a mano e si decide
**Scelta:** B
**Perché:** l'oracolo lo esegue il workflow, non il modello: ciò che il modello dice delle sue prove non conta.
**Esito:** da vedere.
**Fonte:** di chi decide

### CICLO-11. Un consiglio contro una decisione dell'utente

**Scenario:** il consigliere critica la skill e propone di togliere dalla costituzione la sezione sull'accessibilità,
perché il design non la chiede. Quella sezione l'aveva voluta l'utente.
**Domanda:** che cosa fa chi decide?
**Opzioni:**
- A) accoglie il consiglio: il metodo vuole poche regole
- B) lo respinge per iscritto, perché è una decisione dell'utente, e accoglie gli altri consigli che reggono
- C) sospende tutta la revisione finché l'utente non risponde
**Scelta:** B
**Perché:** i disaccordi col consigliere li decide chi decide, per iscritto; una decisione dell'utente non la toglie un
consiglio. Solo i disaccordi grossi vanno all'utente.
**Esito:** respinti due rilievi su quindici, accolti gli altri.
**Fonte:** dal vivo 2026-11-08

### CICLO-12. La revisione dopo le correzioni

**Scenario:** la revisione finale di una tappa delicata ha trovato quindici rilievi gravi; i Lavoranti li hanno
corretti, ognuno con la sua prova vista rossa, e le prove sono verdi. Le correzioni hanno cambiato mezzo giro.
**Domanda:** si unisce?
**Opzioni:**
- A) sì: ogni rilievo ha la sua prova
- B) prima un'altra revisione finale a mente fresca, sul codice corretto
- C) si rilancia solo la stessa revisione di prima, per vedere se i rilievi sono chiusi
**Scelta:** B
**Perché:** le prove dicono che i rilievi vecchi sono chiusi, non che le correzioni non ne abbiano aperti di nuovi; e
chi ha rivisto la prima volta tende a ritrovare ciò che cercava.
**Esito:** la seconda revisione (un revisore nuovo) ha trovato quattro gravi nuovi, uno introdotto proprio dalla
correzione della consegna (il checkout del ramo del modello nel clone del runner).
**Fonte:** dal vivo 2026-11-08

### CICLO-13. Il revisore che si ferma a metà

**Scenario:** la revisione finale va a due revisori di due botteghe; uno dei due si ferma dopo cinque minuti perché i
crediti della sua bottega sono finiti, senza rapporto.
**Domanda:** che cosa fa chi decide?
**Opzioni:**
- A) aspetta il rinnovo dei crediti e rilancia
- B) tiene la revisione dell'altro revisore, se copre il ramo, e segna la mancata nelle misure
- C) fa la revisione da sé
**Scelta:** B
**Perché:** una revisione a mente fresca basta se copre il ramo; la seconda era una riserva. Aspettare ferma la tappa
senza un motivo, e la revisione di chi ha scritto le correzioni non è a mente fresca.
**Esito:** tenuta la revisione Opus; la porta Antigravity ha imparato i crediti finiti (PORTE-2).
**Fonte:** dal vivo 2026-11-08

### CICLO-14. La prova che prepara lo stato a mano

**Scenario:** la revisione trova un caso da correggere (un compito eseguito da due candidati). Il brief delle prove
dice «il compito ha già il campo Esecutore di un altro candidato» e la prova, verde, lo imposta a mano. Nel flusso vero
quel campo lo riscrive un altro passo (`prendi`) subito prima del giro.
**Domanda:** come si scrive la prova di una correzione?
**Opzioni:**
- A) si prepara a mano lo stato che serve, è più semplice
- B) si passa dal flusso vero che produce quello stato (gli stessi comandi, nello stesso ordine)
- C) si scrivono tutte e due
**Scelta:** B
**Perché:** lo stato preparato a mano è quello che chi scrive la correzione immagina, non quello che il programma
produce; la prova passa anche con la correzione sbagliata.
**Esito:** la rilettura ha visto il buco; la correzione nuova (un campo scritto solo dal giro) ha la prova col
`prendi` fra due giri, rossa senza la correzione.
**Fonte:** dal vivo 2026-11-08

### CICLO-15. Il finto che esegue davvero

**Scenario:** il codice nuovo lancia un comando attraverso il prefisso dell'esecutore (`sudo -u <esecutore> --`),
e quel comando uccide processi (`kill -KILL -1`). Nelle prove il prefisso è uno script finto che registra gli
argomenti e poi fa `exec "$@"`.
**Domanda:** cosa si fa prima di lanciare le prove?
**Opzioni:**
- A) niente: il finto registra, la prova controlla il registro
- B) il finto intercetta ogni comando che uccide (`kill`, `pkill`, `killall`) e non lo esegue; il codice che uccide
  chiede prima a quale utente arriva (`id -u` attraverso il prefisso); le prove girano in un namespace PID
- C) si toglie il comando dalle prove
**Scelta:** B
**Perché:** il finto con `exec "$@"` esegue il comando come chi lancia le prove: `kill -1` uccide tutti i suoi
processi, la sessione compresa.
**Esito:** con A è successo due volte (il Lavorante, poi la suite del maestro): la macchina di sviluppo è stata
riavviata due volte. Dopo B, il blocco dell'uid è nel codice (B6-R14), i finti intercettano, e Lavorante e prove girano
in un namespace PID.
**Fonte:** dal vivo 2026-11-09

### CICLO-16. Il cancello che imita il codice

**Scenario:** il cancello in contenitore prova i permessi del giro con due utenti veri, ma prepara le cartelle con
comandi di shell scritti a mano (`chmod 750`), mentre il giro le prepara in Python (`Path.chmod(0o750)`).
**Domanda:** il cancello verde basta?
**Opzioni:**
- A) sì: i modi sono gli stessi
- B) no: il cancello deve lanciare le funzioni vere del codice, come l'utente che le lancia nel giro
**Scelta:** B
**Perché:** lo stesso numero non vuol dire lo stesso effetto: il `chmod` di coreutils conserva il setgid di una
cartella, quello di Python (la chiamata di sistema) lo toglie.
**Esito:** con A il cancello era verde e ogni giro vero sarebbe morto (l'esecutore non poteva copiare il fascicolo):
l'ha trovato una rilettura leggendo il codice. Con B il cancello va ROSSO sullo stesso errore.
**Fonte:** dal vivo 2026-11-09

### CICLO-17. Il controllo che guarda anche i propri file

**Scenario:** un controllo di sicurezza (i workflow del progetto che partono sui rami `bottega/*`) gira a ogni giro
sul ramo principale del progetto. Dopo l'installazione quel ramo contiene anche i workflow della bottega.
**Domanda:** quali prove servono oltre ai casi pericolosi?
**Opzioni:**
- A) bastano i casi pericolosi e qualche caso sicuro inventato
- B) anche una prova sui file che la bottega stessa installa, resi come li scrive l'installazione: non devono mai
  essere un rischio
**Scelta:** B
**Perché:** un controllo prudente («nel dubbio è un rischio») che inciampa nei file della bottega ferma la bottega
stessa, in silenzio, a ogni giro.
**Esito:** con A il distributore installato (un'espressione `${{ … }}` su più righe) risultava un rischio e ogni giro
sarebbe restato in attesa; l'ha trovato la terza rilettura. La prova B è rossa sul codice di prima (B6-R24).
**Fonte:** dal vivo 2026-11-09

### CICLO-18. Il lancio che non parte

**Scenario:** chi decide mette l'etichetta del lavoro e si mette ad aspettare errori e domande. L'etichetta cade dentro
la finestra di manutenzione: il distributore scrive «nessun lavoro avviato» ed esce verde.
**Domanda:** come si lancia un lavoro?
**Opzioni:**
- A) si mette l'etichetta e si aspetta un errore o una domanda
- B) si lancia con un comando che legge che cosa il distributore ha deciso per quel lavoro, e l'attesa guarda anche
  il silenzio (nessun giro da troppo tempo)
**Scelta:** B
**Perché:** un lancio che non parte non dà errori: senza leggere la riga del distributore si aspetta a vuoto.
**Esito:** con A tre ore perse; da B9 `bottega lancia` esce `2` nella finestra e `bottega segui` esce `4` sul fermo.
**Fonte:** dal vivo 2026-11-12

### CICLO-19. Il giro caduto prima di cominciare

**Scenario:** un giro dell'esecutore riceve un `HTTP 503` di GitHub alla prima lettura. Il lavoro torna `pronto`, ma
il giro dopo lo avrebbe chiamato il giro appena caduto: la catena è ferma, e il solo giro pianificato è quello di notte.
**Domanda:** che cosa lo riprende?
**Opzioni:**
- A) il giro di notte
- B) un ritentativo breve sugli errori passeggeri (solo letture, o richieste mai arrivate) e un giro di riserva ogni
  ora
- C) il distributore rilanciato subito dopo ogni errore
**Scelta:** B
**Perché:** un errore passeggero passa in pochi secondi; un guasto fisso con C diventerebbe un anello di workflow; A
lascia il lavoro fermo per ore.
**Esito:** con A il lavoro restava fermo fino al giorno dopo; ripreso a mano, poi B9-R1 e B9-R2.
**Fonte:** dal vivo 2026-11-12

### CICLO-20. Il lavoro chiuso con l'etichetta sopra

**Scenario:** un lavoro chiuso a mano conserva l'etichetta e un `Esito` = `correzioni` di una revisione vecchia. Il
distributore lo prende come pronto («correzioni e non in corso»), lo riapre e lo rimanda all'esecutore; il lavoro nuovo
aspetta.
**Domanda:** chi deve accorgersene?
**Opzioni:**
- A) chi decide, togliendo sempre etichette ed esiti prima di chiudere
- B) la board: un'issue chiusa non è mai pronta, qualunque siano i campi
**Scelta:** B
**Perché:** una regola sul gesto di chi chiude si dimentica; lo stato dell'issue c'è già.
**Esito:** con A un giro sprecato e il lavoro nuovo saltato; B9-R3.
**Fonte:** dal vivo 2026-11-12

### CICLO-21. L'oracolo rosso in una tappa

**Scenario:** un lavoro con sei compiti sullo stesso ramo. L'oracolo del quarto è rosso (una prova di un compito di
prima cade); il giro apre la PR, scrive l'esito, chiude il compito e passa al quinto.
**Domanda:** che cosa fa il giro con un oracolo rosso?
**Opzioni:**
- A) consegna comunque: la PR dice l'esito, chi decide guarderà
- B) non chiude il compito: lo rimette pronto con l'esito fra i commenti, al terzo rosso lo blocca per chi decide
**Scelta:** B
**Perché:** in una tappa il compito dopo parte dalla base del compito prima; un rosso consegnato diventa il problema di
un altro esecutore, che non ha il permesso di toccarlo.
**Esito:** con A il quinto esecutore ha trovato la suite rossa e si è fermato con una domanda; B9-R4 (cambia B3-R12).
**Fonte:** dal vivo 2026-11-12

### CICLO-22. La domanda in testa al rapporto

**Scenario:** l'esecutore scrive `DOMANDA PER CHI DECIDE:` come prima riga del rapporto, poi la diagnosi e le opzioni.
Il giro cerca il segno solo nell'ultima riga.
**Domanda:** dove si riconosce una domanda?
**Opzioni:**
- A) solo nell'ultima riga, come dice la regola data all'esecutore
- B) in ogni riga che comincia col segno; la domanda va da lì alla fine
**Scelta:** B
**Perché:** il modello rispetta il senso della regola più della sua forma; un segno a inizio riga non nasce per caso,
mentre una citazione a metà riga non conta.
**Esito:** con A due domande perse nello stesso giorno: una, con i commit già fatti, è finita in consegna con
l'oracolo rosso; l'altra il giro l'ha contata «nessun commit» e ha rilanciato lo stesso compito senza risposta. B9-R5.
**Fonte:** dal vivo 2026-11-12

### CICLO-23. La regola del piano troppo larga

**Scenario:** il piano dà a un divieto «tutte le entità del dominio». L'esecutore vede che un compito dopo ammetterà
una di quelle entità a un altro proponente, restringe il divieto alle entità che il piano voleva proteggere e lo
scrive come Ruling.
**Domanda:** che cosa fa chi decide alla revisione?
**Opzioni:**
- A) rifiuta: il piano diceva tutte
- B) accetta, perché il Ruling è scritto e protegge ciò che il piano voleva, e corregge il piano
**Scelta:** B
**Perché:** il Ruling dichiarato è il caso per cui esiste; il piano aveva scritto più di quanto aveva deciso.
**Esito:** con B il compito dopo è passato senza scontri su quelle voci.
**Fonte:** dal vivo 2026-11-12

### CICLO-24. Le prove negative che un compito dopo rende positive

**Scenario:** in una tappa, un compito prova un caso rifiutato con un proponente che un compito dopo ammetterà. Il
compito dopo non può toccare le prove degli altri e si ferma.
**Domanda:** come si scrivono le prove negative di una tappa?
**Opzioni:**
- A) con l'esempio più naturale, e si aggiustano dopo
- B) con un ingresso che nessun compito della tappa ammetterà (lo dice il piano), e il brief dei compiti dopo permette
  di allineare le prove di prima solo nei punti che li toccano, come Ruling
**Scelta:** B
**Perché:** il divieto di toccare le prove altrui protegge dalle scorciatoie, ma senza una via d'uscita scritta un
cambio voluto dal piano ferma la tappa.
**Esito:** con A una domanda e un'ora persa; la risposta ha dato le regole di B.
**Fonte:** dal vivo 2026-11-12

### CICLO-25. Il brief che vieta il file dove sta la correzione

**Scenario:** dopo una revisione, chi decide scrive a un esecutore di correggere un difetto in un file di prove e, per
non urtare un altro esecutore, gli vieta la cartella dei sorgenti. Il codice da cambiare sta proprio lì.
**Domanda:** che cosa fa l'esecutore?
**Opzioni:**
- A) cambia il file vietato, perché la correzione lo richiede
- B) scrive le prove, le lascia ferme col perché e dice a chi decide dove sta la correzione, con una bozza
**Scelta:** B
**Perché:** un divieto del brief protegge un altro lavoro in corso; romperlo in silenzio lo rende inutile. Chi decide,
prima di vietare un percorso, controlla dove vive il codice da cambiare.
**Esito:** con B un giro in più, la bozza pronta e la correzione fatta subito dopo dallo stesso esecutore.
**Fonte:** dal vivo 2026-11-12

### CICLO-26. I dati di un comando che il vincolo non ammette

**Scenario:** il brief detta i dati di un comando (un campo che lo script di destinazione richiede); il catalogo dei
vincoli, scritto in una tappa di prima, non ammette nessun campo per quel comando, e una sua prova lo fissa.
**Domanda:** che cosa fa l'esecutore?
**Opzioni:**
- A) scrive il codice come dice il brief: le prove diranno
- B) si ferma prima di scrivere codice e porta a chi decide la contraddizione, con le opzioni e il loro costo
- C) cambia il vincolo da sé
**Scelta:** B
**Perché:** con A il comando sarebbe sempre rifiutato e nessuno se ne accorgerebbe prima dell'unione; con C un
esecutore allargherebbe da sé un confine di sicurezza. Chi decide, prima di dettare i dati di un comando, legge il
vincolo che li deve ammettere.
**Esito:** con B la scelta in un minuto (il campo ammesso, il suo valore chiuso in un tipo, il controllo che manca come
debito) e il compito finito al primo giro.
**Fonte:** dal vivo 2026-11-12
