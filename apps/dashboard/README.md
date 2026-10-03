# dashboard

City panel for the Comune di Milano: stories B10-B13, C12. Uses only the `app_dashboard` database role, which reads `analytics.*`, `core.gaps`, `core.interventions` and writes `core.gaps`, `core.interventions`, `core.access_log`, `analytics.config`. It never reads `pii.*` or `core.cases`.

*In italiano:* pannello per redazione, uffici e direzione. Accesso dimostrativo per ruolo (cookie firmato); in produzione OIDC con Authlib, non implementato nell'hackathon.

## Pages

| Path | Page | Roles |
|---|---|---|
| `/login` | Demo access: choose a role (redazione, ufficio, direzione) | all |
| `/` | Panoramica: first-visit rate by service, language, category; gaps by cause; avoided visits and estimated cost (formula and slot cost shown, labelled "stima") | all |
| `/gaps` | Lacune: filters by cause, service, status; below-threshold groups in a separate section without office or dates; national sources labelled "fonte non comunale" | all |
| `/gaps/{id}` | Dettaglio lacuna: summary, generalised examples, three editable drafts; approve/archive only for `redazione` (POST returns 403 for others); access logged | all |
| `/office` | Segnalazioni ufficio (B12 box): above-threshold gaps aggregated by procedure, never dates or employees | all |
| `/interventions` | Before/after first-visit rate with n; null under k shown as "dati insufficienti" | all |
| `/summary` | Weekly summary from aggregate views (Claude with API key, rule-based text without) | all |
| `/context` | City statistics from `data/context/*.csv` (ds1959, ds1702, ds1511, ds1512, ds74) | all |
| `/settings` | k threshold, cost per slot, window weeks in `analytics.config` | direzione |

Every chart has an equivalent HTML table; metric definitions are in `templates/_macros.html` (keep consistent with `docs/metrics.md`).

## Run

Part of the Docker stack: `make up` from the repository root, then http://localhost:8001. Locally:

```bash
ONEVISIT_DATABASE_URL=postgresql+psycopg://app_dashboard:change-me-dashboard@localhost:5432/onevisit \
ONEVISIT_DATA_DIR=./data ONEVISIT_SESSION_SECRET=dev .venv/bin/uvicorn dashboard.main:app --port 8001
```

Demo data: `ONEVISIT_DATABASE_URL=<owner url> uv run onevisit seed-demo` (400 synthetic cases, idempotent).

## Environment variables

| Variable | Use |
|---|---|
| `ONEVISIT_SERVICE_NAME` | Name returned by `/health` |
| `ONEVISIT_ENVIRONMENT` | `development` or `production` |
| `ONEVISIT_DATABASE_URL` | SQLAlchemy URL with the `app_dashboard` role (opened lazily on first request) |
| `ONEVISIT_DATA_DIR` | Team data folder (default `/app/data`), for `context/*.csv` |
| `ONEVISIT_SESSION_SECRET` | Secret signing the demo role cookie (empty: random per process) |
| `ONEVISIT_K_THRESHOLD` | Fallback k if `analytics.config` lacks it (default 5) |
| `ONEVISIT_COST_PER_SLOT_EUR` | Fallback slot cost if `analytics.config` lacks it |
| `ANTHROPIC_API_KEY` | Optional: Claude writes the weekly summary |
| `ONEVISIT_MODEL_CONVERSATION` | Model for the summary (default `claude-sonnet-5-5`) |
| `ONEVISIT_ROLE_COOKIE_MAX_AGE_S` | Demo role cookie lifetime (default 8 hours) |
