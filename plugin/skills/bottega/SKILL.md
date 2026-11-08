---
name: bottega
description: Metodo di lavoro «bottega» per spendere la quota scarsa solo dove serve. Chi decide scrive piano e brief, chi esegue lavora (in sessione o fuori, come PR su GitHub), un consigliere critica e consiglia. Usala quando un piano con le decisioni prese è pronto da eseguire, quando l'utente dice «bottega», e all'inizio di ogni sessione su un progetto che ha `.github/bottega/bottega.toml`.
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

Tutto il resto è giudizio di chi lavora, controllato dal diff.

## Le parole

- **Bottega:** un abbonamento con la sua quota (un fornitore e un accesso). Ha i suoi modelli e una quota scarsa,
  normale o abbondante.
- **Porta:** la CLI con cui si entra in una bottega. Una CLI può aprire più botteghe e una bottega può avere più porte.
  Ogni porta ha la sua pagina in `porte/`: [Claude Code](porte/claude-code.md), [Antigravity](porte/antigravity.md),
  [Pi](porte/pi.md), [GitHub Copilot CLI](porte/copilot-cli.md).
- **Le quattro funzioni:**

  | Funzione | Che cosa fa |
  |---|---|
  | decidere | brainstorming con l'utente, design, piano, brief, revisione finale, unione, rilascio |
  | eseguire | un compito da un brief, in TDD, in sessione o fuori come PR |
  | rivedere | la rilettura a mente fresca di un ramo o di una PR |
  | consigliare | critiche a design e piani, arbitrati, controlli su tutto il repo, consulti di chi esegue |

- **Candidato:** un modello di una bottega, da una porta, per una funzione. Il suo nome è un titolo più il nome del
  modello, scelto dall'utente («Maestro …», «Lavorante …»). Questa skill non conosce nessun modello: li legge dalla
  configurazione.
- **La configurazione** del progetto è `.github/bottega/bottega.toml`: botteghe, candidati per funzione, chi può
  comandare, l'adattatore della board. Se manca, la bottega lavora solo in sessione: decide il modello della
  sessione, eseguono i suoi sotto-agenti più economici.

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
  con gli stessi numeri (`bottega conti`). Ogni scelta lascia sul lavoro una riga col perché.

## Il ciclo

### Prima del codice

1. **Brainstorming e design** con l'utente. Niente piano finché l'utente non dice di andare avanti.
2. **Il piano**, nel ramo del lavoro. Contiene:
   - i **Ruling** numerati coi valori esatti;
   - il **Review Focus**: i casi che le prove non coprono;
   - i compiti, ognuno con file, interfacce consumate e prodotte, prove per nome e **chi lo esegue**.

   Se un compito chiede giudizio, chi decide prova prima a toglierlo dal compito e a scriverlo nel piano: un Ruling,
   una firma o un valore esatto. È il lavoro che rende sufficiente un esecutore economico. Il giudizio che non si può
   scrivere prima va a un candidato più forte, e il piano dice perché.
3. **Un consigliere critica** design e piano (una PR in bozza, coi suoi commenti). I disaccordi li decide chi decide,
   per iscritto; i grossi l'utente.
4. **L'utente legge il piano** prima del lancio, con le decisioni in testa.
5. **La costituzione del progetto** (`docs/costituzione.md`, modello in `modelli/costituzione.md`): ciò che vale per
   ogni compito. `AGENTS.md` alla radice rimanda a lei. Se manca, chi decide la scrive alla prima tappa.
6. **Le issue.** Una tappa è un'issue madre; i compiti sono le sue sotto-issue, in ordine. Il brief di ogni compito è
   il corpo della sua issue (modello in `modelli/brief.md`), col suo **«Fatto quando»**: il comando che dice se è
   fatto. Un consigliere con quota può dividere il piano in issue; chi decide le scorre prima che partano. Le issue
   scritte di getto, senza brief, nessun esecutore le prende: chi decide le trasforma prima in compiti.

### Per ogni compito

- **In sessione:** un sotto-agente nel worktree di chi decide, col brief dell'issue. Un compito alla volta per
  worktree. Il commit è di chi decide.
- **Fuori:** l'etichetta `bottega: fuori` sull'issue (o la notte, per i compiti pronti). Il workflow sceglie il
  candidato, gli prepara il fascicolo (issue, piano, costituzione, il quaderno del suo modello) e una copia del ramo;
  l'esecutore lavora senza chiavi di GitHub e consegna una patch; il workflow la controlla, lancia il «Fatto quando»,
  spinge e apre o aggiorna una PR in bozza. Un consigliere rilegge il compito nello stesso giro.

**La revisione del compito** la fa chi decide (o chi rivede, a fine tappa):
- si legge prima il **diff**, poi il rapporto, per non vedere il codice con gli occhi di chi l'ha scritto;
- si confronta col piano: interfacce, trappole, prove; l'esito del «Fatto quando» lo dice il workflow, non il modello;
- i Ruling di chi esegue si accettano o si rifiutano, una riga ciascuno; quelli che servono dopo entrano nel piano;
- una modifica fuori brief ma sensata si tiene (per esempio un difetto di un compito prima, corretto con una prova).
  Se però il rapporto tace un file toccato, il diff si rilegge tutto;
- correzioni piccole: un commento (fuori) o un messaggio allo stesso agente (in sessione); strutturali: un brief
  nuovo.

