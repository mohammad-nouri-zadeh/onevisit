# OneVisit app (Streamlit)

The product the jury sees, deployed at https://onevisit.streamlit.app from `main`. One app, two tabs: **Per i cittadini** (the assistant) and **Per il Comune** (the City panel). Italian by default; language menu with Italiano, English, العربية (right to left), 中文, Español.

## Run it

From the repository root, with Python 3.11 or newer (tested with Streamlit 1.65; `requirements.txt` asks for 1.50 or newer):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: add ANTHROPIC_API_KEY for the live version
streamlit run app/streamlit_app.py
```

Then open http://localhost:8501 (the demo replay if there is no key) or http://localhost:8501/?demo=1 (the replay even with a key). `.streamlit/config.toml` sets the theme (Comune di Milano red, Titillium Web) and `enableStaticServing`, which serves the fonts in `app/static/`. Run it from the repository root, otherwise Streamlit doesn't find that config.

On Streamlit Community Cloud the key goes in the app's Secrets as `ANTHROPIC_API_KEY` (template: `.streamlit/secrets.toml.example`); the deployed app follows `main` and is **live by default** once the key is there. `ONEVISIT_MAX_CALLS_PER_SESSION` (default 40) and `ONEVISIT_MAX_CALLS_PER_DAY` (default 1500, for the whole server) cap the Claude calls; when a cap is hit, or a call fails (no credit, no network), that session carries on as the demo replay with a notice instead of an error.

## Live, and the replay for viewers without a key: same data

The product is Claude at runtime. The replay exists so that anyone can try the page without a key; it never claims to be Claude.

| | Live (with a key) | Demo replay (no key, or `?demo=1`) |
|---|---|---|
| Claude's sentences | written by Claude at runtime (`onevisit/agent.py`), signed "OneVisit · Claude" with the badge "Dal vivo: risponde Claude" | recorded templates (`data/demo/script.json`), signed **"OneVisit · replica"** ("OneVisit · replay" in English), with "Gli strumenti hanno letto N fonti" and "Cosa hanno controllato gli strumenti" (never "Claude"); the header chip says "Replica dimostrativa · dati e fonti reali" and one muted line under the title explains it, with a link to the live version when the server has a key |
| A typed message | understood by Claude, in any language | read by keyword rules (`demo.understand`), labelled on the reply; anything unclear is asked with buttons. Replies in Italian, English, Arabic, Spanish or Chinese; a message in another language it recognises (`agent.guess_lang`: French, Portuguese, Tagalog, Ukrainian, Russian, Bengali, Hindi, Urdu, Persian…) gets an English reply that names that language and says the live version answers in it |
| Tools, checklist, form guide, offices, sources | live, from `onevisit/tools.py` over `data/` | the same tools, called by `onevisit/demo.py` |
| Checklist in Arabic, Spanish, Chinese | Claude's cached translations (`data/i18n/`); missing texts translated at runtime by Claude Haiku 4.5 | the cached translations |
| Next 3 actions | Claude orders them (`onevisit/plan.py`), code drops any action outside the checklist | the first items to prepare, in the order of the City's pages, labelled |
| Automatic check | every answer | every answer (the recorded text passes the same check) |
| Report classification | Claude, after code removed personal details | the two example reports, with Claude's recorded classification (`data/demo/classifications.json`) |
| Page-correction drafts | Claude | recorded (`data/demo/drafts.json`) |

The key is read from `.env` or the Streamlit Secrets; the placeholder `sk-ant-...` from `.env.example` doesn't count. A key pasted in the page stays in that browser session only.

## Where Claude works, and how it is checked

1. **Conversation** (`onevisit/agent.py`): Claude picks the service, takes the answers the first message already gives (a first-person "I lost my card" is an adult; "I'm leaving next month" is urgent), asks only the deciding questions that `get_checklist` lists in `still_to_ask`, calls the tools and explains the result in the citizen's language, citing `[source_id]`s. With an online application it calls `get_form_guide` and says where each file goes.
2. **Automatic check** (`onevisit/validator.py`): before the citizen sees a reply, it blocks (a) source ids that don't exist or that no tool returned in this conversation, (b) eligibility or validity claims in it/en/es/fr/pt/ar/zh ("idoneo", "in regola", "garantito", "eligible", "you're all set", "cumples", "مؤهل", "符合条件"…), outside a quoted official sentence (a one-word «idonea» or «è valido» is the reply's own word), (c) replies that state facts without a citation (after the tools returned facts, or whenever they hold digits, amounts or links), (d) quotes in « », “ ”, " ", 「」… that are not word for word in a passage or checklist quote a tool returned (on word boundaries, a question keeps its "?", an ellipsis only inside one paragraph, never dropping a "non"), (e) numbers and links no tool returned (nor the person's own message), (f) an answer from the pages with neither a verbatim quote nor "the pages don't say". A blocked reply is regenerated once with the reasons; if it is blocked again the citizen gets a safe fallback with the official page. In each reply the sources are numbered notes, listed by name and date under it, with the result of the check.
   **Questions** (job B of the same conversation): Claude searches the saved official pages (`search_official_pages`, then `read_source` for a whole page), quotes the sentence that decides the answer between « » with its `[source_id]`, then says what it means in the person's language; when no passage answers it says the saved pages don't say it and links the official page. The reply shows each quote as a card: the page's own words, the question or section it answers, publisher, title, the page's date and link, "Leggi tutto il passaggio", and "word for word from the saved page" only for quotes the validator found (a shortened one says so; a link inside a quote stays a link only if the page has it).
3. **Next 3 actions** (`onevisit/plan.py`): once the case is clear, Claude orders the next three actions from the verified items, with structured output. Code keeps an action only if its item ids are in the checklist and its words promise nothing, and shows how many it dropped.
4. **Translation** (`onevisit/translate.py`): texts missing from `data/i18n/requirements.<lang>.json` (or whose Italian changed) are translated by Claude Haiku 4.5 at runtime, structured output keyed by text, promises dropped. The app labels translated items "Traduzione di Claude · fa fede il testo italiano" and keeps the Italian text and the quote behind the (?).
5. **After the appointment** (`onevisit/outcomes.py`): code removes emails, tax codes, IBANs, dates, phone and document numbers (`scrub`) and says what it removed; Claude classifies the report and writes an anonymous sentence. For groups above the threshold it drafts the page correction that a City officer approves. Both tabs have the report form.

## What the citizen gets

- How the procedure is submitted, from the data: residence from abroad is an **online application** (the City's form `MOD_DDR_ESTERO`, cited); a change of residence from another comune or within Milan is a **declaration on the national ANPR website** with SPID or CIE (`online_form_kind: "anpr"` in the data, so the texts and the button name ANPR, not the City's form); the ID card is a desk appointment (the CIE booking page, cited). Every link comes from `kb.service_links()`, which names the saved source that contains it (the service's own sources first).
- **Which residence procedure**: a typed message that says "mi sono trasferito da Torino", "da un altro comune", "cambio di indirizzo" or "sono italiano" goes to the change of residence; one that names a permit, a visa, a non-EU country or "from abroad" goes to residence from abroad; one that says neither (or an EU citizen) is asked which of the two (`demo.understand`; live, the system prompt gives Claude the same rule).
- **One rental contract, not two**: renting is split into "contratto già registrato" (YesMilano: scan with the registration details) and "non ancora registrato, o non lo so" (the City page: copy of the contract). "I rent a room" alone asks the narrow question "Il tuo contratto d'affitto è già registrato all'Agenzia delle Entrate?" (`narrow` in the deciding question's data).
- **A short page once the case is clear**: a summary card leads (files to upload or to have at hand, verified and open counts, the online form or booking button), the earlier turns fold into "Conversazione · N messaggi" (each keeps its trace) and only the last reply stays open; "Come funziona" and "Dopo" are folded, and so are the form guide's sections. The first screen starts with the example cases; the three-step explainer is folded.
- The path across offices (Questura, Sportello Unico, Agenzia delle Entrate, Comune) in order, each step with its source; the tax-code step lists its three routes, each with its source. From a booking link the booking step shows as done.
- **One dossier download**, at the top of the checklist, then **the files to upload** (online) or **the things to bring** (desk) (`kb.to_upload`). The page has no other copy of the download or of the online-form button.
- The checklist of verified requirements, grouped by what to do with them (**Da preparare**, **Come funziona**, **Se è urgente**, **Dopo**; the `category` of each requirement in `data/services`), then by official source, with the verbatim quote behind the (?) and a tick box for each item. For someone in a hurry, **Se è urgente** comes first and open.
- **Come compilare la domanda online** (`kb.form_guide`): the sections of the City's Modulistica page with this case's files, the City's wording for the housing case, what to write in the form, how to send the files, and a tick per file ready to upload.
- Items without a verified source, with what is unknown ("Da verificare: …") and the official page: never guessed.
- The registry office from open dataset ds549, with City data issues shown, not hidden.
- **Dossier per lo sportello / Dossier per la domanda online** (`onevisit/dossier.py`): a PDF in Italian for the officer with the citizen's language under each item (English, or Claude's translation in Arabic, Spanish or Chinese, labelled), only verified requirements grouped like the checklist, each with source, URL and verification date, the case answers (no personal data), the office and the appointment date, and the final-check line. Fonts: Titillium Web (OFL), Noto Naskh Arabic and Noto Sans SC (OFL; SC subset to GB2312) with Arabic shaped right to left through `uharfbuzz`, DejaVu Sans as fallback, all in `app/assets/fonts/` with their licences.
- **Data e promemoria**: an optional date (it also goes into the dossier) and calendar reminders (.ics) kept on the device.

## Questions about the ID card

Under the example cases, chips ask the questions people ask most (in the page's language): *Quanto costa la carta d'identità?* · *Ho perso il PIN: cosa faccio?* · *Mio figlio di 2 anni deve venire all'appuntamento?* · *Posso fare la foto in Comune?* · *Cosa devo portare se sono extra UE?* · *Quanto ci mette ad arrivare la carta?* · *Posso fare la carta d'identità a domicilio?* · *La carta d'identità vale all'estero?* Any question can also be typed, in any language, at any time, also in the middle of a case: the case is kept and its pending question asked again.

Live, Claude answers (above). In the **replay** (no key, `?demo=1`) the answer is extractive, with no model (`demo.ask`): the keyword search (`onevisit/search.py`) picks the passages and the reply quotes them verbatim as cards, labelled "passages picked by keywords; live, Claude picks them". It shows a passage as the answer only when the search is confident (the passage holds what is asked and its heading is not about another thing), the City's card before a Ministry one or a YesMilano guide saying the same; otherwise it leads with "the saved official pages don't answer this with certainty" and the official link, then the closest passages. Other rules: a question inside a case-opening message or with an answer ("Residente a Milano, e quanto costa?") gets its reply too; a question about another procedure keeps the case and offers a "Nuova pratica" button (a new case typed instead says the earlier one was closed); "a Isola" names the office from the open data, "the nearest office" gets the official list of offices; the page follows the language the replay answers in. How often it answers well: `data/eval/qa/RESULTS.md`.

Try: *Can my friend book the appointment for me using his SPID?* (the booking FAQ: no SPID needed) · *my card was stolen yesterday, can i still travel to rome by train?* (another document is enough in Italy) · *Il chip non funziona più, devo pagare di nuovo 22 euro?* (remade at no cost) · *C'è un parcheggio vicino alla sede di via Larga?* (the honest line).

## Day one: the link in the City's booking confirmation email

```
https://onevisit.streamlit.app/?servizio=carta-identita&sede=ds549-11&data=2026-10-20&lang=it
```

opens the app with service, office and date already set and starts the conversation (`app/deeplink.py`). No personal data in the link; unknown values are dropped. The same link without office and date and with `canale=yesmilano` (YesMilano student guide) or `canale=benvenuto` (the City's welcome email) opens the service only:

```
https://onevisit.streamlit.app/?servizio=iscrizione-anagrafica-extra-ue&lang=en&canale=yesmilano
```

### Link parameters

| Parameter | Alias | Values | Effect |
|---|---|---|---|
| `servizio` | `service` | a service id from `data/services/`: `carta-identita`, `iscrizione-anagrafica-extra-ue`, `cambio-residenza` | Opens that service and starts the conversation. Without a known service the other parameters are ignored, except `lang` and `demo` |
| `sede` | `office` | an office id from `data/offices.json` (dataset ds549), e.g. `ds549-11` (Largo De Benedetti 1, the office near Isola) or `ds549-01` (via Larga 12) | Sets the office, with its address and entrance in Claude's greeting |
| `data` | `date` | `YYYY-MM-DD` | Sets the appointment date (dossier, calendar reminder); an invalid date is dropped |
| `lang` | | `it`, `en`, `ar`, `es`, `zh` | Interface and reply language (default `it`) |
| `canale` | `channel` | `prenotazione`, `benvenuto`, `yesmilano` | Where the link was placed, shown to the citizen ("From the link in the booking confirmation email"). Defaults to `prenotazione` when office or date are given |
| `demo` | | `1` | Forces the demo replay, even when a key is configured |

`deeplink.build(service_id, office_id, date, lang, channel=..., demo=...)` writes the same links; the City tab uses it for its mock-ups. Office ids: `python -c "from onevisit import kb; [print(o['id'], o['address']) for o in kb.find_offices(limit=100)]"`.

A student waiting for a first study permit answers "Something else" and sees that the official document list doesn't cover that case, with the City page to ask: the same gap the City panel shows as a report group, with Claude's draft correction. The City tab shows labelled mock-ups of the confirmation email and of the YesMilano page with the one added line, and the table "Per renderlo proattivo" (booking link, welcome emails and YesMilano path, ANPR via PDND, SPID/CIE, App IO), with owner and privacy note per step.

## Files

- `app/streamlit_app.py` the app; `app/i18n.py` interface text (it and en complete, ar/es/zh for the citizen side); `app/deeplink.py` the booking link; `app/static/fonts/` Titillium Web served by Streamlit (`enableStaticServing`).
- `onevisit/demo.py` + `data/demo/script.json`, `personas.json`, `drafts.json`, `classifications.json`, `simulated-outcomes.json`: the demo replay without a key. The recorded drafts and simulated reports describe the real gaps found in the sources (the 2013 document list still asking for "originale e fotocopia"; no rule for a first study permit). Six invented personas: a newcomer from Cairo registering residence (Arabic or the UI language), a person who lost their ID card, is travelling next month and lives in Isola, a student waiting for a first study permit (the sources don't cover her case), an ID card renewal in Spanish (Bovisa), a family from China with a registered rental contract (Chinese), an Italian moving from Turin (change of residence).
- `onevisit/plan.py` the next 3 actions; `onevisit/translate.py` translations; `data/i18n/requirements.{ar,es,zh}.json` Claude's translations of every requirement, step and form-guide text, each with the Italian it was made from; `onevisit/evaluate.py` the scenario runner (`python -m onevisit.evaluate`, needs a key).
- Look: Italian public administration style (Titillium Web, design-tokens-italia neutrals, Comune di Milano red `#a60d27` for primary actions and links), light and dark mode, larger text. No City coat of arms: this is a prototype, not a City service.

