# Stato di avanzamento

Claude Code aggiorna questo file alla fine di ogni storia. È la memoria del progetto tra una sessione e l'altra.

Stati possibili:

- **da fare**;
- **in corso**;
- **fatta**: criteri verificati e `make test` verde;
- **bloccata**: il motivo va scritto nelle note.

## Milestone

| Milestone | Stato | Note |
|---|---|---|
| M0 · Verifica dello scheletro | fatta | 3 ott 13:20: `scripts/check.sh` verde con Postgres 17 in Docker: 11 test superati, nessuno saltato; ruff, mypy strict, copertura 96%. Nella sandbox cloud la build delle immagini non scarica da PyPI (ispezione TLS del proxy): Python gira con `uv sync` sull'host, Postgres e Mailpit in Docker. Build delle immagini da riverificare su una macchina del team |
| M1 · Fondamenta | fatta | 3 ott, integrazione: migrazioni 0001-0002 applicate al db di sviluppo, ruoli e permessi verificati dai test; documenti di architettura, dati e privacy scritti |
| M2 · Fonti e base di conoscenza | in corso | Libreria e `onevisit catalog-check` (OK) fatte; il catalogo ha 2 requisiti verificati e 17 da fare, `data/pages/` vuota perché comune.milano.it è bloccato dalla sandbox: serve salvataggio dal browser e revisione umana |
| M3 · Agente e web chat | in corso | Agente, validatore e chat funzionano con il client finto e, senza chiave, mostrano il messaggio di cortesia con il link ufficiale (verificato con uvicorn). Manca la prova con la vera API e `onevisit eval` |
| M4 · Contatti, promemoria e SMS | in corso | Verificato dal vivo: email di conferma inviata a Mailpit dal gateway, clic sul link `/confirm/` di assistant_web, promemoria programmato e inviato. SMS con provider finto e Twilio testato con trasporto simulato; scheduler ridotto a un ciclo asyncio |
| M5 · Ciclo di miglioramento e pannello | fatta | Pannello verificato dal vivo con i dati demo: pagine, "dati insufficienti" sotto k, approvazione da redazione (303) e divieto per direzione (403); la correzione approvata compare nella checklist del cittadino |
| M6 · Demo, consegna e video | in corso | Dati demo (seme 42) caricati sul db di sviluppo; runbook e sceneggiatura scritti; mancano prova generale, consegna e video |

## Storie

