"""OneVisit: citizen assistant + City staff panel.

    streamlit run app/streamlit_app.py

Needs ANTHROPIC_API_KEY in .env (Claude runs every conversation and every report).
"""
import datetime as dt
import html
import os
import pathlib
import sys
import uuid

import streamlit as st
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from onevisit import kb, outcomes  # noqa: E402
from onevisit.agent import MODEL, run_turn  # noqa: E402

st.set_page_config(page_title="OneVisit", page_icon="🗂️", layout="centered")

# ---------- look ----------
big = st.session_state.get("big_text", False)
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Titillium+Web:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html {{ font-size: {'20px' if big else '16px'}; }}
.stMarkdown, .stMarkdown p, .stMarkdown li, h1, h2, h3, .stCaption, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] p {{ font-family: "Titillium Web", -apple-system, system-ui, sans-serif; }}
.ov-chip {{ display:inline-block; font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:0.72em; padding:1px 8px; margin-left:6px; border-radius:999px;
           background:#111214; color:#FFFFFF; white-space:nowrap; vertical-align:middle; }}
.ov-chip.todo {{ background:transparent; color:#6E727C; border:1px dashed #C6C8CE; }}
.ov-item {{ padding:8px 0; border-bottom:1px solid #E4E5E9; }}
.ov-muted {{ color:#6E727C; }}
.ov-warn {{ border-top:1px solid #C6C8CE; color:#4A4D55; padding:6px 0; font-size:0.9em; }}
.ov-foot {{ color:#6E727C; font-size:0.8em; margin-top:2rem; border-top:1px solid #C6C8CE; padding-top:10px; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; letter-spacing:-0.02em; }}
.stButton > button, .stDownloadButton > button {{ border-radius:999px; border:1.5px solid #111214; font-weight:600; }}
@media (prefers-color-scheme: dark) {{
  .ov-chip {{ background:#F2F2F3; color:#0C0C0E; }}
  .ov-chip.todo {{ color:#8B8E97; border-color:#3A3C42; }}
  .ov-item {{ border-color:#24252A; }}
  .stButton > button, .stDownloadButton > button {{ border-color:#F2F2F3; }}
}}
</style>""", unsafe_allow_html=True)

state = st.session_state
state.setdefault("messages", [])      # full API history, including tool turns
state.setdefault("chat", [])          # what we show: {"role", "text", "options", "trace"}
state.setdefault("checklist", None)
state.setdefault("offices", None)
state.setdefault("service_id", None)
state.setdefault("drafts", {})
state.setdefault("approved", set())

if not os.getenv("ANTHROPIC_API_KEY"):  # Streamlit Community Cloud: key stored in the app's Secrets
    try:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
has_key = bool(os.getenv("ANTHROPIC_API_KEY"))

with st.sidebar:
    st.toggle("Larger text", key="big_text")
    st.caption(f"Runs on Claude · `{MODEL}`")
    if not has_key:
        st.error("ANTHROPIC_API_KEY is missing. Add it to `.env` to talk to OneVisit.")
    if st.button("New conversation"):
        for k in ("messages", "chat", "checklist", "offices", "service_id"):
            state[k] = [] if k in ("messages", "chat") else None
        st.rerun()


def chip(text: str, todo: bool = False) -> str:
    return f'<span class="ov-chip{" todo" if todo else ""}">{html.escape(text)}</span>'


def show_checklist(cl: dict) -> None:
    with st.container(border=True):
        st.markdown("**Your checklist, from official sources**")
        for r in cl["requirements"]:
            text = r.get("text_en") or r["text_it"]
            tip = html.escape(f'"{r.get("quote", "")}"')
            st.markdown(f'<div class="ov-item" title={tip}>✓ {html.escape(text)}'
                        f'{chip(r["source_id"] + " · checked " + str(r.get("verified_at")))}</div>',
                        unsafe_allow_html=True)
        for rid in cl.get("not_yet_verified", []):
            st.markdown(f'<div class="ov-item ov-muted">? {html.escape(rid.replace("-", " ").capitalize())}'
                        f'{chip("no verified source yet: check comune.milano.it", todo=True)}</div>',
                        unsafe_allow_html=True)
        if cl.get("still_to_ask"):
            st.caption("Still to clarify: " + ", ".join(cl["still_to_ask"]))
        st.caption("The officer at the desk makes the final check.")


def show_offices(offices: list) -> None:
    with st.container(border=True):
        st.markdown("**Registry offices** " + chip("ds549 · City open data"), unsafe_allow_html=True)
        for o in offices:
            where = o["address"] + (f" ({o['entrance_note']})" if o.get("entrance_note") else "")
            dist = f" · {o['distance_km']} km" if "distance_km" in o else ""
            st.markdown(f"**{html.escape(where)}**{dist}  \n{html.escape(o.get('hours_it') or '')}")
            if o.get("booking_without_spid"):
                st.caption("You can book without SPID.")
            for issue in o.get("data_issues", []):
                st.markdown(f'<div class="ov-warn">City data note: {html.escape(issue)}</div>', unsafe_allow_html=True)


def ics(appointment: dt.date) -> str:
    def event(day: dt.date, title: str) -> str:
        d = day.strftime("%Y%m%d")
        nxt = (day + dt.timedelta(days=1)).strftime("%Y%m%d")
        return (f"BEGIN:VEVENT\r\nUID:{uuid.uuid4()}@onevisit\r\nDTSTAMP:{dt.datetime.utcnow():%Y%m%dT%H%M%SZ}\r\n"
                f"DTSTART;VALUE=DATE:{d}\r\nDTEND;VALUE=DATE:{nxt}\r\nSUMMARY:{title}\r\nEND:VEVENT\r\n")
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//OneVisit//EN\r\n"
            + event(appointment - dt.timedelta(days=3), "OneVisit: check your documents with the checklist")
            + event(appointment, "Registry office appointment")
            + "END:VCALENDAR\r\n")


def ask(text: str) -> None:
    state.chat.append({"role": "user", "text": text})
    state.messages.append({"role": "user", "content": text})
    with st.spinner("Claude is checking the official sources…"):
        try:
            reply = run_turn(state.messages)
        except Exception as e:  # show the error instead of a blank screen during the demo
            state.messages.pop()
            state.chat.append({"role": "assistant", "text": f"Something went wrong: {e}", "options": [], "trace": []})
            return
    for step in reply["trace"]:
        if step["tool"] == "get_checklist" and "requirements" in step["output"]:
            state.checklist = step["output"]
            state.service_id = step["output"]["service_id"]
        if step["tool"] == "find_offices" and isinstance(step["output"], list):
            state.offices = step["output"]
    state.chat.append({"role": "assistant", **reply})


citizen, panel = st.tabs(["For citizens", "For City staff"])

# ---------- citizen ----------
with citizen:
    st.title("OneVisit")
    st.markdown("Get ready for your registry office appointment, in your language. "
                "Every answer comes from official City sources, with the source shown.")

    if not state.chat:
        st.caption("Try: *I just moved to Milan from Cairo and need to register my residence* · "
                   "*Perdí mi carta de identidad italiana* · *أحتاج إلى بطاقة هوية*")

    for i, m in enumerate(state.chat):
        with st.chat_message(m["role"]):
            st.markdown(m["text"])
            if m["role"] == "assistant" and m.get("trace"):
                with st.expander("What Claude checked"):
                    for step in m["trace"]:
                        out = step["output"]
                        if isinstance(out, dict) and "requirements" in out:
                            summary = f"{len(out['requirements'])} verified, {len(out.get('not_yet_verified', []))} not yet verified"
                        elif isinstance(out, list):
                            summary = f"{len(out)} results"
                        else:
                            summary = "ok" if "error" not in str(out)[:50] else "error"
                        st.markdown(f"`{step['tool']}({', '.join(f'{k}={v}' for k, v in step['input'].items())})` → {summary}")
            if m["role"] == "assistant" and m.get("options") and i == len(state.chat) - 1:
                cols = st.columns(len(m["options"]))
                for col, opt in zip(cols, m["options"]):
                    if col.button(opt, key=f"opt-{i}-{opt}", use_container_width=True):
                        state.pending = opt
                        st.rerun()

    if state.checklist:
        show_checklist(state.checklist)
    if state.offices:
        show_offices(state.offices)

    if state.checklist:
        with st.expander("Remind me before the appointment"):
            day = st.date_input("Appointment date", min_value=dt.date.today())
            st.download_button("Add reminders to my calendar (.ics)", ics(day), "onevisit.ics", "text/calendar")
            st.caption("Saved on your device only. We don't ask for your email.")

        with st.expander("After your appointment: how did it go?"):
            outcome = st.radio("Outcome", ["All fine", "Something was missing", "Other"], horizontal=True)
            note = st.text_input("What happened? Please don't write names or document numbers.")
            if st.button("Send", disabled=not has_key):
                code = {"All fine": "ok", "Something was missing": "missing", "Other": "other"}[outcome]
                with st.spinner("Claude is removing personal details and classifying your report…"):
                    try:
                        result = outcomes.classify(state.service_id or "unknown", code, note)
                        row = outcomes.save_report(state.service_id or "unknown", code, result)
                        st.markdown(f"**✓ Thank you.** Recorded as: {outcomes.CAUSES[row['cause']][0]}. "
                                    f"Saved: “{row['summary_en']}” (your own words are not stored).")
                    except Exception as e:
                        st.error(f"Could not send: {e}")

    prompt = st.chat_input("Describe your situation in any language", disabled=not has_key)
    pending = state.pop("pending", None)
    if prompt or pending:
        ask(prompt or pending)
        st.rerun()

# ---------- panel ----------
with panel:
    st.title("What the appointments tell the City")
    st.caption("Prototype panel for City staff. Statistics are real City open data; reports marked SIMULATED are demo data.")

    ctx = kb.context_tables()
    arrivals = {r["year"]: r for r in ctx["arrivals-from-abroad"]}
    res = {r["group"]: r for r in ctx["residence-2022-helped-by-group"]}
    c1, c2, c3 = st.columns(3)
    c1.metric("Registered from abroad, 2024", f"{int(arrivals['2024']['registrations_from_abroad']):,}",
              help="ds1959 · Comune di Milano open data")
    c2.metric("Online residence service didn't help: foreign citizens", f"{res['Straniero']['helped_little_or_not_pct']}%",
              help="ds1702 · 2022 survey, 1,612 answers")
    c3.metric("…Italian citizens", f"{res['Italiano']['helped_little_or_not_pct']}%",
              help="ds1702 · 2022 survey, 8,582 answers")

    st.subheader("Problems in City data, found today")
    for o in [o for o in json_offices if o["data_issues"]] if (json_offices := kb._offices()) else []:
        st.markdown(f"**{o['address']}** {chip('ds549')}", unsafe_allow_html=True)
        for issue in o["data_issues"]:
            st.markdown(f"- {issue}")

    st.subheader("Reports after appointments")
    st.caption(f"A group reaches the office only with at least {outcomes.THRESHOLD} similar reports. "
               "Smaller groups are visible to web editors only, without dates or office.")
    for g in outcomes.groups():
        key = f"{g['service_id']}|{g['cause']}"
        tag = " · SIMULATED" if g["simulated"] == g["count"] else (f" · {g['simulated']} simulated" if g["simulated"] else "")
        status = "Ready for the office" if g["over_threshold"] else "Web editors only (below threshold)"
        with st.container(border=True):
            st.markdown(f"**{g['count']} reports · {g['cause_label']}** · {g['service_id']}{tag}  \n"
                        f"To: {g['recipient']} · {status}")
            for ex in g["examples_en"]:
                st.caption(f"“{ex}”")
            if key in state.approved:
                st.markdown("**✓ Approved by a City officer.** The checklist will be updated once the page is changed.")
            elif key in state.drafts:
                with st.container(border=True):
                    st.markdown(state.drafts[key])
                if st.button("Approve correction", key=f"ap-{key}"):
                    state.approved.add(key)
                    st.rerun()
            elif st.button("Draft a correction with Claude", key=f"dr-{key}", disabled=not has_key):
                with st.spinner("Claude is drafting…"):
                    try:
                        state.drafts[key] = outcomes.draft_fix(g)
                    except Exception as e:
                        st.error(f"Could not draft: {e}")
                st.rerun()

st.markdown('<div class="ov-foot">Prototype built at the Claude Impact Lab Milano, 3 Oct 2026. '
            'Not an official City of Milan service. Open source, MIT.</div>', unsafe_allow_html=True)
