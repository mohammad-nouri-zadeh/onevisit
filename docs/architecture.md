# Architettura di OneVisit

*Storia A3. Documento di riferimento per il team e per la giuria. Le interfacce tra i pacchetti sono fissate in [contracts.md](contracts.md); le decisioni sono negli [ADR](adr/). Concept completo: [concept-v2.md](concept-v2.md).*

## In breve

OneVisit è fatto di due prodotti che condividono un database PostgreSQL:

- l'**assistente** (web chat del cittadino, più promemoria via email e SMS), in cui Claude capisce il caso, indica enti e ufficio, costruisce la checklist con le fonti e raccoglie l'esito;
- il **pannello** del Comune, separato dal bot, in cui Claude classifica gli esiti, raggruppa le lacune, scrive le bozze di correzione e la sintesi settimanale. Una persona approva.

Claude non inventa i requisiti: li prende dal **catalogo** (livello dati del team: `data/services/*.json`, `data/sources.csv`, `data/pages/`), dove ogni requisito mostrato al cittadino ha una citazione letterale da una fonte ufficiale salvata ([ADR 0003](adr/0003-catalogo-fonte-dei-requisiti.md), [ADR 0007](adr/0007-catalogo-dal-livello-dati-del-team.md)).

## I quattro schemi del concept

### Schema 1 · Panoramica del sistema

```mermaid
flowchart TD
    C["Cittadino"] <--> G["Gateway dei canali<br/>web, email, SMS"]
    G <--> A["Assistente OneVisit<br/>Claude"]
    F["Fonti ufficiali<br/>Comune ed enti"] --> A
    A --> D[("PostgreSQL")]
    D --> P["Pannello del Comune"]
    P --> R["Redazione e uffici"]
    R -->|pagine corrette| F
```

### Schema 2 · Il percorso del cittadino

```mermaid
flowchart TD
    S1["1 · Capire<br/>servizio, variante, scadenza"] --> S2["2 · Dove andare<br/>ente, ufficio, ordine"]
    S2 --> S3["3 · Prenotare<br/>rimando al canale ufficiale"]
    S3 -.->|rimando, nessun dato scambiato| PR["Prenotazione del Comune"]
    S3 --> S4["4 · Restare in contatto<br/>email e/o telefono, facoltativi"]
    S4 --> S5["5 · Prepararsi<br/>promemoria e checklist"]
    S5 --> S6["6 · Dopo l'appuntamento<br/>com'è andata?"]
    S4 --> N["Servizio notifiche"]
    N --> S5
    N --> S6
    S6 --> DB[("Database<br/>esito classificato")]
```

### Schema 3 · Dati e pannello del Comune

```mermaid
flowchart TD
    subgraph PG["PostgreSQL"]
        CT["Contatti<br/>schema pii, cifrato"]
        CA["Casi<br/>pseudonimizzati"]
        LA["Lacune e interventi"]
        ME["Metriche<br/>solo aggregati"]
    end
    CT --> N["Servizio notifiche"]
    CA --> AN["Analisi · Claude<br/>diagnosi e bozze"]
    AN --> LA
    CA --> ME
    LA --> ME
    ME --> P["Pannello del Comune"]
    AN --> P
    P --> R["Redazione e uffici<br/>approvano o correggono"]
    R --> KB["Base di conoscenza"]
    KB --> AS["Assistente"]
```

### Schema 4 · Canali e connettori

```mermaid
flowchart LR
    W["Web chat<br/>conversazione completa"] <--> G["Gateway dei canali<br/>messaggio normalizzato"]
    SMS["SMS<br/>notifiche e risposte brevi"] <--> G
    G --> EM["Email<br/>solo in uscita"]
    G <--> A["Agente · Claude"]
    A --> Q["Scheduler<br/>promemoria e follow-up"]
    Q --> G
```

## Struttura del repository

