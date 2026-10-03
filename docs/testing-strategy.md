# Strategia di test

`make test` esegue nel container l'intera batteria che deve essere verde a ogni commit:

1. formattazione;
2. lint;
3. mypy;
4. test unitari e di integrazione con Postgres;
5. controllo della copertura.

I test che costano denaro o tempo sono separati e marcati.

## Livelli

| Livello | Cosa verifica | Dove | Marcatore | Comando |
|---|---|---|---|---|
| Unitari | Funzioni pure, validatori, calcoli di tempi e metriche, adattatori con fornitori finti | `*/tests/` | nessuno | `make test` |
| Integrazione | Repository e migrazioni su Postgres vero, permessi dei ruoli, webhook con firma | `*/tests/` | `db` | `make test` (anche solo `make test-db`) |
| Agente con client finto | Il flusso dei turni, gli strumenti, il validatore delle risposte | `libs/onevisit_agent/tests/` | nessuno | `make test` |
| Agente con Claude vero | Scenari reali di conversazione | `data/eval/` | `llm` | `make eval`, `make test-llm` |
| End-to-end | Il percorso demo nel browser, sullo stack avviato | `e2e/` | `e2e` | `make e2e` |

## Il client Claude finto

L'agente riceve il client come parametro (`typing.Protocol`). Nei test si usa un `FakeClaudeClient` con una lista di risposte preparate: testo e chiamate agli strumenti. Così si verifica:

- che l'agente chiami lo strumento giusto con i parametri giusti;
- che il validatore blocchi una risposta senza `source_id` o con una parola vietata;
- che un errore del modello produca il messaggio di cortesia con il link alla pagina ufficiale.

Il client finto sta in `libs/onevisit_agent/src/onevisit_agent/testing.py`, così lo possono usare anche i test delle applicazioni.

## Fornitori finti

Lo stesso schema vale per gli altri servizi esterni:

- **SMS:** `FakeSmsProvider` registra i messaggi inviati e simula errori a richiesta;
- **Email:** `FakeMailer`, oppure Mailpit nei test di integrazione;
- **Orologio:** `FakeClock`, perché i tempi dei promemoria si verificano senza aspettare.

## Database nei test

- Database dedicato `onevisit_test`, creato dall'inizializzazione di Postgres.
- Una fixture di sessione applica le migrazioni con Alembic (storia C2).
- Ogni test lavora in una transazione annullata alla fine, così i test restano indipendenti.
- Per verificare i permessi, i test si connettono con i ruoli dei servizi (`SET ROLE app_dashboard`) e controllano che le query vietate falliscano.

## Test obbligatori per le regole non negoziabili

Ogni regola di `CLAUDE.md` ha almeno un test con un nome riconoscibile:

| Regola | Test minimo |
|---|---|
| Nessuna richiesta di dati di identità | Il prompt di sistema contiene il divieto; uno scenario di valutazione verifica che l'assistente non chieda il codice fiscale |
| Nessuna dichiarazione di idoneità | Il validatore blocca "idoneo", "in regola", "garantito" e le traduzioni in inglese |
| Ogni requisito ha una fonte | Il validatore blocca un requisito con `source_id` inesistente |
| Dati personali solo in `pii` | Il ruolo `app_dashboard` riceve un errore su `pii.*` |
| Nessun dato personale nei log | Il test cerca email, telefoni e codici fiscali nei log catturati durante i test di flusso |
| Testo libero mai salvato | Dopo un esito con testo libero, nel database ci sono solo i campi strutturati |
| Notifiche minime | Ogni modello di SMS ed email, in ogni lingua, non contiene nomi di servizi del catalogo |
| Revoca rispettata | Dopo STOP, l'esecuzione dei lavori pianificati non invia messaggi |
| Soglia k | Le viste aggregate non restituiscono gruppi con meno di k casi |

## Corpus per la privacy

`libs/onevisit_privacy/tests/fixtures/pii_corpus.yaml` contiene almeno 20 frasi realistiche con dati personali (email, telefoni, codici fiscali, IBAN, numeri di documento, nomi e indirizzi). Nessuno di quei dati deve uscire dalla pipeline. Il corpus è sintetico: nessun dato reale.

## Scenari di valutazione

Ogni file in `data/eval/` descrive uno scenario in YAML:

```yaml
id: cie-smarrimento-it
quick: true            # incluso in `onevisit eval --quick` (CI)
messages:
  - "ho perso la carta d'identità e tra un mese parto"
expect:
  service: carta-identita
  variant: smarrimento
  language: it
  requirements_include: [denuncia-smarrimento]
  forbidden_phrases: [idoneo, in regola]
  must_not_ask: [codice fiscale, nome]
```

`onevisit eval` produce un report in Markdown in `docs/eval-report.md` e restituisce un codice d'uscita diverso da zero se uno scenario fallisce.

## Copertura

| Momento | Soglia minima (`COVERAGE_MIN`) |
|---|---|
| Fino a M2 | 70% |
| Da M3 in poi | 80% sulle librerie |

La copertura non è l'obiettivo: un test che esegue codice senza verificare nulla non conta. La revisione di `code-reviewer` lo controlla.

## Playwright

Playwright è open source (licenza Apache 2.0) e gira su Linux nel container `e2e`. Il test del percorso demo (storia D4) usa i dati sintetici e il fornitore SMS finto, così non dipende da servizi esterni.
