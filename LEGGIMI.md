# bottega

**La visione: ottenere il massimo risultato spendendo il minimo.** Tutto il resto viene da qui.

Un metodo per lavorare con più modelli e più abbonamenti spendendo la quota scarsa solo dove serve. Il modello che
decide scrive il piano e i brief; un modello più economico, o di un altro fornitore, esegue; il diff si rivede prima
di unire. La regia è GitHub: issue, Project, Actions.

L'immagine è la bottega rinascimentale: il maestro disegna, decide e firma; i lavoranti eseguono.

## Come funziona

- **Botteghe e porte.** Una bottega è un abbonamento (un fornitore e un accesso); una porta è la CLI con cui ci si
  entra: Claude Code, Antigravity, Pi, GitHub Copilot CLI. Le botteghe sono quante ne ha l'utente.
- **Funzioni, non ruoli fissi.** Decidere, eseguire, rivedere, consigliare. A ogni compito la **scelta viva** prende
  l'esecutore col costo atteso più basso per un risultato buono, tenendo conto della quota del momento e dei risultati
  misurati. Un'etichetta `esegue: <nome>` vince sempre.
- **Un lavoro è un'issue** col brief e il suo «Fatto quando» (i comandi che lo provano). Il distributore, un workflow
  di Actions, lo dà a una bottega. L'esecutore lavora su un runner self-hosted e consegna un ramo `bottega/*` con una
  PR in bozza; il workflow esegue l'oracolo. Chi decide rivede e unisce con una firma.
- **Il modello non ha mai chiavi.** L'esecutore è un utente Unix separato, senza credenziali GitHub; le spinte, i
  commenti e la board li fa il workflow, dopo i controlli sulla patch (niente `.github/`, niente rami protetti,
  gitleaks). La sua rete raggiunge internet ma non la rete di casa né i servizi della macchina.
- **Il sigillo è una firma.** Le unioni nel ramo principale sono firmate con una chiave ammessa, e il rilascio parte
  solo da una punta firmata.
- **Impara dal lavoro.** Misure per compito nei campi del Project, quaderni per modello, una casistica di scenari
  risolti.

Il disegno completo è in `docs/specs/2026-11-08-metodo-design.md`; le tappe della costruzione in
`docs/plans/2026-11-08-tappe.md`.

## Che cosa c'è

| Cartella | Contenuto |
|---|---|
| `plugin/` | la skill `bottega` e le pagine per ogni porta: si installa come plugin |
| `attrezzi/bottega/` | il comando `bottega` (Python 3.11 o più, solo libreria standard) |
| `.github/workflows/` | i workflow riusabili (distributore, esecutore) e il controllo del repo |
| `casistica/`, `quaderni/` | i precedenti del metodo e le lezioni per modello |
| `docs/` | design, piani delle tappe, ricognizioni, costituzione del repo |

## Installare

Si chiede alla propria CLI: «installa la bottega seguendo `INSTALLA.md`». La guida è scritta per lei: fa da sola
tutto ciò che può, chiede solo ciò che non può sapere, e mostra la prova a vuoto prima di ogni passo che cambia la
macchina o il progetto.

Serve Linux, o Windows con WSL 2; `git`, `python3` 3.11 o più, `gh` collegato al proprio account. Per l'esecutore
fuori servono anche systemd, `sudo` (una volta) e `nftables`.

## Stato

Versione 0.2.5. Costruita in quattordici tappe (B0-B13), più di mille prove. Il collaudo è stato fatto dal vivo,
adottandola in un progetto vero: sei lavori dell'esecutore fuori, più di venti compiti, sono arrivati alla PR,
e ogni intervento a mano è diventato una correzione con la sua prova. La 0.2.1 chiude i fermi silenziosi visti dal
vivo: ritentativi sugli errori passeggeri di GitHub, un giro di riserva ogni ora, un oracolo rosso che non chiude il
compito, la domanda riconosciuta in ogni riga, `bottega lancia` e `bottega segui`. La 0.2.2 non perde più le misure
in silenzio: il giro scrive sul lavoro quelle che la board non prende e `bottega segui` le dice; il contratto
dell'adattatore della board è scritto in `docs/adattatore.md`. La 0.2.3 chiede all'esecutore pochi passi (il tempo di un
giro va nei passi del modello, non nelle prove) e dice quale compito manca del «Fatto quando». La 0.2.4 conosce le quote
separate di un abbonamento (i secchi: un 429 ferma solo il suo), i candidati di riserva e il quaderno in comune fra
più livelli dello stesso modello. La 0.2.5 dà una tappa intera, col piano come
brief, a un esecutore che pianifica da sé, scelto solo a richiesta e con un tempo di lancio suo.

**Limiti noti:**
- Il token del runner (`BOTTEGA_TOKEN`) è l'accesso `gh` di chi installa e vale su tutti i suoi repo. Un token a grana
  fine, o una GitHub App per il solo progetto, è più stretto: si crea dal browser.
- I progetti di una stessa macchina sono un solo dominio di fiducia: il runner è uno solo. Un secondo progetto vuole
  un suo utente dell'esecutore.
- Sul loopback l'esecutore apre solo connessioni TCP verso i server suoi; le prove che parlano UDP sul loopback non
  passano come esecutore.
- La rete chiusa dell'esecutore vale per IP: socket unix, D-Bus di sistema e Bluetooth restano come li lascia la
  macchina. L'IP pubblico si aggiorna ogni dieci minuti; i server DNS si leggono all'installazione (se cambiano, si
  rilancia `installa macchina`).
- Su WSL con l'interop accesa l'esecutore può lanciare programmi di Windows, che non passano dalla sua rete chiusa:
  l'installazione lo avvisa.
- L'oracolo resta aggirabile da un modello che riscrive le prove: lo vede chi rivede il diff.
- Senza un consigliere col runner i lavori fuori arrivano senza rilettura: la revisione di chi decide resta
  necessaria.

## Licenza

MIT. Vedi `LICENSE`.
