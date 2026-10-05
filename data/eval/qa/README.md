# Question bank: the ID card (CIE) in Milan

`cie-questions.yaml` holds 255 questions people ask about the carta d'identità elettronica, written the way they ask them: formal, chatty or with typos, mostly in Italian and English, plus Spanish, French, Arabic, Chinese, Ukrainian and Bengali. Each question names the saved official pages that answer it. For each of those pages it also gives a quote copied word for word, so a test can show the answer really is on the page.

| Set | Count | Purpose |
|---|---|---|
| Tuning | 187 answerable | Read them, tune the search and the prompts against them |
| Honesty | 14 unanswerable + 6 out of scope | No saved page answers these, or they aren't about the ID card. The right reply says so and links `redirect.url` |
| Holdout | 48 answerable (20%) | Accuracy on questions nobody tuned against. They sit at the end of the file under a banner. Don't read them while you tune |

Languages: it 114, en 97, es 15, ar 7, zh 7, uk 6, fr 5, bn 4. The questions use 131 saved pages and 533 evidence quotes.

## Check it

```
python data/eval/qa/check_bank.py          # counts per facet and language, then errors; exit 1 on any error
python data/eval/qa/check_bank.py --json
```

The checker uses only the standard library and runs with or without PyYAML. It fails when any of these is true:

- a quote isn't in `data/pages/<source>.md` (spacing and curly quotes are normalised, case is not);
- a source id isn't in `data/sources.csv`;
- an expected source has no quote;
- an unanswerable question has sources, or has no redirect;
- a redirect claims a source that neither is that URL nor links to it.

Run it after editing the bank. Also run it after re-saving pages, because a changed page can break a quote.

## Use it

```python
import sys

sys.path.insert(0, "data/eval/qa")
import check_bank

bank = check_bank.load_bank()["questions"]
tuning = [q for q in bank if not q["holdout"]]
```

- **Retrieval.** A question passes when one of the top k passages comes from any of its `expected_sources`. Skip `answerable: false`, or count it as passed when the search marks no result `confident` (`onevisit.search.best_answer`). `run_retrieval.py` does all of this; see below.
- **Answers.** Compare the reply with `answer`, written in English for a human or an LLM grader. Every source the reply cites should be in `expected_sources`. For `answerable: false`, the reply must say the official pages don't cover it, must not state a rule, and must link `redirect.url`. Every question also follows the project rules: no "idoneo", "in regola" or "garantito", and no personal data asked for.
- **Holdout.** Report holdout accuracy apart from the rest. If a holdout question fails, don't fix that question. Fix the general cause, then add a new tuning question that shows the failure. `search-retrieval.json` in this folder is the search tuner's own regression set. No holdout question repeats one of its queries in the same language.

## Measure retrieval

```
python data/eval/qa/run_retrieval.py                  # tuning set; the holdout is not run
python data/eval/qa/run_retrieval.py --holdout        # final measurement, holdout apart
python data/eval/qa/run_retrieval.py --out report.md  # also write the Markdown report
```

Every question runs `onevisit.search.search(question, service_id="carta-identita", k=5)`. A hit is an expected source whose passage contains, or overlaps by 30 characters, one of that source's evidence quotes; `page@k` counts the source alone. The report gives hit@1/3/5 for Italian and English, for the other languages and per language, the share of answerable questions the search marks `confident`, the confidence of the unanswerable ones, and the failures at k=3 (holdout failures apart). `tests/streamlit/test_search.py` asserts minimum rates on the tuning set.

