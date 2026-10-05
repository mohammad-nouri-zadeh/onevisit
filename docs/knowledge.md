# Knowledge: how OneVisit gets the official pages it answers from

OneVisit answers questions about a City procedure (first of all the ID card, *carta d'identità elettronica*, CIE) only from official pages saved in the repository: `data/pages/<source_id>.md`, listed in `data/sources.csv`. Claude cannot read the official sites live: the City's firewall answers 403 to programs, and an answer must cite text that a person can check later. So the knowledge is downloaded beforehand, saved with its date and hash, searched at runtime, and quoted. When nothing saved covers a question, the assistant says so and links the official page.

This page explains how the pages are found, re-checked and added. The tool is `data/tools/crawl.py`, configured by `data/tools/crawl_seeds.json`. How Claude then searches and quotes them is in [Searching the saved pages](#searching-the-saved-pages-onevisitsearchpy).

## The pipeline at a glance

| Step | Tool | What comes out | What guarantees it |
|---|---|---|---|
| 1. Download | `crawl.py discover` (or a browser save, see `data/README.md`) | raw HTML/PDF bytes and `manifest.json`, outside the repository | domain allowlist, robots.txt, pacing, TLS on; `sha256` of the raw bytes |
| 2. Clean | `data/tools/clean_html.py` | the article only (or the PDF text) | never changes a word: menus, scripts, bold markers go, sentences stay |
| 3. Ingest with hash | `onevisit ingest` / `crawl.py ingest` | `data/pages/<id>.md`: front matter (`url`, `ente`, `servizio`, `verified_at`, `content_hash` = SHA-256 of the body) and the row in `data/sources.csv`, in status `review` when `crawl.py` saved it | a person chose the page; `crawl.py ingest` never overwrites a saved page (without `--force`) nor saves a URL twice; re-ingesting the same text prints "Contenuto invariato" |
| 3b. Approve | `crawl.py approve` | the row's status goes from `review` to `ok` | a person read the saved Markdown: only then the search quotes it |
| 4. Passage index | `onevisit/search.py` | ~490 passages of 149 pages (about 400 of the 135 ID-card pages), each a verbatim slice of a saved page, with its heading path; a circular's letterhead and addressees are left out | built from the files at first use, rebuilt when any of them changes; `index_stats()["hash_mismatches"]` lists pages edited by hand after ingest |
| 5. Claude tool | `search.TOOL` + `search.run_tool()` | JSON: `source_id`, `title`, `publisher`, `url`, `saved_at`, `updated_at` (the page's own date), `kind` (page, faq, news, circular...), `heading`, `text`, `confidence`, `confident` | the tool returns the page's own words, never a summary; an empty result carries the note "say you don't know and link the official page" |
| 6. Citation | the agent's answer | an answer in the user's language that cites `source_id`s; the UI links `url` and shows `saved_at` | requirements in a checklist still need a verified quote (`validate.py`); a passage is evidence for an answer, not a new catalog requirement |
| 7. Refresh | `crawl.py refresh` | unchanged / changed (with a diff) / failed, per saved page | a changed page is re-ingested by a person, then `validate.py` re-checks every quote |

## The commands

Run them from the repository root with the kit environment (`.venv`, Python 3.13). `discover` and `rescore` alone work with any Python 3.11+ (standard library only).

```sh
# 1. Find pages: nothing is written in the repository, only in --out
.venv/bin/python data/tools/crawl.py discover --topic carta-identita --out /tmp/cie-crawl --depth 2 --max-pages 300
.venv/bin/python data/tools/crawl.py rescore --topic carta-identita --out /tmp/cie-crawl   # new keywords or thresholds, offline

# 2. Check whether the saved pages changed on the official sites
.venv/bin/python data/tools/crawl.py refresh --topic carta-identita --out /tmp/cie-refresh
.venv/bin/python data/tools/crawl.py refresh --from-crawl /tmp/cie-crawl --offline   # reuse a discover run, no download

# 3. Save the pages a person picked (ids from the manifest; rename with old=new): status "review"
.venv/bin/python data/tools/crawl.py ingest --from-crawl /tmp/cie-crawl --ids cie-faq-00411,cie-ministero-en-help=cie-ministero-faq-en --dry-run
.venv/bin/python data/tools/crawl.py ingest --from-crawl /tmp/cie-crawl --ids cie-faq-00411

# 4. After reading data/pages/cie-faq-00411.md: the search may quote it
.venv/bin/python data/tools/crawl.py approve --ids cie-faq-00411
```

### discover

Starts from the topic's seeds: the URLs listed in `crawl_seeds.json` plus every source of the topic already in `data/sources.csv` (by id pattern, or because the saved page's `servizio` names the topic's service). Then:

- **Search and sitemaps.** It asks the City support centre's own search (`servizicrm.comune.milano.it/Support/SearchService`, the endpoint the support-centre page calls) with the topic's queries, and reads each host's `sitemap.xml` (from `robots.txt` when declared). A sitemap index too large to read, with no relevant sub-sitemap names (www.comune.milano.it has about 3,000), is skipped: links are enough there.
- **Breadth-first links** up to `--depth` (default 2) from the seeds. A link is queued only if its anchor text or URL words match the topic's `link_keywords` (strong: 3 points, weak: 1), on any host. Within a depth, the best-scoring links go first, so the `--max-pages` cap (default 300) cuts the least promising ones; among links of the same score, those on a host all about the topic (`topic_hosts`: cartaidentita.interno.gov.it) go first. The host is only a tie-breaker: when it added a point to every link, the Ministry's menus, hubs and English twins used up the 300 pages at depth 1 of the first run.
- **Relevance.** A page is scored on the text ingest would keep of it (`clean_rules`: the Ministry's `<article>`, the support centre's question, answer and date; elsewhere `<main>`, else `<article>`, else the body without menus, header, footer and scripts) and on its title without the site's name (`title_suffixes`: "Cookie policy - Carta di Identità Elettronica (CIE)" is "cookie policy"). It is kept when it scores at least `min_score` on the topic `keywords` (strong 3, medium 2, weak 1 per hit, at most 5 hits per keyword, a bonus for keywords in the title) and its text has at least `min_strong_hits` strong hits (the title never counts toward them). PDFs are scored on their text (`pdftotext`). Keywords match whole words, without accents, in lower case, with typographic apostrophes made plain. For the ID card, `min_score` 8 and `min_strong_hits` 1 are calibrated on that cleaned text: a support-centre answer is a few lines.
- **Output** in `--out`: `raw/` (the exact bytes downloaded, HTML or PDF), `text/` (the main text of kept pages, for reading), and `manifest.json`, saved every 20 pages so an interrupted run keeps what it fetched.
- **rescore** reads the raw files of a finished run again with the current keywords, thresholds and id rules, without any request: calibrate there, not by crawling again.

Each manifest entry has: `url`, `final_url` (after redirects), `http_status`, `content_type`, `sha256` of the raw bytes, `fetched_at`, `title`, `h1`, `score`, `keyword_hits`, `strong_hits`, `kept` and `reason`, `depth`, `links_from` (the pages, sitemap or search query that led to it), `anchors`, `raw_file`, `text_file`, `already_saved_as` (the source id when the URL, or a URL serving the same page, is in `sources.csv`), `duplicate_of` (the first address of the same page: a redirect to a page already fetched, or the same main text, as with `/en/documents/...` and `/documents/...`), `suggested_id` (from the topic's `id_rules`; none for duplicates), `publisher`, `kind`, `text_sha256`. The manifest also lists the `robots.txt` status of every host, the searches, the sitemaps, and the URLs **not** fetched with the reason (outside the allowlist, blocked pattern, robots.txt, deeper than `--depth`, page cap reached).

### refresh

For every source with a saved page (or `--topic`, `--ids`), downloads the page again (or takes it from `--from-crawl`), cleans it exactly as it was saved (`clean_html.py`, then `onevisit ingest`'s Markdown conversion; support-centre articles keep only `#faqtitle`, `#faqcontent`, `#faqlastmodified`; the Ministry's CIE pages only `<article>`; PDFs through `pdftotext`) and compares the `content_hash` with the one in `data/pages/<id>.md`:

- `unchanged`: same hash (or same text with different spacing);
- `changed`: the text differs; with `--out` the new text and a unified diff are written there. Every requirement that quotes the page must be re-verified by a person;
- `failed`: download refused or not 200 (the reason is printed), or with `--offline` a page the crawl did not fetch;
- `skipped`: open data and sources without a saved page.

`refresh` never writes in `data/`. Updating a page stays a human step: `onevisit ingest <id> --html <clean file> --url <url>` and then `python data/tools/validate.py`.

### ingest

For the entries a person picked (`--ids` from the manifest's `suggested_id`, optionally `old=new` to choose the id; there is no "every entry above a score": a score says a page is on the topic, not that it is worth quoting, and hubs, site maps and chip specifications score high too):

1. checks against the repository **as it is now**, not as it was when the crawl ran (another person, or another session, may have saved pages since): an id already in `sources.csv`, a URL (or the final URL) already saved under another id ("already saved as X (use refresh)"), a `data/pages/<id>.md` already on disk (skipped unless `--force`), and a URL that the current `crawl_seeds.json` policy blocks are all skipped;
2. `data/tools/clean_html.py` on the raw file (with `--pdf`, `--select article` or `--unescape-inner` as `clean_rules` say; support-centre articles are reduced to question, answer and date first);
3. a new row in `data/sources.csv` (publisher and kind from the policy, a note saying how it was found);
4. `onevisit ingest <id> --html <clean file> --url <final url>`, which writes `data/pages/<id>.md` with front matter and hash;
5. the row's status set to **`review`**: the search skips the page.

Then a person reads the saved Markdown (and, for an English version, compares it with the Italian page) and runs `crawl.py approve --ids <id>`: status `ok`, and the search quotes the page from the next query. **Approving is publishing**: from then on Claude may answer from that page. A page that should only be linked, or that has mistakes (the City's English CIE page, see below), stays in `review`.

`--dry-run` prints the plan. `--data-dir` points everything at another copy of `data/` (the tests use a temporary one). A searchable page is **not** a verified fact: a checklist requirement becomes `verified` only with a verbatim quote that `validate.py` finds in the page.

## Rules the crawler follows

- **Domain allowlist** (`policy.allowed_domains`): comune.milano.it and its public subdomains, yesmilano.it, cartaidentita.interno.gov.it, dait.interno.gov.it, poliziadistato.it. It never leaves it, not even through a redirect: redirects are followed by hand and every hop is checked. The login hosts (`servizicdm`, `ssocdm`), the booking flows (`servizicrm.../spec/`, `/appuntamenti`), the site search, Liferay portlet actions, language versions we do not use, the Ministry site's sections for public administrations and businesses, cookie and accessibility pages, and images, scripts and office files are blocked.
- **robots.txt** of every host, read with `urllib.robotparser` plus the `*` and `$` wildcards it ignores (both must allow). A missing robots.txt (404) allows everything; a refused or unreachable one (401, 403, 5xx) blocks the host. `Crawl-delay` is honoured.
- **Pacing**: at least 1 s between two requests to the same host, 3 s for yesmilano.it (both of its hosts together) and for the support centre, more if robots.txt asks. On 429 or a dropped connection it waits 30 s and retries once.
- **Who it is**: the user agent says `OneVisitCrawler/1.0` with the project's address, the same name its robots.txt rules are read for; never a browser's. No cookies, no JavaScript, no attempt to pass a challenge. A page behind a JavaScript challenge or a login stays unsaved and is listed as such.
- **A 403 is a no.** It is never retried or worked around: the report says "refused (403): ask the site". The City's firewall answers 403 to scripts, so for comune.milano.it the way is to ask the Comune di Milano (the event's partner) to allow `OneVisitCrawler` or to send the pages, and meanwhile a person saves a page from an ordinary browser and ingests it (`onevisit ingest <id> --html <file>`, see `data/README.md`). Until 5 October 2026 the crawler sent a browser's user agent and retried a 403 once, as the earlier `curl` downloads did: the 16 pages added that day were fetched that way (their content is the public page, unchanged). That was a way around the operator's bot control, not polite crawling, and it is gone.
- **TLS** verification on, with the default CA bundle; the environment's `HTTPS_PROXY` is used.
- **No personal data**: only public pages are fetched; nothing is posted; forms are not submitted.

## Adding a topic

Add a block next to `carta-identita` under `topics` in `crawl_seeds.json`:

```json
"residenza": {
  "title": "Residenza a Milano",
  "service_id": "iscrizione-anagrafica-extra-ue",
  "id_prefix": "residenza",
  "seed_sources": {"id_patterns": ["^residenza", "^cambio-residenza$", "^dimora-abituale$"], "exclude_kinds": ["opendata"]},
  "seeds": ["https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza"],
  "keywords": {"strong": ["residenza", "iscrizione anagrafica"], "medium": ["dimora abituale"], "weak": ["anagrafe"]},
  "min_score": 8, "min_strong_hits": 1,
  "link_keywords": {"strong": ["residenza"], "weak": ["anagrafe"]},
  "search_endpoints": [], "sitemaps": {"hosts": []}, "id_rules": []
}
```

Then run `discover --topic residenza`, read the manifest, and calibrate `min_score` with `rescore` on pages you know are relevant (`already_saved_as` set) and pages you know are not. Add the new sites' name suffixes to `title_suffixes`.

## First run for the ID card (4 October 2026)

`discover --topic carta-identita --depth 2 --max-pages 300`: 300 pages in 28 minutes (380 requests, 296 answered 200), 219 relevant to the CIE. 107 of them were already saved, 6 were the same page under another address, 106 were new. A person-style review kept 34 worth saving: 16 that answer questions no saved page covers (support-centre articles on the home-service attachments, where to check in and a CIE not recognised online; the Ministry's pages on the CieID app, logging in and signing with the CIE, fingerprint storage, the chip-defect check, Ve.Do., the national booking portal, AIRE, the privacy notice) and 18 official English versions of pages saved in Italian. The City's own English CIE page is **not** among them: it says the unlimited validity is for "citizens aged 8 or over 70" (the Italian page: 70 or older) and calls DL 108/2026 a "Legislative Decree"; since English passages rank first for English questions, it would answer a newcomer with the wrong age. It goes to the City panel as a gap. It also found an older version of the provisional-ID form still linked from eight support articles, and an organ-donation brochure that sends changes to the ASL while the City and the Ministry say the Comune. The other 71 were hubs, pages for public administrations, site boilerplate, dated news or other City services; the PA sections are now blocked. `refresh --from-crawl --offline` found all 120 saved CIE pages unchanged. Nothing was ingested by this run: saving is a person's decision.

Re-scored on 5 October with the relevance described above (`crawl.py rescore`, offline): 204 relevant instead of 219; on the Ministry's site 82 kept and 32 dropped instead of 111 and 3 (the dropped ones are the hubs, menus and news lists, whose `<article>` is empty, plus two photo pages that never name the card in their own text). Every page recommended in the first review is still kept.

## Tests

`tests/streamlit/test_crawl.py` covers the allowlist, URL normalisation, relevance scoring, robots.txt (with wildcards), pacing and retries, redirects, the manifest of a crawl over a fake site (search endpoint, sitemap, depth and page cap, duplicates), `rescore`, refresh (unchanged, changed with a diff, failed, skipped, reuse of a crawl) and ingest (with a fake runner, and for real on a temporary copy of `data/` when the kit `.venv` exists): no overwrite of a saved page without `--force`, no second source for a URL already saved, the current policy applied, only picked ids, status `review` and `approve`; relevance on the cleaned text and the title without the site's name, and the topic host as a tie-breaker only. No test opens a network connection.

```sh
python -m pytest tests/streamlit/test_crawl.py -q
```

## Searching the saved pages (`onevisit/search.py`)

The checklist tools answer "what do I bring". Every other question about the ID card ("can my son travel with the receipt?", "¿cuánto cuesta?", "我的身份证丢了怎么办") is answered from the saved pages through a passage search. It uses only the Python standard library, so the deployed app needs nothing beyond `requirements.txt`, and it never goes to the network.

```python
from onevisit import search

search.search("I lost my ID card", service_id="carta-identita", k=5, lang="en")
# [{"source_id": "cie-ministero-faq", "passage_id": "cie-ministero-faq#13",
#   "title": "CIE: assistenza e domande frequenti", "publisher": "Ministero dell'Interno",
#   "url": "https://www.cartaidentita.interno.gov.it/assistenza/", "saved_at": "2026-10-04",
#   "updated_at": "", "kind": "page",   # the page's own date when it has one; news, circular, faq...
#   "lang": "it", "heading": "In evidenza > Come faccio a bloccare la mia Carta in caso di furto o smarrimento?",
#   "text": "Come faccio a bloccare ... (verbatim)", "score": 3.9,
#   "confidence": 0.93, "confident": true}, ...]
search.best_answer("Posso pagare con Satispay?", service_id="carta-identita")
# {"confident": true | false, "confidence": 0.71,
#  "reason": "ok" | "no_match" | "weak_match" | "off_topic" | "other_document" | "unknown_words",
#  "passages": [...]}
search.passages_for("cie-faq-00305")  # every passage of one page, in order
search.index_stats()  # pages, passages, terms, build time, hash mismatches
search.TOOL, search.run_tool(args)  # Claude tool definition and its JSON result
```

```sh
python -m onevisit.search "quanto costa la carta d'identità" --service carta-identita
python -m onevisit.search "posso pagare con satispay" --service carta-identita --best
python -m onevisit.search --stats
python -m onevisit.search --eval data/eval/qa/search-retrieval.json
```

**Passages.** Each page body is cut by Markdown heading, then into blocks (paragraphs, lists) packed into passages of about 40 to 220 words (a short remainder joins the previous passage, up to 286 words; a very long paragraph is split at line ends, then sentence ends). A passage's `text` is always `body[start:end]` of the saved page: nothing is reworded, joined or translated. Breadcrumbs, in-page menus, share buttons, image-only blocks, "Estensione - Dimensione" and link-only lists are left out. A question heading (the one heading of every support-centre article, and any heading ending in "?", such as the 53 questions of the Ministry's FAQ page) stays with its whole answer in one passage, up to 600 words, and the question is indexed three times. The City's service pages put a tab's label one level *above* the section that holds it ("### Carta d'identità provvisoria", its text, then "## Documenti da presentare" for the provisional card's own list: two photos, EUR 5.42). Read literally, the label would close the section and own every section after it, so the provisional list was headed like the CIE's own list and "Costo e durata" (EUR 22.20) sat under "Documenti in caso di rilascio a domicilio". A heading is now read as a label of the section before it when it comes right after a heading one level deeper and that heading has no text of its own, or when the same title appears more than once at its level (tab labels repeat, section titles don't); the next heading closes it. The label's section counts as the passage's own heading too (its concepts are the passage's topic), so the provisional list is a section about the provisional document.

**Ranking.** BM25 (k1 1.2, b 0.75) over words without accents, in lower case, without Italian, English, Spanish and French stopwords (and without "Milano": every page is about Milan, so the city's name says nothing about the topic), lightly stemmed so that cognates meet (`documenti`, `documentos`, `documents` → `document`; `-zione`, `-ción` → `-tion`; `visibile`, `visible` → `visibil`). Bengali and other Indic words keep their vowel signs (Python's `\w` treats those as marks, which used to cut "আইডি" in pieces). Then:

- **Concepts across languages.** `onevisit/search_synonyms.json` groups the ID-card vocabulary in Italian, English, Spanish, French, Arabic, Chinese, Ukrainian (with some Russian) and Bengali into 112 concepts (lost, stolen, police report, minor, adult, parent, single parent, guardian, delegate, cost, photo, background, colour, expression, glasses, PIN/PUK, expiry, duration, validity, travel, booking, reschedule, cancel, waiting, weekday, delivery, pick-up, missed delivery, home service, organ donation, residence permit, passport, driving licence, SPID, tax code, foreigner, student, damaged, chip, residence, AIRE, consulate, office, hours, walk-in, disability, priority, baby care, civil status, address, signature, no other document...). A concept is one search term shared by the pages and the questions, so "I lost my ID card", "perdí mi DNI", "فقدت بطاقة الهوية", "загубила ID-картку" and "ho perso la carta d'identità" search for the same two concepts. Arabic, Cyrillic and Bengali phrases match at the start of a word, after an Arabic prefix (و ف ب ك ل, the article ال, and their combinations: "للأجانب" finds "أجانب"), so a stem finds its endings ("дитин" finds дитина, дитини, дитиною) but not the middle of another word; a phrase of four letters or fewer must be the whole word, up to an Arabic pronoun ending or three letters of Cyrillic or Bengali ending ("وجه", face, is not in "أتوجه", I go; "عملي", my work, not in "عملية", process; "форм" not in "інформація"). Chinese phrases match as substrings. A concept's `not` phrases stop a match where the words mean something else: "ho subito un furto" is not urgent, "I arrived in Milan" is not a delivery, "in busta separata" is not a civil status, a child who may "stay at home" is not asking for the home service. Patterns read ages only as ages ("I'm 72", "my dad is 81", "ha 10 anni", "un bambino di 12 anni", "12岁"; never "vale 10 anni", "meno di 6 mesi", "entro 90 giorni" or "più di 70 euro"), durations ("how many years is it valid", "quanto dura"), "do I need an appointment" (walk-in) and "serve X?" / "do I need my X" (documents). Domiciled people are one concept whatever the grammatical gender (domiciliato, domiciliata). Numbers weigh half a word, and the numbers of identifiers ("circolare n.81/2023", "prot. N.0017063") are not read: "my dad is 81" no longer finds circular 81. Concepts that mean different things are kept apart: how long a card lasts is not when it expired, a provisional paper document is not an urgent case, cancelling is not rescheduling. The file is data: a person reviews it, and it holds no facts.
- **Query words.** Chat shorthand is read as the word (`nn` → non, `x` → per, `u` → you; the `abbreviations` table of the synonym file). A query word that no page and no concept knows is read as the known word one typing error away, with the same first letter and at least 6 letters (`expierd` → expired, `documneti` → documenti, `smarita` → smarrita), using a symmetric-delete index of the pages' words built with the index. A real word the pages don't use must not become another real word: a verb or participle form (-are, -ere, -ire, -ato, -uto, -ito, -ing, -ed) is never read with one letter changed ("votare" is not "volare", "avuto" is not "aiuto"), a correction that turns the word into a concept word needs a letter added, dropped or swapped and 7 letters, and any other correction needs a word the pages use at least 3 times.
- **Two questions in one message** ("Qual è il prezzo della CIE e quali documenti devo presentare?") are searched one at a time, split after "?" or at "and" + a question word, and the results alternate; each says which part it answers (`part`). A part with nothing of its own ("e la carta d'identità?") stays with the one before it. One passage that names a price and a list of documents is rarely the answer to either (it was the provisional card's list). The tool description also asks Claude to make one search per question.
- **English words don't pull to English pages.** A word found only in the 7 English pages (YesMilano) gets its IDF among them and counts half in a query, and the words inside a concept phrase count 0.3: the concept carries the meaning, the word only breaks ties. A concept's IDF is always over all passages (a concept is the same term in every language).
- **Fit to the question.** With two or more concepts asked, a passage that has only some of them loses up to 40%; a section whose own heading is about something not asked loses 15% per topic, 30% when it is another object (`"distinct"`: PIN codes, digital credentials, organ donation, residence permit, passport, tax code, the CIE receipt...), at most 40%. "I lost my ID card" then finds the loss and theft passages before "I lost my PIN". Concepts that headings name together (`"related"`: "Furto e smarrimento") don't count as another topic, and question words (`"weight": 0.3`: "how many", "what is") weigh less and are never a topic, so "Quante sono le sedi?" doesn't land on "Quante fotografie servono?". The section headings count twice (the FAQ question three times).
- **Source priors.** Support-centre FAQ ×1.1, PDFs ×0.95, news ×0.85, YesMilano guides ×0.9, the Ministry's circulars (`circ-*`, kind `circular`: written for prefectures and registry staff) ×0.8: the City's and the Ministry's own pages win ties. Each page's own date is read ("Ultimo aggiornamento: 02/10/2026", a news item's "Data: 19 gennaio 2026", "(modificato il 18/02/2026)", a circular's protocol date or the date in its address) and returned as `updated_at`; news older than 180 days and circulars older than 5 years, counted back from the newest page's save date, lose ×0.8 and ×0.75 more (the January news on paper cards "cesseranno la loro validità", superseded by DL 108/2026; the 2017 circular on toner and workstations). For what the City sets itself (cost, offices, hours, booking) its own pages get ×1.15, so Milan's EUR 22.20 comes before the Ministry's national EUR 16.79. `lang` (the reader's language) multiplies passages in that language by 1.1 and never filters.
- **At most 2 passages per page** in a result (`per_source`), so one long circular cannot fill the top five, and a page that repeats a section (the Ministry FAQ's "In evidenza") gives it once.

**Service filter.** `service_id` keeps the pages the service's catalog cites (`data/services/<id>.json`, read at query time, so the catalog can change), the pages whose front matter `servizio` names it, and the id patterns in `SERVICE_PAGES` (for the ID card: `cie`, `cie-*`, `circ-dait-*`, `prenotazione`, `sedi-anagrafiche`, the YesMilano ID-card guides, `news-cie-*`, `news-anagrafe-*`, the detainees' news, the Polizia di Stato pages, `oggetti-smarriti`). An unknown service gives an empty result.

**Freshness.** The index is cached on the list of `data/pages/*.md` with their sizes and modification times, `data/sources.csv` and the synonym file. Only rows in status `ok` are indexed: a page added by `crawl.py ingest` (status `review`) becomes searchable at the next query after `crawl.py approve`; no restart.

**Confidence.** Every result has `confidence`, the share of the question it holds: its score, counted at most 1.6 times the IDF of the query terms it holds (each once, so a section that repeats "foto" in its heading and text holds one word of "posso avere la barba nella foto?", not all of it), against what a passage holding every query word once would score. A Latin-script word that no page has counts as the rarest word (no passage can hold it), and so does, at half weight, each Arabic, Chinese, Cyrillic or Bengali word that no concept reads (function words, Milan and Italy apart): those words can only reach the pages through the concept map, and when it misses them the passages hold less of the question than the concepts suggest. `confident` needs confidence 0.40, a score of at least 1.5 (the lowest top score of an answerable tuning question is 1.7) and within half of the best result's, and a query that passes four gates:

- **off topic**: small talk and questions about no procedure ("Che tempo fa domani?", "What's the weather tomorrow?", "Qual è la capitale della Francia?", a restaurant near the Duomo: the `small_talk` concept, `"off_topic": true`, query words only) get no confident answer unless the query also names the service's subject (the ID card). Before this gate "Che tempo fa domani?" was a confident match on the travel page ("domani" reads as urgent, "tempo" is a page word). "qual" and the forms of "stare" (sto, stai, sta, stanno) are stopwords, so "Come stai?" matches nothing. Words that also open real questions are not small talk: "come va fatta la foto?", "how are you supposed to pay?", "se piove", "ricetta medica", "calcio" (only "come va?" or "how are you?" as the whole message is);
- **other document**: a question about another document (renewing a passport or a driving licence, getting SPID or a health card: `"other_document"` in the synonym file) and not the ID card is out of the service. A question that names one as something to bring or show is about this service's documents and passes: "Devo portare il permesso di soggiorno all'appuntamento?", "Serve la tessera sanitaria?", "Should I bring my passport to the appointment?" (the `documents` or `mandatory` concept is asked). SPID as the means of booking or of going online (`"means_for"`) is about the card: "Can my friend book for me with his SPID?". Asking to obtain or renew another document is about that document even next to the card (`obtain_other`, `"asks_other_document"`): "Posso fare il passaporto all'anagrafe insieme alla carta d'identità?";
- **topic no page answers**: parking near an office, bringing a pet, temporary protection (`"unanswered_topic"`) give `unknown_words`, whatever generic word ("sede", "anagrafe") the question shares with the pages;
- **nothing asked**: a question whose only concept is the card itself, in more than half of the passages ("x x x x x carta"), and no other known word, is a weak match;
- **unknown words**: a question whose Latin-script words are mostly unknown to every page is not matched.

`best_answer()` gives the reason: `ok`, `no_match`, `weak_match`, `off_topic`, `other_document`, `unknown_words`.

**A passage must hold what is asked.** Since the review of the Q&A on 5 October a passage is confident only when, besides the score, (a) it holds the question's concepts, up to one in three missing (a question with two concepts needs both: "is the card free for people over 70?" is not answered by the over-70s' validity), leaving out the card itself, question words, how the question is asked (`"frame"`: what to bring, where, when, must I, can I apply) and the person's situation when the passage holds something else asked (`"situation"`: lost, stolen, expired, a minor, a student, a foreign resident: the fee answers "quanto costa se l'ho persa?"); and (b) its own heading is not about another thing the question doesn't ask (`"distinct"`: a FAQ on the PIN codes, the digital identity, the receipt or the provisional card answers another question, even when it scores first). `search.held_concepts()` and `search.heading_mismatch()` say why. The replay uses the same rules to choose its cards (the closest passages leave out (b) too), shows the City's card first and drops a Ministry or YesMilano card that says the same (no EUR 16.79 next to Milan's EUR 22.20, no "ten working days" next to the City's six), and quotes a passage of up to 700 characters whole.

What it can't do: tell a page on the same topic from a page that answers. "How do I cancel my appointment?" finds the booking FAQ, "Can I travel to London?" finds the travel page, "Can I pay with Satispay?" finds the payment FAQ: every word is known and the pages are on topic, so the score is high. In the question bank 12 of the 20 unanswerable questions now come out not confident (the 6 out of scope ones by the gate, 3 topics no page answers, 3 weak matches); the other 8 are confident. The rules above cost answerable confidence too: tuning 0.961 → 0.936, holdout 0.875 → 0.812 (hit@k unchanged: they decide what is called an answer, not the order). So `confident` is advice for Claude, not a verdict: Claude reads the passages and says it doesn't know when they don't answer.

The table below was measured before those rules, on the 0.40 threshold alone:

| threshold | tuning answerable confident | holdout answerable confident | unanswerable not confident | off-topic queries not confident |
|---|---|---|---|---|
| 0.25 | 164/165 | 42/43 | 6/15 | 0/13 |
| 0.30 | 162/165 | 42/43 | 6/15 | 3/13 |
| 0.35 | 162/165 | 38/43 | 7/15 | 3/13 |
| **0.40** (default) | 162/165 | 37/43 | 7/15 | 6/13 |
| 0.45 | 157/165 | 36/43 | 8/15 | 6/13 |

The off-topic queries are 13 made-up questions outside the ID card (tram tickets, parking, a bank account, a SIM card...). The thresholds were chosen on the tuning questions and on 40 adversarial questions written in the review of 5 October 2026 (there the cap on held terms, the score floor and the script gaps took the unanswerable ones from 4 of 5 confident to 3 of 5); the holdout shows 0.40 flags 6 of 43 new answerable questions. Lower it to 0.30 if a missed answer costs more than a weak one.

**Measured on the question bank** (`data/eval/qa/cie-questions.yaml`, `python data/eval/qa/run_retrieval.py --holdout`). A hit is an expected page whose passage contains or overlaps the quoted evidence, not just the right page.

| set | n | hit@1 | hit@3 | hit@5 | right page in top 3 |
|---|---|---|---|---|---|
| tuning, Italian and English, before this work | 131 | 0.54 | 0.73 | 0.81 | 0.78 |
| tuning, Italian and English | 131 | 0.73 | 0.90 | 0.94 | 0.95 |
| tuning, other languages, before this work | 27 | 0.41 | 0.59 | 0.70 | 0.70 |
| tuning, other languages | 27 | 0.82 | 0.93 | 0.96 | 0.96 |
| holdout, Italian and English, before this work | 36 | 0.47 | 0.75 | 0.81 | 0.81 |
| holdout, Italian and English, first measurement | 36 | 0.58 | 0.83 | 0.89 | 0.89 |
| holdout, other languages, first measurement | 7 | 0.71 | 0.71 | 1.00 | 0.71 |
| holdout, Italian and English, final | 36 | 0.61 | 0.83 | 0.89 | 0.92 |
| holdout, other languages, final | 7 | 1.00 | 1.00 | 1.00 | 1.00 |
| tuning, Italian and English, after the review fixes (5 October) | 135 | 0.70 | 0.90 | 0.95 | 0.96 |
| tuning, other languages, after the review fixes | 30 | 0.80 | 0.93 | 0.97 | 0.97 |
| holdout, Italian and English, after the review fixes | 36 | 0.56 | 0.83 | 0.86 | 0.92 |
| holdout, other languages, after the review fixes | 7 | 1.00 | 1.00 | 1.00 | 1.00 |
| tuning, Italian and English, after the Q&A review (5 October, evening) | 156 | 0.68 | 0.90 | 0.93 | 0.94 |
| tuning, other languages, after the Q&A review | 31 | 0.74 | 0.94 | 0.94 | 0.97 |
| holdout, Italian and English, after the Q&A review | 40 | 0.55 | 0.83 | 0.88 | 0.88 |
| holdout, other languages, after the Q&A review | 8 | 0.88 | 1.00 | 1.00 | 1.00 |

The last four rows count the questions added since (the review's 8 Italian and English questions in tuning; the holdout is the same 48 questions, 40 and 8), so their tuning sets are not those of the rows above. The tuning rows before them are the bank's original 158 tuning questions; with the 4 added afterwards (one still fails) Italian and English are at 0.71 / 0.89 / 0.93 (n 133) and the other languages at 0.83 / 0.93 / 0.97 (n 29). The tuning gain (+17 points at hit@3) is twice the holdout gain (+8): part of the vocabulary fits the questions it was written against. On new Italian and English questions, expect the right passage in the top 3 about 83% of the time and the right page about 92%. "Final" is after one more round that fixed general causes seen in the failing holdout questions (question words as topics, durations asked in years, Chinese words for posting and collecting, family facilities); the "first measurement" rows are the clean ones. For other languages the replay demo searches in the user's words; live Claude can also search with an Italian rewording of the question, which the Italian figures describe.

The review of 5 October found problems the bank's hit rates didn't show (the bank checks that the right passage is in the top 3, not that a wrong one isn't): the provisional card's list (two photos, EUR 5.42) answering CIE questions, common words read as another topic ("cara", "usa", "status", "found", "arrived", "né"), ages read in durations and amounts, Arabic and Ukrainian stems found inside other words, real words corrected into others ("votare" → "volare"), the 2017 staff circular and old news in the top 3, an Arabic question with one known concept marked fully confident, and "Devo portare il permesso di soggiorno?" refused as another document. On its 40 adversarial questions the fixes took the right passage in the top 3 from 17 to 29 of 35 answerable, the misleading passages in the top 3 from 21 to 2, the confident-but-wrong top 3 from 14 to 6, and the confident unanswerable ones from 4 of 5 to 3 of 5. On the bank, tuning hit@3 went from 0.90 to 0.91 (three questions added for the general causes, in `cie-questions.yaml`: Spanish "saco cita", bringing a residence permit, "quanto si spende"), holdout hit@3 stayed at 0.86 and hit@1 went from 0.67 to 0.63: two holdout answers ranked first were a circular (now ranked lower) and the YesMilano guide for "Do I need my codice fiscale for the appointment?" (now the City's documents FAQs, which list it, but the bank expects only the guide). Kept as measured, not tuned.

Index build about 0.7 s (the spelling index adds about 0.2 s), query about 5 ms. The older regression set `data/eval/qa/search-retrieval.json` (49 questions in six languages): an expected page first for 49 of 49.

## The Claude tool and the citations

`search.TOOL` is a tool definition in the same shape as `onevisit/tools.py` (`search_official_pages`, input `query`, optional `service_id` and `k`), and `search.run_tool(args, lang)` returns its JSON: `confident`, `reason` and the passages (never the query back: it is the person's text; a query is cut at 1,000 characters and at most 4 of its questions are searched one by one; an unknown `service_id` such as "cie" falls back to the conversation's service, with a `service_note` listing the valid ids), plus a note when nothing matched (say you don't know, link the official page) or the match is weak (read the passages; if none answers, say you don't know; never fill the gap from memory). The agent adds both to its tool list with one line each. The tool description tells Claude to answer only from the passages, cite the `source_id`, say it doesn't know (with the official page) when no passage answers, prefer the City's current page over older news and over circulars for registry staff when two passages disagree (saying what the other says), and make one search per question when the user asks two things. The same rules as the rest of OneVisit apply to the answer: no fact from model memory, no "valid"/"in regola" judgement on a person's documents (the desk officer decides), no personal data in the query.

Each result carries what a citation needs: `source_id` (a row of `sources.csv`), `url` (the page that was saved), `saved_at` (the date it was saved and checked; the same for every page saved on 4 October), `updated_at` (the page's own date, so Claude can tell a January news item from the City's page updated on 2 October), `kind` (page, faq, news, circular, pdf, form), `publisher`, the `heading` path to find the passage on the page, and the verbatim `text`. Because the text is a slice of the saved page, anyone can check a quote with `grep` in `data/pages/<source_id>.md`.

## Refresh

1. `crawl.py refresh --topic carta-identita --out DIR` tells which saved pages changed on the official site.
2. A person reads the diff and re-ingests the page (`onevisit ingest`), which writes the new `content_hash`.
3. `python data/tools/validate.py` re-checks every catalog quote against the new text; quotes that no longer match must be fixed or the requirement goes back to `todo`.
4. The passage index needs nothing: it rebuilds itself on the next query. `python -m onevisit.search --eval data/eval/qa/search-retrieval.json` shows whether answers moved, and `--stats` whether a page was edited by hand after ingest (`hash_mismatches`).

New pages found by `discover` follow the same path: a person picks them, `crawl.py ingest` saves them in status `review`, a person reads them and `crawl.py approve` makes them searchable.

## Limits

- **The search finds; it doesn't understand.** It is lexical plus a hand-made concept map: a question in words the map doesn't know, in a language other than the eight covered, or about a topic phrased very differently from the pages can miss the right passage (the same words with another meaning too: "stampata a colori" finds the colour photo you bring, not the black-and-white photo printed on the card). Its `confident` flag can't tell a related page from an answer. Claude reads the top passages and must say "I don't know" when they don't answer; a miss then costs a link to the official page, not a wrong fact. Add the missed question to the retrieval set and the missing words to the synonym file.
- **Only what was saved.** Pages behind a login or a JavaScript challenge (the booking flows, the support centre's own search) are not in the index; booking screens are described only by the pages that talk about them.
- **Dated.** A passage is as current as its `saved_at`. Official pages change (the paper ID card expiry of 3 August 2026, the 70+ rule of 30 July 2026): run `refresh` before a demo or a release and show `saved_at` with every answer.
- **Not catalog facts.** A passage can support an answer to a question; it does not become a checklist requirement until a person adds it to `data/services/*.json` with a quote that `validate.py` accepts.
- **Sources disagree sometimes** (YesMilano's "ten working days" for delivery against the Ministry's and the City's 6 working days). The search ranks the City's and the Ministry's pages first and the replay leaves out a guide that says the same as a City card; Claude should cite the official one and mention the date.
- **The replay is lexical; Claude is not measured here.** Without a key the app answers with the keyword search and the rules above (`data/eval/qa/RESULTS.md`: about two answerable questions in three get a card holding the evidence, 12 of 20 unanswerable ones the honest line). Claude's live answers, which read the passages, are measured only with a key: `python -m onevisit.evaluate --qa`.

Tests: `tests/streamlit/test_search.py` (passages are verbatim slices of every saved page, sizes, FAQ question kept with its answer and boosted, menus left out, English/Spanish/French/Arabic/Chinese questions finding the Italian passage, service filter, a new page found without restart, empty and garbage queries, stable order and ties, the `lang` boost, citation fields, hand-edited pages reported, the tool JSON, build and query time, the retrieval set; minimum hit rates on the question bank's tuning set, out-of-scope questions never confident, typo and shorthand reading, Bengali and Ukrainian words, duration against expiry, question words, related headings, repeated sections, `best_answer` reasons, the weak-match note; and the review fixes: tab labels kept in their section on the City page and in a made-up one, ordinary sections untouched, the provisional list out of plain CIE questions, 18 common words that must not bring another topic, ages only as ages, domiciled in one concept, 11 Arabic, Ukrainian and Bengali words not found inside others, real words not corrected, bringing another document passing the gate, "carta" alone never confident, the score floor, unread script words lowering confidence, `updated_at` and `kind`, old news and circulars ranked lower, identifier numbers not read, two questions searched one at a time, the City's page first for its fee, pages in `review` not searchable). No network, no key.

```sh
python -m pytest tests/streamlit/test_search.py -q
```
