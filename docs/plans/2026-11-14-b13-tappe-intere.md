# B13: le tappe intere — piano

> **Per chi esegue:** si esegue col metodo della bottega (`plugin/skills/bottega/SKILL.md`). Questa tappa la esegue
> **per intero** l'Orchestrator (Argon) di Antigravity, come collaudo di sé stessa: un solo brief, questo piano.

**Scopo:** chi decide può dare una tappa intera a un esecutore scelto, che la scelta viva non prende mai da sola, con
un tempo di lancio adatto a una tappa.

**Architettura:** nessun tipo di lavoro nuovo. Una tappa intera è un lavoro senza sotto-issue (il giro lo tratta già
come compito singolo, `attrezzi/bottega/giro.py:1036-1047`) col piano come brief e l'etichetta `esegue:`. Il candidato
impara due chiavi: `su_richiesta` (solo con `esegue:`) e `tempo` (i minuti di un lancio).

**Strumenti:** Python ≥ 3.11, sola libreria standard; `pytest` e Hypothesis nelle prove.

**Disegno:** `docs/specs/2026-11-14-b13-tappe-intere-design.md`. Parte da B12 (`v0.2.4`): secchi, `riserva`,
`quaderno` (`docs/plans/2026-11-14-b12-quote.md`).

## Vincoli di tutta la tappa

- Costituzione del repo (`docs/costituzione.md`): italiano, righe fino a 120 colonne, niente di personale, la skill
  senza nomi di modelli.
- Una configurazione senza le chiavi nuove si comporta come in B12.
- Le prove dei file toccati in primo piano: `uv run pytest -q <file>…`.

## Le decisioni (Ruling)

- **B13-R1 `su_richiesta`.** Chiave booleana facoltativa del candidato (di serie falso), campo `su_richiesta: bool =
  False` in coda a `Candidato`. Un candidato `su_richiesta` non è mai fra gli eleggibili della scelta viva (né normale
  né di riserva) e non vale come precedente; lo sceglie solo l'etichetta `esegue:` (`_scegli_per_etichetta_esegue`,
  invariata). `su_richiesta = true` insieme a `riserva = true`: errore sul percorso `candidati.<id>.su_richiesta`.
- **B13-R2 `tempo`.** Chiave intera facoltativa del candidato, in minuti, da 5 a 270 compresi (di serie 60), campo
  `tempo: int = 60` in coda a `Candidato` (un booleano non è un intero). Il giro passa `tempo=candidato.tempo * 60`
  al lancio dell'esecutore (`giro.py`, la chiamata `porta_esecutore.lancia(...)` dentro il ciclo `while True`). I lanci
  del consigliere restano col tempo di serie della porta.
- **B13-R3 Il modello del corpo** di una tappa intera sta nella skill: il percorso del piano nel repo, le sezioni da
  eseguire, `## Fatto quando` col comando della tappa.
- **B13-R4 La versione** è `0.2.5` (gli stessi sei posti di B12-R9, più la riga in `LEGGIMI.md`).

## Review Focus

1. Una funzione che ha solo candidati `su_richiesta`: la scelta dice che non c'è nessun candidato (non aspetta per
   sempre una quota).
2. Un candidato `su_richiesta` col secchio esaurito e l'etichetta `esegue:`: aspetta, come ogni `esegue:` senza quota.
3. `tempo = 271`, `tempo = 4`, `tempo = true`, `tempo = "60"`: errori di configurazione.
4. Un lavoro a più sotto-issue il cui primo compito l'ha fatto un candidato `su_richiesta`: il secondo non lo eredita
   come precedente senza `esegue:`.
5. Il modello di configurazione resta valido e mostra le chiavi nuove.

---

## B13.1 La configurazione, la scelta e il tempo

**File:** `attrezzi/bottega/configurazione.py`, `attrezzi/bottega/scelta.py`, `attrezzi/bottega/giro.py`; prove in
`attrezzi/tests/test_configurazione.py`, `attrezzi/tests/test_scelta.py`, `attrezzi/tests/test_giro.py`.

- [x] Prove rosse: `test_su_richiesta_letto`, `test_su_richiesta_e_riserva_insieme_errore`,
      `test_su_richiesta_non_booleano_errore`, `test_tempo_letto` (di serie 60), `test_tempo_fuori_intervallo_errore`
      (4 e 271), `test_tempo_non_intero_errore` (`true`, `"60"`, `60.5`) in `test_configurazione.py`;
      `test_su_richiesta_mai_scelto_dalla_scelta_viva` (semi 0-99, anche quando è l'unico con quota fra i normali
      esauriti), `test_su_richiesta_scelto_con_esegue`, `test_solo_su_richiesta_nessun_candidato` (Review Focus 1:
      `aspetta` falso), `test_precedente_su_richiesta_non_ereditato` (Review Focus 4) in `test_scelta.py`;
      `test_tempo_del_candidato_al_lancio` (la porta finta riceve `tempo == 240 * 60`) in `test_giro.py`.
