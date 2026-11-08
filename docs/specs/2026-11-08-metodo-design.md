# La bottega: design del metodo

Stato: design, da approvare. Scritto l'8 novembre 2026 da un brainstorming con l'utente che ha fondato il metodo,
riletto da un costruttore (Gemini 4 Argon) e rifatto dopo le sue domande.

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

**La scelta viva.** Per ogni compito chi decide sceglie chi esegue fra i candidati guardando:
- la quota del momento: un candidato senza quota passa il turno al successivo;
- i risultati misurati dello stesso genere di compito (esito delle revisioni, giri, costo per chi decide);
- il genere di compito, cioè se serve subito in sessione o può aspettare una PR.

Di serie va **fuori**, come PR, tutto ciò che può aspettare una revisione; **in sessione** resta ciò che serve subito.
Lo stesso vale per i consulti: il primo consigliere con quota risponde.

**Due modi di eseguire:**
- **in sessione:** un sotto-agente nel worktree di chi decide; il consulto è immediato; il commit è di chi decide;
- **fuori:** un esecutore lanciato da GitHub Actions nel suo clone, con commit suoi e una PR in bozza; il sigillo di
  chi decide è l'unione `--no-ff` dopo la revisione.

## GitHub come spina dorsale

| Cosa | Dove vive |
|---|---|
| il lavoro da fare | issue del progetto, nel suo Project |
| chi lo esegue e il suo stato | campi del Project |
| la consegna | una PR in bozza con la riga `Lavoro: #N` |
| un consulto e la sua risposta | commenti sulla PR o sull'issue |
| design e piani da criticare | PR in bozza, con commenti di revisione del consigliere |
| il resoconto della notte | commenti sui lavori toccati, letti da chi decide |
| le misure | campi del Project, uno per misura |
| lezioni per modello e casistica | file del repo `bottega`, cambiati solo con PR |
| la skill e i suoi aggiornamenti | il repo `bottega`, installato come plugin |

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
  - **il raccoglitore:** un giro non riceve un lavoro, lo prende; ogni giro sceglie dal Project il prossimo lavoro
    pronto e, finito quello, il seguente, finché ce ne sono. Un giro cancellato non perde niente, perché lo stato sta
    su GitHub; un orario fa da rete di sicurezza;
  - **uno per bottega:** un gruppo di concorrenza per bottega, così due esecutori della stessa quota non girano
    insieme, mentre esecutori di botteghe diverse possono;
  - **mai due giri sullo stesso lavoro:** un commento che arriva mentre un esecutore ci lavora lo legge il giro dopo,
    che parte appena il primo finisce; un giro in corso non si interrompe mai;
  - **il consulto nello stesso giro:** esecutore, consigliere e ripresa stanno nello stesso job, così un solo runner
    non si blocca aspettando se stesso;
  - **le scritture su GitHub** di un giro (campi, commenti, etichette) restano sotto i limiti di GitHub: i giri lunghi
    le raccolgono e le scrivono a fine lavoro.
- **Chi può comandare:** solo i commenti e le etichette di chi ha il ruolo di proprietario o collaboratore del repo;
  il resto è testo.
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

## L'esecutore fuori: libertà e confini

- **Fiducia larga da subito**, anche sul codice delicato quando il piano dà firme e valori.
- **Che cosa fa:** prima i lavori che chi decide gli assegna; finiti quelli, sceglie fra i debiti e i bug che hanno un
  oracolo, e lo annuncia sul lavoro prima di cominciare. Non sceglie mai da solo: decisioni dell'utente, design e
  specifiche, lavori che aspettano l'utente o già presi, ciò che tocca segreti, dati veri, cancellazioni o azioni
  irreversibili o verso l'esterno, più ciò che la costituzione del progetto aggiunge.
