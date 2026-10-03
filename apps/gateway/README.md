# gateway

Webhook SMS, link di risposta delle email e worker dello scheduler: storie C5-C8.

## Avvio

Fa parte dello stack Docker: `make up` dalla radice del repository. In sviluppo risponde su http://localhost:8002.

## Variabili d'ambiente

| Variabile | Uso |
|---|---|
| `ONEVISIT_SERVICE_NAME` | Nome del servizio, restituito da `/health` |
| `ONEVISIT_ENVIRONMENT` | `development` o `production` |
| `ONEVISIT_DATABASE_URL` | URL SQLAlchemy, con il ruolo dedicato al servizio (impostata da `compose.yaml`) |

Le storie che aggiungono funzionalità aggiornano questa tabella.
