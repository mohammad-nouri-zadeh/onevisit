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
| `carta-identita` | 143 requirements, 5 steps (step 1 with 2 alternative routes: walk-in, home service) | 3 (whether you can apply while the residence application is being checked; whether the receipt of a first permit application is enough; whether someone living in Milan and resident outside Lombardy can get a first card or replace a lost card or a faulty chip in Milan) | 64 sources: the City's CIE page, 35 articles of the City support centre (`cie-faq-*`), 5 more City pages and forms (home service page and form, organ donation, temporary-card form, correction of foreigners' data), 13 pages of the Ministry's CIE site, 4 Ministry circulars, 2 Polizia di Stato pages, 2 YesMilano guides, `prenotazione`, `ds549` (see below) |
| `iscrizione-anagrafica-extra-ue` | 44 requirements, 6 steps (step 2 with 2 alternative routes), 14 form-guide section titles and housing options | 1 (documents for a first permit for study or other cases not in Annex A) | `residenza-estero`, `residenza-estero-modulistica`, `residenza-estero-extraue` (Annex A PDF), `residenza-estero-modulo` (online form), `permesso-soggiorno`, `codice-fiscale`, `dimora-abituale`, `cambio-residenza`, `yesmilano-students` |
| `cambio-residenza` | 18 requirements, 3 steps | 1 (how to declare without SPID or CIE: no saved source says) | `cambio-residenza` (Comune), `anpr-cambio-residenza` (Anagrafe Nazionale, Ministero dell'Interno) |
| **Total** | **223: 205 requirements, 14 steps, 4 routes** (plus 14 form-guide titles and housing options) | **5** | 133 pages, 6 datasets |

Renting, for residence from abroad, has two options since 4 October: `affitto-registrato` (the YesMilano student guide: scan of the contract with its registration number, place and date) and `affitto` (contract not yet registered, being registered, or the person doesn't know: the City page asks for a copy of the contract). The two items used to apply together and the files to upload listed the rental contract twice. The `narrow` entry of the `alloggio` question holds the short follow-up ("Il tuo contratto d'affitto è già registrato all'Agenzia delle Entrate?") asked when a message only says "I rent". The change of residence from another comune asks only whether the home is yours (`proprieta`, `non-proprietario`): the ANPR page asks for cadastral references for an owner and, for example, the rental contract details and the owner's ID card otherwise.

Facts the demo can show, each with its quote:

- **CIE**: only for Milan residents and Milan's AIRE registrants (people living in Milan and resident outside Lombardy: renewal for serious documented reasons; Lombardy residents go to their own comune, newcomers register as residents first); health card or tax code, colour photo 45 x 35 mm, recent, printed on paper (no USB), the photo rules (expression, glasses, head covering for religious, cultural or medical reasons per the Ministry, while the City page asks for a bare head: the desk officer decides), the old card for a renewal, another ID for an adult's first card (or two witnesses), the police report for loss or theft (or the Polizia di Stato's online loss report, with SPID or CIE) and the toll-free number to block cards issued after 4 July 2016, the residence permit for non-EU citizens (an expired permit: the renewal receipt or the prenotafacile booking is enough); **EUR 22.20** cash or debit card; booking without SPID, on the City's system (not the national portal), up to five household members with SPID or CIE, rescheduling, compulsory check-in in the e-mail's time window; fingerprints from age 12, organ donation choice for adults; the receipt with the first half of PIN and PUK, valid as ID in Italy only; online services and CieSign signature with the card; posted **within 6 working days** by registered mail, second attempt, 30 days at the post office, returned to sender; validity by age (3, 5, about 10 years; unlimited from 70 for cards issued from 30 July 2026; 3 years for asylum seekers, also over 70; 1 year without fingerprints); minors (both parents, one parent with a witness or the child's permit or old card, newborns with both parents or another adult after 30 working days, consent for travel on the City's form, under-14 travel rules, accompanying declaration at the Questura); the card is a travel document only for Italian citizens (an Italian who loses it abroad asks the consulate for an Emergency Travel Document); walk-in without appointment for loss/theft with a report and no other ID or a damaged card, while tickets last (the CIE page says 8:30 to 15:00, the offices page until half an hour before closing); a faulty chip: report it to the Ministry, then a free new card without appointment; urgencies (15 days before the event, trips without a passport, notary deeds, not assured in the last 5 days before a trip in Europe); the temporary paper ID at via Larga, only to replace a previous card (once, 6 months, EUR 5.42, 2 photos and a form, handed back with the CIE); the home service for health reasons (online form with SPID or CIE, medical certificate, ID, delegation, call-back from 02.884 after at least 15 working days, free visit, payment at home also by credit card); lost PIN and PUK (cards from 3 August 2017: duplicate at any office by appointment, or the PUK in the CieID app after 48 hours, or the home service) and a change of contact details, each with its own booking page; no new card for a change of address, residence or marital status; paper ID cards expired on 3 August 2026 (still usable in Italy until 31 January 2027 if they don't expire first, and for contracts signed with them).
- **Residence from abroad**: it is an **online application** (form MOD_DDR_ESTERO) with scanned documents, **not a desk visit**; files only through the form (email is ignored, 7 MB per file); the documents change with the permit situation (four cases of Annex A); housing proof changes with owner / rent / public housing / free loan / guest / domestic worker; residence counts **from the date of the declaration**; summary email then protocol number; checks with a home visit (45 days per YesMilano); only one open application at a time, so the first submission must be complete; afterwards **60 days** to renew the habitual residence declaration after each permit renewal and **20 days** to report a change of address.
- **Change of residence from another comune or within Milan**: for Italian and foreign people coming from another Italian comune, changing address in Milan, or Italians back from abroad registered with AIRE; online on the **Anagrafe Nazionale (ANPR)** with SPID or CIE; **within 20 days** of moving; **free**; two kinds of declaration (new residence, or joining an existing household); a permit is required for non-EU citizens; other adults moving confirm in their own ANPR area; registered within **2 days**, checks for at most **45 days**, status in "Le tue richieste" with notifications by email and on App IO; TARI to declare.
- **Order across bodies**: permit within **8 working days** of entry (Polizia di Stato) → tax code (three routes, each quoted from the Agenzia delle Entrate page: the Questura during the permit procedure, the Sportello Unico for entries for work or family reunification, otherwise an in-person appointment at the Agenzia) → residence online. No source fixes the order between permit and tax code: this is written in `unknowns_it`.

## The ID card checklist: who sees what

The CIE questions are asked in this order: `residenza`, `motivo`, `eta`, `cittadinanza`, `presenza`. Every requirement has a `when` built from them (the checklist keeps an item only when every question in its `when` has one of the listed answers):

- **Residence first.** Everything about applying in Milan needs `residenza` in `milano`, `domicilio-milano` or `aire`. Someone resident in another Lombardy comune or not yet resident in Italy gets only the items that say where to go (`solo-residenti`, `residenti-lombardia`, `prima-la-residenza`, `residenza-non-permesso`, the open `residenza-in-corso`): no booking, cost or delivery items.
- **`motivo`** has seven answers: `prima`, `rinnovo`, `deteriorata` (damaged card), `chip` (card intact, chip not working: Ministry first, then a free card without appointment, so no cost or booking items), `smarrimento-furto`, `pin-puk` (lost PIN or PUK, or contact details to change: only those items, any registry office) and `gia-cie` (already has the card: change of address or marital status, delivery questions; no visit needed).
- **`presenza`**: booking, check-in, the photo booth, the cost at the desk, walk-in exceptions, urgent desk routes and the temporary card need `sportello`; the home-service items need `domicilio-salute`.
- **Adults and minors**: another ID or two witnesses, fingerprints at the desk, organ donation and the adult validity are for adults; minors get the minors' rules (both parents, one parent with a witness or the child's document, newborns, fingerprints from 12).
- **Citizenship**: the trip items (15 and 5 days before a trip, the temporary card abroad, the consulate's E.T.D.) are for Italian citizens only, because the CIE is a travel document only for them; EU and non-EU citizens get `espatrio-adulti-non-italiani`.
- **The temporary paper ID** replaces a previous card (the City's form says so): it is shown for `rinnovo`, `deteriorata` and `smarrimento-furto`, not for a first card.

Answers can carry a **route** (`option_routes` in the question), which the demo and the agent read: `stop` (no booking link and no desk dossier, a link to the residence services OneVisit covers), `home` (the home-service form instead of the booking page), `walk-in`, `info`, and booking links of their own (the PIN/PUK duplicate and the contact change, on the City's CIE page). `validate.py` checks that every link is on the saved page of its source. The old `scadenza` date question was removed: no requirement used it and nothing compared it with the delivery time.

Coverage of the CIE, facet by facet (verified items, then the sources they quote):

| Facet | Verified items | Sources |
|---|---|---|
| Who can apply in Milan (residence, domicile, AIRE) | 9; todo: `residenza-in-corso`, `domiciliati-altri-casi` | `cie-faq-00302`, `yesmilano-id-card`, `yesmilano-work-registering-resident`, `cie`, `cie-faq-00413`, `circ-dait-054-2026` |
| Booking and check-in | 9 | `ds549`, `cie-faq-00578`, `cie-faq-03767`, `cie`, `cie-faq-03790`, `prenotazione`, `cie-faq-03783`, `cie-faq-00307` |
| Documents and identification | 8; todo: `primo-permesso-in-attesa` | `cie`, `cie-ministero`, `cie-faq-00564` |
| Photo | 8 | `cie`, `cie-ministero`, `cie-faq-00308`, `cie-ministero-foto`, `cie-faq-00414` |
| Cost | 2 | `cie`, `cie-faq-04023` |
| At the desk (fingerprints, contacts, donation, declarations) | 9 | `cie-ministero`, `cie-ministero-impronte`, `cie`, `cie-faq-00542`, `cie-donazione-organi`, `circ-dait-081-2023` |
| Renewal and paper cards | 9 | `cie-faq-00405`, `cie-faq-00303`, `cie-faq-04180`, `cie`, `cie-ministero-faq` |
| Loss and theft (also abroad) | 9 | `cie`, `pds-denunce-online`, `cie-ministero-faq`, `cie-ministero-furto-smarrimento`, `cie-ministero-viaggiare`, `cie-faq-00580`, `cie-faq-00355` |
| Damaged card and faulty chip | 5 | `cie`, `cie-faq-00418`, `cie-faq-00310`, `cie-faq-00409` |
| Walk-in: tickets and hours | 2 | `cie` |
| Urgent cases | 6 | `cie`, `cie-faq-00306` |
| Temporary paper ID | 7 | `cie`, `cie-faq-04349`, `cie-provvisoria-modulo` |
| Minors | 17 | `cie`, `cie-faq-00302`, `cie-faq-00354`, `cie-faq-00353`, `pds-espatrio-minori`, `cie-ministero-minori`, `cie-ministero-attiva` |
| Citizenship and travel | 4 | `circ-dait-004-2017`, `cie-faq-00472`, `rettifica-dati-stranieri`, `circ-dait-060-2026` |
| Home service for health reasons | 10 | `cie-domicilio-salute`, `cie-faq-00392`, `cie-faq-04024`, `cie`, `cie-domicilio-modulo`, `cie-faq-04028` |
| Delivery and receipt | 13 | `cie`, `cie-ministero-spedizione`, `cie-faq-00471`, `cie-faq-00407`, `cie-ministero-ricevuta`, `cie-faq-00304` |
| Validity | 5 | `cie-faq-00517`, `cie` |
| PIN, PUK and digital identity | 10 | `cie-ministero-pin-puk`, `cie-ministero-credenziali`, `cie`, `cie-ministero-recupero-puk`, `cie-faq-00470`, `cie-faq-04366` |
| Already have the CIE (change of address or marital status) | 1 | `cie-faq-00518` |

No facet of the City's CIE page or of its support articles is left without a verified item; what the sources do not say is in the three open items and in `unknowns_it`.


## How the pages were fetched

comune.milano.it is behind an Azure Application Gateway WAF that answers 403 to scripts (including `onevisit ingest --url`, whose user agent is `OneVisit/0.1`). The pages were downloaded once each with `curl` and ordinary browser headers (user agent, `Accept`, `Accept-Language`), one request per second, with TLS verification on. yesmilano.it sometimes answers 403 to repeated requests: waiting a few seconds is enough. poliziadistato.it, agenziaentrate.gov.it, cartaidentita.interno.gov.it and dait.interno.gov.it answer normally.

The City's support centre (`servizicrm.comune.milano.it/centro-supporto/KA-xxxxx`) holds about sixty dated questions and answers on the ID card. It answers 403 when requests are less than about 2 seconds apart (3 seconds worked); the site search is behind a JavaScript challenge, so the articles were found with the support centre's own search and by trying nearby KA numbers. Each article is saved as `cie-faq-<number>`: its question (`#faqtitle`), answer (`#faqcontent`) and date (`#faqlastmodified`) are copied word for word into a small HTML file, then cleaned with `clean_html.py` and saved with `onevisit ingest` (the page around them is menus, related articles and a feedback form). The booking pages (`/spec/appuntamenti/anagrafecie` and the PIN/PUK and contact-update bookings) redirect scripts to the SSO login page, so their screens are not saved.

The review of the CIE catalog on the evening of 4 October (wrong conditions, texts that said more than their quote, the routes for non-residents, the home service and lost PIN/PUK) needed no new page: every correction quotes a page already saved, and the PIN/PUK and contact booking links are the ones printed on the saved CIE page.

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
- **Adult non-Italians and travel**: the City's CIE page says a non-Italian minor's card is not valid for travel abroad but says nothing about adults. Since 4 October the answer comes from the Ministry's circular n. 4/2017 (the CIE is a travel document "per i soli cittadini italiani") and the YesMilano guide ("not valid for crossing border").

## Sources, one by one

Saved on 4 October 2026 (open data on 3 October); the date in brackets is the "last updated" date printed on the page. Counts are the verified facts that cite each page.

| id | Publisher | Page | Verified facts citing it |
|---|---|---|---|
| `cie` | Comune di Milano | [Carta d'identità](https://www.comune.milano.it/servizi/anagrafe/carta-d-identita) (02/10/2026; re-fetched twice on 4 October evening: identical) | 55, 1 step, 1 route, the PIN/PUK and contact booking links; and the via Larga entrance |
| `cie-ministero` | Ministero dell'Interno | [CIE: rilascio e rinnovo in Italia](https://www.cartaidentita.interno.gov.it/richiedi/rilascio-e-rinnovo-in-italia/) | 4, 2 steps |
| `prenotazione` | Comune di Milano | [Prenota il tuo appuntamento in Comune](https://www.comune.milano.it/servizi/prenota-il-tuo-appuntamento-in-comune) (18/08/2026; re-fetched: identical) | 1 |
| `cie-faq-<KA number>` (77 saved, 35 used) | Comune di Milano (support centre) | Questions and answers "Anagrafe / Carta d'identità" at `servizicrm.comune.milano.it/centro-supporto/KA-<number>/…`, each dated (31/08/2025 to 02/10/2026): who can apply in Milan, photo rules, expired permit, newborns, one parent, urgent trips and notary deeds, chip, check-in, rescheduling, delivery problems, home service, temporary ID, new citizens, 70+ | 47, 1 step (most: `cie-faq-00302` 5, `00308` 4, `00306` 3); `cie-faq-00393` backs the open item on a first permit |
| `cie-domicilio-salute`, `cie-domicilio-modulo` | Comune di Milano | [Servizi anagrafici a domicilio per motivi di salute](https://www.comune.milano.it/servizi/anagrafe/servizi-anagrafici-a-domicilio-per-motivi-di-salute) (14/09/2026) and its [online form](https://formshd3.comune.milano.it/rwe2/module_preview.jsp?MODULE_TAG=SERVIZIO_ANAGRAFICO_DOMICILIO) | 3 and 1 route; 2 and the home-service form link |
| `cie-donazione-organi`, `cie-provvisoria-modulo`, `rettifica-dati-stranieri` | Comune di Milano | [Donazione di organi](https://www.comune.milano.it/servizi/anagrafe/esprimi-la-tua-volonta-sulla-donazione-di-organi) (16/06/2026), [temporary-ID form](https://www.comune.milano.it/documents/d/guest/richiesta-carta-provvisoria-1?download=true) (PDF of 13/08/2026), [Rettifica dati anagrafici per stranieri](https://www.comune.milano.it/servizi/anagrafe/rettifica-dati-anagrafici-per-cittadine-e-cittadini-stranieri) (12/05/2026) | 1 each |
| `cie-ministero-*` (14 saved, 12 used) | Ministero dell'Interno | cartaidentita.interno.gov.it: minors, photos, fingerprints, delivery, receipt, loss and theft, FAQ (blocking the card), PIN and PUK, PUK recovery in the CieID app, credentials, activation, travel (the E.T.D. abroad); saved for context: card features, what the CIE is | 18, 1 step |
| `circ-dait-004-2017`, `circ-dait-054-2026`, `circ-dait-060-2026`, `circ-dait-081-2023` (and `circ-dait-008-2026`, saved) | Ministero dell'Interno | Circulars on dait.interno.gov.it (PDF): the CIE is a travel document only for Italian citizens; AIRE in any comune; 3 years for asylum seekers; parents' declaration for travel documents | 1 each |
| `pds-denunce-online`, `pds-espatrio-minori` | Polizia di Stato | [Denunce online](https://www.poliziadistato.it/articolo/denunce-online) (25/06/2026), [Passaporto per i minori e espatrio](https://www.poliziadistato.it/articolo/passaporto-per-i-minori-e-espatrio) | 2 and 1 |
| `yesmilano-id-card`, `yesmilano-work-registering-resident` (and 2 more saved) | YesMilano | [How to get your Italian ID card](https://studyandwork.yesmilano.it/en/study/how-to/id-card), [Registering as a resident](https://studyandwork.yesmilano.it/en/work/getting-started-guide/registering-resident-milano) | 1 each |
| `sedi-anagrafiche`, `cie-foto-requisiti`, `cie-cabine-foto`, `oggetti-smarriti`, 6 City news items | Comune di Milano | Saved for context and for the panel (office hours, the 2007 photo PDF, the outdated photo-booth list, paper-card campaign news); not cited | 0 |
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
| `ds549` | City open data | Sedi dei servizi anagrafici (resource modified 28 Jan 2026; CSV re-downloaded on 4 October: byte-identical) | 1; the 13 offices |

Open data also used for context: `ds1959` (registrations by previous residence: 46,953 in 2024, 19,755 from abroad, 27,184 from other Italian comuni), `ds1702` (2022 survey of the online residence service), `ds1511` and `ds1512` (2021 surveys), `ds74` (foreign residents by citizenship). See `context/README.md`.

### What the sources themselves get wrong

Each gap is written in the data (`unknowns_it` in the service files, `data_issues` and `dataset_notes` in `offices.json`); the open questions are shown to the citizen as *Da verificare* with the official page.

- **Annex A is out of date**: a 2013 PDF asking for "originale e fotocopia", while the application today is an online upload of scans; it covers four permit cases only (no first study permit).
- **A registered rental contract**: the City page lists no document for it; YesMilano asks for the contract and its registration details.
- **The host's ID** for guests is asked for by YesMilano, not by the City page.
- **A tax code from abroad**: the Agenzia delle Entrate says a consulate can issue it; YesMilano (May 2025) says it no longer can.
- **An adult non-Italian's CIE for travel abroad**: the City page answers only for minors (the Ministry's circular n. 4/2017 and YesMilano answer for adults).
- **CIE, sources that disagree** (all in `unknowns_it` of `carta-identita.json`): head covering in the photo (City page "capo scoperto", Ministry rules allow religious, cultural or medical reasons); walk-in hours (8:30-15:00 on the CIE page, urgent tickets until half an hour before closing on the offices page and in `ds549`); documents for an urgent trip differ between the support articles on loss, theft and a damaged card; the 70+ unlimited validity ("dal", "dopo" or "prima" 30 July 2026); organ donation optional (Ministry) or a form adults "must" sign (KA-00542), and two different e-mail addresses to cancel it; home service "impossibilità di muoversi" or "in modo permanente"; delivery 6 working days (City) or ten (YesMilano); the photo-booth list of January 2022 names an office that no longer exists; the City's English CIE page mistranslates the 70+ rule. Since the evening review the checklist shows two of them next to the items: the photo's head covering (`foto-copricapo`) and the walk-in hours (`senza-appuntamento-orario`); the walk-in without appointment for a card without PIN and PUK comes only from a 2025 support article (KA-00303), not from the current CIE page.
- **CIE, what no source says**: whether you can apply while the residence application is being checked; whether a first-permit receipt is enough; whether someone living in Milan and resident outside Lombardy can get a first card, or replace a lost card or a faulty chip, in Milan (the sources speak only of renewal); how an absent parent abroad signs the minor's travel consent, and what applies when a parent refuses it (the judge's authorisation appears only on the Polizia di Stato passport page); documents specific to EU citizens; AIRE registrants of other comuni in Milan; credit cards at the desk; the cost of a duplicate after loss or theft; cancelling an appointment; which offices issue the CIE; the check-in margin; language help at the desk; wrong data printed on the card; an adult under guardianship at the desk; what a person with only a temporary-residence declaration can do; the CIE for homeless people or people in prison (only a 2023 news item on the IP3 document); whether the via Larga priority lane of December 2024 is still active.
- **A move without SPID or CIE**: the City page sends everyone to ANPR, which needs SPID or CIE; neither page says what to do without them.
- **`ds549`**: the Via Passerini 5 office has no Municipio, phone or booking notes and still says "lunedì 5 gennaio 2026: CHIUSO"; the via Larga 12 entrance is still "INGRESSO PROVVISORIO" in the dataset while the City's ID card page gives it without saying so.
