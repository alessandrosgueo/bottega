---
name: bottega
description: Metodo di lavoro «bottega» per spendere la quota scarsa solo dove serve. Chi decide scrive piano e brief, chi esegue lavora (in sessione o fuori, come PR su GitHub), un consigliere critica e consiglia. Usala all'inizio di ogni sessione su un progetto che ha `.github/bottega/bottega.toml` o `docs/costituzione.md`, per pianificare ed eseguire un lavoro in quei progetti, e quando l'utente dice «bottega».
---

# Bottega

L'immagine è la bottega di una volta: il maestro disegna, decide e firma; i lavoranti eseguono; un collega di
un'altra bottega dà il suo parere. Qui le botteghe sono gli **abbonamenti** dell'utente, ognuno con la sua quota.

**Lo scopo è spendere la quota scarsa solo dove serve.** Chi decide prende le decisioni prima, per iscritto, nel piano
e nel brief. A chi esegue resta il *come*, non il *cosa*. Così il lavoro va ai modelli più economici o alle quote più
abbondanti, anche di altri fornitori, senza perdere qualità.

**Poche regole.** Le barriere ci sono solo dove un errore farebbe un danno vero:
- segreti;
- dati veri;
- cancellazioni;
- azioni irreversibili o che escono verso l'esterno.

Tutto il resto è giudizio di chi lavora, controllato dal diff. In questa skill «le quattro barriere» sono queste.

## Le parole

- **Bottega:** un abbonamento con la sua quota (un fornitore e un accesso). Ha i suoi modelli e una quota scarsa,
  normale o abbondante. Un abbonamento con più quote separate (Antigravity: una per gruppo di modelli) diventa una
  bottega per quota, con la stessa porta.
- **Porta:** la CLI con cui si entra in una bottega. Una CLI può aprire più botteghe e una bottega può avere più porte.
  Ogni porta ha la sua pagina: [Claude Code](porte/claude-code.md), [Antigravity](porte/antigravity.md),
  [Pi](porte/pi.md), [GitHub Copilot CLI](porte/copilot-cli.md).
- **Le quattro funzioni:**

  | Funzione | Che cosa fa |
  |---|---|
  | decidere | brainstorming con l'utente, design, piano, brief, pesa le revisioni, unisce, rilascia |
  | eseguire | un compito da un brief, in TDD, in sessione o fuori come PR |
  | rivedere | la rilettura a mente fresca di un compito, di un ramo o di una PR |
  | consigliare | critiche a design e piani, arbitrati, controlli su tutto il repo, consulti di chi esegue |

- **Candidato:** un modello di una bottega, da una porta, per una funzione. Il suo nome è un titolo più il nome del
  modello, scelto dall'utente («Maestro …», «Lavorante …»). Questa skill non conosce nessun modello: li legge dalla
  configurazione.
- **La configurazione** del progetto è `.github/bottega/bottega.toml`: botteghe, candidati per funzione, chi può
  comandare, l'adattatore della board (il comando del progetto, se ne ha uno, attraverso cui i workflow scrivono sul
  Project; il suo contratto è `docs/adattatore.md` nel clone della bottega). La crea l'installazione, che la CLI
  segue da `INSTALLA.md` nel clone della bottega. **Senza configurazione, o senza runner self-hosted** (alcuni repo
  non li ammettono), la bottega lavora solo in sessione: decide il modello della sessione, eseguono i suoi sotto-agenti
  più economici.
- **Project:** la board di GitHub del progetto (GitHub Projects): lavori, campi, misure.
- **Ruling:** una decisione scritta nel piano, numerata, con il valore esatto («R3. Il timeout è 15 s»), che toglie un
  giudizio a chi esegue.
- **Fuori e la notte:** «fuori» è un esecutore lanciato dai workflow di GitHub Actions sul runner di una macchina; la
  notte è un giro a orario che prende i lavori pronti, se una macchina col runner resta accesa.
