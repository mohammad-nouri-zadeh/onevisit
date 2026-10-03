# Piano di implementazione con Claude Code

Il lavoro è diviso in sette milestone, dalla M0 alla M6. Ognuna ha:

- un obiettivo;
- le storie del backlog che la compongono;
- il prompt da incollare in Claude Code;
- cosa devi controllare tu;
- il criterio di uscita.

Non si passa alla milestone successiva finché il criterio di uscita non è soddisfatto.

## Prima di iniziare

**Sull'host servono:**

- Docker con Compose v2;
- make;
- git;
- Claude Code.

Nient'altro: Python e le dipendenze stanno nei container.

**Preparazione:**

```bash
git init && git add . && git commit -m "chore: scheletro iniziale di OneVisit"
make env        # crea .env da .env.example
```

Apri `.env` e compila almeno `ANTHROPIC_API_KEY` e le quattro chiavi da 32 byte (il comando per generarle è nel file). Le password del database vanno bene così in sviluppo.

**Come lavorare con Claude Code:**

- **Una milestone per sessione.** Alla fine usa `/clear`. Lo stato passa da una sessione all'altra tramite `docs/progress.md`, che Claude Code aggiorna a ogni storia.
- **Modalità piano all'inizio di ogni milestone** (Shift+Tab). Fai proporre il piano, correggilo, poi lascia scrivere il codice.
- **Una storia alla volta**, con `/implementa-storia <ID>`. Dopo ogni storia leggi il diff, e fai il commit tu.
- **Subagent:**
  - `privacy-reviewer` dopo le storie che toccano dati, notifiche o prompt;
  - `code-reviewer` prima di chiudere una milestone;
  - `test-runner` quando la batteria fallisce e la causa non è chiara.
- **Chiusura:** `/chiudi-milestone M<n>` verifica il criterio di uscita e aggiorna `progress.md`.

---

## M0 · Verifica dello scheletro

**Obiettivo.** Dimostrare che l'infrastruttura Docker funziona prima di scrivere logica. Lo scheletro è stato verificato fuori da Docker; la build delle immagini e compose no.

**Storie.** Nessuna.

**Prompt**

```
Leggi CLAUDE.md e docs/deployment.md. Siamo alla milestone M0: verifica dello scheletro.
Esegui in ordine `make test` e `make up`, poi controlla che /health risponda su
localhost:8000, 8001 e 8002 e che Mailpit sia raggiungibile su localhost:8025.
In `make test` i test marcati db devono girare (non essere saltati).
Se qualcosa fallisce, correggi solo l'infrastruttura (Dockerfile, compose, Makefile, script),
senza aggiungere funzionalità, e spiegami ogni correzione.
Alla fine aggiorna docs/progress.md con l'esito e le correzioni fatte.
```

**Cosa controlli tu**

- `make ps` mostra `postgres`, `assistant_web`, `dashboard` e `gateway` in stato `healthy`, e `migrate` terminato con codice 0.
- Apri http://localhost:8000/health e http://localhost:8025.

**Criterio di uscita.** `make test` verde con 11 test superati e nessuno saltato; `make up` porta tutti i servizi a `healthy`.

---

## M1 · Fondamenta

**Obiettivo.** Decisioni scritte, modello dei dati e database con la separazione tra contatti, casi e metriche imposta dai ruoli.

**Storie.** C1 (completamento), A3, A4, C2.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md e in docs/backlog.md le storie C1, A3, A4, C2.
Siamo alla milestone M1 "Fondamenta". In modalità piano proponimi:
l'ordine delle storie, i file che creerai o modificherai, le migrazioni,
e per ogni criterio di accettazione il test che lo verifica.
Aspetta la mia conferma. Poi procedi una storia alla volta con /implementa-storia,
fermandoti dopo ciascuna per farmi rivedere il diff.
Per C2 il test dei permessi deve dimostrare che app_dashboard riceve un errore
se interroga lo schema pii. Dopo C2 chiedi una revisione a privacy-reviewer.
```

**Cosa controlli tu**

- Gli ADR in `docs/adr/` riflettono davvero le decisioni del concept.
- In `make psql`, `\dn` mostra i tre schemi, e `SET ROLE app_dashboard; SELECT * FROM pii.contacts;` dà un errore di permessi.

**Criterio di uscita.** Storie chiuse in `progress.md`, `make test` verde con i test dei permessi, nessun problema aperto segnalato da privacy-reviewer.

---

## M2 · Fonti e base di conoscenza

**Obiettivo.** Pagine ufficiali raccolte e catalogo delle procedure validato.

**Storie.** A1, A2, C4.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md e le storie A1, A2, C4 in docs/backlog.md.
Milestone M2. Implementa prima A1 (comando `onevisit ingest`) e mostrami l'inventario
delle fonti prima di proseguire. Per A2 genera la proposta di catalogo con Claude,
ma non marcare nulla come revisionato: la revisione la faccio io riga per riga.
Il validatore `onevisit catalog-check` deve far fallire `make test` se il catalogo
non è valido. Per i test non usare la rete: usa pagine HTML di esempio in tests/fixtures.
```

**Cosa controlli tu.** Questa è la revisione più importante del progetto:

