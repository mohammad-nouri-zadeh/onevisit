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
| Track | 01 (proposed; confirm before submitting) | |
| Runtime model | `claude-sonnet-5-5` (agent, classification, drafts) | team / @Saroth85, 13:20; used in the app 14:46 |
| Stack for agent and UI | Demo: Streamlit app (`app/`) on the shared data layer. Production plan: the kit on branch `claude/busy-mccarthy-uq5xoi` | @mohammad-nouri-zadeh, 14:46 |
| Demo case | Lost ID card, Egyptian newcomer living in Isola, chat in Arabic or English | @mohammad-nouri-zadeh, 14:46 |

## Log

Newest at the top. One line per push that others depend on: time, handle, what changed.

- 15:25 · @Saroth85 · Merged `main` (Streamlit app, video, README) into `claude/busy-mccarthy-uq5xoi`: the kit and the Streamlit demo now live side by side. README keeps main's submission text and adds a short "Production path: the OneVisit kit" section.
- 15:19 · @mohammad-nouri-zadeh · Final demo video `video/onevisit-final.mp4` (2:02): AI male voiceover + ducked music + sound effects (`video/mix_voice.py`).
- 15:12 · @mohammad-nouri-zadeh · Demo video soundtrack: music bed + synced sound effects (`video/sound.py`) on `video/onevisit-final.mp4` and `video/clips/`; still no voice.
- 15:08 · @mohammad-nouri-zadeh · Demo video now silent (we record our own voice): script with timings in `video/VOICEOVER.md`, six clips of 15–28 s in `video/clips/`.
- 15:03 · @mohammad-nouri-zadeh · Demo video re-cut in motion: `video/film2.html` (camera zooms, typing, cursor, animated numbers) replaces the slide-style scenes in `video/onevisit-final.mp4` (2:02).
- 14:55 · @Saroth85 · The three apps now use `libs/onevisit_ui` (chat, panel, gateway restyled like the prototype; ?lang=it|en menu in the chat). Fix: a contact that can't be decrypted (another key) no longer stops the gateway's send loop; the notification becomes `failed` and the others go out. New screenshots in the README.
- 14:50 · @Saroth85 · **Design system** from @mohammad-nouri-zadeh's prototype (`design/onevisit-prototype.html` on `momo/streamlit-demo`) turned into the shared package `libs/onevisit_ui`: monochrome tokens, Titillium Web + IBM Plex Mono served locally, components for chat, checklist and panel, htmx and Chart.js served from `/ui/vendor/` (no CDNs on citizen pages). Guide: `docs/design-system.md`. Only change from the prototype: `--pewter` #5E626B for AA contrast.
- 14:46 · @mohammad-nouri-zadeh · **Working product on `main`**: Streamlit app (`app/`), agent loop (`onevisit/agent.py`), reports and drafts (`onevisit/outcomes.py`), design prototype, final video. Tested end to end with real Claude (Sonnet 5.5). README completed.
- 14:46 · @mohammad-nouri-zadeh · Final demo video `video/onevisit-final.mp4` (2:02, voiceover + B&W AI-generated cold open, labelled), built by `video/build_final.py` on branch `momo/streamlit-demo`.
- 14:35 · @Saroth85 · **Kit implemented** on branch `claude/busy-mccarthy-uq5xoi` (to merge into main): web chat (`apps/assistant_web`, :8000), City panel (`apps/dashboard`, :8001), gateway with email/SMS and `/demo/phone` (`apps/gateway`, :8002), libs `onevisit_knowledge` (reads `data/` in place, only verified facts), `onevisit_agent` (prompt `libs/onevisit_agent/src/onevisit_agent/prompts/system.md`, citation validator, no eligibility claims), `onevisit_db` (migrations 0001-0003, roles, views with k>=5), `onevisit_privacy`, `onevisit_channels`, `onevisit_analytics` (`onevisit seed-demo`: 400 synthetic cases). 484 tests, 92% coverage. Contract changes after review: `docs/contracts.md` section 8. Status per story: `docs/progress.md`. Not yet tested with the real API (no key in this sandbox): `onevisit eval --quick` with `ANTHROPIC_API_KEY` set. `make demo` now passes `ONEVISIT_DEMO_MODE` to the containers.
- 13:45 · @Saroth85 · `docs/contracts.md`: interfaces between kit packages (knowledge, agent, privacy, db tables and roles, channels, apps). **Request to @mohammad-nouri-zadeh:** the kit's knowledge library reads `data/services/*.json`, `data/sources.csv` and `data/pages/` as they are, but only 2 requirements are `verified`. For the demo we need the pages `cie`, `residenza-estero`, `prenotazione` saved and the quotes verified (above all: CIE loss/theft report, documents issued abroad / translation for non-EU registration). This sandbox can't reach comune.milano.it; from a browser: `python data/tools/save_page.py <id> --html file --url ...` or `onevisit ingest <id> --html file --url ...`.
- 13:20 · @Saroth85 · **Added the OneVisit kit** (Docker/uv monorepo: `apps/assistant_web`, `apps/dashboard`, `apps/gateway`, `libs/onevisit_*`, `Makefile`, `compose*.yaml`, `docs/backlog.md` = spec, `docs/progress.md` = status). Nothing deleted: `onevisit/`, `data/` and `requirements.txt` unchanged. Start with `make env && make up` (or `uv sync --all-packages` without Docker). M0 checks green: 11 tests, ruff, mypy strict. ruff skips `onevisit/` and `data/tools/`.
- 12:32 · @mohammad-nouri-zadeh · City statistics in `data/context/` (surveys, arrivals, foreign residents) and `kb.context_tables()` for the panel. Summary: `data/context/README.md`.
- 12:26 · @mohammad-nouri-zadeh · Added TEAM.md (this file) and a pointer to it at the top of CLAUDE.md.
- 12:23 · @mohammad-nouri-zadeh · Repo created: data layer, `onevisit/kb.py`, `onevisit/tools.py`, validator, README draft.

## Timeline

Submission closes at **16:00** (the hub repo's issue form). Proposed: from 15:30, no new features; only fixes, the README and the demo video.
