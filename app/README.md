# OneVisit demo app (Streamlit)

A working end-to-end demo on top of the shared data layer: citizen chat run by Claude with the tools in `onevisit/tools.py`, checklist with source chips, registry offices, calendar reminders, post-appointment report classified by Claude, and the City staff panel (real City statistics, real data issues, simulated reports clearly marked, Claude-drafted corrections that a person approves).

```bash
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY from console.anthropic.com
streamlit run app/streamlit_app.py
```

- Agent loop: `onevisit/agent.py` (system prompt and tool loop). Reports and corrections: `onevisit/outcomes.py`.
- Model: `CLAUDE_MODEL` (default `claude-opus-5-5`), effort `CLAUDE_EFFORT` (default `medium`).
- Simulated reports for the panel: `data/demo/simulated-outcomes.json` (invented, labelled SIMULATED in the app). Live reports go to `runtime/` (gitignored).
- It doesn't replace the kit in `apps/`: it's a fallback that already runs.