- **Tiene vive le sue PR:** risolve i conflitti col ramo principale e corregge ciò che chi decide chiede nei commenti.
- **I sotto-agenti** solo col suo modello, mai con quello di un consigliere, la cui quota è di solito scarsa.
- **Dove gira:** un utente Unix suo, con la sua cartella chiusa, il runner, la sua porta col suo accesso e un `gh`
  coll'account dell'utente; non vede segreti del progetto, chiavi, archivi di password, memorie di altre CLI. La rete
  la decide la costituzione del progetto (di serie libera).
- **Tre guardie locali:** un `gh` che rifiuta di unire e chiudere PR e issue; un controllo di git che rifiuta il push
  sui rami protetti; un controllo di git che rifiuta il push di un ramo che tocca `.github/`. Sono freni contro gli
  errori, non confini.
- **Il confine vero sul rilascio:** l'esecutore committa con un'identità git sua; un progetto che rilascia da solo dal
  ramo principale non rilascia una punta che non è un'unione di chi decide o dell'utente, e avvisa.

## Come impara

- **Una skill sola**, generica, nel plugin; le differenze fra le porte in una pagina per porta.
- **I quaderni, uno per modello:** le lezioni sul modello, ognuna come regola breve con la PR da cui viene. Le scrive
  chi decide durante la revisione, con una PR al repo `bottega`. Quando il fornitore cambia modello, il quaderno si
  rilegge. Le lezioni sul progetto vanno nella costituzione del progetto, nel suo repo.
- **La casistica:** riparte da zero. Ogni caso ha scenario, domanda, opzioni, la **scelta** presa (così uno script
  confronta senza modello), il perché e l'esito. Cresce con PR al repo `bottega`; un caso che parla di un progetto
  resta nel progetto.
- **Il banco di prova:** quando la skill cambia, un consigliere risponde a 100-200 casi (tutti, finché sono meno) con
  la skill nuova e senza le risposte; un workflow confronta le scelte; chi decide guarda solo le divergenze.
- **Le misure: tutto, nei campi del Project.** Per ogni lavoro: chi l'ha eseguito, con che modello, da che porta, in
  sessione o fuori; la quota spesa da chi decide per brief e revisione (il numero che decide, dai token delle
  trascrizioni della sua porta); le quote altrui e le durate, se la porta le dà; giri e consulti; l'esito della
  revisione (unito com'era, corretto, rifiutato); i rilievi gravi e da dove venivano. Per i consiglieri, i consigli
  accolti, respinti e, col tempo, giusti o sbagliati. Le misure alimentano la scelta viva; chi decide dice all'utente
  solo ciò che cambia la strada.

## Il repo, il plugin e l'installazione

- **Il repo `bottega`**, pubblico, licenza MIT, in italiano: il plugin (skill, pagine per porta, modelli di brief e di
  costituzione), i workflow modello, i quaderni, la casistica, la guida per le persone (`LEGGIMI.md`) e quella per la
  CLI (`INSTALLA.md`).
- **Il plugin** si installa e si aggiorna col sistema di plugin di ogni porta, dal repo GitHub, come le altre raccolte
  di skill che supportano più CLI; le skill compagne sono sue dipendenze. Come ogni porta installa un plugin da GitHub
  si verifica prima di scriverne la pagina.
- **L'installazione** (la CLI segue `INSTALLA.md`) fa da sola tutto ciò che può: riconosce porte e sistema, installa
  il plugin in ogni porta, scopre abbonamenti e modelli, propone funzioni e candidati, e chiede solo ciò che non può
  sapere: come l'utente vuole essere chiamato, il progetto, quali abbonamenti si possono usare su quel progetto (un
  progetto di lavoro può avere regole su dove va il codice), se vuole l'esecutore fuori e la notte. Poi scrive nel
  progetto, con una PR: la costituzione, un `AGENTS.md` alla radice che rimanda a lei, la configurazione delle botteghe
  e dei candidati, i workflow; prepara i campi del Project. Sulla macchina, se richiesto: l'utente dell'esecutore, il
  runner, le guardie (chiede `sudo` una volta).
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
