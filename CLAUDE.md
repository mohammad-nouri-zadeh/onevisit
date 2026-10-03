# CLAUDE.md: OneVisit

> **Several people, each with their own Claude account, work on this repo at the same time. Your session doesn't share memory with theirs: the repo is the only shared state.** Before any task, read [TEAM.md](TEAM.md) (who owns what, git rules, decisions, log) and run `git pull --rebase origin main`. Stay in your own area, push small commits often, never force-push or delete others' work, and write any decision or contract change in TEAM.md in the same push.

We are a team at the Claude Impact Lab Milano (3 October 2026, with the Comune di Milano). Hub repo with the brief, rules and judging: https://github.com/Claude-Milano/impact-lab-oct-2026. The concept, in Italian, is in `docs/concept.md`.

Our user: a person going to a City registry desk, first of all a non-EU citizen who has just arrived and doesn't speak Italian well.
Our outcome: they arrive at the appointment with everything they need, checked against official sources, and the procedure closes on the first visit.

## Non-negotiables

- **Runs on Claude.** Claude does the work at runtime through the API: understands the case, asks only the questions that change the answer, builds the checklist, picks the office, answers in the user's language.
- **Facts only from `onevisit/kb.py`.** Never let the agent state a City requirement, address, hour, cost or deadline from model memory. It calls the tools in `onevisit/tools.py` and cites `source_id`s. If the tools don't have it, the agent says it doesn't know and links the official page. This is what makes OneVisit different from asking a general chatbot.
- **Never hand-edit facts without a quote.** A requirement becomes `"verified"` only with a verbatim quote from a saved source; `python data/tools/validate.py` must pass before every push.
- **No personal data.** No names, tax codes, document numbers or real emails, in code, data, screenshots or the video. Use invented cases. Email reminders are simulated in the prototype.
- **A human decides.** The agent never says documents are "valid"; the desk officer decides.
- **API keys** in `.env` only (gitignored).
- **Deadline 16:00.** Scope down before polishing.

## Layout

- `data/`: sources, saved pages, open data, services, offices. Owner: Mohammad. Read `data/README.md`.
- `onevisit/kb.py`: functions over the data. `onevisit/tools.py`: Claude tool definitions plus `run_tool()`.
- Agent, web UI, panel, channels, DB: the OneVisit kit (`apps/`, `libs/`), see the section below. `libs/onevisit_knowledge` reads the `data/` files with the same "only verified facts" rule as `onevisit/kb.py`.

## Stack

Kit: Python 3.13, uv workspace, FastAPI + Jinja2 + HTMX, PostgreSQL 17, Docker Compose (`make help`). `anthropic` SDK. Runtime models: `claude-sonnet-5-5` (conversation, analysis), `claude-haiku-4-5-20251001` (short tasks). The old data layer (`onevisit/`, `data/tools/`) still runs on Python 3.11+.

## Il kit OneVisit (aggiunto da @Saroth85 alle 13:20): architettura, regole e comandi

Da qui in poi è il `CLAUDE.md` del kit. Vale per tutto ciò che sta in `apps/`, `libs/`, `docker/`, `e2e/` e per i documenti in `docs/`. Le regole di team in alto (TEAM.md, push, aree) restano valide. Dove il kit parla di `data/procedures/` e `data/sources/`, il catalogo in uso è `data/services/*.json` con `data/sources.csv` e `data/pages/` (vedi `docs/adr/0003-catalogo-fonte-dei-requisiti.md`).

OneVisit accompagna il cittadino dal bisogno allo sportello del Comune di Milano: quale servizio, quale ente, quale ufficio, come prenotare, cosa portare. L'obiettivo è che la pratica si chiuda al primo appuntamento. Gli esiti degli appuntamenti diventano segnalazioni al Comune su dove le procedure pubblicate sono incomplete, superate o mancanti.

Il sistema ha due prodotti:

- l'**assistente**, una web chat che ricontatta il cittadino via email o SMS;
- il **pannello del Comune**, un'applicazione separata.

### Documenti di riferimento

Leggi quelli pertinenti prima di lavorare. La specifica è il backlog, non questo file.

| File | Contenuto |
|---|---|
| `docs/concept.md` | Cosa fa OneVisit e perché |
| `docs/backlog.md` | Le storie con i criteri di accettazione: è la specifica da implementare |
| `docs/implementation-plan.md` | Ordine dei milestone e criteri di uscita |
| `docs/progress.md` | Stato del lavoro. **Aggiornalo a ogni storia chiusa**: è la memoria tra una sessione e l'altra |
| `docs/conventions.md` | Stile del codice, struttura, documentazione, commit |
| `docs/testing-strategy.md` | Tipi di test, marcatori, finti client, copertura |
| `docs/deployment.md` | Avvio locale, demo, produzione, backup, rollback |
| `docs/adr/` | Decisioni di architettura; per una decisione nuova si aggiunge un ADR |

### Regole non negoziabili

1. **Tutto gira in Docker.** Non installare nulla sull'host e non eseguire Python o uv fuori dai container: usa i target del `Makefile`. Eccezione: nelle sandbox cloud dove i container non raggiungono PyPI, `uv sync --all-packages` sull'host (Python 3.13) con Postgres e Mailpit in Docker (`docker compose up -d postgres mailpit`) e `sh scripts/check.sh` con `DATABASE_URL_TEST` che punta a `localhost:5432`.
2. **Stack fisso:** Python 3.13 e le librerie del backlog. Ogni nuova dipendenza va motivata nel messaggio di commit, e `uv.lock` si aggiorna con `make lock`.
3. **L'assistente:**
   - non chiede mai nome, codice fiscale, indirizzo o foto dei documenti;
   - non prenota al posto del cittadino;
   - non dichiara mai l'idoneità: niente "idoneo", "in regola", "garantito" né le loro traduzioni.
