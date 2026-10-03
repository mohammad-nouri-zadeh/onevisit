# 0007 · Il catalogo è il livello dati del team

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** A1, A2, C4

## Contesto

Il backlog del kit prevedeva un catalogo in `data/procedures/*.yaml` con pagine in `data/sources/`. Prima dell'arrivo del kit il team aveva già un livello dati funzionante, con un responsabile (@mohammad-nouri-zadeh): `data/services/*.json`, `data/sources.csv`, `data/pages/<id>.md`, un validatore (`data/tools/validate.py`) che controlla che ogni citazione compaia alla lettera nella pagina salvata, e `onevisit/kb.py` + `onevisit/tools.py`.

## Decisione

Il catalogo è il livello dati del team, letto così com'è da `onevisit_knowledge` senza copiarlo né convertirlo. Le regole:

- un requisito diventa `"status": "verified"` solo con `source_id` presente in `sources.csv` con snapshot salvato, `quote` copiata alla lettera dalla pagina e `verified_at`;
- `python data/tools/validate.py` e `onevisit catalog-check` devono passare prima di ogni push;
- la **revisione umana** è il passaggio a `verified` fatto dal responsabile dei dati, con citazione e data (al posto di `reviewed_by`/`reviewed_at` dei file YAML del kit).

## Conseguenze

- Una sola fonte di verità per agente, prototipo (`onevisit/tools.py`) e pannello.
- Cambiare un nome di campo nei JSON rompe l'agente: va annotato nel log di `TEAM.md`.
- Le storie A1 e A2 del backlog si leggono con questi percorsi al posto di `data/sources/` e `data/procedures/`.
- La sandbox cloud non raggiunge comune.milano.it: le pagine si salvano da un browser e si importano con `onevisit ingest <id> --html <file> --url <url>` o `data/tools/save_page.py`.

## Alternative considerate

- Convertire i JSON in YAML del kit: doppio lavoro e due fonti che si scostano.
