# 0008 · Scheduler semplice per l'hackathon

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** C8

## Contesto

Il kit prevedeva Procrastinate (code e lavori programmati su Postgres) con due worker separati (profilo `workers` in Compose). In una giornata, con la demo in modalità compressa (un giorno = 60 secondi), un sistema di code aggiunge processi da avviare, monitorare e spiegare.

## Decisione

Per l'hackathon l'invio delle notifiche è un ciclo asyncio dentro il gateway (`apps/gateway/src/gateway/scheduler.py`): ogni 30 secondi, 5 in modalità demo (impostazioni `dispatch_interval_s` e `dispatch_interval_demo_s`), legge `core.notifications` con `due_notifications(now)`, invia tramite gli adattatori e aggiorna lo stato con `mark_notification`. Le notifiche sono righe programmate al momento del contatto (`schedule_notification`). Procrastinate resta nel lockfile e nel profilo `workers` per dopo.

## Conseguenze

- Un processo in meno; lo stato delle notifiche è tutto in una tabella, facile da ispezionare.
- Con più istanze del gateway servirebbe un blocco (`SELECT ... FOR UPDATE SKIP LOCKED`) o il passaggio a Procrastinate.
- I tentativi falliti si contano in `attempts`; il ripiego sull'altro canale è logica del ciclo.

## Alternative considerate

- Procrastinate da subito: più robusto, ma più lavoro di quanto la giornata permette.
- Cron di sistema: fuori dai container e difficile da comprimere nel tempo per la demo.
