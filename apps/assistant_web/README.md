# assistant_web

Citizen web chat (FastAPI + Jinja2 + HTMX): stories B1-B5, B7 (checklist), B8 (outcome), B9 (consents), B11 (approved corrections as catalog overlays).

**In breve (IT):** chat del cittadino. Il messaggio passa da `redact` prima dell'agente; nel database vanno solo campi strutturati; contatti cifrati in `pii`; pagine personali con link firmati.

## Run

Part of the Docker stack (`make up`), on http://localhost:8000. On the host:
`ONEVISIT_DATA_DIR=data .venv/bin/uvicorn assistant_web.main:app --port 8000`.
Without `ANTHROPIC_API_KEY` the chat answers with the courtesy message and the official link.

## Routes

`/` chat, `POST /chat` (HTMX turn), `POST /contact`, `GET /confirm/{token}`, `GET /case.ics`,
`/c/{token}` checklist, `/o/{token}` outcome, `/consents/{token}`, `/health`.

## Environment

| Variable | Use |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key; empty = fallback message only |
| `ONEVISIT_DATABASE_URL` | SQLAlchemy URL with role `app_assistant`; empty = no DB features |
| `ONEVISIT_DATA_DIR` | Team data layer (default `/app/data`) |
| `ONEVISIT_INCLUDE_DRAFTS` | Dev only: show unverified requirements |
| `ONEVISIT_MODEL_CONVERSATION`, `ONEVISIT_MODEL_FAST` | Claude models |
| `ONEVISIT_ENCRYPTION_KEY`, `ONEVISIT_HMAC_KEY` | Contact encryption (32 bytes base64) |
| `ONEVISIT_LINK_SIGNING_KEY`, `ONEVISIT_SESSION_SECRET` | Signed links and session cookie (random per process if empty) |
| `ONEVISIT_DEMO_MODE`, `ONEVISIT_DEMO_SECONDS_PER_DAY` | Compressed notification times |
| `ONEVISIT_REMINDER_DAYS_BEFORE`, `ONEVISIT_SOURCE_STALE_DAYS` | Reminder lead time, source staleness |
| `ONEVISIT_PUBLIC_BASE_URL`, `ONEVISIT_GATEWAY_BASE_URL` | Public URLs for personal links |
| `ONEVISIT_SESSION_TTL_S`, `ONEVISIT_LINK_MAX_AGE_DAYS`, `ONEVISIT_CONTACT_RETENTION_DAYS`, `ONEVISIT_CATALOG_REFRESH_S` | Timeouts and retention |
