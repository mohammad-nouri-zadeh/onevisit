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
| `enti.json` | The bodies involved (Comune, Questura, Agenzia delle Entrate, Sportello Unico per l'Immigrazione, Poste, YesMilano student desk, Anagrafe Nazionale ANPR), each role backed by a quote that `validate.py` checks |
| `services/*.json` | One file per service: deciding questions, requirements, steps (a step may have alternative `routes`, each with its own quote), the guide to the online form (`form_guide`: section titles and housing options quoted from the City's pages; each requirement's `form_section`), short names of the files to upload (`short_it`, `short_en`), the urgent options to lead with (`urgent_lead`), what the sources don't say (`unknowns_it`) |
| `i18n/requirements.<lang>.json` | Claude's translation of every requirement, step and form-guide text into Arabic, Spanish and Chinese, each with the Italian it was made from (a changed Italian text makes the entry stale). Not facts: the Italian text and the quote stay authoritative. Refresh with `python -m onevisit.translate --lang <lang> --write` |
| `eval/*.yaml` | Conversation scenarios: expected service, variant, language, requirements, forbidden phrases. `python -m onevisit.evaluate` runs them through the Streamlit app's agent, `make eval` through the kit's (both need a key) |
| `demo/` | Demo mode without an API key: recorded replies, invented personas and the recorded classification of two invented example reports (no fact is written there) |
| `tools/clean_html.py` | Keeps only the article of an official page (or the text of a PDF) before `onevisit ingest` |

## The rule for every fact

A requirement can be marked `"status": "verified"` only when:

1. its `source_id` is in `sources.csv` with a saved snapshot;
2. its `quote` is copied **word for word** from that snapshot;
3. it has a `verified_at` date.

`python data/tools/validate.py` checks all three and fails if a quote isn't in the saved page. Anything not verified stays `"todo"` and the agent never states it (unless `ONEVISIT_INCLUDE_DRAFTS=1` is set for development).

`validate.py` also checks the `quote` of each body in `enti.json` against its `quote_source_id`, the quote of every step route, form-guide section and housing option, and the quote that confirms an office entrance in `offices.json` (`entrance_confirmed_by`: the via Larga entrance, which `ds549` still calls provisional, is confirmed by the City's ID card page; `tools/clean_offices.py` writes it and keeps the dataset's wording in `dataset_notes` for City staff). The kit's `onevisit catalog-check` applies the same quote rule to services and steps.

Optional fields in a requirement, ignored by the validators:

- `category`: `prepare` (a document or payment to get ready), `how` (how the procedure works), `after` (what happens after you apply or attend), `if-urgent`. The UI can use it to group a long checklist.
- `lead_time_days`: only when a source states a duration. For the CIE delivery the source says "6 giorni lavorativi"; the 8 calendar days in the file are the team's prudent conversion, written in `unknowns_it`.

## What is verified now (4 October 2026)

| Service | Verified | Todo | Sources used |
|---|---|---|---|
| `carta-identita` | 34 requirements, 3 steps | 1 (whether a non-Italian adult's CIE is valid for travel: no saved source says) | `cie`, `cie-ministero`, `prenotazione`, `ds549` |
| `iscrizione-anagrafica-extra-ue` | 44 requirements, 6 steps (step 2 with 2 alternative routes), 14 form-guide section titles and housing options | 1 (documents for a first permit for study or other cases not in Annex A) | `residenza-estero`, `residenza-estero-modulistica`, `residenza-estero-extraue` (Annex A PDF), `residenza-estero-modulo` (online form), `permesso-soggiorno`, `codice-fiscale`, `dimora-abituale`, `cambio-residenza`, `yesmilano-students` |
| `cambio-residenza` | 18 requirements, 3 steps | 1 (how to declare without SPID or CIE: no saved source says) | `cambio-residenza` (Comune), `anpr-cambio-residenza` (Anagrafe Nazionale, Ministero dell'Interno) |
| **Total** | **110: 96 requirements, 12 steps, 2 routes** (plus 14 form-guide titles and housing options) | **3** | 16 pages, 6 datasets |

Renting, for residence from abroad, has two options since 4 October: `affitto-registrato` (the YesMilano student guide: scan of the contract with its registration number, place and date) and `affitto` (contract not yet registered, being registered, or the person doesn't know: the City page asks for a copy of the contract). The two items used to apply together and the files to upload listed the rental contract twice. The `narrow` entry of the `alloggio` question holds the short follow-up ("Il tuo contratto d'affitto è già registrato all'Agenzia delle Entrate?") asked when a message only says "I rent". The change of residence from another comune asks only whether the home is yours (`proprieta`, `non-proprietario`): the ANPR page asks for cadastral references for an owner and, for example, the rental contract details and the owner's ID card otherwise.

Facts the demo can show, each with its quote:

- **CIE**: health card or tax code, colour photo on light background (printed, no USB), the old card for a renewal, another ID for a first card (or two witnesses), the police report for loss or theft, the residence permit for non-EU citizens; **EUR 22.20** cash or debit card; posted **within 6 working days**; walk-in without appointment only for loss/theft with a report and no other ID, 8:30 to 15:00, limited tickets; paper ID cards expired on 3 August 2026.
- **Residence from abroad**: it is an **online application** (form MOD_DDR_ESTERO) with scanned documents, **not a desk visit**; files only through the form (email is ignored, 7 MB per file); the documents change with the permit situation (four cases of Annex A); housing proof changes with owner / rent / public housing / free loan / guest / domestic worker; residence counts **from the date of the declaration**; summary email then protocol number; checks with a home visit (45 days per YesMilano); only one open application at a time, so the first submission must be complete; afterwards **60 days** to renew the habitual residence declaration after each permit renewal and **20 days** to report a change of address.
- **Change of residence from another comune or within Milan**: for Italian and foreign people coming from another Italian comune, changing address in Milan, or Italians back from abroad registered with AIRE; online on the **Anagrafe Nazionale (ANPR)** with SPID or CIE; **within 20 days** of moving; **free**; two kinds of declaration (new residence, or joining an existing household); a permit is required for non-EU citizens; other adults moving confirm in their own ANPR area; registered within **2 days**, checks for at most **45 days**, status in "Le tue richieste" with notifications by email and on App IO; TARI to declare.
- **Order across bodies**: permit within **8 working days** of entry (Polizia di Stato) → tax code (three routes, each quoted from the Agenzia delle Entrate page: the Questura during the permit procedure, the Sportello Unico for entries for work or family reunification, otherwise an in-person appointment at the Agenzia) → residence online. No source fixes the order between permit and tax code: this is written in `unknowns_it`.

## How the pages were fetched

comune.milano.it is behind an Azure Application Gateway WAF that answers 403 to scripts (including `onevisit ingest --url`, whose user agent is `OneVisit/0.1`). The pages were downloaded once each with `curl` and ordinary browser headers (user agent, `Accept`, `Accept-Language`), one request per second, with TLS verification on. yesmilano.it sometimes answers 403 to repeated requests: waiting a few seconds is enough. poliziadistato.it, agenziaentrate.gov.it and cartaidentita.interno.gov.it answer normally.

Then, for each page:

```bash
.venv/bin/python data/tools/clean_html.py raw.html clean.html [--select article] [--unescape-inner] [--pdf]
.venv/bin/onevisit ingest <id> --html clean.html --url <official url>
```

`clean_html.py` never changes a word: it keeps the `<main>` (or `<article>`) element, removes bold and italic markers so quotes don't contain Markdown asterisks, decodes the escaped description of the City's online forms (`--unescape-inner`) and extracts the text of a PDF with `pdftotext -raw` (`--pdf`). Re-ingesting a page with the same content prints "Contenuto invariato"; a changed page lists the requirements to re-verify.

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

The CIE page confirms the Via Pecorari 3 entrance for the main office in Via Larga 12 ("ingresso lato via Pecorari, 3"), so that entrance is real; whether it is still "provisional" is not stated.

Reading the official pages for the two services found more gaps, the kind the City panel is for:

- **Annex A is old.** The list of documents for non-EU citizens (`residenza-estero-extraue`) is a PDF created in 2013. It asks for "originale e fotocopia" and the post office receipt, while the procedure today is an online upload of scans.
- **Annex A covers four cases only**: valid permit, permit being renewed, waiting for a first permit for employment, waiting for a first permit for family reunification. A student waiting for a first study permit is not covered.
- **Registered rental contract**: the City page lists a document only for contracts *not yet* registered; for a registered one it says nothing. The YesMilano student guide asks for the contract and its registration details.
- **Host's ID**: the YesMilano guide asks guests for a copy of the host's ID; the City page does not.
- **Tax code from abroad**: the Agenzia delle Entrate page says residents abroad can ask a consulate; the YesMilano guide (May 2025) says this is no longer possible.
- **Adult non-Italians and travel**: the CIE page says a non-Italian minor's card is not valid for travel abroad but says nothing about adults.

## Sources, one by one

Saved on 4 October 2026 (open data on 3 October); the date in brackets is the "last updated" date printed on the page. Counts are the verified facts that cite each page.

| id | Publisher | Page | Verified facts citing it |
|---|---|---|---|
| `cie` | Comune di Milano | [Carta d'identità](https://www.comune.milano.it/servizi/anagrafe/carta-d-identita) (02/10/2026) | 28; and the via Larga entrance |
| `cie-ministero` | Ministero dell'Interno | [CIE: rilascio e rinnovo in Italia](https://www.cartaidentita.interno.gov.it/richiedi/rilascio-e-rinnovo-in-italia/) | 6 |
| `prenotazione` | Comune di Milano | [Prenota il tuo appuntamento in Comune](https://www.comune.milano.it/servizi/prenota-il-tuo-appuntamento-in-comune) (18/08/2026) | 1 |
| `residenza-estero` | Comune di Milano | [Cambio di residenza per persone straniere provenienti dall'estero](https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza-per-persone-straniere-provenienti-dall-estero) (27/07/2026) | 4 |
| `residenza-estero-modulistica` | Comune di Milano | [Modulistica](https://www.comune.milano.it/servizi/anagrafe/richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero/modulistica-richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero) (16/06/2026) | 14; and 12 form-guide titles and housing options |
| `residenza-estero-extraue` | Comune di Milano (Annex A, PDF created in 2013) | [Elenco documenti per persone provenienti da Paesi extra UE](https://www.comune.milano.it/documents/20118/42443/Elenco+documenti+per+persone+provenienti+da+Paesi+extraUE.pdf/f59656a6-d8aa-7960-fc88-60daf732aeb3) | 12 |
| `residenza-estero-modulo` | Comune di Milano (online form) | [MOD_DDR_ESTERO](https://formshd4.comune.milano.it/rwe2/module_preview.jsp?MODULE_TAG=MOD_DDR_ESTERO) | 7; and 2 form-guide titles |
| `cambio-residenza` | Comune di Milano | [Cambio di residenza](https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza) (16/06/2026) | 8 |
| `anpr-cambio-residenza` | Ministero dell'Interno (ANPR) | [Cambio di residenza](https://www.anagrafenazionale.interno.it/area-cittadino/cambio-di-residenza/) | 14 |
| `dimora-abituale` | Comune di Milano | [Rinnovo dichiarazione dimora abituale](https://www.comune.milano.it/servizi/anagrafe/rinnovo-dichiarazione-dimora-abituale-per-persone-extra-ue) (27/07/2026) | 2 |
| `permesso-soggiorno` | Polizia di Stato | [Il rilascio del permesso di soggiorno](https://www.poliziadistato.it/articolo/225) (05/01/2024) | 2 |
| `permesso-soggiorno-come` | Polizia di Stato | [Permesso di soggiorno: come, dove e quanto costa](https://www.poliziadistato.it/articolo/217) (18/04/2019) | roles in `enti.json` |
| `codice-fiscale` | Agenzia delle Entrate | [Il Codice Fiscale](https://www.agenziaentrate.gov.it/portale/codice-fiscale-e-tessera-sanitaria/che-cos-) (7 March 2025) | 2, and the 2 tax-code routes |
| `yesmilano-students` | YesMilano | [Take Residence in Milano](https://www.yesmilano.it/en/study/how-to/take-residence-milano-students) | 6 |
| `yesmilano-permesso`, `yesmilano-codice-fiscale` | YesMilano | [Residence permit](https://www.yesmilano.it/en/study/how-to/residence-permit-students), [tax code](https://www.yesmilano.it/en/study/how-to/get-italian-tax-code-codice-fiscale) | saved, context for the student path |
| `ds549` | City open data | Sedi dei servizi anagrafici (resource modified 28 Jan 2026) | 2; the 13 offices |

Open data also used for context: `ds1959` (registrations by previous residence: 46,953 in 2024, 19,755 from abroad, 27,184 from other Italian comuni), `ds1702` (2022 survey of the online residence service), `ds1511` and `ds1512` (2021 surveys), `ds74` (foreign residents by citizenship). See `context/README.md`.

### What the sources themselves get wrong

Each gap is written in the data (`unknowns_it` in the service files, `data_issues` and `dataset_notes` in `offices.json`); the open questions are shown to the citizen as *Da verificare* with the official page.

- **Annex A is out of date**: a 2013 PDF asking for "originale e fotocopia", while the application today is an online upload of scans; it covers four permit cases only (no first study permit).
- **A registered rental contract**: the City page lists no document for it; YesMilano asks for the contract and its registration details.
- **The host's ID** for guests is asked for by YesMilano, not by the City page.
- **A tax code from abroad**: the Agenzia delle Entrate says a consulate can issue it; YesMilano (May 2025) says it no longer can.
- **An adult non-Italian's CIE for travel abroad**: the City page answers only for minors.
- **A move without SPID or CIE**: the City page sends everyone to ANPR, which needs SPID or CIE; neither page says what to do without them.
- **`ds549`**: the Via Passerini 5 office has no Municipio, phone or booking notes and still says "lunedì 5 gennaio 2026: CHIUSO"; the via Larga 12 entrance is still "INGRESSO PROVVISORIO" in the dataset while the City's ID card page gives it without saying so.