- **Il sigillo:** chi decide firma con la sua chiave SSH ciò che entra nel ramo principale; le chiavi ammesse sono in
  `.github/bottega/firme-ammesse`.

## La scelta viva

Lo schema da cui il metodo nasce è un decisore forte che pensa e un esecutore economico che fa: massimo risultato,
minimo costo. La scelta viva lo serve, non lo sostituisce.

- **Il criterio:** il compito va al candidato col **costo atteso più basso per un risultato buono**: la quota scarsa
  che spende (quella di chi decide per brief e revisione, più la sua se è scarsa), divisa per la probabilità che il suo
  lavoro sia unito com'è. Chi fa rifare metà del lavoro costa più di chi consuma un po' di quota e consegna giusto.
- **Il genere di compito** sono le etichette che il progetto ha già. I risultati si contano per candidato ed
  etichetta.
- **Il punto di partenza**, prima dei numeri: va **fuori**, al primo candidato con quota abbondante, tutto ciò che può
  aspettare una PR. Resta **in sessione** ciò che serve subito. I sotto-agenti in sessione consumano l'abbonamento di
  chi decide: è il motivo del «fuori» di serie.
- **La quota del momento:** quando una bottega finisce la quota, il suo stato («esaurita fino a…») va in una variabile
  di GitHub Actions e i giri la saltano finché lo stato non scade. A metà tappa, chi resta senza quota tiene il
  compito per un giro; se manca ancora, passa al candidato seguente, che riparte dal ramo e dalle note.
- **A mano:** l'etichetta `esegue: <nome>` su un lavoro vince sulla scelta. Il risultato conta comunque.
- **Chi sceglie:** per i compiti fuori il workflow, con un calcolo senza modello; per quelli in sessione chi decide,
  con gli stessi numeri (`bottega conti`). Ogni scelta lascia sul lavoro una riga col perché. Lo stesso criterio
  sceglie quale consigliere risponde a un consulto.

## Il ciclo

### All'inizio di una sessione

Chi decide guarda il Project: i lavori toccati nelle ultime 24 ore (i resoconti della notte sono commenti lì), quelli
«bloccati», gli avvisi delle porte, le PR con esito da pesare. Poi riprende da dove si era.

### Prima del codice

1. **Brainstorming e design** con l'utente. Niente piano finché l'utente non dice di andare avanti.
2. **Il piano**, nel ramo del lavoro. Contiene:
   - i **Ruling** coi valori esatti;
   - il **Review Focus**: i casi che le prove non coprono;
   - i compiti, ognuno con file, interfacce consumate e prodotte, prove per nome e **dove si esegue** (in sessione o
     fuori). Il candidato lo sceglie la scelta viva; il piano lo fissa solo per un motivo, scritto, con
     `esegue: <nome>`.

   Se un compito chiede giudizio, chi decide prova prima a toglierlo dal compito e a scriverlo nel piano come Ruling,
   firma o valore esatto. È il lavoro che rende sufficiente un esecutore economico.
3. **Un consigliere critica** design e piano: chi decide li apre in una PR in bozza e scrive `/bottega consulta` lì. I
   disaccordi li decide chi decide, per iscritto; i grossi l'utente.
4. **L'utente legge il piano** prima del lancio, con le decisioni in testa.
5. **La costituzione del progetto** (`docs/costituzione.md`, modello in `modelli/costituzione.md`): ciò che vale per
   ogni compito. `AGENTS.md` alla radice (modello in `modelli/agents.md`) rimanda a lei. Se mancano, chi decide le
   scrive alla prima tappa.
6. **Le issue.** Una tappa è un'issue madre; i compiti sono le sue sotto-issue, in ordine. Il brief di ogni compito è
   il corpo della sua issue (modello in `modelli/brief.md`), con la sezione **«Fatto quando»**: il comando che dice se
   è fatto. Un consigliere con quota può dividere il piano in issue; chi decide le scorre prima che partano. Le issue
   scritte di getto, senza brief, nessun esecutore le prende: chi decide le trasforma prima in compiti.

