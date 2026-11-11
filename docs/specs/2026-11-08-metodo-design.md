# La bottega: design del metodo

Stato: approvato e costruito (tappe B0-B8, `docs/plans/2026-11-08-tappe.md`). Scritto l'8 novembre 2026 da un
brainstorming con l'utente che ha fondato il metodo, riletto da un costruttore (Gemini 4 Argon) e rifatto dopo le sue
domande.

## Perché

Chi lavora con le CLI di programmazione ha più abbonamenti, più modelli e una risorsa sola davvero scarsa: la quota del
modello che decide. La bottega spende quella quota solo dove serve. Chi decide prende le decisioni prima, per iscritto,
nel piano e nel brief; a chi esegue resta il *come*, non il *cosa*. Così l'esecuzione va a modelli più economici o a
quote più abbondanti, anche di altri fornitori.

Tre richieste dell'utente danno la forma a tutto:

1. **Dinamica, non legata a un assetto.** Il metodo non conosce modelli, fornitori né ruoli fissi: conosce funzioni e
   botteghe, e sceglie a ogni compito chi lo fa.
2. **Legata a GitHub.** Lavoro, consegne, consulti, misure, lezioni e regia vivono su GitHub e si muovono coi suoi
   eventi. Niente cartelle né script per sincronizzare.
3. **Da regalare.** Un repo pubblico che si installa come plugin in più CLI: lo si dà a un amico, la sua CLI lo
   installa e lui è pronto.

Questa versione non è compatibile all'indietro con quella a una bottega sola: è un nuovo inizio.

## Obiettivi

- Spendere la quota scarsa solo per decidere e rivedere.
- Usare le quote abbondanti di ogni abbonamento senza che un esecutore confuso possa fare danni.
- Adattarsi da sola agli abbonamenti, ai modelli e alle CLI che l'utente ha, oggi e domani.
- Imparare dal lavoro: lezioni per modello, casistica, misure di tutto, che guidano le scelte.

## Non obiettivi

- Windows senza WSL e macOS: questa versione gira su Linux e su Windows con WSL.
- Un orchestratore proprio: la regia è GitHub Actions.
- Sostituire le skill di processo che la CLI ha già (brainstorming, piani, prove): la bottega ci si appoggia.

## Anti-obiettivi

