# Question bank: the ID card (CIE) in Milan

`cie-questions.yaml` holds 223 questions people ask about the carta d'identità elettronica, written the way they ask them: formal, chatty or with typos, mostly in Italian and English, plus Spanish, French, Arabic, Chinese, Ukrainian and Bengali. Each question names the saved official pages that answer it. For each of those pages it also gives a quote copied word for word, so a test can show the answer really is on the page.

| Set | Count | Purpose |
|---|---|---|
| Tuning | 165 answerable | Read them, tune the search and the prompts against them |
| Honesty | 10 unanswerable + 5 out of scope | No saved page answers these, or they aren't about the ID card. The right reply says so and links `redirect.url` |
| Holdout | 43 answerable (21%) | Accuracy on questions nobody tuned against. They sit at the end of the file under a banner. Don't read them while you tune |

Languages: it 98, en 84, es 13, ar 7, zh 7, fr 5, uk 5, bn 4. The questions use 116 saved pages and 484 evidence quotes.

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

## Facets

`booking` (channels, SPID, check-in, rescheduling, waiting time) · `offices` (where, hours, urgent tickets) · `documents` · `photo` (rules, booths, USB) · `cost` · `renewal` (180 days, paper cards after 3 Aug 2026, reminders, new citizens) · `validity` (by age, 70+, no fingerprints) · `loss_theft` (report, walk-in, blocking, damage, abroad, lost and found) · `urgent` (urgent issue, provisional paper ID, receipt) · `minors` (presence, one parent, assent form, newborns, fingerprints, travel under 14, non-Italian minors) · `foreigners` (EU and non-EU, expired permit, travel validity, residence, detainees) · `non_residents` (domiciled, other Lombardy towns, AIRE) · `home_service` · `delivery` (post, delegate, intercom, failed delivery, tracking, pick-up) · `pin_puk` · `digital_identity` (credentials, CieID, NFC, minors, signature) · `organ_donation` · `data_change` (address, marital status, contacts, foreigners' data) · `travel` · `at_the_desk` · `card_info` · `accessibility` · `out_of_scope`

## Where the sources disagree

Some questions show two sources that disagree. A good answer gives the City's current rule, or presents both:

- **Delivery time.** YesMilano says ten working days. The City and the Ministry say six.
- **Applying in another town.** The Ministry says you can apply in any Comune. Milan serves only its residents and people domiciled in Milan but resident outside Lombardy.
- **Organ donation.** The Ministry says you state your choice "se lo desidera" (only if you want to). City FAQ KA-00542 says adults sign a form.
- **Head covering in the photo.** The City page says bare head. The Ministry allows religious, cultural or medical head coverings.
- **Paper cards at banks.** The June 2026 news says private companies may refuse them. The current City page (DL 108/2026) keeps them valid for bank and post office operations until 31 January 2027.

## Add a question

1. Copy the quote from `data/pages/<source>.md`. Never take it from search results.
2. Write values as JSON strings in double quotes, one key per line. Evidence items are one JSON object per line. This keeps the file readable without PyYAML.
3. Use the next free `cie-<facet>-<nn>` id.
4. Put the question in the tuning section unless it is meant for the holdout.
5. Run the checker.