**Una tappa, un ramo, una PR.** I compiti di una tappa si fanno in ordine sullo stesso ramo, un commit per compito; il
compito seguente parte solo dopo il precedente. I lavori sciolti (un debito, un bug) hanno ognuno il suo ramo e la sua
PR.

### Per ogni compito

- **In sessione:** un sotto-agente nel worktree della tappa, col brief dell'issue; un compito alla volta per worktree.
  Chi decide rivede il diff e committa.
- **Fuori:** l'etichetta `bottega: fuori` sull'issue madre o sul lavoro sciolto (o la notte). Il workflow sceglie il
  candidato, gli prepara il fascicolo (issue, piano, costituzione, il quaderno del suo modello) e una copia del ramo;
  l'esecutore lavora senza chiavi di GitHub e consegna una patch; il workflow la controlla, lancia il «Fatto quando»,
  spinge e apre o aggiorna la PR in bozza della tappa. **Un consigliere rilegge ogni compito nello stesso giro**; se
  non ha quota il compito va avanti senza rilettura e il lavoro lo segna. Chi decide rivede la PR intera a fine tappa.

**Come si rivede** (chi decide in sessione, il consigliere fuori, chi rivede a fine tappa):
- prima il **diff**, poi il rapporto, per non vedere il codice con gli occhi di chi l'ha scritto;
- il confronto è col piano: interfacce, trappole, prove. L'esito del «Fatto quando» e della CI lo dice il workflow, non
  il modello: servono verdi tutti e due;
- i Ruling di chi esegue si accettano o si rifiutano; quelli che servono dopo entrano nel piano;
- una modifica fuori brief ma sensata si tiene (per esempio un difetto di un compito prima, corretto con una prova);
  un file toccato che il rapporto tace è un motivo per rileggere tutto il diff;
- **le correzioni** in sessione vanno allo stesso agente; fuori sono un commento che indica il commit del compito,
  più l'esito `correzioni` nel campo «Esito»: è il campo che fa ripartire il lavoro, non il commento. Una correzione
  grande diventa un compito nuovo, una sotto-issue del lavoro, col suo brief e il suo «Fatto quando» (senza, il
  distributore salta il lavoro e dice quale compito); e il ramo della tappa non si spinge mentre un giro gira, perché
  il giro spingerebbe sopra una base vecchia. Correzioni indipendenti che toccano file diversi possono andare fuori
  dal lavoro, in parallelo, in sessione o con altri esecutori, e si uniscono al ramo della tappa alla fine.

**Il consulto.** Chi esegue si ferma con `DOMANDA PER CHI DECIDE:` e una domanda precisa quando la scelta contraddice
il piano o tocca una delle quattro barriere, o quando è bloccato. In sessione risponde chi decide allo stesso agente.
Fuori risponde nello stesso giro il consigliere scelto dalla scelta viva, solo sui dubbi tecnici dentro il piano; una
domanda che cambia il piano o tocca le quattro barriere ferma il lavoro e passa a chi decide. Per il resto, dove il
piano lascia spazio, chi esegue decide e lo scrive come Ruling.

### Fine della tappa

1. **La revisione finale** del ramo intero, a mente fresca, da chi rivede (un candidato forte per i rami grandi o
   delicati), partendo dai compiti che nessun consigliere ha riletto e dalle PR che il workflow ha segnato (prove già
   esistenti cambiate, il controllo dei segreti scattato). Riceve il diff dalla base, il piano, il Review Focus e i
   Ruling, e dice cosa ha controllato e cosa no.
