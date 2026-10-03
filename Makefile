# Tutti i comandi passano da Docker: sull'host servono solo Docker e make.
# `make help` elenca i comandi.

COMPOSE := docker compose
PROD    := docker compose -f compose.yaml -f compose.prod.yaml
TEST    := $(COMPOSE) --profile test run --rm --build test

.DEFAULT_GOAL := help
.PHONY: help env up down restart logs ps build test test-db test-llm lint fmt typecheck lock \
        migrate migration seed-demo demo eval e2e shell psql \
        deploy prod-logs prod-ps backup

help: ## Mostra i comandi disponibili
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------ sviluppo
env: ## Crea .env da .env.example (non sovrascrive)
	@test -f .env && echo ".env esiste gia'" || (cp .env.example .env && echo "Creato .env: completa le chiavi")

up: ## Avvia lo stack di sviluppo con ricarica automatica
	$(COMPOSE) up --build -d
	@echo "Web chat:  http://localhost:8000"
	@echo "Pannello:  http://localhost:8001"
	@echo "Gateway:   http://localhost:8002"
	@echo "Mailpit:   http://localhost:8025"

down: ## Ferma lo stack (i dati restano nel volume)
	$(COMPOSE) down

restart: down up ## Riavvia lo stack

logs: ## Segue i log di tutti i servizi
	$(COMPOSE) logs -f --tail=100

ps: ## Stato dei servizi
	$(COMPOSE) ps

build: ## Ricostruisce le immagini
	$(COMPOSE) build

# ------------------------------------------------------------ qualita'
test: ## Batteria completa nel container: formattazione, lint, tipi, test, copertura
	$(TEST)

test-db: ## Solo i test che usano il database
	$(TEST) uv run pytest -m db

test-llm: ## Test che chiamano davvero Claude (serve ANTHROPIC_API_KEY)
	$(TEST) uv run pytest -m llm

lint: ## Solo ruff
	$(TEST) sh -c "uv run ruff format --check . && uv run ruff check ."

fmt: ## Formatta e corregge in automatico (modifica i file)
	$(TEST) sh -c "uv run ruff format . && uv run ruff check --fix ."

typecheck: ## Solo mypy
	$(TEST) uv run mypy apps libs conftest.py

lock: ## Aggiorna uv.lock dopo aver cambiato le dipendenze
	$(TEST) uv lock

e2e: ## Test end-to-end Playwright sullo stack avviato
	$(COMPOSE) --profile e2e run --rm --build e2e

# ------------------------------------------------------------ dati
migrate: ## Applica le migrazioni
	$(COMPOSE) run --rm migrate

migration: ## Crea una nuova migrazione: make migration name="crea tabella casi"
	$(COMPOSE) --profile tools run --rm tools alembic -c libs/onevisit_db/alembic.ini revision -m "$(name)"

seed-demo: ## Carica i dati sintetici dello scenario demo
	$(COMPOSE) --profile tools run --rm tools onevisit seed-demo

demo: ## Avvia lo stack in modalita' demo (tempi compressi) con i dati sintetici
	ONEVISIT_DEMO_MODE=true $(COMPOSE) up --build -d
	$(MAKE) seed-demo

eval: ## Esegue gli scenari di valutazione dell'agente
	$(COMPOSE) --profile tools run --rm tools onevisit eval

shell: ## Shell nel container degli strumenti
	$(COMPOSE) --profile tools run --rm tools sh

psql: ## Console SQL sul database di sviluppo
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" "$$POSTGRES_DB"'

# ------------------------------------------------------------ produzione
deploy: ## Sul server: build, migrazioni, avvio in produzione
	$(PROD) build
	$(PROD) run --rm migrate
	$(PROD) up -d --remove-orphans

prod-logs: ## Log di produzione
	$(PROD) logs -f --tail=200

prod-ps: ## Stato dei servizi in produzione
	$(PROD) ps

backup: ## Backup compresso del database in ./backups
	mkdir -p backups
	$(PROD) exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' | gzip > backups/onevisit-$$(date +%Y%m%d-%H%M%S).sql.gz