- leggi `data/procedures/*.yaml` riga per riga, confrontandoli con le pagine ufficiali;
- compila `reviewed_by` e `reviewed_at`.

**Criterio di uscita.** Catalogo revisionato da una persona; `make test` verde con il validatore attivo.

---

## M3 · Agente e web chat

**Obiettivo.** Il cittadino descrive la situazione nella sua lingua e riceve servizio, enti, ufficio e modo di prenotare, con le fonti. I dati personali non vengono salvati.

**Storie.** C3, C9, C13, B1, B2, B3, B4.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md, docs/testing-strategy.md e le storie C3, C9, C13,
B1, B2, B3, B4. Milestone M3. Ordine: C3 (agente con client Claude iniettabile e
validatore), C9 (pipeline privacy), C13 (scenari di valutazione), poi B1-B4 nella
web chat. Nei test unitari usa il client finto descritto in testing-strategy.md.
Per ogni regola non negoziabile 3, 4 e 6 di CLAUDE.md voglio almeno un test esplicito.
Dopo C9 e dopo B4 chiedi una revisione a privacy-reviewer.
```

**Cosa controlli tu**

- Apri http://localhost:8000 e prova tre casi: "ho perso la carta d'identità e tra un mese parto", un messaggio in inglese, e un messaggio che contiene il tuo codice fiscale (poi verifica in `make psql` che non sia stato salvato).
- `make eval` produce il report degli scenari.

**Criterio di uscita.** I tre casi funzionano a mano, `make eval` supera tutti gli scenari, `make test` è verde.

---

## M4 · Contatti, promemoria e SMS

**Obiettivo.** Il cittadino lascia email o telefono e riceve promemoria e follow-up; può rispondere all'SMS e revocare i consensi.

**Storie.** C5, C6, C7, C8, B5, B6, B7, B9.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md e le storie C5, C6, C7, C8, B5, B6, B7, B9.
Milestone M4. Il fornitore SMS deve restare dietro l'adattatore: nei test usa un
fornitore finto che registra i messaggi inviati. Per C8 applica lo schema di
Procrastinate con una migrazione, concedi i permessi ai ruoli dei worker e solo
dopo rimuovi il profilo "workers" da compose.yaml. Implementa la modalità demo
con tempi compressi. Verifica con un test che dopo STOP nessun lavoro invii messaggi.
Alla fine chiedi una revisione a privacy-reviewer su tutti i testi dei messaggi.
```

**Cosa controlli tu**

- Con `make demo` registra un appuntamento lasciando la tua email: in Mailpit (http://localhost:8025) arrivano promemoria e follow-up nei tempi compressi.
- Con le credenziali di prova del fornitore SMS in `.env` e il tuo numero verificato, ricevi l'SMS.
- Il testo di SMS ed email non nomina la pratica.

**Criterio di uscita.** Ciclo completo osservato in Mailpit e su un telefono vero; worker in stato `running`; `make test` verde.

---

## M5 · Ciclo di miglioramento e pannello

**Obiettivo.** Gli esiti diventano lacune con bozze di correzione; la redazione approva; il pannello mostra metriche e confronto prima e dopo.

**Storie.** B8, C10, C11, C12, A5, B10, B11, B12, B13.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md e le storie B8, C10, C11, C12, A5, B10, B11, B12, B13.
Milestone M5. Il pannello usa solo il ruolo app_dashboard: aggiungi un test che fallisce
se il codice del pannello prova a leggere pii. Il filtro k va applicato nelle viste SQL,
non nei template. Per i grafici fornisci sempre una tabella equivalente (accessibilità).
Prima di chiudere, chiedi una revisione a code-reviewer e a privacy-reviewer.
```

**Cosa controlli tu**

- Con i dati demo, il pannello (http://localhost:8001) mostra le lacune e quelle sotto soglia, senza sede né date.
- Approva una bozza e verifica che la checklist successiva nella web chat contenga il nuovo requisito.
- Le metriche con meno di 5 casi mostrano "dati insufficienti".

**Criterio di uscita.** Ciclo esito, lacuna, bozza, approvazione e nuova checklist funzionante; `make test` verde.

---

## M6 · Demo, consegna e video

**Obiettivo.** Una demo riproducibile, la CI verde, la documentazione completa, il video.

**Storie.** D1, D2, D3, D4, A6, D5, E1. Le storie E2 ed E3, registrazione e revisione del video, le fai tu.

**Prompt**

```
Leggi CLAUDE.md, docs/progress.md e le storie D1, D2, D3, D4, A6, D5, E1.
Milestone M6. Il generatore di dati demo deve essere deterministico. Scrivi il test
Playwright del percorso demo in e2e/ e fallo girare con `make e2e`. Completa README.md
in inglese con la sezione obbligatoria "Where does Claude work when someone uses this?".
Per E1 scrivi docs/video/script.md con tempi, inquadrature e testo parlato.
Chiudi con /chiudi-milestone M6.
```

**Cosa controlli tu**

- Su una macchina pulita, o dopo `docker compose down -v`, segui solo il README: `make env`, compilazione di `.env`, `make demo`. Deve funzionare tutto.
- Fai una prova generale cronometrata del percorso demo.
- Registra il video seguendo `docs/video/script.md`.

**Criterio di uscita.** CI verde, demo riproducibile dal README, video consegnato.