- [x] Il codice, fino al verde.
- [x] `uv run pytest -q attrezzi/tests/test_configurazione.py attrezzi/tests/test_scelta.py attrezzi/tests/test_giro.py
      attrezzi/tests/test_distributore.py` verde.

## B13.2 I documenti

**File:** `plugin/skills/bottega/SKILL.md`, `plugin/skills/bottega/porte/antigravity.md`,
`plugin/skills/bottega/modelli/bottega.toml`, `attrezzi/tests/test_configurazione.py` (le due prove del modello),
`casistica/ciclo.md`.

- [x] La skill: una sezione breve «Le tappe intere» (quando conviene: un esecutore che pianifica da sé; come si fa:
      lavoro senza sotto-issue, il corpo col modello di B13-R3, `esegue:`; il candidato `su_richiesta` e `tempo`),
      senza nomi di modelli.
- [x] La pagina della porta Antigravity: l'Orchestrator (`gemini-pro-orchestrator-g1-pro`): Argon pianifica e
      ripianifica, Hydrogen esegue, un solo agente, livello fisso (niente `--effort`), consuma la quota di Argon; la
      prova del 2026-11-14 (stesso bug: 56 s e 48k token contro Hydrogen 33 s e 27k); conviene sulle tappe intere, con
      `su_richiesta = true` e un `tempo` lungo.
- [x] Il modello di configurazione mostra `su_richiesta` e `tempo` su un candidato (commentate come le altre) e resta
      valido; aggiornate `test_esempio_si_legge_per_intero` e `test_esempio_ha_ogni_chiave_ammessa`.
- [x] Casistica `CICLO-32` (l'Orchestrator: compiti difficili / tappe intere dal piano / non usarlo → tappe intere;
      `Fonte: deciso dall'utente`). `uv run python -m bottega casi` verde.

## B13.3 Versione, revisione, unione, Jarvis, collaudo dal vivo

**Chi:** chi decide.

- [x] B13-R4; tutte le prove in gabbia; controllo pubblico; revisione di chi decide (diff piccolo) più Argon.
- [x] CI `controllo` verde, unione `--no-ff` in `main`, tag `v0.2.5`, spinta.
- [x] Jarvis: candidato `orchestratore` («Orchestratore Argon», `gemini-pro-orchestrator-g1-pro`, secchio `argon`,
      `su_richiesta = true`, `tempo = 240`, funzione `eseguire`, `quaderno = "orchestrator-argon"`) e
      `bottega aggiorna --tag v0.2.5`; unione firmata.
- [x] Collaudo fuori: un lavoro vero di Jarvis, piccolo e con un oracolo meccanico, senza sotto-issue, col piano nel
      corpo ed `esegue: Orchestratore Argon`; lanciato con `bottega lancia`, seguito con `bottega segui`, rivisto e
      unito da chi decide.
- [x] Misure; casistica dal vivo.

## Misure

| Compito | Esecutore e livello | Token (Google) | Durata | Giri di correzione | Rilievi gravi (origine) |
|---|---|---|---|---|---|
| B13.1 e B13.2, tappa intera | Orchestrator (Argon), in sessione | 623 898 (quota: Argon 5 punti della settimana; Gemini circa 4 della finestra di 5 ore) | 14 min 25 s | 0 | 0 |
| revisione | chi decide (diff di prodotto di circa 60 righe) | — | — | — | 0; Argon non speso per un diff così piccolo (scostamento dal piano, per la quota) |
| collaudo fuori, un bug piccolo del progetto | Orchestrator (Argon), fuori | 427 706 al primo giro (46 passi, più 4,8 M di contesto riletto); 78 224 al secondo, che ha fatto la domanda; consigliere Argon 14 293 + 50 479 | 18 min + 3 min (giri di 21 e 8 min) | 1 domanda, nessuna correzione | 1 (brief: il «Fatto quando» chiedeva uno strumento che sul runner non gira) |

Il brief della tappa intera era il corpo di un lavoro: dieci righe. In B12 tre compiti avevano chiesto tre brief.

Il collaudo fuori: il codice era giusto al primo giro (70 righe, con la prova), e chi decide ha riprodotto e
visto corretto il bug dal vivo. L'oracolo era rosso per il brief: il «Fatto quando» usava lo strumento di tetto
della sessione locale, che sul runner non gira; la costituzione del progetto per i giri fuori dice `timeout`.
Chi decide ha corretto il corpo, ha provato l'oracolo e ha unito senza rilanciare il giro, per non spendere
un altro giro di Argon su un codice già fatto. Su un compito singolo l'Orchestrator è costato circa quattro volte
Hydrogen `medium` su lavori di misura simile: conferma la scelta di `CICLO-32`.
