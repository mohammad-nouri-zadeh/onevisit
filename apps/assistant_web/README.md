# assistant_web

Web chat del cittadino: storie B1-B5, B7, B8.

## Avvio

Fa parte dello stack Docker: `make up` dalla radice del repository. In sviluppo risponde su http://localhost:8000.

## Variabili d'ambiente

| Variabile | Uso |
|---|---|
| `ONEVISIT_SERVICE_NAME` | Nome del servizio, restituito da `/health` |
| `ONEVISIT_ENVIRONMENT` | `development` o `production` |
| `ONEVISIT_DATABASE_URL` | URL SQLAlchemy, con il ruolo dedicato al servizio (impostata da `compose.yaml`) |

Le storie che aggiungono funzionalità aggiornano questa tabella.
