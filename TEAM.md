# TEAM.md: several people, several Claude accounts, one repo

**If you are a Claude session working in this repo, read this first.**

Four people work on OneVisit at the same time, each with their own Claude account and their own Claude Code, Cowork or claude.ai session. You don't share memory or chat history with the other sessions. **This repo is the only thing you share.** Anything another session needs to know (a decision, a changed function, a new file) must be written here or in the code, then pushed.

## Who owns what

Edit files in your own area. For anything outside it, make the smallest change you can, and say so in the log below.

| Area | Folder or files | Owner (GitHub) |
|---|---|---|
| Data and sources | `data/` | @mohammad-nouri-zadeh |
| Data contract (functions and tool definitions) | `onevisit/kb.py`, `onevisit/tools.py` | @mohammad-nouri-zadeh; change only after telling the team |
| Agent (system prompt, loop, validator) | `libs/onevisit_agent/`, `libs/onevisit_privacy/` | @Saroth85 |
| Interface (chat UI), channels, gateway | `apps/assistant_web/`, `apps/gateway/`, `libs/onevisit_channels/` | @Saroth85 |
| Panel for City staff, analytics | `apps/dashboard/`, `libs/onevisit_analytics/` | @Saroth85 |
| Kit infrastructure: Docker, DB, CLI, knowledge loader | `Makefile`, `compose*.yaml`, `Dockerfile`, `pyproject.toml`, `libs/onevisit_db/`, `libs/onevisit_cli/`, `libs/onevisit_knowledge/` | @Saroth85 |
| README, pitch, demo video | `README.md`, `docs/` | @Saroth85 (take over by writing your handle here) |

Owners: replace TODO with your handle and folder in your first push.

## Git rules for every session

1. **Pull before you start, and again right before you push:** `git pull --rebase origin main`.
2. **Small commits, pushed often** (every 20–30 minutes), so the others build on current code.
3. **Never** force-push, rewrite history, `git reset --hard`, or delete or rename someone else's files.
4. **On a conflict, keep both sides' intent.** If you can't tell which version is right, stop and ask your human. Don't pick one.
5. **Shared files** (`README.md`, `CLAUDE.md`, `TEAM.md`, `requirements.txt`, `.gitignore`): add to them, don't rewrite them. Add your own dependencies to `requirements.txt`; don't remove other people's.
6. **Before pushing:** `python data/tools/validate.py` must print `OK`, and nothing you push may contain an API key or personal data.

## The contract between data and agent

The agent reads City facts only through `onevisit/tools.py` (`TOOLS` and `run_tool`), which uses `onevisit/kb.py`. Don't hard-code requirements, addresses or hours in the agent or the UI, and don't let the model answer them from memory. If the agent needs something the tools don't give, add a request to the log below rather than working around it.

Changing a tool's name, its inputs or a field it returns breaks the other side. Note it in the log in the same push.

**Since 13:20 (the kit):** `libs/onevisit_knowledge` reads the same files directly (`data/services/*.json`, `data/sources.csv`, `data/pages/*.md`, `data/offices.json`, `data/enti.json`, `data/context/*.csv`) and applies the same rule: only `"status": "verified"` facts reach the citizen. **These file formats are the contract**: changing a field name breaks the agent, so note it in the log. `onevisit/kb.py` and `onevisit/tools.py` stay as they are for anyone still using them.

## Decisions

Record a decision here when the team makes it, so every session follows it.

| Decision | Value | Decided by, when |
|---|---|---|
| Track | TODO (01 or 03) | |
| Runtime model | `claude-sonnet-5-5` for conversation and analysis, `claude-haiku-4-5-20251001` for short tasks (PII removal, classification) | @Saroth85, 13:20 |
| Stack for agent and UI | The OneVisit kit: Python 3.13, uv workspace (`apps/`, `libs/`), FastAPI + Jinja2 + HTMX, PostgreSQL 17 with `pii`/`core`/`analytics` schemas, Docker Compose, `make` targets. Spec: `docs/backlog.md`; plan: `docs/implementation-plan.md`; status: `docs/progress.md` | @Saroth85, 13:20 |
| Demo case | Daniel (non-EU, writes in English, registry enrolment) and Giulia (lost ID card, leaves in a month); personas in `docs/backlog.md` | @Saroth85, 13:20 |

## Log

Newest at the top. One line per push that others depend on: time, handle, what changed.

- 13:20 · @Saroth85 · **Added the OneVisit kit** (Docker/uv monorepo: `apps/assistant_web`, `apps/dashboard`, `apps/gateway`, `libs/onevisit_*`, `Makefile`, `compose*.yaml`, `docs/backlog.md` = spec, `docs/progress.md` = status). Nothing deleted: `onevisit/`, `data/` and `requirements.txt` unchanged. Start with `make env && make up` (or `uv sync --all-packages` without Docker). M0 checks green: 11 tests, ruff, mypy strict. ruff skips `onevisit/` and `data/tools/`.
- 12:32 · @mohammad-nouri-zadeh · City statistics in `data/context/` (surveys, arrivals, foreign residents) and `kb.context_tables()` for the panel. Summary: `data/context/README.md`.
- 12:26 · @mohammad-nouri-zadeh · Added TEAM.md (this file) and a pointer to it at the top of CLAUDE.md.
- 12:23 · @mohammad-nouri-zadeh · Repo created: data layer, `onevisit/kb.py`, `onevisit/tools.py`, validator, README draft.

## Timeline

Submission closes at **16:00** (the hub repo's issue form). Proposed: from 15:30, no new features; only fixes, the README and the demo video.