**Il consulto.** Chi esegue e si trova davanti a una scelta che contraddice il piano, è irreversibile o tocca segreti o
dati veri si ferma con una domanda precisa (`DOMANDA PER CHI DECIDE:`). In sessione risponde chi decide allo stesso
agente; fuori risponde il primo consigliere con quota, nello stesso giro, e l'esecutore riprende nella sua
conversazione. Per il resto, dove il piano lascia spazio, chi esegue decide e lo scrive come Ruling.

### Fine della tappa

1. **La revisione finale** del ramo intero, a mente fresca, da chi rivede (un candidato forte per i rami grandi o
   delicati). Riceve il diff dalla base, il piano, il Review Focus e i Ruling, e dice cosa ha controllato e cosa no.
2. **I rilievi** si pesano per il loro effetto e si contano per **origine**: piano, brief o esecuzione. I gravi si
   correggono con una prova che li fissa; i minori vanno nell'elenco del progetto. Un errore che torna va nella
   costituzione.
3. **L'unione** in `main` è di chi decide, `--no-ff`, **firmata** con la sua chiave: è il sigillo. Un esecutore non
   unisce, non chiude lavoro, non manda in produzione. Ciò che è irreversibile o esce verso l'esterno si chiede
   all'utente.
4. **Se la quota di chi decide finisce** la revisione finale non si taglia: la tappa resta aperta. Un sostituto con
   quota può rivedere e segnare l'esito «pronta per l'unione» o «correzioni»; l'unione aspetta chi decide.
5. **Quaderni e casistica**: chi decide scrive le lezioni nuove (sotto, «Come impara»).

## Fuori, su GitHub

- **Il lavoro vive su GitHub:** issue e Project per il lavoro, il corpo dell'issue per il brief, i campi del Project
  per stato, esecutore, esito e misure, PR in bozza per le consegne, commenti per i consulti, variabili di Actions per
  la quota. Niente cartelle, copie o script di sincronia.
- **La regia sono i workflow** della bottega, sui runner self-hosted delle macchine con le porte: un distributore in
  fila sceglie il lavoro e il candidato, un esecutore per bottega lavora.
- **Chi comanda:** gli account della configurazione, con le etichette (`bottega: fuori`, `esegue: <nome>`) e coi
  comandi nei commenti: `/bottega riprova` (un'altra passata), `/bottega consulta <domanda>` (al consigliere),
  `/bottega ferma` (questo lavoro si ferma). I commenti scritti dai workflow portano un segno nascosto e non sono mai
  comandi.
- **L'esito** di una revisione è il campo «Esito» del Project (`pronta per l'unione`, `correzioni`, `rifiutata`): il
  distributore riprende i lavori con `correzioni`. Una PR rifiutata la chiude chi decide, col motivo.
- **Fermi:** tre tentativi a giro; un lavoro che fallisce un giro intero diventa «bloccato» e torna a chi decide; ramo
  principale rosso = niente lavori nuovi; una porta che non risponde lascia un solo avviso e nessun lavoro toccato.
- **L'interruttore:** `bottega ferma` spegne i workflow della bottega, `bottega riparti` li riaccende.
- **L'esecutore fuori non sceglie mai da solo:** decisioni dell'utente, design, lavori che aspettano l'utente o già
  presi, ciò che tocca segreti, dati veri, cancellazioni, azioni irreversibili o verso l'esterno, più ciò che la
  costituzione aggiunge. Non tocca `.github/` né i rami protetti: la consegna lo rifiuta.

## Le misure

Per ogni compito, nei campi del Project (o, senza Project, in un registro del progetto):
- chi l'ha eseguito, da che porta, in sessione o fuori; durata, giri, consulti;
- **la quota spesa da chi decide** per brief e revisione: un segno all'inizio e uno alla fine (`bottega segno inizio
  <lavoro>`, `bottega segno fine`), e il comando legge i contatori dalla trascrizione della sua porta. Un segno
  dimenticato lascia il numero vuoto, mai inventato;
- l'esito della revisione per compito (unito com'era, corretto, rifiutato) e i rilievi gravi per origine.

`bottega conti` legge i numeri. Chi decide tiene d'occhio la spia del metodo, cioè se rivedere il lavoro di chi esegue
costa meno che farlo, e dice all'utente ciò che giudica utile.

## Come impara

- **I quaderni** (`quaderni/<modello>.md` nel repo della bottega): le lezioni su un modello, ognuna una regola breve
  con la PR da cui viene. Le scrive chi decide durante la revisione, con una PR. Il fascicolo dell'esecutore contiene
  sempre il quaderno del suo modello.
- **Le lezioni sul progetto** vanno nella costituzione del progetto, non nei quaderni.
- **La casistica** (`casistica/<area>.md`): casi con scenario, domanda, opzioni, la **scelta** presa, il perché e
  l'esito. Non sono regole: sono precedenti, e la skill vince sempre. Quando la skill non risponde a un caso si cerca
  un precedente per parole chiave; un caso nuovo (un Ruling rifiutato, un rilievo grave, un esecutore che ha fallito,
  una scelta fatta a giudizio) si aggiunge a fine tappa. Un caso che parla di un progetto resta nel progetto.
- **Il banco di prova:** quando la skill cambia, un consigliere risponde ai casi con la skill nuova e senza le
  risposte (`bottega casi --domande` dà il foglio); si confrontano le scelte e chi decide guarda solo le divergenze:
  si corregge la skill o il caso.

## Dopo una compattazione o un crash

Si riparte da GitHub e dai file: il Project, le issue della tappa, le PR aperte, il piano, `git log`, `git status`,
`git worktree list`. Un agente ancora in volo manda la sua notifica: si aspetta quella, non se ne lancia un altro
sullo stesso worktree.