4. **Fonti.** Ogni requisito mostrato al cittadino ha un `source_id` che esiste nel catalogo. Nessun requisito inventato: vengono dal catalogo validato da una persona.
5. **Separazione dei dati.**
   - I dati personali stanno solo nello schema `pii`.
   - Il pannello legge solo `analytics`, `core.gaps` e `core.interventions`.
   - Le viste aggregate non mostrano gruppi sotto la soglia k.
6. **Nessun dato personale** finisce in log, messaggi di errore, eccezioni o snapshot di test. Il testo libero dei cittadini non si salva mai: si salvano solo i campi strutturati (storia C9).
7. **Notifiche minime.** SMS ed email non nominano mai la pratica, né nel testo né nell'oggetto: solo giorni mancanti e link personale.
8. **Canali:** solo web chat, email e SMS. Niente Telegram, WhatsApp o altri.
9. **Configurazione.** Le librerie in `libs/` non leggono variabili d'ambiente: ricevono la configurazione come parametri. Solo le applicazioni in `apps/` leggono l'ambiente, con pydantic-settings.
10. **Testi per il cittadino** in italiano e inglese, nei template, mai come stringhe sparse nel codice.
11. **Modello dietro un'interfaccia.** Claude si chiama attraverso un'interfaccia iniettabile. I test unitari usano un client finto e non vanno mai in rete. Le chiamate vere stanno solo nei test marcati `llm` e in `make eval`.

### Mappa del codice

```
apps/assistant_web   web chat (FastAPI, Jinja2, HTMX)            ruolo DB: app_assistant
apps/dashboard       pannello del Comune (FastAPI, HTMX, Chart.js) ruolo DB: app_dashboard
apps/gateway         webhook SMS, link di risposta               ruolo DB: app_assistant
apps/gateway/worker  Procrastinate: code notifications e analysis  ruoli: app_notifier, app_analysis
libs/onevisit_*      logica condivisa: il docstring di ogni __init__.py dice cosa contiene
data/                fonti, catalogo delle procedure, scenari di valutazione
docker/              inizializzazione di Postgres, Caddyfile
```

Direzione delle dipendenze ammessa: `apps → libs` e `libs → libs`, come dichiarato nei `pyproject.toml`. Mai `libs → apps`.

### Comandi

| Comando | Cosa fa |
|---|---|
| `make env` | Crea `.env` da `.env.example` (una volta sola) |
| `make up`, `make down`, `make logs` | Stack di sviluppo con ricarica automatica |
| `make test` | Batteria completa: formattazione, lint, mypy, pytest con Postgres, copertura |
| `make fmt` | Formatta e corregge in automatico |
| `make lock` | Aggiorna `uv.lock` dopo un cambio di dipendenze |
| `make migration name="..."` | Nuova migrazione Alembic |
| `make migrate` | Applica le migrazioni |
| `make seed-demo`, `make demo` | Dati sintetici e modalità demo |
| `make eval` | Scenari di valutazione dell'agente (usa la vera API) |
| `make e2e` | Test end-to-end con Playwright |
| `make shell`, `make psql` | Shell e console SQL |

Un singolo test: `docker compose --profile test run --rm test uv run pytest percorso/del/test.py -k nome`

### Flusso per ogni storia

Usa `/implementa-storia <ID>`. In sintesi:

1. Leggi la storia e controlla le dipendenze in `docs/progress.md`. Se una dipendenza è aperta, fermati e dillo.
2. Proponi un piano breve e aspetta conferma.
3. Scrivi prima i test, almeno uno per ogni criterio di accettazione.
4. Implementa.
5. Porta `make test` al verde.
6. Aggiorna la documentazione e `docs/progress.md`.
7. Proponi un messaggio di commit nel formato `feat(B1): ...`.

Una storia per commit. Push su `main` secondo le regole di `TEAM.md` (pull --rebase prima, commit piccoli, mai force-push).

### Definition of Done

- Ogni criterio di accettazione ha almeno un test che lo verifica, oppure una nota in `progress.md` che spiega perché è verificato a mano.
- `make test` è verde e la copertura non scende sotto la soglia.
- Nessun dato personale finisce nei log. Se la storia tocca dati o notifiche, il subagent `privacy-reviewer` non ha segnalato problemi aperti.
- Docstring presenti su moduli e funzioni pubbliche. README, ADR e `progress.md` aggiornati.
- I testi rivolti al cittadino esistono in italiano e in inglese.

### Stato dello scheletro iniziale

- **Verificato fuori da Docker con Python 3.13:** `uv lock`, test (10 superati, 1 saltato senza database), ruff, formattazione, mypy strict.
- **Non ancora verificato:** build delle immagini, compose e Caddy. È il primo compito: milestone M0 in `docs/implementation-plan.md`.
- **Lasciato volutamente aperto:**
  - profilo `workers` e schema di Procrastinate (C8);
  - fixture che applica le migrazioni al database di test (C2);
  - testo integrale della licenza (D5);
  - README completo (A6).

### Cosa non fare

- Disattivare test, segnarli come `skip` o abbassare la copertura per far passare la batteria.
- Aggiungere `# type: ignore` o `# noqa` senza un commento che spieghi il motivo.
- Modificare una migrazione già applicata: se ne crea una nuova.
- Leggere o modificare `.env`.
- Eseguire il deploy di produzione (`make deploy`).
- Ampliare il perimetro di una storia. Le idee in più vanno annotate in `docs/progress.md`, sezione "Proposte".
