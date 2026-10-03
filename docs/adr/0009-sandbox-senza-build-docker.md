# 0009 · Sandbox cloud senza build delle immagini Docker

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** C1, D3

## Contesto

Parte del lavoro avviene in una sandbox cloud di Claude Code. Lì il proxy di rete ispeziona il TLS: la build delle immagini Docker non riesce a scaricare i pacchetti da PyPI, e comune.milano.it non è raggiungibile. Docker funziona per le immagini già pronte (Postgres, Mailpit).

## Decisione

Nella sandbox Python gira sull'host da un ambiente uv (`uv sync --all-packages`, poi `.venv/bin/...`), mentre Postgres 17 e Mailpit girano in Docker (`docker compose up -d postgres mailpit`). Migrazioni e applicazioni si avviano a mano con `ONEVISIT_DATABASE_URL` puntato a `localhost:5432` (vedi [runbook](../runbook.md)). Sulle macchine del team il riferimento resta `make up` / `make demo`, tutto in container.

## Conseguenze

- La build dell'immagine va riverificata su una macchina del team prima della consegna.
- Nella sandbox non si eseguono `uv lock` né `docker build`; `uv.lock` è bloccato.
- Le pagine ufficiali si salvano da un browser e si importano con `onevisit ingest`.

## Alternative considerate

- Disattivare la verifica TLS o configurare il certificato del proxy nell'immagine: rischioso e diverso dalla produzione.
