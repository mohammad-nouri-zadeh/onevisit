#!/bin/bash
# Eseguito da Postgres una sola volta, alla prima inizializzazione del volume.
# Crea i ruoli di login dei servizi e il database dei test.
# I permessi su schemi e tabelle sono concessi dalle migrazioni Alembic.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner="$POSTGRES_USER" \
  -v db="$POSTGRES_DB" \
  -v assistant_pw="$APP_ASSISTANT_PASSWORD" \
  -v notifier_pw="$APP_NOTIFIER_PASSWORD" \
  -v analysis_pw="$APP_ANALYSIS_PASSWORD" \
  -v dashboard_pw="$APP_DASHBOARD_PASSWORD" <<'EOSQL'
CREATE ROLE app_assistant LOGIN PASSWORD :'assistant_pw';
CREATE ROLE app_notifier  LOGIN PASSWORD :'notifier_pw';
CREATE ROLE app_analysis  LOGIN PASSWORD :'analysis_pw';
CREATE ROLE app_dashboard LOGIN PASSWORD :'dashboard_pw';

REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO app_assistant, app_notifier, app_analysis, app_dashboard;

CREATE DATABASE onevisit_test OWNER :"owner";
EOSQL