```
onevisit/
  apps/
    assistant_web/        web chat del cittadino (FastAPI + Jinja2 + HTMX), porta 8000
    dashboard/            pannello del Comune (FastAPI + Jinja2 + HTMX), porta 8001
    gateway/              webhook SMS, link di risposta /r/{token}, telefono finto /demo/phone,
                          ciclo di invio delle notifiche (ADR 0008), porta 8002
  libs/
    onevisit_knowledge/   legge il catalogo del team (data/), checklist con sole voci verificate
    onevisit_agent/       agente Claude: prompt di sistema, strumenti, validatore delle risposte
    onevisit_privacy/     rimozione dei dati personali, cifratura dei contatti, esiti strutturati
    onevisit_db/          modelli SQLAlchemy, migrazioni Alembic, ruoli, funzioni repo
    onevisit_channels/    SMS (Twilio o finto), email (SMTP o finta), modelli dei messaggi, link firmati
    onevisit_analytics/   classificazione degli esiti, lacune, bozze, metriche, dati sintetici
    onevisit_cli/         comandi Typer: ingest, catalog-check, seed-demo, eval
  onevisit/               kb.py e tools.py del livello dati (contratto originale, invariato)
  data/                   livello dati del team (owner: @mohammad-nouri-zadeh)
    services/*.json       il catalogo: un servizio per file, domande decisive, passaggi, requisiti
    sources.csv           elenco delle fonti con URL, editore, data di recupero, stato
    pages/<id>.md         testo salvato delle pagine ufficiali (le citazioni devono comparire qui)
    offices.json          13 sedi anagrafiche pulite dal dataset ds549
    enti.json             enti coinvolti (Comune, Questura, Agenzia delle Entrate)
    context/              statistiche del Comune per il pannello e il pitch
    opendata/             dataset scaricati così come sono
    eval/                 scenari di valutazione dell'agente (C13)
    tools/                validate.py, save_page.py, clean_offices.py, fetch/summarise opendata
  docs/                   architettura, ADR, modello dei dati, privacy, metriche, runbook, video
  docker/                 inizializzazione di Postgres (ruoli), configurazione di Caddy
  e2e/                    test end-to-end con Playwright
  Dockerfile, compose*.yaml, Makefile
```

Regole di dipendenza: le `apps/` importano le `libs/`; le `libs/` non leggono variabili d'ambiente e non importano FastAPI; solo le `apps/` leggono la configurazione (prefisso `ONEVISIT_`). Il catalogo si legge solo tramite `onevisit_knowledge` (o `onevisit/tools.py` per chi usa ancora il prototipo).

## Flussi principali

### Conversazione (web chat)

```mermaid
sequenceDiagram
    autonumber
    actor Cit as Cittadino
    participant W as assistant_web
    participant P as onevisit_privacy
    participant A as onevisit_agent
    participant C as Claude (Sonnet)
    participant K as onevisit_knowledge
    participant DB as PostgreSQL (core, pii)
    Cit->>W: messaggio libero (qualsiasi lingua)
    W->>P: redact(testo)
    P-->>W: testo con segnaposto [EMAIL] [TELEFONO] ...
    W->>A: run_turn(stato, testo redatto, capacità del canale)
    A->>C: prompt di sistema + catalogo (cache) + storia
    C->>A: tool_use identify_case / get_procedure / build_checklist / get_office
    A->>K: catalog.checklist(servizio, risposte)
    K-->>A: solo voci verificate + source_id + citazione
    A->>C: risultati degli strumenti
    C-->>A: risposta con citazioni [fonte: id]
    A->>A: validate_reply: fonti esistenti, nessuna parola di idoneità
    alt risposta bloccata
        A->>C: una rigenerazione
        A-->>W: se ancora bloccata, messaggio di cortesia + link ufficiale
    end
    A-->>W: TurnResult (messaggi, pulsanti, eventi strutturati)
    W->>DB: core.cases / core.case_answers (solo campi strutturati)
    W-->>Cit: risposta nella sua lingua, termini ufficiali in italiano
```

Il testo libero del cittadino resta solo in memoria per la durata della sessione e non viene mai salvato.

### Notifica (promemoria e follow-up)

```mermaid
sequenceDiagram
    autonumber
    actor Cit as Cittadino
    participant W as assistant_web
    participant DB as PostgreSQL
    participant G as gateway (ciclo di invio)
    participant CH as onevisit_channels
    participant SMS as Fornitore SMS / SMTP
    Cit->>W: dopo la prenotazione: lascia email e/o telefono, sceglie le finalità
    W->>DB: pii.contacts (cifrato) + pii.appointments + core.notifications programmate
    loop ogni pochi secondi (ADR 0008)
        G->>DB: due_notifications(now)
        G->>DB: legge il contatto (decifra solo qui)
        G->>CH: render_notification(kind, lingua, giorni mancanti, link firmato)
        CH-->>G: testo minimo, senza nome della pratica
        G->>SMS: invio
        G->>DB: mark_notification(sent / failed), ripiego sull'altro canale
    end
    SMS-->>Cit: Hai un appuntamento tra 3 giorni, link personale
    Cit->>W: apre /c/{token}: controllo della checklist voce per voce
    Cit->>G: dopo l'appuntamento risponde 1 / 2 / 3 o STOP (SMS o /r/{token})
    G->>DB: esito strutturato in core.cases, revoca consensi se STOP
```