Il metodo è fallito, anche se funziona, se:
- diventa un recinto di regole: le barriere stanno solo dove un errore farebbe un danno vero (segreti, dati veri,
  cancellazioni, azioni irreversibili o verso l'esterno), il resto è giudizio di chi lavora, controllato dal diff;
- la skill nomina un modello, un fornitore o un assetto particolare;
- qualcosa si sincronizza fuori da git e da GitHub;
- un esecutore esterno può unire nel ramo principale, chiudere lavoro o mandare in produzione;
- rivedere il lavoro di un esecutore costa più di quanto risparmia;
- nel repo pubblico finisce qualcosa di personale o di un progetto.

## I concetti

**Bottega:** un abbonamento con la sua quota, cioè un fornitore e un accesso. Le botteghe sono quante ne ha l'utente.
Ognuna dichiara nella configurazione i suoi modelli, com'è la sua quota (scarsa, normale, abbondante) e da quali porte
ci si entra.

**Porta:** la CLI con cui si entra in una bottega. Una CLI può aprirne più d'una (Pi con un accesso Anthropic e uno
Copilot); una bottega può avere più porte (Anthropic da Claude Code su una macchina, da Pi su un'altra). Le porte della
prima versione: Claude Code, Antigravity, Pi, GitHub Copilot CLI.

**Funzioni, non ruoli fissi.** Il metodo conosce quattro funzioni:

| Funzione | Che cosa fa |
|---|---|
| decidere | brainstorming con l'utente, design, piano, brief, revisione finale, unione, rilascio |
| eseguire | un compito da un brief, in TDD, in sessione o fuori come PR |
| rivedere | la rilettura a mente fresca di un ramo o di una PR |
| consigliare | critiche a design e piani, arbitrati, controlli su tutto il repo, consulti di chi esegue |

Per ogni funzione la configurazione elenca i **candidati** (un modello di una bottega, da una porta). Il nome di un
candidato è un titolo più il nome del modello, scelto dall'utente all'installazione («Maestro Opus», «Lavorante
Gemini 3.8»): il metodo non ne conosce nessuno.

**La scelta viva.** Lo schema da cui il metodo nasce resta: un decisore forte che pensa e un esecutore economico che
fa, per il massimo risultato al minimo costo. La scelta viva lo serve, non lo sostituisce.

- **Il criterio:** a ogni compito va il candidato col **costo atteso più basso per un risultato buono**: la quota
  scarsa che spende (quella di chi decide per brief e revisione, più quella del candidato se è scarsa), divisa per la
  probabilità che la sua PR sia unita com'è. Chi fa rifare metà del lavoro costa più di chi consuma un po' di quota e
  consegna giusto. La probabilità si impara dai risultati veri (unito com'era, corretto, rifiutato), con un po' di
  esplorazione per non smettere di imparare; non ci sono soglie fisse.
- **Il genere di compito** sono le etichette che il progetto ha già: la bottega non impone un suo elenco. I risultati
  si contano per candidato ed etichetta.
- **Il punto di partenza**, prima dei numeri: va **fuori** al primo candidato con quota abbondante tutto ciò che può
  aspettare una PR; **in sessione** resta ciò che serve subito. I numeri correggono da lì. I sotto-agenti in sessione
  consumano l'abbonamento di chi decide (meno del suo modello, ma lo consumano): è il motivo del «fuori» di serie.
- **La quota del momento:** nessuna porta la dice prima che finisca. Quando finisce, il workflow scrive lo stato della
  bottega («esaurita fino a…», dall'ora del rinnovo se il messaggio la dà) in una variabile di GitHub Actions del repo;
  i giri saltano quella bottega finché lo stato non scade.
- **Chi sceglie:** per i compiti fuori il workflow, con un calcolo semplice e senza modello; per quelli in sessione chi
  decide, con gli stessi numeri. Ogni scelta lascia sul lavoro una riga col perché.
- **A metà tappa** l'esecutore senza quota la tiene per un giro; se manca ancora, passa al candidato seguente, che
  riparte dal ramo e dalle note.
- **A mano:** un'etichetta «esegue: <nome>» sul lavoro vince sulla scelta; il risultato conta comunque.
- **I consulti** seguono la stessa regola fra i consiglieri: risponde il candidato col costo atteso più basso che ha
  quota.

**Due modi di eseguire:**
- **in sessione:** un sotto-agente nel worktree di chi decide; il consulto è immediato; il commit è di chi decide;
- **fuori:** un esecutore lanciato da GitHub Actions nel suo clone, con commit suoi e una PR in bozza; il sigillo di
  chi decide è l'unione `--no-ff` dopo la revisione.

## GitHub come spina dorsale

| Cosa | Dove vive |
|---|---|
| il lavoro da fare | issue del progetto, nel suo Project |
| il brief di un compito, in sessione o fuori | il corpo della sua issue |
| chi lo esegue e il suo stato | campi del Project |
| la consegna | una PR in bozza con la riga `Lavoro: #N` |
| un consulto e la sua risposta | commenti sulla PR o sull'issue |
| design e piani da criticare | PR in bozza, con commenti di revisione del consigliere |
| il resoconto della notte | commenti sui lavori toccati, letti da chi decide |
| lo stato della quota di ogni bottega | variabili di GitHub Actions del repo |
| le misure | campi del Project, uno per misura |
| lezioni per modello e casistica | file del repo `bottega`, cambiati solo con PR |
| la skill e i suoi aggiornamenti | il repo `bottega`, installato come plugin |

Un progetto che ha già un suo comando per la board lo collega come **adattatore**: i workflow non scrivono sul Project
da soli ma passano da lui, con cinque operazioni (leggere i lavori pronti, prenderne uno, cambiarne lo stato, scrivere
una consegna, scrivere un campo). Senza adattatore i workflow usano `gh` direttamente.

Niente cartelle condivise, niente copie, niente script di sincronia: ciò che serve a più macchine passa da git o da
GitHub.

## La regia: GitHub Actions

I workflow della bottega stanno nel progetto e girano su **runner self-hosted**, cioè sulle macchine dove la porta ha
fatto l'accesso al suo abbonamento.

- **Eventi:** un lavoro etichettato o assegnato all'esecuzione fuori fa partire un esecutore; un comando in un
  commento chiede un consulto o una nuova passata; un orario fa partire la notte, fuori dalla finestra di manutenzione
  del progetto.
- **La concorrenza.** `concurrency` di Actions non è una coda: tiene un giro in corso e uno solo in attesa, e cancella
  l'attesa più vecchia quando ne arriva una nuova. Quindi:
  - **il distributore:** un solo job, in fila con se stesso (un gruppo di concorrenza unico), sceglie dal Project il
    prossimo lavoro pronto e il candidato (scelta viva), scrive l'assegnazione sul lavoro e lancia l'esecutore di
    quella bottega. Siccome è uno solo, due esecutori non prendono mai lo stesso lavoro. Riparte alla fine di ogni
    giro e a orario; un giro cancellato non perde niente, perché lo stato sta su GitHub. Se il runner di una bottega è
    spento (un PC di lavoro la sera), il giro di quella bottega aspetta in coda finché il runner torna;
  - **uno per bottega:** l'esecutore di ogni bottega ha il suo gruppo di concorrenza fisso (un workflow per bottega,
    scritto dall'installazione), così due esecutori della stessa quota non girano insieme, mentre esecutori di
    botteghe diverse possono;
  - **mai due giri sullo stesso lavoro:** un commento che arriva mentre un esecutore ci lavora lo legge il giro dopo,
    che parte appena il primo finisce; un giro in corso non si interrompe mai;
  - **il consulto nello stesso giro:** esecutore, consigliere e ripresa stanno nello stesso job, così un solo runner
    non si blocca aspettando se stesso;
  - **le scritture su GitHub** di un giro (campi, commenti, etichette) restano sotto i limiti di GitHub: i giri lunghi
    le raccolgono e le scrivono a fine lavoro.
- **Chi può comandare:** gli account elencati nella configurazione (di serie il proprietario del repo), coi commenti
  senza segno e con le etichette-comando. I workflow non mettono mai un'etichetta-comando: le etichette che scrivono
  (stato, quota, allarmi) non fanno partire niente, quindi niente anelli.
- **Un workflow sceglie il candidato** coi criteri della scelta viva; a quota esaurita (riconosciuta dai messaggi
  d'errore della porta) il lavoro prende un'etichetta e il giro dopo riprova o passa al candidato seguente.
- **Il consulto di un esecutore bloccato:** l'esecutore chiude il turno con un commento di consulto; il workflow
  chiama il primo consigliere con quota, che risponde nello stesso filo, e riprende l'esecutore nella sua
  conversazione.
- **Fermi automatici:** tre tentativi per lavoro a giro; un lavoro che fallisce un giro intero diventa «bloccato» e
  passa a chi decide; ramo principale rosso = niente lavori nuovi.
- **Interruttore:** `bottega ferma` disattiva i workflow della bottega (`gh workflow disable`), `bottega riparti` li
  riattiva.
- **Senza runner sempre acceso** (per esempio un PC di lavoro spento la sera) non c'è la notte: l'esecutore fuori
  parte solo quando lo si chiama, sul runner di quella macchina, mentre è accesa.

## La vita di un lavoro

- **Una tappa, un ramo, una PR.** I compiti di un piano che dipendono l'uno dall'altro si fanno in ordine sullo stesso
  ramo, un commit per compito; il raccoglitore prende il compito seguente di una tappa solo su quel ramo e solo dopo il
  precedente. Un consigliere rilegge ogni compito appena fatto, nello stesso giro; chi decide rivede la PR intera a
  fine tappa. I lavori sciolti (un debito, un bug) hanno ognuno il suo ramo e la sua PR.
- **Il sostituto.** Se il primo candidato a decidere è senza quota, il primo candidato con quota rivede le PR pronte e
  le segna «pronta per l'unione» o chiede correzioni; non pianifica e non unisce. L'unione resta a chi decide, che al
  ritorno parte dalla revisione del sostituto.
- **Salvataggio e ripresa.** Un giro che deve fermarsi (quota finita, runner che si riavvia, tempo scaduto) committa e
  spinge lo stato sul suo ramo e scrive sul lavoro dov'era arrivato e l'identificativo della conversazione. Il giro
  dopo riprende la conversazione se la porta la ha ancora, altrimenti riparte dal ramo e dalle note.
- **Il controllo all'apertura.** Prima di toccare un lavoro, il giro controlla che la porta risponda, che l'accesso
  sia valido e quale versione della porta c'è (le porte si aggiornano da sole). Se qualcosa non va non tocca nessun
  lavoro e lascia un solo avviso per chi decide, che resta finché il guasto dura; i lavori non diventano «bloccati»
  per un guasto della porta.

- **I brief dei compiti fuori:** chi decide scrive il piano coi Ruling; il primo consigliere con quota lo divide in
  issue coi brief; chi decide li scorre prima che partano (legge, non scrive). Senza consigliere con quota li scrive
  chi decide.
- **Il consigliere senza quota a metà tappa:** il compito va avanti senza rilettura e il lavoro lo segna; la revisione
  di fine tappa guarda quei compiti per primi.
- **Il repo pubblico non ha runner self-hosted** né workflow che girano su PR altrui (una PR da un fork farebbe girare
  codice estraneo sulla macchina): solo il controllo dei dati personali, sui runner di GitHub. Le lezioni ci arrivano
  con PR aperte da chi decide.
- **Più progetti sulla stessa bottega:** un runner appartiene a un repo e `concurrency` vale dentro un repo, quindi
  due progetti possono far lavorare insieme due esecutori della stessa quota; li reggono la scelta viva e la «quota
  esaurita».
- **L'oracolo lo esegue il workflow, non il modello.** Il «fatto quando» del brief è un comando, in un campo
  strutturato del lavoro; il workflow lo lancia dopo il modello e scrive lui l'esito sulla PR. Ciò che il modello dice
  delle sue prove non conta. In un progetto con la sua CI valgono tutte e due: la CI e il comando del brief, se c'è.
- **Ciò che salta all'occhio lo segna il workflow:** una PR che cambia prove già esistenti, o che fa scattare il
  controllo dei segreti, prende un'etichetta, e la revisione la guarda per prima.
- **Le issue senza brief** (scritte di getto dall'utente) l'esecutore non le prende: chi decide le trasforma in
  compiti.
- **Cosa scrive il modello alla fine:** il testo della PR, dei commenti e della consegna in file con un formato fisso,
  nello spazio di lavoro del giro, che si butta a fine giro. Le sue trascrizioni restano sul runner, non nei log di
  GitHub.
- **Il fascicolo** che il workflow prepara contiene sempre, oltre al lavoro, la costituzione del progetto e il quaderno
  del modello dell'esecutore: le lezioni arrivano da sole.
- **Una PR rifiutata** la chiude chi decide, col motivo scritto; la lezione va nel quaderno; il lavoro torna da rifare
  o si chiude.
- **Il resoconto** per chi decide è una vista del Project, «toccati nelle ultime 24 ore», non un testo scritto apposta.

## L'esecutore fuori: libertà e confini

- **Fiducia larga da subito**, anche sul codice delicato quando il piano dà firme e valori.
- **Che cosa fa:** prima i lavori che chi decide gli assegna; finiti quelli, il distributore gli dà i debiti e i bug che
  hanno un «fatto quando» strutturato (il consigliere può aggiungerlo a quelli che lo meritano), e lo annuncia sul
  lavoro prima di cominciare. Non sceglie mai da solo: decisioni dell'utente, design e
  specifiche, lavori che aspettano l'utente o già presi, ciò che tocca segreti, dati veri, cancellazioni o azioni
  irreversibili o verso l'esterno, più ciò che la costituzione del progetto aggiunge.
- **Tiene vive le sue PR:** risolve i conflitti col ramo principale e corregge ciò che chi decide chiede nei commenti.
- **I sotto-agenti** solo col suo modello, mai con quello di un consigliere, la cui quota è di solito scarsa.
- **Dove gira:** un utente Unix suo, con la sua cartella chiusa e la sua porta col suo accesso; non vede
  segreti del progetto, chiavi, archivi di password, memorie di altre CLI. La rete la decide la costituzione del
  progetto (di serie libera).
- **Le chiavi le tiene il workflow, non il modello, e non sono nemmeno lo stesso utente.** Sulla macchina ci sono due
  utenti: quello del runner, che ha il token di GitHub, e quello dell'esecutore, che ha solo la sua porta. Ogni giro
  ha tre passi: prima il runner prepara il fascicolo del lavoro (issue, piano, commenti, stato della PR) e una copia
  del ramo per l'esecutore; poi il modello lavora come utente dell'esecutore, **senza nessuna chiave di GitHub** e
  senza accesso al runner, committa nella sua copia e consegna **una patch** più i testi della PR, dei commenti e
  delle consegne; infine il runner applica la patch su un clone pulito suo (così nessun hook o programma lasciato dal
  modello scatta col token) e controlla: ramo dell'esecutore, mai i rami protetti, niente file sotto `.github/`. Solo
  allora spinge, apre la PR in bozza, scrive commenti e campi. Una pagina malevola letta durante una ricerca non arriva
  a nessun repo.
- **Il token del runner** viene da un accesso `gh` suo, fatto dall'installazione (si apre il browser una volta): non
  dipende dalla sessione `gh` della macchina dell'utente.
- **Le prove che vogliono permessi** (per esempio una gabbia per le prove) passano da un solo comando di root, stretto,
  che la costituzione del progetto definisce: l'esecutore non riceve altri `sudo`.
- **Si chiama da GitHub**, di giorno come di notte: un'etichetta o un'assegnazione sul lavoro. Una sessione aperta a
  mano con la porta dell'esecutore serve per esplorare, non per consegnare.
- **Un solo account GitHub**, quello dell'utente, per tutti: niente account in più da creare. Il workflow mette un
  segno nascosto su ogni commento e PR che scrive, e il segno dice chi scrive (esecutore, revisore, consigliere). Un
  commento col segno non è mai un comando, ma entra nel fascicolo come dato: così le correzioni chieste da un sostituto
  arrivano all'esecutore. A muovere il lavoro sono i campi del Project, non i commenti: le revisioni sono di solo
  commento (le uniche ammesse sulla propria PR) e l'esito («pronta per l'unione», «correzioni», «rifiutata») è un campo;
  il distributore riprende i lavori con esito «correzioni», e il sostituto rivede solo quelli «da rivedere».
- **Il sigillo è una firma:** chi decide firma ciò che mette nel ramo principale (unioni e, se capita, commit diretti)
  con una chiave SSH che esiste solo sulla sua macchina. Il repo tiene l'elenco delle chiavi ammesse sotto `.github/`
  (dove l'esecutore non consegna); un attrezzo di rilascio che scrive da sé sul ramo principale (per esempio un ritorno
  indietro automatico) ha la sua chiave, ammessa anch'essa. Un progetto che rilascia da solo rilascia solo una punta
  firmata con una chiave ammessa, e l'elenco lo legge dall'ultimo rilascio, non dalla punta nuova: un push estraneo non
  può autorizzare la propria chiave. Altrimenti si ferma e avvisa: un push sbagliato resta rosso.

## Come impara

- **Una skill sola**, generica, nel plugin; le differenze fra le porte in una pagina per porta.
- **I quaderni, uno per modello:** le lezioni sul modello, ognuna come regola breve con la PR da cui viene. Le scrive
  chi decide durante la revisione, con una PR al repo `bottega`. Quando il fornitore cambia modello, il quaderno si
  rilegge. Le lezioni sul progetto vanno nella costituzione del progetto, nel suo repo.
- **La casistica:** riparte da zero. Ogni caso ha scenario, domanda, opzioni, la **scelta** presa (così uno script
  confronta senza modello), il perché e l'esito. Cresce con PR al repo `bottega`; un caso che parla di un progetto
  resta nel progetto.
- **Le lezioni di chi installa:** un amico che usa la bottega tiene le sue lezioni e i suoi casi nel repo del suo
  progetto (versionati, su GitHub), e il fascicolo li legge insieme a quelli del repo `bottega`; mandarceli con una PR
  è facoltativo.
- **Il banco di prova:** quando la skill cambia, un consigliere risponde a 100-200 casi (tutti, finché sono meno) con
  la skill nuova e senza le risposte; uno script confronta le scelte; chi decide guarda solo le divergenze. Gira dalla
  macchina di chi decide (il repo pubblico non ha runner coi suoi abbonamenti), e l'esito va come commento sulla PR del
  repo `bottega`. Senza quota del consigliere lo fa l'esecutore.
- **Le misure: tutto, nei campi del Project**, sul lavoro di ogni compito (al più 50 campi per Project):
  - l'esecutore (un campo a scelta coi nomi dei candidati, le cui opzioni si aggiungono senza perdere i valori), da che
    porta, in sessione o fuori; durata, giri, consulti; la quota dell'esecutore se la porta la dà: li scrive il
    workflow, o chi decide in sessione;
  - **la quota spesa da chi decide** per brief e revisione, il numero che decide: chi decide mette un segno d'inizio e
    uno di fine quando scrive un brief o rivede; un comando legge i contatori della trascrizione della sua porta e
    scrive il campo. Un segno dimenticato lascia il compito senza numero, mai con uno inventato. Una porta che non dà
    tutti i contatori (Copilot registra per turno solo i token in uscita) scrive ciò che ha, segnato «parziale». Il
    costo di un lavoro fatto per tutta una tappa (una revisione finale, i brief scritti insieme) sta sulla tappa; la
    scelta viva lo divide fra i compiti dichiarandolo stima;
  - **l'esito della revisione** (unito com'era, corretto, rifiutato) **per compito** quando si può: ogni commento di
    correzione indica il commit del compito; i compiti senza commenti sono «uniti com'erano»; se non si può dire,
    l'esito vale per tutta la tappa;
  - i rilievi gravi, un numero per origine (piano, brief, esecuzione); per i consiglieri, i consigli accolti e respinti,
    e quelli che col tempo si rivelano giusti o sbagliati, quando chi decide lo vede.
- **La lettura.** La scelta viva legge da sola esiti e costi per candidato ed etichetta. Chi decide legge i conti con un
  comando che interroga il Project; tiene d'occhio la spia del metodo (rivedere il lavoro dell'esecutore fuori costa
  meno che farlo in sessione?) e dice all'utente ciò che giudica utile, senza una regola. Le viste e i grafici del
  Project, che le API di GitHub non creano, l'utente li può creare una volta a mano da un elenco che l'installazione gli
  dà; la bottega funziona anche senza.

## Il repo, il plugin e l'installazione

- **Il repo `bottega`**, pubblico, licenza MIT, in italiano: il plugin (skill, pagine per porta, modelli di brief e di
  costituzione), i workflow modello, i quaderni, la casistica, la guida per le persone (`LEGGIMI.md`) e quella per la
  CLI (`INSTALLA.md`).
- **Il plugin** si installa in ogni porta da un clone git del repo sulla macchina, aggiornato con `git pull`: l'unico
  mezzo di sincronia resta git (Claude Code accetta un marketplace che è una cartella; Antigravity accetta solo una
  cartella locale o un marketplace già collegato, senza dipendenze). Così nessun documento scrive il proprietario del
  repo (deciso in B1). Il modello dell'esecutore non
  tocca GitHub, quindi non gli servono skill di board; le skill di stile (Python, Rust) restano facoltative, dalle loro
  fonti.
- **L'installazione** (la CLI segue `INSTALLA.md`) fa da sola tutto ciò che può: riconosce porte e sistema, installa
  il plugin in ogni porta, scopre abbonamenti e modelli, propone funzioni e candidati, e chiede solo ciò che non può
  sapere: come l'utente vuole essere chiamato, il progetto, quali abbonamenti si possono usare su quel progetto (un
  progetto di lavoro può avere regole su dove va il codice), se vuole l'esecutore fuori e la notte. Poi scrive nel
  progetto, con una PR: la costituzione, un `AGENTS.md` alla radice che rimanda a lei, la configurazione delle botteghe
  e dei candidati, i workflow; prepara i campi del Project (se manca il permesso lancia `gh auth refresh -s project`,
  che apre il browser una volta; se manca il Project, lo crea). Crea la chiave di firma di chi decide e configura git
  per firmare. Mette fra i segreti del repo il token dell'accesso che `gh` ha già (`gh secret set`), senza far creare
  token a mano (il token è quello dell'accesso `gh` del runner, fatto dall'installazione). Sulla macchina, se
  richiesto: l'utente dell'esecutore, l'utente del runner col runner, e il solo `sudo` che serve al runner per lanciare
  la porta come utente dell'esecutore (chiede `sudo` una volta).
  Se il repo non ammette runner self-hosted (succede nei repo aziendali) o l'utente non li vuole, la bottega lavora
  solo in sessione e lo dice in una riga.
- **Il repo è pubblico:** un workflow controlla ogni PR del repo `bottega` cercando segreti, nomi e percorsi personali.

## Lasciato al costruttore

La disposizione dei file del plugin e dei workflow; il formato della configurazione; i nomi dei campi del Project e
delle etichette; i comandi di consulto nei commenti; come ogni porta lavora senza mani e come se ne leggono modelli,
token ed errori di quota; il peso dei criteri della scelta viva.

## Le scelte di chi ha scritto il design

Fatte durante il brainstorming o dopo la revisione del costruttore, non dall'utente, e quindi rivedibili: la licenza
MIT; il controllo delle PR del repo pubblico; «senza quota si passa al candidato seguente»; le lezioni sul progetto
nella costituzione e non nel quaderno; i tre tentativi a giro; il rinvio a `AGENTS.md`; i sotto-agenti solo col
modello dell'esecutore; la «scelta» codificata nei casi; la quota di chi decide misurata dalle trascrizioni; chi può
comandare dai commenti.
