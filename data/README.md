# Data: what the agent is allowed to know

This folder is the difference between OneVisit and asking a general chatbot. The agent answers questions about City rules **only** from these files, and every fact carries its source and the date it was checked. If a fact isn't here and verified, the agent says it doesn't know and links the official page.

## Files

| File | What it holds |
|---|---|
| `sources.csv` | Every source: URL, publisher, saved snapshot, retrieval date, status |
| `opendata/` | City open datasets exactly as downloaded (never edited by hand) |
| `pages/` | Official web pages saved as clean text, one file per source id |
| `offices.json` | Registry offices, cleaned from dataset `ds549` by `tools/clean_offices.py` |
| `context/` | City statistics for the pitch and the panel (surveys, arrivals from abroad, foreign residents), built by `tools/summarise_opendata.py`. Read `context/README.md` |
| `enti.json` | The offices responsible (Comune, Questura, Agenzia delle Entrate) |
| `services/*.json` | One file per service: deciding questions, requirements, steps |

## The rule for every fact

A requirement can be marked `"status": "verified"` only when:

1. its `source_id` is in `sources.csv` with a saved snapshot;
2. its `quote` is copied **word for word** from that snapshot;
3. it has a `verified_at` date.

`python data/tools/validate.py` checks all three and fails if a quote isn't in the saved page. Anything not verified stays `"todo"` and the agent never states it (unless `ONEVISIT_INCLUDE_DRAFTS=1` is set for development).

## Adding a page (5 minutes per page)

```bash
# 1. Find the official page in your browser and copy its URL
python data/tools/save_page.py cie --url "https://www.comune.milano.it/..."
#    If it fails with 403 (the site blocks scripts): save the page from the browser
#    (Ctrl+S, "Web page, HTML only") and run:
python data/tools/save_page.py cie --html ~/Downloads/page.html --url "https://..."

# 2. Open data/pages/cie.md, find the sentence for each requirement,
#    paste it into "quote" in data/services/carta-identita.json,
#    write text_it / text_en in plain words, set verified_at and status "verified"

# 3. Check
python data/tools/validate.py
```

## Refreshing the open data

`python data/tools/fetch_opendata.py` downloads every dataset we use; `python data/tools/summarise_opendata.py` rebuilds `context/`.


`opendata/ds549-sedi-dei-servizi-anagrafici.csv` was downloaded from the City's CKAN API on 3 Oct 2026 (resource last modified 28 Jan 2026, licence CC BY). To refresh it, download the CSV again from the dataset page into `opendata/`, then run `python data/tools/clean_offices.py`.

## What the City data already shows

Cleaning `ds549` found real problems in the City's own dataset (they are in `offices.json` under `data_issues`):

- The Via Passerini 5 office has no Municipio, no phone and no booking notes, and its hours still say "lunedì 5 gennaio 2026: CHIUSO", nine months later.
- The Municipio 1 office is listed with a "provisional" entrance (from Via Pecorari 3), which needs checking.

This is the "page not up to date" cause from the concept, found in real City data on day one.