## Tests

```bash
pip install -r tests/requirements.txt   # pytest and pypdf, on top of requirements.txt
python -m pytest tests/streamlit -q     # 652 passed on 5 October 2026
python data/tools/validate.py           # every verified fact quotes its saved source: prints OK
```

The tests never call the Anthropic API: the live path runs against a fake client (`tests/streamlit/fakes.py`). The real model is exercised by `python -m onevisit.evaluate` (the 20 scenarios in `data/eval/` through the app's own agent; writes `docs/eval-results.md` with pass/fail, blocked, regenerated, fallback, API requests, seconds, tokens from `response.usage` and list-price cost; `--usd-to-eur` adds euros) and by the kit's `make eval`; both need a key. **Not run against the API in this build**: it was prepared without a key.

Validator (unknown and unread sources, uncited facts, eligibility words in several languages, clean answers; quotes, ellipses, other quotation marks, numbers and links no tool returned, answers from the pages without a quote: `test_validator_safety.py`), the Q&A (search, replay, quote cards, the review's regressions: `test_qa_demo.py`, `test_engine_qa.py`, `test_integration_qa.py`, `test_review_fixes.py`, `test_quote_cards.py`), agent regeneration and fallback with a fake client, demo personas end to end on live data, dossier contents, deep link parsing, alignment between the demo script and the live content (every question and option labelled in all five languages, persona answers that exist, categories, links backed by a saved source, drafts naming only real sources), the guidance fixes (tax-code routes, booked appointment, lost card and travelling, via Larga entrance, items the answers rule out), the form guide, translations (complete, current, no promises, stale ones fall back to English) and the dossier in Arabic, Spanish and Chinese, the next actions and their check, the scrub before classification, the evaluation runner, the demo's keyword reading, and the app itself with `streamlit.testing`, without key and without network: typed text, language switch, upload list and form guide, footnotes, the live path wired to a fake Claude (turn and next actions), the fallback to demo when Claude is down, the request cap, the report form in the City tab.

## Privacy and safety

- OneVisit never asks for a name, tax code, home address, document number or a photo of a document; the prompt tells Claude not to repeat them if the person writes them.
- The deep link carries only a service id, an office id from `ds549`, a date, a language and a channel; unknown values are dropped, never guessed.
- The dossier holds the case answers (e.g. "renting, alone") and verified requirements, no personal data. The calendar reminder stays on the device.
- After the appointment, code removes emails, tax codes, IBANs, dates, phone and document numbers before Claude reads the report, and says what it removed. Only the cause and an anonymous sentence are stored. A group of reports reaches an office only from 5 reports up.
- Live, the conversation goes to the Anthropic API to write the answer; the app keeps it only in memory for that session and writes no chat log. The key is read from `.env` (gitignored) or the Streamlit Secrets; a key pasted in the page stays in that browser session. Spending is capped per session and per day.
- In the kit, personal data lives only in a separate `pii` schema the panel's role cannot read (a test proves it), and aggregate views hide groups under k = 5 ([docs/privacy.md](../docs/privacy.md)).

## Deadlines already verified

What reminders (App IO, phase 2) would count from, each with its source:

| Deadline | Source |
|---|---|
| Apply for the residence permit within 8 working days of entry | `permesso-soggiorno` |
| CIE posted within 6 working days of the application | `cie-ministero` |
| Home check after the residence application: 45 days (YesMilano; ANPR: at most 45 days for a move from another comune) | `yesmilano-students`, `anpr-cambio-residenza` |
| Renew the declaration of habitual abode within 60 days of each permit renewal | `dimora-abituale` |
| Declare a change of city or address within 20 days | `cambio-residenza` |

## For City staff (tab "Per il Comune")

- Real City statistics (`ds1959`, `ds1702`) and an **expected impact** formula on both residence procedures: (19,755 registrations from abroad × share who submit again + 27,184 from other Italian comuni × share who declare again) × share who use OneVisit × share of second attempts avoided, all 2024 `ds1959` figures, four assumptions staff can move (starting at 20%, 10%, 30%, 50%: about 1,000 a year), labelled *STIMA, non un risultato*. ID cards are left out because no saved source gives their yearly volume.
- **How it switches on**: labelled mock-ups of the booking-confirmation email and of the YesMilano guide with the one added line; their links open the app.
- **What would make it proactive**: data and permissions, owner, privacy rule and phase for each step (ANPR via PDND, SPID/CIE, App IO).
- **Reports after appointments**, grouped by cause, threshold 5; a report can be tried right there. Claude drafts the correction, a City officer approves it. The pre-loaded reports are simulated and labelled.
- **Problems in the City's own data** found while cleaning `ds549`.

## Screenshots

All in the demo replay with invented cases (`docs/screenshots/`):

| | |
|---|---|
| Phone, first screen · Cairo case in Arabic · files to upload · what the tools checked · move from Turin · City tab | [home](../docs/screenshots/streamlit-home-390.png) · [Arabic, done](../docs/screenshots/streamlit-phone-arabic-done-390.png) · [files](../docs/screenshots/streamlit-phone-files-390.png) · [trace](../docs/screenshots/streamlit-phone-trace-390.png) · [Turin](../docs/screenshots/streamlit-phone-torino-390.png) · [City](../docs/screenshots/streamlit-phone-city-390.png) |
| Full pages | [Cairo, Italian, desktop](../docs/screenshots/streamlit-cairo-it-1280.png) · [Cairo, Arabic, phone](../docs/screenshots/streamlit-cairo-ar-390.png) · [Turin, phone](../docs/screenshots/streamlit-torino-it-390.png) · [from the booking email](../docs/screenshots/streamlit-deeplink-en-1280.png) · [City tab with the draft](../docs/screenshots/streamlit-city-draft-1280.png) · [lost ID card, phone](../docs/screenshots/streamlit-cie-en-390.png) · [typed in Spanish](../docs/screenshots/streamlit-typed-es-1280.png) · [YesMilano link](../docs/screenshots/streamlit-yesmilano-en-390.png) · [dark mode](../docs/screenshots/streamlit-dark-en-1280.png) |
| ID card questions (replay, quotes from saved pages) | [landing with question chips](../docs/screenshots/streamlit-qa-landing-en-1280.png) · [family booking, Italian](../docs/screenshots/streamlit-qa-family-it-1280.png) · [child at the desk, Chinese](../docs/screenshots/streamlit-qa-chip-zh-1280.png) · [photo, Spanish, dark](../docs/screenshots/streamlit-qa-photo-es-dark-1280.png) · [travel, Arabic, phone](../docs/screenshots/streamlit-qa-travel-ar-390.png) · [question in the middle of a case](../docs/screenshots/streamlit-qa-midcase-en-1280.png) · [another service mid-case](../docs/screenshots/streamlit-qa-other-case-it-1280.png) · [off-topic and other document: honest replies](../docs/screenshots/streamlit-qa-honest-it-1280.png) · [PIN route](../docs/screenshots/streamlit-qa-pin-route-it-1280.png) · [home route, phone](../docs/screenshots/streamlit-qa-home-route-en-390.png) |
| The kit | [web chat](../docs/screenshots/chat-welcome-en-mobile.png) · [reminder on the demo phone](../docs/screenshots/demo-phone.png) · [checklist](../docs/screenshots/checklist-mobile.png) · [panel](../docs/screenshots/panel-overview.png) |
