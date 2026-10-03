# Avvio, demo e deploy

Tutto gira in container. Sull'host servono solo Docker (con Compose v2) e make. Su Windows si usa WSL2.

## 1. Sviluppo locale

```bash
make env      # crea .env da .env.example
# compila in .env almeno ANTHROPIC_API_KEY e le quattro chiavi da 32 byte
make up       # avvia lo stack con ricarica automatica
make test     # batteria completa
```

| Servizio | Indirizzo |
|---|---|
| Web chat | http://localhost:8000 |
| Pannello | http://localhost:8001 |
| Gateway | http://localhost:8002 |
| Mailpit (email di sviluppo) | http://localhost:8025 |
| Postgres | localhost:5432 |

Il codice è montato nei container: le modifiche si vedono senza ricostruire. Dopo un cambio di dipendenze servono `make lock` e `make up`, che ricostruisce l'immagine.

### Attenzione all'inizializzazione di Postgres

I ruoli dei servizi e il database di test vengono creati solo alla prima inizializzazione del volume (`docker/postgres/init/`). Se cambi le password in `.env` dopo il primo avvio, o se il volume esiste da prima, in sviluppo ricrea il volume:

```bash
docker compose down -v   # cancella i dati di sviluppo
make up
```

## 2. Demo

```bash
make demo
```

Avvia lo stack in modalità demo (un giorno dura `ONEVISIT_DEMO_SECONDS_PER_DAY` secondi) e carica i dati sintetici.

Per ricevere gli SMS su un telefono vero servono le credenziali di prova del fornitore in `.env`, con il numero del telefono verificato presso il fornitore. Per ricevere anche le risposte SMS, il gateway deve essere raggiungibile da internet:

```bash
cloudflared tunnel --url http://localhost:8002
```

Poi configura l'URL del webhook presso il fornitore: `https://<tunnel>/webhooks/sms`.

## 3. Produzione

### Requisiti

- Un server Linux con Docker e Compose v2. Bastano 2 vCPU, 4 GB di RAM e 40 GB di disco.
- Tre nomi DNS che puntano al server: `ASSISTANT_DOMAIN`, `DASHBOARD_DOMAIN`, `GATEWAY_DOMAIN`.
- Firewall aperto solo sulle porte 22, 80 e 443.

### Primo deploy

```bash
git clone <repository> onevisit && cd onevisit
make env
```

Compila `.env` per la produzione:

- password robuste e diverse per ogni ruolo;
- chiavi nuove, diverse da quelle di sviluppo;
- `ONEVISIT_ENVIRONMENT=production`;
- `ONEVISIT_PUBLIC_BASE_URL=https://<ASSISTANT_DOMAIN>`;
- l'SMTP istituzionale al posto di Mailpit;
- le credenziali del fornitore SMS;
- i tre domini e `ACME_EMAIL`.

Poi:

```bash
make deploy
```

`make deploy` costruisce l'immagine, applica le migrazioni e avvia i servizi con `compose.yaml` e `compose.prod.yaml`. Caddy ottiene da solo i certificati HTTPS.

Per verificare:

```bash
make prod-ps
curl https://<ASSISTANT_DOMAIN>/health
```

Infine configura il webhook SMS presso il fornitore: `https://<GATEWAY_DOMAIN>/webhooks/sms`.

### Aggiornamento

```bash
docker tag onevisit:latest onevisit:previous   # conserva la versione corrente
git pull
make backup
make deploy
```

### Rollback

```bash
ONEVISIT_IMAGE=onevisit:previous docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Le migrazioni devono essere compatibili all'indietro per almeno una versione: prima si aggiunge, poi si rimuove in un rilascio successivo. Così il rollback dell'immagine non richiede un rollback del database.

### Backup e ripristino

```bash
make backup   # crea backups/onevisit-AAAAMMGG-HHMMSS.sql.gz
```

Pianifica il backup con cron sul server, per esempio ogni notte, e copia i file fuori dal server.

Ripristino:

```bash
gunzip -c backups/<file>.sql.gz | docker compose -f compose.yaml -f compose.prod.yaml \
  exec -T postgres sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

Il backup contiene lo schema `pii`. Va conservato cifrato e con la stessa scadenza dei dati: un backup più vecchio della scadenza dei contatti va cancellato.

## 4. Sicurezza: controlli prima di andare online

- [ ] `.env` di produzione con password e chiavi nuove, leggibile solo dall'utente che gestisce il servizio (`chmod 600 .env`)
- [ ] Postgres non esposto: in produzione nessuna porta pubblicata, salvo 80 e 443 di Caddy
- [ ] Container eseguiti con utente non privilegiato (già previsto nel `Dockerfile`)
- [ ] Firma dei webhook SMS verificata (storia C6)
- [ ] Accesso al pannello con il sistema di autenticazione del Comune, non con gli utenti dimostrativi (storia C12)
- [ ] Lavoro `retention_purge` attivo e verificato (storia C9)
- [ ] Informativa pubblicata e fornitori indicati (storia A4)
- [ ] Backup pianificati e prova di ripristino eseguita

## 5. Problemi frequenti

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| `migrate` fallisce con "role app_assistant does not exist" | Il volume di Postgres esisteva già prima dello script di inizializzazione | In sviluppo `docker compose down -v`; in produzione eseguire a mano lo script di `docker/postgres/init/` |
| I test `db` vengono saltati | `DATABASE_URL_TEST` non impostata | Eseguire i test con `make test`, non direttamente |
| Un servizio resta `unhealthy` | Errore all'avvio | `docker compose logs <servizio>` |
| Caddy non ottiene i certificati | DNS non ancora propagato o porte 80/443 chiuse | Verificare DNS e firewall, poi `docker compose ... restart caddy` |
| I worker non partono | Profilo `workers` ancora attivo | Atteso fino alla storia C8 |
