# dashboard

Pannello del Comune: storie B10-B13, C12. Usa solo il ruolo database app_dashboard.

## Avvio

Fa parte dello stack Docker: `make up` dalla radice del repository. In sviluppo risponde su http://localhost:8001.

## Variabili d'ambiente

| Variabile | Uso |
|---|---|
| `ONEVISIT_SERVICE_NAME` | Nome del servizio, restituito da `/health` |
| `ONEVISIT_ENVIRONMENT` | `development` o `production` |
| `ONEVISIT_DATABASE_URL` | URL SQLAlchemy, con il ruolo dedicato al servizio (impostata da `compose.yaml`) |

Le storie che aggiungono funzionalità aggiornano questa tabella.
