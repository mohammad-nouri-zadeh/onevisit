# Runbook: avvio, verifica, demo

*Storia D3. Per chi presenta la demo e per chi la riprende dopo l'hackathon. Nessun segreto in questo file: le chiavi stanno solo in `.env` (ignorato da git). Deploy in produzione: [deployment.md](deployment.md).*

## Servizi e porte

| Servizio | URL locale | A cosa serve |
|---|---|---|
| Web chat del cittadino (`assistant_web`) | http://localhost:8000 | Conversazione, checklist `/c/{token}`, esito `/o/{token}`, consensi |
| Pannello del Comune (`dashboard`) | http://localhost:8001 | Metriche, lacune, approvazione, sintesi |
| Gateway (`gateway`) | http://localhost:8002 | Webhook SMS, link di risposta `/r/{token}`, **telefono finto `/demo/phone`**, ciclo di invio |
| Mailpit | http://localhost:8025 | Casella di prova: nessuna email esce davvero (SMTP su 1025) |
| PostgreSQL 17 | localhost:5432 | Database `onevisit` (utente proprietario `onevisit_owner`) |

## 1. Avvio (macchina del team, solo Docker e make)

```bash
make env            # crea .env da .env.example (non sovrascrive)
```

Completare `.env`:

- `ANTHROPIC_API_KEY` (senza chiave la chat non può usare Claude: serve per la demo);
- le quattro chiavi da 32 byte, generate con
  `python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"`:
  `ONEVISIT_ENCRYPTION_KEY`, `ONEVISIT_HMAC_KEY`, `ONEVISIT_LINK_SIGNING_KEY`, `ONEVISIT_SESSION_SECRET`;
- le password dei ruoli se non si usano quelle di sviluppo;
- facoltativo: credenziali SMS (vedi sotto).

Poi:

```bash
make demo           # stack in modalità demo (un giorno = 60 s) + dati sintetici (make seed-demo)
# oppure, per sviluppo:
make up             # stack con ricarica automatica, senza dati demo
make seed-demo      # carica lo scenario sintetico (~400 casi, 8 settimane, seme fisso 42)
```

`make demo` imposta `ONEVISIT_DEMO_MODE=true`: tempi compressi, ciclo di invio ogni 5 secondi, pagina `/demo/phone` attiva.

## 2. Verifica

```bash
make ps                                   # tutti i servizi "running" / "healthy"
curl -fsS http://localhost:8000/health    # web chat
curl -fsS http://localhost:8001/health    # pannello
curl -fsS http://localhost:8002/health    # gateway
```

Poi a mano:

1. http://localhost:8000: scrivere in inglese "I just moved to Milan from Brazil for work and need to register my residence" e verificare che la risposta citi le fonti `[fonte: ...]` e indichi gli enti in ordine.
2. Lasciare un numero di prova finto (`+39 333 000 0000`) o un'email `@example.org`.
3. http://localhost:8002/demo/phone: entro pochi secondi compare l'SMS con giorni mancanti e link, senza il nome della pratica.
4. http://localhost:8025: le email di conferma e promemoria compaiono in Mailpit.
5. http://localhost:8001: lacune per causa, una lacuna "procedura mancante", approvazione, confronto prima e dopo.

Test e qualità: `make test` (ruff, mypy strict, pytest con Postgres, copertura), `make eval` (scenari dell'agente, richiede la chiave).

## 3. Azzeramento dei dati

```bash
docker compose down -v      # ferma tutto e cancella il volume di Postgres
make demo                   # riparte da zero con i dati sintetici
```

`make down` ferma lo stack lasciando i dati nel volume.

## 4. Se manca la rete durante la demo

| Problema | Cosa fare |
|---|---|
| Nessuna rete o API di Claude irraggiungibile | Passare subito al **video di riserva già registrato** (link nel README). Non improvvisare |
| Rete instabile ma API raggiungibile | Usare solo la web chat in locale; le email restano su Mailpit, che non esce mai dalla macchina |
| SMS reale non arriva | Mostrare `/demo/phone` sul gateway, che riceve gli stessi messaggi dal fornitore finto |
| Pannello vuoto | `make seed-demo` (deterministico: i numeri sono sempre gli stessi) |

Il tunnel pubblico (cloudflared o ngrok) serve solo a ricevere le risposte SMS reali su `/sms/inbound`; l'invio funziona anche senza.

## 5. SMS: account di prova

- Fornitore nell'hackathon: Twilio, account di prova (`ONEVISIT_SMS_PROVIDER=twilio`). Con un account di prova si può scrivere solo a numeri **verificati** nella console del fornitore: il numero del telefono usato nella demo va verificato prima.
- Credenziali (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `ONEVISIT_SMS_FROM`) solo in `.env` della macchina che presenta. Non scriverle in documenti, chat, screenshot o video.
- Senza credenziali il gateway usa il fornitore finto e i messaggi compaiono in `/demo/phone`.
- Gli SMS dell'account di prova iniziano con un prefisso del fornitore: va detto nel video.
- Responsabile dell'account e numero verificato: annotati dal team fuori dal repository.

## 6. Alternativa nella sandbox cloud (senza build Docker)

Nella sandbox di Claude Code le immagini non scaricano da PyPI ([ADR 0009](adr/0009-sandbox-senza-build-docker.md)). Python gira sull'host, Postgres e Mailpit in Docker:

```bash
uv sync --all-packages                          # crea .venv con tutte le app e le librerie
docker compose up -d postgres mailpit           # solo database e casella di prova

# migrazioni con l'utente proprietario
ONEVISIT_DATABASE_URL=postgresql+psycopg://onevisit_owner:change-me-owner@localhost:5432/onevisit \
  .venv/bin/alembic -c libs/onevisit_db/alembic.ini upgrade head

# dati sintetici
ONEVISIT_DATABASE_URL=postgresql+psycopg://onevisit_owner:change-me-owner@localhost:5432/onevisit \
  .venv/bin/onevisit seed-demo

# applicazioni, ciascuna con il suo ruolo (in tre terminali)
export ONEVISIT_DATA_DIR=$PWD/data ONEVISIT_SMTP_HOST=localhost ONEVISIT_DEMO_MODE=true
ONEVISIT_DATABASE_URL=postgresql+psycopg://app_assistant:change-me-assistant@localhost:5432/onevisit \
  .venv/bin/uvicorn assistant_web.main:app --port 8000
ONEVISIT_DATABASE_URL=postgresql+psycopg://app_dashboard:change-me-dashboard@localhost:5432/onevisit \
  .venv/bin/uvicorn dashboard.main:app --port 8001
ONEVISIT_DATABASE_URL=postgresql+psycopg://app_assistant:change-me-assistant@localhost:5432/onevisit \
  .venv/bin/uvicorn gateway.main:app --port 8002
```

Le altre variabili (chiavi, `ANTHROPIC_API_KEY`) vengono da `.env` o vanno esportate nello stesso modo. Test dei database: `export DATABASE_URL_TEST=postgresql+psycopg://onevisit_owner:change-me-owner@localhost:5432/onevisit_test` e poi `.venv/bin/pytest`.

Sulle macchine del team il riferimento resta `make up` / `make demo`.

## 7. Prima della consegna (16:00)

- `python data/tools/validate.py` stampa `OK`; `onevisit catalog-check` senza errori.
- Nessuna chiave o dato personale nei file aggiunti (`git diff --staged`).
- Link al video nel README; prova del link da una finestra in incognito.