| Storia | Milestone | Stato | Data | Note |
|---|---|---|---|---|
| C1 | M1 | fatta | 2026-10-03 | Monorepo, ambiente e `scripts/check.sh` verdi (453 test, copertura 91,9%); build Docker da riverificare fuori dalla sandbox |
| A3 | M1 | fatta | 2026-10-03 | `docs/architecture.md` e ADR 0001-0009 |
| A4 | M1 | fatta | 2026-10-03 | `docs/data-model.md`, `docs/privacy.md`, informativa it/en; durata di conservazione dei contatti da confermare con il DPO |
| C2 | M1 | fatta | 2026-10-03 | Migrazione 0002 (core, pii, analytics, viste con soglia k); test dei permessi per ruolo su Postgres vero |
| A1 | M2 | in corso | 2026-10-03 | Inventario in `docs/sources-inventory.md` e `onevisit ingest` pronti; `data/pages/` vuota: le pagine vanno salvate dal browser |
| A2 | M2 | in corso | 2026-10-03 | `onevisit catalog-check` stampa OK; 2 verificati, 17 da fare: serve la revisione umana con citazione |
| C4 | M2 | fatta | 2026-10-03 | `onevisit_knowledge` con correzioni approvate come overlay; ingest elenca i requisiti da ricontrollare |
| C3 | M3 | fatta | 2026-10-03 | Agente con 8 strumenti, validatore (fonti, parole vietate), rigenerazione e fallback; testato con client finto |
| C9 | M3 | fatta | 2026-10-03 | Redazione dei dati personali, cifratura AES-GCM, filtro dei log, feedback strutturato |
| C13 | M3 | in corso | 2026-10-03 | 16 scenari in `data/eval/` e comando `onevisit eval` pronti; esecuzione con la vera API non ancora fatta |
| B1 | M3 | fatta | 2026-10-03 | Identificazione del caso con il client finto; da provare con la chiave reale |
| B2 | M3 | fatta | 2026-10-03 | Lingua dal browser e marcatore `<lang>`; senza chiave il messaggio di cortesia segue la lingua del browser |
| B3 | M3 | fatta | 2026-10-03 | Sedi da `offices.json` con distanza e problemi dei dati |
| B4 | M3 | fatta | 2026-10-03 | Registrazione dell'appuntamento e avviso sui tempi; il sistema non prenota mai |
| C5 | M4 | fatta | 2026-10-03 | `onevisit_channels` e gateway con dispatcher, ritentativi e ripiego su email |
| C6 | M4 | fatta | 2026-10-03 | SMS con provider finto e Twilio via httpx testato con trasporto simulato; non provato con un account reale |
| C7 | M4 | in corso | 2026-10-03 | Invio email verificato su Mailpit; email in ingresso rinviata |
| C8 | M4 | in corso | 2026-10-03 | Ciclo asyncio nel gateway (30 s, 5 s in demo) al posto di Procrastinate; mancano promemoria della vigilia e job di pulizia per conservazione |
| B5 | M4 | fatta | 2026-10-03 | Modulo contatti con tre consensi separati e cifratura; manca la verifica del numero via codice SMS (opzionale) |
| B6 | M4 | fatta | 2026-10-03 | Risposte SMS (STOP, AIUTO, 1/2/3) con firma Twilio e MessageSid una sola volta (in memoria) |
| B7 | M4 | fatta | 2026-10-03 | Checklist `/c/{token}` con fonti e date; link dal promemoria email verificato dal vivo |
| B9 | M4 | fatta | 2026-10-03 | Pagina consensi con revoca e cancellazione; STOP via SMS |
| B8 | M5 | fatta | 2026-10-03 | Pagina esito `/o/{token}`; il testo del suggerimento non ha un campo e serve solo a stimare la causa |
| C10 | M5 | fatta | 2026-10-03 | Classificazione e raggruppamento delle lacune, con regole fisse senza chiave |
| C11 | M5 | fatta | 2026-10-03 | Viste analytics con soglia k e confronto prima/dopo; viste normali, non materializzate |
| C12 | M5 | fatta | 2026-10-03 | Pannello con login demo per ruolo, registro accessi, nessuna lettura di `pii` |
| A5 | M5 | fatta | 2026-10-03 | `docs/metrics.md`: 10 metriche; "tempo utile" senza vista SQL |
| B10 | M5 | fatta | 2026-10-03 | Lacune in ordine di priorità, sotto soglia senza link |
| B11 | M5 | fatta | 2026-10-03 | Approvazione solo da redazione verificata dal vivo; la correzione arriva alla checklist del cittadino |
| B12 | M5 | fatta | 2026-10-03 | Riquadro delle segnalazioni aggregate nel pannello |
| B13 | M5 | fatta | 2026-10-03 | Metriche e sintesi settimanale; costo per slot a 0 finché la direzione non lo imposta |
| D1 | M6 | fatta | 2026-10-03 | `onevisit seed-demo`: 400 casi sintetici, 5 lacune, 1 intervento; caricati sul db di sviluppo |
| D2 | M6 | in corso | 2026-10-03 | `scripts/check.sh` verde in locale; esecuzione su GitHub Actions da verificare |
| D3 | M6 | fatta | 2026-10-03 | `docs/runbook.md` |
| D4 | M6 | da fare | 2026-10-03 | Prova generale con la vera API |
| A6 | M6 | in corso | 2026-10-03 | README con la sezione obbligatoria; nomi del team, Track e Day-one ancora TODO; licenza da scegliere (EUPL-1.2 o MIT) |
| D5 | M6 | da fare | 2026-10-03 |  |
| E1 | M6 | fatta | 2026-10-03 | `docs/video/script.md` e `storyboard.md`; controllare il numero di casi della scena 4 sul pannello |
| E2 | M6 | da fare | 2026-10-03 | Lavoro umano |
| E3 | M6 | da fare | 2026-10-03 | Lavoro umano |

## Proposte

Idee emerse durante il lavoro, fuori dal perimetro delle storie. Si valutano prima di aggiungerle al backlog.

Rimasti dall'integrazione del 3 ottobre 2026:

1. Risolto: la chat registra la procedura mancante come caso `non-in-catalogo` con causa `procedura-mancante` (via `record_outcome`).
2. Il suggerimento della pagina esito non ha un campo in `record_outcome`: oggi serve solo a stimare la causa.
3. Dipendenze da dichiarare quando si potrà aggiornare `uv.lock`: `itsdangerous` e `httpx` in `libs/onevisit_channels/pyproject.toml`, `onevisit-analytics` in `libs/onevisit_cli/pyproject.toml` (funzionano già nel venv).
4. Job ancora da scrivere: promemoria della vigilia (`purge_expired` ora gira nel ciclo del gateway una volta al giorno); valutare Procrastinate dopo l'hackathon.
5. Idempotenza dei MessageSid solo in memoria: si perde al riavvio del gateway.
6. `cost_per_slot_eur` a 0: la direzione deve impostarlo in Impostazioni con una fonte.
7. La pagina Ufficio raggruppa le lacune per procedura: `core.gaps` non ha la sede.
8. Eseguire `onevisit eval` con la chiave reale (esportata da `.env`) prima della prova generale.
9. Verificare la build delle immagini Docker su una macchina del team.

Revisione privacy e correttezza (pomeriggio del 3 ottobre), ancora aperti:

10. Avviso di correzione (B8, `correction_notice`): nessun processo lo programma; servono permessi su `core.gap_cases` per il gateway o l'analisi.
11. `core.gaps` e' ancora letta direttamente da `app_dashboard`: la soglia k sulle lacune e' applicata dal server del pannello, non da una vista.
12. `make demo`: `ONEVISIT_DEMO_MODE` va passata ai container in `compose.yaml` (file del coordinatore).
13. Il servizio `iscrizione-anagrafica-extra-ue` non ha requisiti ne' passi verificati: la scena principale del video dipende dal livello dati.
