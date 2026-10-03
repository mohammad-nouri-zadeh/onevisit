# 0001 · Python e componenti aperti

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** A3, C1

## Contesto

Il progetto nasce in un hackathon ma è pensato per essere donato al Comune di Milano e riusato da altre amministrazioni. Serve uno stack che il team conosce, che un fornitore della PA possa mantenere e che non leghi il Comune a servizi proprietari.

## Decisione

Python 3.13 con componenti aperti: FastAPI, Jinja2 e HTMX per le interfacce; PostgreSQL 17 con SQLAlchemy 2, Alembic e psycopg 3; Pydantic v2 per i modelli condivisi; Typer per la riga di comando; uv per il workspace (`apps/`, `libs/`); Docker Compose e `make` per l'avvio. L'unico servizio esterno indispensabile è l'API di Claude tramite l'SDK ufficiale `anthropic`.

## Conseguenze

- Gli stessi modelli Pydantic validano catalogo, strumenti dell'agente e API.
- Tutto gira su Linux in container; nessun software Windows o proprietario.
- La licenza dichiarata dal kit è EUPL-1.2, mentre `LICENSE` oggi è MIT: il team deve sceglierne una prima della consegna.
- Le dipendenze sono bloccate in `uv.lock`: aggiungerne una richiede `make lock`.

## Alternative considerate

- Node.js/TypeScript: SDK equivalente, ma meno diffuso nella PA e due linguaggi nel team.
- Piattaforme low-code o servizi cloud gestiti: più veloci all'inizio, ma vincolano il Comune a un fornitore.
