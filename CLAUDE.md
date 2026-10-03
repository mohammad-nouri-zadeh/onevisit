# CLAUDE.md: OneVisit

We are a team at the Claude Impact Lab Milano (3 October 2026, with the Comune di Milano). Hub repo with the brief, rules and judging: https://github.com/Claude-Milano/impact-lab-oct-2026. The concept, in Italian, is in `docs/concept.md`.

Our user: a person going to a City registry desk, first of all a non-EU citizen who has just arrived and doesn't speak Italian well.
Our outcome: they arrive at the appointment with everything they need, checked against official sources, and the procedure closes on the first visit.

## Non-negotiables

- **Runs on Claude.** Claude does the work at runtime through the API: understands the case, asks only the questions that change the answer, builds the checklist, picks the office, answers in the user's language.
- **Facts only from `onevisit/kb.py`.** Never let the agent state a City requirement, address, hour, cost or deadline from model memory. It calls the tools in `onevisit/tools.py` and cites `source_id`s. If the tools don't have it, the agent says it doesn't know and links the official page. This is what makes OneVisit different from asking a general chatbot.
- **Never hand-edit facts without a quote.** A requirement becomes `"verified"` only with a verbatim quote from a saved source; `python data/tools/validate.py` must pass before every push.
- **No personal data.** No names, tax codes, document numbers or real emails, in code, data, screenshots or the video. Use invented cases. Email reminders are simulated in the prototype.
- **A human decides.** The agent never says documents are "valid"; the desk officer decides.
- **API keys** in `.env` only (gitignored).
- **Deadline 16:00.** Scope down before polishing.

## Layout

- `data/`: sources, saved pages, open data, services, offices. Owner: Mohammad. Read `data/README.md`.
- `onevisit/kb.py`: functions over the data. `onevisit/tools.py`: Claude tool definitions plus `run_tool()`.
- Agent, web UI and panel: TODO (agent team), import `onevisit.tools`.

## Stack

Python 3.11+. `anthropic` SDK. Runtime model: TODO (the hub's starter kit suggests `claude-sonnet-5-5`; each of us has $100 of API credits).