2. **I rilievi** li pesa chi decide, per il loro effetto, e li conta per **origine**: piano, brief o esecuzione. I gravi
   si correggono con una prova che li fissa; i minori diventano issue del progetto. Un errore che torna va nella
   costituzione. Per ogni compito chi decide scrive l'esito e i rilievi con `bottega misura <N> --esito
   unito|corretto|rifiutato --rilievi-piano … --rilievi-brief … --rilievi-esecuzione …`: il distributore impara solo da
   lì, e un compito senza esito non conta.
3. **L'unione** nel ramo principale è di chi decide, `--no-ff`, **firmata**: è il sigillo. Chi decide unisce in locale
   con `git merge --no-ff -S` e spinge; si firmano solo le unioni, così un commit di lavoro non diventa mai una punta
   da rilasciare. Un'unione dal sito di GitHub è firmata da GitHub e non passa la verifica (un attrezzo di rilascio che
   scrive da sé sul ramo principale ha la sua chiave, ammessa anch'essa). La chiave e il git che firma li prepara
   `bottega firma prepara`, una volta sulla macchina di chi decide. Una pipeline di rilascio chiama, **come primo
   passo, prima di ogni codice del repo**, `bottega firma verifica --stato <file fuori dal repo> --avvisa` (il file
   tiene lo SHA dell'ultimo rilascio verificato; il primo rilascio con `--primo`), su un clone con tutta la storia, e
   si ferma se non è buona. Una chiave si revoca togliendo la sua riga, mai con le date.
   Un esecutore non unisce, non chiude lavoro, non manda in produzione. Ciò che è irreversibile o esce verso l'esterno si
   chiede all'utente. Una PR rifiutata la chiude chi decide, col motivo; il lavoro torna da rifare o si chiude.
4. **Se la quota di chi decide finisce** la revisione finale non si taglia: la tappa resta aperta. Un sostituto con
   quota può rivedere e segnare l'esito (`pronta per l'unione` o `correzioni`); non pianifica e non unisce. Al ritorno
   chi decide parte dalla sua revisione.
5. **Quaderni e casistica**: chi decide scrive le lezioni nuove (sotto, «Come impara»).

## Fuori, su GitHub

- **Il lavoro vive su GitHub:** issue e Project per il lavoro, il corpo dell'issue per il brief, i campi del Project
  per stato, esecutore, esito e misure, PR in bozza per le consegne, commenti per i consulti, variabili di Actions per
  la quota. Niente cartelle, copie o script di sincronia.
- **La regia sono i workflow** della bottega, sui runner self-hosted delle macchine con le porte: un distributore in
  fila sceglie il lavoro e il candidato, un esecutore per bottega lavora.