The four questions `cie-validity-10`, `cie-delivery-14`, `cie-accessibility-05` and `cie-card-info-06` were added after the first holdout measurement, as this README asks: each shows a general cause found in a failing holdout question (duration asked as "how many years" in Ukrainian, Chinese words for posting and collecting, the registry's family facilities, "printed on the card"). `cie-card-info-06` still fails: "stampata a colori" finds the pages on the colour photo you bring.

The three questions `cie-booking-12`, `cie-documents-09` and `cie-cost-10` were added after the review of 5 October 2026 for general causes it found: Spanish booking verbs the concept map lacked ("saco cita", seen in a failing holdout question), a question that names another document as something to bring ("Devo portare anche il permesso di soggiorno?", which the other-document gate refused), and Italian cost words ("quanto si spende").

Thirteen questions come from the review of the Q&A replies (5 October 2026, evening): 8 answerable in the tuning set (travelling to Rome by train after a theft, booking with a friend's or one SPID for the family, a lost health card, "come va fatta la foto?" and "how are you supposed to pay?" that the small-talk gate refused, delivery to a dorm, a faulty chip at no cost) and 5 in the honesty set (parking near via Larga, a dog at the anagrafe, temporary protection, a free card over 70, a passport at the anagrafe). The fixes were made looking at them, so none is in the holdout.

On 5 October 2026 the bank followed the pages saved that day (`docs/sources-inventory.md`, section "Pagine aggiunte il 5 ottobre"). Nine tuning questions gained the new page that answers them as an expected source, with its quote (`cie-home-service-02`, `cie-digital-identity-03`, `-06`, `-07`, `-09`, `-12`, `cie-organ-donation-03`, `-05`, `cie-pin-puk-07`). Fourteen tuning questions cover what the new pages answer: signing a PDF with the phone, the software for a computer, a card not recognised at login, other EU countries' online services, the chip-date check, the IDEA app, the privacy notice, the Ve.Do. production status and receipt check, cancelling the organ-donation choice, the delegation for a minor's home service, cropping or retouching the photo and its width (35 mm against the City's 2007 guide), travelling in Italy with another document (the Polizia di Stato's travel-documents page). Five holdout questions were added at the end, written before the search was run on them (metro instead of a ticket, a folded photo, the attachments for a lost card at home, AIRE at the consulate, collecting the card with no ID at all); no existing holdout question was changed.

## Measure the replay (no key)

```
python data/eval/qa/run_demo_qa.py --out data/eval/qa/RESULTS.md   # tables, holdout apart, failures listed
python data/eval/qa/run_demo_qa.py --json
```

Without an API key the app answers with the replay (`onevisit/demo.py`): keyword rules tell a question from a case, and a question gets the passages the search ranks first, quoted word for word as cards. `run_demo_qa.py` sends every bank question through `demo.respond`, the function the page calls for a typed message, as a first message and in the middle of the lost-ID case, and through `demo.ask` (the example chips). A reply is a **hit** when a card shown as the answer comes from an expected page and shares 30 characters with an evidence quote; it also counts the right page with the answer behind "Leggi tutto", the honest "the pages don't answer" line, wrong-confident replies, cases and unclear messages. `RESULTS.md` holds the numbers and, below its notes marker, a person's reading of the wrong-confident replies (kept when the script rewrites the file). The live path, Claude with the same tools, is measured with `python -m onevisit.evaluate --qa` when a key is set.

## Facets

`booking` (channels, SPID, check-in, rescheduling, waiting time) · `offices` (where, hours, urgent tickets) · `documents` · `photo` (rules, booths, USB) · `cost` · `renewal` (180 days, paper cards after 3 Aug 2026, reminders, new citizens) · `validity` (by age, 70+, no fingerprints) · `loss_theft` (report, walk-in, blocking, damage, abroad, lost and found) · `urgent` (urgent issue, provisional paper ID, receipt) · `minors` (presence, one parent, assent form, newborns, fingerprints, travel under 14, non-Italian minors) · `foreigners` (EU and non-EU, expired permit, travel validity, residence, detainees) · `non_residents` (domiciled, other Lombardy towns, AIRE) · `home_service` · `delivery` (post, delegate, intercom, failed delivery, tracking, pick-up) · `pin_puk` · `digital_identity` (credentials, CieID, NFC, minors, signature) · `organ_donation` · `data_change` (address, marital status, contacts, foreigners' data) · `travel` · `at_the_desk` · `card_info` · `accessibility` · `out_of_scope`

## Where the sources disagree

Some questions show two sources that disagree. A good answer gives the City's current rule, or presents both:

- **Delivery time.** YesMilano says ten working days. The City and the Ministry say six.
- **Applying in another town.** The Ministry says you can apply in any Comune. Milan serves only its residents and people domiciled in Milan but resident outside Lombardy.
- **Organ donation.** The Ministry says you state your choice "se lo desidera" (only if you want to). City FAQ KA-00542 says adults sign a form.
- **Head covering in the photo.** The City page says bare head. The Ministry allows religious, cultural or medical head coverings.
- **Photo width.** The Ministry and City FAQ KA-00308 say 35 mm. The City's 2007 photo guide, still linked from the CIE page, says 35-40 mm.
- **Paper cards at banks.** The June 2026 news says private companies may refuse them. The current City page (DL 108/2026) keeps them valid for bank and post office operations until 31 January 2027.

## Add a question

1. Copy the quote from `data/pages/<source>.md`. Never take it from search results.
2. Write values as JSON strings in double quotes, one key per line. Evidence items are one JSON object per line. This keeps the file readable without PyYAML.
3. Use the next free `cie-<facet>-<nn>` id.
4. Put the question in the tuning section unless it is meant for the holdout.
5. Run the checker.
