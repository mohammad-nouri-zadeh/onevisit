# OneVisit

> Claude Impact Lab Milano · 3 October 2026 · Track **TODO: 01 or 03, decide as a team**

**One line:** for people who go to a City of Milan registry desk (above all non-EU newcomers), OneVisit checks with them, from official sources, everything they need before the appointment, so the procedure closes on the first visit.

**Demo video:** TODO

## The problem

Daniel, a Brazilian engineer who has just moved to Milan, books an appointment at the registry office, waits, goes, and finds out at the desk that something is missing. He has to book again. The slot he used could have served someone else.

The full concept, in Italian, is in [docs/concept.md](docs/concept.md).

## What we built

TODO: the agent's flow, step by step, with a screenshot or two.

Built today:

- **A sourced knowledge base** (`data/`): every requirement carries a verbatim quote from an official page or City dataset and the date it was checked. A validator rejects any fact whose quote isn't in the saved source.
- **Registry offices from City open data** (`data/offices.json`, from dataset `ds549`), cleaned, with the dataset's own errors flagged.
- **Tools for the agent** (`onevisit/tools.py`): list services, get the deciding questions, get the checklist for this case, find offices, cite a source.
- TODO: the agent, the post-appointment loop, the panel.

## Where Claude works

*Required section. TODO: the agent team completes this once the agent runs.*

- **Model(s):** TODO
- **What it does at runtime:** understands the citizen's situation in their own language; picks the service and variant; asks only the questions that change the answer (`get_service` → `deciding_questions`); builds the checklist with `get_checklist`; points to the right office with `find_offices`; answers in the citizen's language and cites every source.
- **Prompts and tools:** system prompt in TODO; tools in [`onevisit/tools.py`](onevisit/tools.py), backed by [`onevisit/kb.py`](onevisit/kb.py).
- **What it decides, and what a human confirms:** Claude proposes the checklist; the citizen confirms the summary of their case; the officer at the desk makes the final assessment. OneVisit never says the documents are "valid", only that, according to the cited sources, everything listed is present.
- **What happens when it's wrong:** Claude can only state requirements returned by `get_checklist`, which returns only facts whose quote was checked against the saved source. When a requirement isn't verified, Claude says it doesn't know and links the official page.

## City data and sources

| Source | How we used it |
|---|---|
| `ds549-sedi-dei-servizi-anagrafici` (retrieved 3 Oct 2026; resource last modified 28 Jan 2026) | The 13 registry offices: address, hours, booking rules, coordinates. Cleaning found a stale note ("5 gennaio 2026: CHIUSO") and missing fields |
| comune.milano.it service pages (TODO, see [data/sources.csv](data/sources.csv)) | Requirements for each service, quoted word for word |

Full list with retrieval dates: [data/sources.csv](data/sources.csv). How the data works: [data/README.md](data/README.md).

## Day one

TODO: what the Comune needs to switch it on (the source pages it already has, a list of requirements per service, a hook into the existing appointment confirmation emails).

## Run it

```bash
git clone https://github.com/mohammad-nouri-zadeh/onevisit
cd onevisit
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # add your ANTHROPIC_API_KEY
python data/tools/validate.py      # check the data
python -m onevisit.tools           # try the tools without the API
```

## Team

| Name | Role | GitHub |
|---|---|---|
| Mohammad Nouri Zadeh | Data and sources | [@mohammad-nouri-zadeh](https://github.com/mohammad-nouri-zadeh) |
| TODO | TODO | [@Saroth85](https://github.com/Saroth85) |

## Licence

MIT. Built at the Claude Impact Lab Milano and donated to the Comune di Milano.
