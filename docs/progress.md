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
| M1 · Fondamenta | da fare | |
| M2 · Fonti e base di conoscenza | da fare | |
| M3 · Agente e web chat | da fare | |
| M4 · Contatti, promemoria e SMS | da fare | |
| M5 · Ciclo di miglioramento e pannello | da fare | |
| M6 · Demo, consegna e video | da fare | |

## Storie

| Storia | Milestone | Stato | Data | Note |
|---|---|---|---|---|
| C1 | M1 | in corso | | Scheletro presente; completamento in M1 |
| A3 | M1 | da fare | | |
| A4 | M1 | da fare | | |
| C2 | M1 | da fare | | |
| A1 | M2 | da fare | | |
| A2 | M2 | da fare | | Richiede revisione umana del catalogo |
| C4 | M2 | da fare | | |
| C3 | M3 | da fare | | |
| C9 | M3 | da fare | | |
| C13 | M3 | da fare | | |
| B1 | M3 | da fare | | |
| B2 | M3 | da fare | | |
| B3 | M3 | da fare | | |
| B4 | M3 | da fare | | |
| C5 | M4 | da fare | | |
| C6 | M4 | da fare | | |
| C7 | M4 | da fare | | |
| C8 | M4 | da fare | | Rimuove il profilo `workers` |
| B5 | M4 | da fare | | |
| B6 | M4 | da fare | | |
| B7 | M4 | da fare | | |
| B9 | M4 | da fare | | |
| B8 | M5 | da fare | | |
| C10 | M5 | da fare | | |
| C11 | M5 | da fare | | |
| C12 | M5 | da fare | | |
| A5 | M5 | da fare | | |
| B10 | M5 | da fare | | |
| B11 | M5 | da fare | | |
| B12 | M5 | da fare | | |
| B13 | M5 | da fare | | |
| D1 | M6 | da fare | | |
| D2 | M6 | da fare | | CI già presente nello scheletro |
| D3 | M6 | da fare | | |
| D4 | M6 | da fare | | |
| A6 | M6 | da fare | | |
| D5 | M6 | da fare | | |
| E1 | M6 | da fare | | |
| E2 | M6 | da fare | | Lavoro umano |
| E3 | M6 | da fare | | Lavoro umano |

## Proposte

Idee emerse durante il lavoro, fuori dal perimetro delle storie. Si valutano prima di aggiungerle al backlog.