### Analisi (lacune, bozze, approvazione)

```mermaid
sequenceDiagram
    autonumber
    participant DB as PostgreSQL (core)
    participant AN as onevisit_analytics
    participant H as Claude (Haiku)
    participant S as Claude (Sonnet)
    participant D as dashboard
    actor M as Marco (redazione)
    participant A as Assistente
    AN->>DB: esiti "mancava qualcosa" / "altro" (campi strutturati)
    AN->>H: classifica la causa (una delle sei)
    AN->>AN: raggruppa per servizio, causa, requisito
    AN->>S: bozza di correzione (it, italiano facile, en) con destinatario
    AN->>DB: core.gaps + core.gap_cases
    D->>DB: legge core.gaps e analytics.* (soglia k=5 nelle viste)
    M->>D: apre la lacuna, modifica la bozza, approva
    D->>DB: core.interventions + core.access_log
    A->>DB: approved_corrections()
    A-->>A: la voce compare nella checklist con origin="approved_correction"
    D->>DB: analytics.intervention_effect: 4 settimane prima vs 4 dopo
```

## Confini di fiducia

| Chi | Cosa vede | Cosa non vede mai |
|---|---|---|
| **Modello (Claude, Anthropic)** | Testo del cittadino già passato da `redact()` (email, telefoni, codici fiscali, IBAN, numeri di documento sostituiti da segnaposto); il catalogo (servizi, domande, requisiti verificati, fonti); i risultati degli strumenti (checklist, sedi, enti). Nel pannello: campi strutturati degli esiti e suggerimenti già generalizzati | Contatti (email, telefono), data e ora esatte dell'appuntamento legate a una persona, identificativi di `pii`, documenti (non vengono mai caricati) |
| **Pannello (`app_dashboard`)** | Viste `analytics.*` con celle sotto `k_threshold` = 5 soppresse dentro la vista; `core.gaps` (lacune, esempi generalizzati); `core.interventions`. Ogni accesso finisce in `core.access_log` | `pii.*` e `core.cases` (il ruolo riceve un errore di permesso), nomi di dipendenti, sedi e date dei casi sotto soglia |
| **Fornitore SMS / email** | Numero di telefono o email del destinatario, al momento dell'invio; testo minimo: giorni mancanti e link personale firmato | Nome della procedura, servizio, sede, esito, qualsiasi contenuto della conversazione |
| **Prenotazione del Comune** | Tutto ciò che il cittadino inserisce lì, come oggi | Nulla arriva da OneVisit: il bot rimanda al link ufficiale e non prenota ([ADR 0002](adr/0002-nessuna-prenotazione-dal-bot.md)) |
| **Log applicativi** | Identificativi opachi; ogni messaggio passa da `PiiLogFilter` | Testo libero, contatti, dati personali |

I ruoli del database applicano questi confini nello schema, non nel codice: vedi [data-model.md](data-model.md) e [privacy.md](privacy.md).

## Modelli

| Uso | Modello | Perché |
|---|---|---|
| Conversazione, bozze di correzione, sintesi settimanale | `claude-sonnet-5-5` | Qualità della comprensione e della scrittura |
| Rimozione dei dati personali (secondo passo dopo le regex), classificazione breve degli esiti | `claude-haiku-4-5-20251001` | Costo e latenza bassi |

Catalogo e definizioni degli strumenti sono passati con prompt caching.

## Riferimenti

- Interfacce: [contracts.md](contracts.md)
- Decisioni: [adr/](adr/)
- Dati e ruoli: [data-model.md](data-model.md); privacy: [privacy.md](privacy.md); metriche: [metrics.md](metrics.md)
- Fonti: [sources-inventory.md](sources-inventory.md); avvio e demo: [runbook.md](runbook.md)
