# Costituzione del repo bottega

Il repo della bottega: la skill e le pagine per porta (il plugin, in `plugin/`), il comando `bottega` (Python, sola
libreria standard), i workflow, i quaderni e la casistica. Diventerà pubblico: chi lo riceve lo installa nella sua CLI.

## Dove si lavora e cosa non si tocca

- Si lavora nel worktree della tappa (`.worktrees/<tappa>`, ramo `<tappa>`). Il commit è di chi decide.
- **Niente di personale o di un progetto:** nessun nome di persona, account, percorso di casa, email, indirizzo IP o
  MAC veri, nome di macchina o di servizio di chi sviluppa. Negli esempi si usano segnaposto (`/home/<utente>/`,
  `192.0.2.1`, `02:00:00:00:00:01`, `example.com`).
- **Nelle prove gli esempi che il controllo pubblico trova si compongono mentre la prova gira** (`"/ho" + "me/x/y"`):
  scritti per intero, il controllo troverebbe se stesso.
- Il proprietario del repo non si scrive da nessuna parte: si installa sempre dal clone locale.
- `.github/` lo cambia solo chi decide.

## Le prove

- `uv run pytest -q` dalla radice; sulla macchina di chi sviluppa valgono le sue regole (per esempio un tetto di
  memoria).
- **Il controllo pubblico** si lancia dopo `git add` (legge solo i file in indice) e prima del commit, fermandosi se
  non passa: `PAROLE_VIETATE=… uv run python -m bottega controlla-pubblico --richiedi-elenco || exit 1`.
- La CI `controllo` (prove, controllo pubblico, gitleaks) deve essere verde prima dell'unione.
- **Un finto non esegue mai un comando che uccide.** Un prefisso o un esecutore finto che fa `exec "$@"` intercetta
  prima `kill`, `pkill` e `killall`, li registra ed esce 0. Il codice che uccide processi attraverso il prefisso passa
  dal controllo dell'uid (`giro._uccidi_processi_esecutore`). Chi sviluppa può chiudere le prove in un namespace PID
  suo, dove un `kill -1` sfuggito non esce: `unshare --user --map-user="$(id -u)" --map-group="$(id -g)" --pid --fork
  --kill-child uv run pytest -q` (B6.4).

## Lo stile

- Italiano nei testi, nei commenti, nei nomi e nei messaggi; righe fino a 120 colonne.
- Solo libreria standard nel pacchetto, Python ≥ 3.11; `pytest` solo nel gruppo di sviluppo.
- La skill non nomina modelli, fornitori o assetti; le pagine per porta nominano la loro CLI; i quaderni il loro
  modello.

## Lezioni del progetto

- Un dato da tenere fuori dai log di Actions va fra i segreti, non fra le variabili, anche se non è una credenziale:
  GitHub stampa l'`env` di ogni passo e maschera solo i segreti (B0).
- I nomi dei servizi e delle macchine di chi sviluppa non vanno nemmeno nei commenti (B0.6).
- Un `kill -KILL -1` passato da un prefisso finto con `exec "$@"` parte come chi lancia le prove e uccide tutti i suoi
  processi: la sessione, l'editor, il Lavorante. È successo due volte in B6.4, prima che il codice chiedesse `id -u`
  attraverso il prefisso (B6.4).