- **Chi comanda:** gli account della configurazione, con le etichette (`bottega: fuori`, `esegue: <nome>`) e coi
  comandi nei commenti: `/bottega riprova` (un'altra passata subito, senza aspettare un esito), `/bottega consulta
  <domanda>` (al consigliere), `/bottega sospendi` (questo lavoro si ferma). I commenti scritti dai workflow portano un
  segno nascosto e non sono mai comandi.
- **L'esito** di una revisione è il campo «Esito» del Project (`pronta per l'unione`, `correzioni`, `rifiutata`): il
  distributore riprende i lavori con `correzioni`.
- **Che cosa prende l'esecutore fuori:** prima i lavori che chi decide gli assegna; finiti quelli, i debiti e i bug
  che hanno un «Fatto quando» (un consigliere può scriverlo a quelli che lo meritano), annunciandolo sul lavoro. Non
  prende mai: decisioni dell'utente, design, lavori che aspettano l'utente o già presi, ciò che tocca le quattro
  barriere, più ciò che la costituzione aggiunge. Non tocca `.github/` né i rami protetti: la consegna lo rifiuta. Usa
  sotto-agenti solo col suo modello.
- **Solo issue di un comandante:** il brief è il corpo dell'issue, e chi l'ha scritta lo può cambiare anche dopo
  l'etichetta. Un lavoro proposto da altri si copia in un'issue nuova.
- **La CI del progetto e i rami `bottega/*`:** quei rami li scrive un modello, e la CI che li prova esegue codice suo.
  Nessun segreto ai job che lo eseguono (il controllo che ha bisogno di un segreto prende il suo codice dal ramo
  principale e il ramo solo come dati) e nessun runner self-hosted per loro: lì il modello sarebbe l'utente del
  runner.
- **Fermi:** tre tentativi a giro; un lavoro che fallisce un giro intero diventa «bloccato» e torna a chi decide; ramo
  principale rosso = niente lavori nuovi; una porta che non risponde lascia un solo avviso e nessun lavoro toccato. Un
  oracolo rosso non chiude il compito: torna all'esecutore, e al terzo rosso a chi decide.
- **Lanciare e aspettare:** `bottega lancia <N>` mette l'etichetta e dice se il distributore ha avviato davvero quel
  lavoro (una finestra di manutenzione o una bottega occupata non danno errori); `bottega segui <N>` aspetta e sveglia
  chi decide sulla fine, su una domanda, su un blocco e sul silenzio (nessun giro da troppo tempo).
- **L'interruttore**, dalla macchina di chi decide: `bottega ferma` spegne tutti i workflow della bottega del progetto,
  `bottega riparti` li riaccende.
- **L'installazione** la fa la CLI seguendo `INSTALLA.md` del clone della bottega: `bottega installa macchina`,
  `runner` e `progetto`, ognuno prima con `--prova`. `bottega aggiorna --tag <tag>` porta i workflow del progetto a un
  rilascio nuovo della bottega, con una PR.

## Le misure

Per ogni compito, nei campi del Project:
- chi l'ha eseguito, da che porta, in sessione o fuori; durata, giri, consulti;
- **la quota spesa da chi decide** per brief e revisione: un segno all'inizio e uno alla fine (`bottega segno inizio
  <numero dell'issue>`, `bottega segno fine`), e il comando legge i contatori dalla trascrizione della sua porta. Un
  segno dimenticato lascia il numero vuoto, mai inventato;
- l'esito della revisione per compito (unito com'era, corretto, rifiutato) e i rilievi gravi per origine;
- per i consiglieri, i consigli accolti e respinti, e quelli che col tempo si rivelano giusti o sbagliati.

`bottega conti` legge i numeri. Chi decide tiene d'occhio la spia del metodo: brief più revisione di un compito fatto
fuori costano meno che farlo in sessione? Dice all'utente ciò che giudica utile.

## Come impara

- **I quaderni**, uno per modello: le lezioni su come quel modello lavora, ognuna una regola breve con la PR da cui
  viene. Chi decide legge il quaderno del modello quando scrive un brief per lui e quando rivede il suo lavoro, e
  scrive le lezioni nuove durante la revisione. Il fascicolo dell'esecutore contiene sempre il quaderno del suo modello.
- **La casistica:** casi con scenario, domanda, opzioni, la **scelta** presa, il perché e l'esito. Non sono regole: sono
  precedenti, e la skill vince sempre. Quando la skill non risponde a un caso si cerca un precedente per parole chiave;
  un caso nuovo (un Ruling rifiutato, un rilievo grave, un esecutore che ha fallito, una scelta fatta a giudizio) si
  aggiunge a fine tappa.
- **Dove stanno:** quaderni e casistica comuni nel clone della bottega (`quaderni/`, `casistica/`); quelli di chi
  usa la bottega nel repo del suo progetto (`.github/bottega/quaderni/`, `.github/bottega/casistica/`), che il
  fascicolo legge insieme ai comuni. Mandare una lezione al repo della bottega, con una PR, è facoltativo; ciò che
  parla di un progetto resta nel progetto. Le lezioni sul progetto vanno nella sua costituzione.
- **Il banco di prova:** quando la skill cambia, un consigliere risponde ai casi con la skill nuova e senza le risposte
  (`bottega casi --domande` dà il foglio), dalla macchina di chi decide; si confrontano le scelte e chi decide guarda
  solo le divergenze: si corregge la skill o il caso. L'esito va come commento sulla PR della skill.

## Dopo una compattazione o un crash

Si riparte da GitHub e dai file: il Project, le issue della tappa, le PR aperte, il piano, `git log`, `git status`,
`git worktree list`. Un esecutore ancora al lavoro sullo stesso worktree o sullo stesso lavoro si lascia finire: non
se ne lancia un altro.
