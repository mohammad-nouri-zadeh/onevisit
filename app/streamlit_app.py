"""OneVisit: citizen assistant + City staff panel.

    streamlit run app/streamlit_app.py

With ANTHROPIC_API_KEY (in .env or the app's Secrets) Claude runs every conversation,
every report classification and every page-correction draft. Without a key, or with
?demo=1 in the URL, the app plays the demo replay: the assistant's sentences are recorded
and typed messages are read by keywords, while the tools, the checklist, the offices and
the sources are computed live on the verified data.

Deep link from the City's booking confirmation email (no personal data):
    ?servizio=carta-identita&sede=ds549-11&data=2026-10-20&lang=it
"""
from __future__ import annotations

import datetime as dt
import html
import inspect
import json
import os
import pathlib
import re
import sys
import threading
import uuid
from urllib.parse import urljoin

import streamlit as st
from dotenv import load_dotenv

APP = pathlib.Path(__file__).resolve().parent
ROOT = APP.parent
for p in (str(ROOT), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)
load_dotenv(ROOT / ".env")

# E402 below: these imports need the paths above and the key from .env loaded first
import deeplink  # noqa: E402
from i18n import CAUSES_IT, LANGS, PROACTIVE, RTL, STRINGS, t, t_variant  # noqa: E402
from onevisit import demo, dossier, kb, outcomes, plan, search, translate, validator  # noqa: E402
from onevisit.agent import MODEL, guess_lang, run_turn  # noqa: E402

# The agent takes the service the app already knows (the default for search_official_pages), when it can.
TURN_TAKES_SERVICE = "service_id" in inspect.signature(run_turn).parameters

st.set_page_config(page_title="OneVisit · Servizi anagrafici Milano", page_icon="🗂️", layout="centered",
                   initial_sidebar_state="collapsed")

state = st.session_state
qp = st.query_params

# ---------- state ----------
for key, default in {"messages": [], "chat": [], "checklist": None, "offices": None, "service_id": None,
                     "answers": {}, "office_id": None, "demo_state": None, "appointment": None,
                     "drafts": {}, "approved": set(), "pending": None, "theme_mode": "light",
                     "big_text": False, "urgent": False, "plans": {}, "translated": set(), "live_calls": 0,
                     "live_off": None, "notice": None}.items():
    state.setdefault(key, default)
if "_lang_next" in state:  # set by a turn (the language the person writes in), applied before the menu exists
    state.lang = state.pop("_lang_next")

if not state.get("_boot"):
    state._boot = True
    link = deeplink.parse(qp.to_dict())
    lang_q = qp.get("lang")
    state.lang = (link or {}).get("lang") or (lang_q if lang_q in LANGS else "it")
    if link:
        state.appointment = link
        state.office_id = link["office_id"]
        state.offices = [o for o in kb.find_offices(limit=1000) if o["id"] == link["office_id"]] or None
        state.pending = {"kind": "appointment"}
state.setdefault("lang", "it")


def real_key(value: str | None) -> bool:
    """A key that can work: not empty and not the .env.example placeholder ("sk-ant-...")."""
    value = (value or "").strip()
    return len(value) >= 30 and "..." not in value


if not real_key(os.getenv("ANTHROPIC_API_KEY")):  # Streamlit Community Cloud: key stored in the app's Secrets
    try:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
SERVER_KEY = os.getenv("ANTHROPIC_API_KEY") if real_key(os.getenv("ANTHROPIC_API_KEY")) else ""
pasted_key = (state.get("api_key") or "").strip()
has_key = bool(SERVER_KEY or real_key(pasted_key))
FORCE_DEMO = qp.get("demo") == "1"
# Live by default when the deployment has a key; ?demo=1 is the fallback for a pitch without network.
# A session falls back to demo by itself when Claude can't be reached or the request cap is hit.
LIVE = has_key and not FORCE_DEMO and not state.get("live_off")


def _setting(name: str, default: int) -> int:
    """A number from the environment or the app's Secrets (e.g. ONEVISIT_MAX_CALLS_PER_DAY)."""
    raw = os.getenv(name)
    if raw is None:
        try:
            raw = st.secrets.get(name)
        except Exception:
            raw = None
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


MAX_PER_SESSION = _setting("ONEVISIT_MAX_CALLS_PER_SESSION", 40)
MAX_PER_DAY = _setting("ONEVISIT_MAX_CALLS_PER_DAY", 1500)


@st.cache_resource
def _day_counter() -> dict:
    """Claude calls made today by this server (all sessions), to cap spending on the public demo."""
    return {"day": None, "n": 0, "lock": threading.Lock()}


def take_live_call() -> bool:
    """Count one Claude call; False (and this session goes to demo) once a cap is reached."""
    if not LIVE:
        return False
    if not SERVER_KEY:  # a key pasted in the page pays for its own calls
        return True
    counter = _day_counter()
    with counter["lock"]:
        today = dt.date.today().isoformat()
        if counter["day"] != today:
            counter["day"], counter["n"] = today, 0
        if state.live_calls >= MAX_PER_SESSION or counter["n"] >= MAX_PER_DAY:
            state.live_off = "limit"
            return False
        counter["n"] += 1
    state.live_calls += 1
    return True


def client():
    """Server key if configured, otherwise the key pasted in this browser session only."""
    import anthropic
    return anthropic.Anthropic(api_key=SERVER_KEY or pasted_key)


def L(key: str, **kw: object) -> str:
    return t(key, state.lang, **kw)


DL_FROM = {"prenotazione": "dl_from", "yesmilano": "dl_from_yesmilano", "benvenuto": "dl_from_benvenuto"}


def link_origin(appt: dict) -> str:
    """Where the citizen's link was placed: booking email, welcome email, YesMilano guide."""
    return L(DL_FROM.get(appt.get("channel") or "", "dl_from_link"))


def online_service(service_id: str | None) -> bool:
    """The procedure is sent online with the City's form (no desk appointment), as the data says."""
    return bool(service_id) and "online_form_url" in kb.service_links(service_id)


def LV(key: str, service_id: str | None, **kw: object) -> str:
    """Interface text for this service: the "_online" wording for online procedures, and the wording of
    the site it is sent on when the data names one (e.g. "_anpr": the national registry website)."""
    if online_service(service_id):
        kind = (kb.get_service(service_id) or {}).get("online_form_kind")
        if kind and any(f"{key}_{kind}" in STRINGS[x] for x in (state.lang, "en", "it") if x in STRINGS):
            return t_variant(key, kind, state.lang, **kw)
        return t_variant(key, "online", state.lang, **kw)
    return t(key, state.lang, **kw)


def LR(key: str, service_id: str | None, route_kind: str | None, **kw: object) -> str:
    """LV, with the home-service wording ("_home") when the case's route sends an officer to the home."""
    return t_variant(key, "home", state.lang, **kw) if route_kind == "home" else LV(key, service_id, **kw)


# ---------- look: .italia tokens, Comune di Milano red ----------
DARK = state.get("theme_mode") == "dark"
RTL_UI = state.lang in RTL
C = ({"bg": "#0f1215", "surface": "#1a1f24", "surface2": "#232a31", "fg": "#f1f2f3", "fg2": "#c9d3dc", "muted": "#a3b1bf",
      "line": "#3a444e", "accent": "#ff9aa9", "accent_bg": "#a60d27", "accent_hover": "#c41a37", "accent_soft": "#3a1a20",
      "slim": "#4a0612", "center": "#7d0a1e", "user": "#2b4a6a", "ok": "#5fd3a6", "warn_bg": "#3b2e14", "warn_line": "#d9a441"}
     if DARK else
     {"bg": "#ffffff", "surface": "#f5f5f5", "surface2": "#ebeced", "fg": "#1a1a1a", "fg2": "#2f475e", "muted": "#5c6f82",
      "line": "#c5c7c9", "accent": "#a60d27", "accent_bg": "#a60d27", "accent_hover": "#6f030c", "accent_soft": "#f4e2e5",
      "slim": "#630817", "center": "#a60d27", "user": "#17324d", "ok": "#008055", "warn_bg": "#f6e4c8", "warn_line": "#995c00"})
BIG = state.get("big_text", False)
st.markdown(f"""
<style>
@font-face {{ font-family:"Titillium Web"; src:url("app/static/fonts/titillium-web-v10-latin-ext_latin-regular.woff2") format("woff2"); font-weight:400; font-display:swap; }}
@font-face {{ font-family:"Titillium Web"; src:url("app/static/fonts/titillium-web-v10-latin-ext_latin-600.woff2") format("woff2"); font-weight:600; font-display:swap; }}
@font-face {{ font-family:"Titillium Web"; src:url("app/static/fonts/titillium-web-v10-latin-ext_latin-700.woff2") format("woff2"); font-weight:700; font-display:swap; }}
:root {{ --ov-accent:{C['accent']}; }}
html {{ font-size:{'19px' if BIG else '16px'}; color-scheme:{'dark' if DARK else 'light'}; }}
html, body, .stApp {{ overflow-x:hidden; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background:{C['bg']} !important; color:{C['fg']}; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea, .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
  font-family:"Titillium Web", Geneva, Tahoma, sans-serif !important; }}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], footer {{ display:none !important; }}
[data-testid="stMainBlockContainer"], .block-container {{ max-width:780px !important; padding:0 16px 3rem !important; }}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMarkdownContainer"] p, .stApp [data-testid="stMarkdownContainer"] li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp [data-testid="stWidgetLabel"] p, .stApp [data-testid="stCheckbox"] p,
.stApp [data-testid="stRadio"] p, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] p, [data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {{ color:{C['fg']} !important; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color:{C['muted']} !important; }}
.stApp a {{ color:{C['accent']}; text-underline-offset:3px; }}
.stApp a:hover {{ color:{C['accent_hover'] if not DARK else C['fg']}; }}
.stApp h2 {{ font-size:1.55rem !important; font-weight:700 !important; margin-top:1.4rem !important; }}
.stApp h3 {{ font-size:1.2rem !important; font-weight:700 !important; }}
:focus-visible {{ outline:3px solid {C['fg']} !important; outline-offset:2px; }}
/* full-bleed header: slim bar + centre band (Modello Comuni) */
.ov-bleed {{ width:100vw; position:relative; left:50%; margin-left:-50vw; direction:ltr; }}
.ov-slim {{ background:{C['slim']}; color:#fff; font-size:.85rem; }}
.ov-shell {{ max-width:780px; margin:0 auto; padding:0 16px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
.ov-slim .ov-shell {{ min-height:40px; justify-content:space-between; }}
.ov-slim .ov-mode {{ font-weight:600; opacity:.95; padding:1px 9px; border:1px solid rgba(255,255,255,.75); border-radius:999px; cursor:help; white-space:nowrap; }}
.ov-center {{ background:{C['center']}; color:#fff; }}
.ov-center .ov-shell {{ min-height:92px; padding-top:14px; padding-bottom:14px; }}
.ov-center {{ margin-bottom:10px; }}
.ov-brand {{ display:grid; gap:2px; }}
.ov-brand-name {{ font-size:2rem; line-height:1.1; font-weight:700; letter-spacing:-.01em; color:#fff; }}
.ov-brand-sub {{ font-size:1rem; color:#fff; opacity:.92; }}
.ov-callout {{ border-left:4px solid {C['warn_line']}; background:{C['warn_bg']}; color:{C['fg']}; padding:10px 14px; border-radius:4px; margin:14px 0 4px; font-size:.95rem; }}
.ov-callout b {{ display:block; }}
.ov-callout.appt {{ border-left-color:{C['accent_bg']}; background:{C['accent_soft']}; }}
.ov-live {{ display:inline-block; font-size:.78rem; font-weight:600; padding:1px 8px; border-radius:999px; background:#fff; color:#630817; }}
/* tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap:4px; border-bottom:2px solid {C['line']}; }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ padding:10px 14px !important; }}
[data-testid="stTabs"] [data-baseweb="tab"] p {{ font-size:1.05rem !important; font-weight:600 !important; color:{C['fg2']} !important; }}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p {{ color:{C['accent']} !important; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background:{C['accent']} !important; height:3px !important; }}
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ display:none; }}
/* buttons */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{ border-radius:4px !important; font-weight:600 !important; min-height:44px; }}
[data-testid="stElementContainer"]:has(style), [data-testid="stElementContainer"]:has(> .stHtml:empty) {{ display:none !important; }}
.stApp [data-testid^="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] p, .stApp [data-testid^="stBaseLinkButton-secondary"] p,
.stApp [data-testid^="stBaseButton-tertiary"] [data-testid="stMarkdownContainer"] p {{ color:{C['accent']} !important; }}
.stApp [data-testid^="stBaseButton-primary"] [data-testid="stMarkdownContainer"] p, .stApp [data-testid^="stBaseLinkButton-primary"] p,
.stApp [data-testid^="stBaseLinkButton-primary"] span {{ color:#fff !important; }}
[data-testid^="stBaseLinkButton-secondary"] {{ border:2px solid {C['accent']} !important; background:{C['bg']} !important; border-radius:4px !important; }}
[data-testid^="stBaseLinkButton-primary"] {{ border:2px solid {C['accent_bg']} !important; background:{C['accent_bg']} !important; border-radius:4px !important; }}
[data-testid^="stBaseLinkButton"] span[data-testid="stIconMaterial"], [data-testid^="stBaseButton"] span[data-testid="stIconMaterial"] {{ color:inherit !important; }}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondary"]:focus:not(:active) {{ background:{C['bg']} !important; color:{C['accent']} !important; border:2px solid {C['accent']} !important; }}
[data-testid="stBaseButton-secondary"] p {{ color:{C['accent']} !important; }}
[data-testid="stBaseButton-secondary"]:hover {{ background:{C['accent_soft']} !important; }}
[data-testid="stBaseButton-primary"] {{ background:{C['accent_bg']} !important; border:2px solid {C['accent_bg']} !important; color:#fff !important; }}
[data-testid="stBaseButton-primary"] p {{ color:#fff !important; }}
[data-testid="stBaseButton-primary"]:hover {{ background:{C['accent_hover']} !important; border-color:{C['accent_hover']} !important; }}
[data-testid="stBaseButton-tertiary"] p {{ color:{C['accent']} !important; text-decoration:underline; text-underline-offset:3px; }}
[data-testid="stBaseButton-secondary"]:disabled, [data-testid="stBaseButton-primary"]:disabled {{ opacity:.45; }}
[class*="st-key-persona-"] [data-testid="stBaseButton-secondary"] {{ text-align:start; justify-content:flex-start; border-width:1px !important; border-color:{C['line']} !important;
  border-left:4px solid {C['accent']} !important; color:{C['fg']} !important; padding:12px 14px !important; }}
[class*="st-key-persona-"] [data-testid="stBaseButton-secondary"] > div, [class*="st-key-persona-"] [data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] {{
  justify-content:flex-start !important; text-align:start !important; width:100%; }}
.stApp [class*="st-key-persona-"] [data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"] p {{ color:{C['fg']} !important; text-align:start; }}
[class*="st-key-persona-"] [data-testid="stBaseButton-secondary"] p {{ color:{C['fg']} !important; font-weight:400; font-size:1.02rem; }}
/* inputs */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="input"] > div, [data-baseweb="base-input"], .stTextInput input,
[data-testid="stDateInput"] input, [data-testid="stChatInput"] > div, [data-testid="stChatInputTextArea"] {{ background:{C['surface']} !important; color:{C['fg']} !important; border-color:{C['line']} !important; }}
[data-testid="stChatInputTextArea"]::placeholder, .stTextInput input::placeholder {{ color:{C['muted']} !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="calendar"], [data-baseweb="calendar"] * {{ background:{C['surface']} !important; color:{C['fg']} !important; }}
[data-testid="stSelectbox"] [data-baseweb="select"] div, [data-testid="stSelectbox"] [data-baseweb="select"] span {{ color:{C['fg']} !important; }}
[data-testid="stSelectbox"] svg {{ fill:{C['fg']} !important; }}
[data-testid="stSelectbox"] input {{ color:{C['fg']} !important; -webkit-text-fill-color:{C['fg']} !important; }}
[data-testid="stButtonGroup"] button:not([aria-checked="true"]):not([data-testid$="Active"]) span {{ color:{C['fg2']} !important; }}
.st-key-big_text label:has(input:not(:checked)) > span + div {{ background:{C['line']} !important; }}
[data-testid="stButtonGroup"] button {{ background:{C['bg']} !important; border-color:{C['line']} !important; }}
[data-testid="stButtonGroup"] button p {{ color:{C['fg2']} !important; }}
[data-testid="stCaptionContainer"] {{ opacity:1 !important; }}
.stApp [data-testid="stSelectbox"] div, .stApp [data-testid="stDateInputField"], .stApp [data-testid="stDateInputField"] * {{ background-color:{C['surface']} !important; color:{C['fg']} !important; }}
[data-testid="stTooltipIcon"] svg, [data-testid="stTooltipHoverTarget"] svg {{ color:{C['muted']} !important; opacity:1 !important; }}
[data-testid="stTooltipIcon"], [data-testid="stTooltipIcon"] button, [data-testid="stTooltipHoverTarget"] {{ opacity:1 !important; color:{C['muted']} !important; }}
[data-testid="stTooltipIcon"] svg, [data-testid="stTooltipIcon"] svg * {{ stroke:{C['muted']} !important; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{ white-space:normal !important; overflow:visible !important; text-overflow:clip !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:{C['accent_bg']} !important; border-color:{C['accent_bg']} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[aria-checked="true"] span {{ color:#fff !important; }}
[data-testid="stButtonGroup"] button[data-testid$="Active"] {{ background:{C['accent_bg']} !important; border-color:{C['accent_bg']} !important; }}
[data-testid="stButtonGroup"] button[data-testid$="Active"] p {{ color:#fff !important; }}
[data-testid="stExpander"] details {{ border-radius:4px !important; border-color:{C['line']} !important; background:{C['bg']}; }}
[data-testid="stExpander"] summary:hover p {{ color:{C['accent']} !important; }}
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlock"][class*="border"] {{ border-color:{C['line']} !important; border-radius:6px !important; }}
[data-testid="stMetric"] {{ background:{C['surface']}; border-radius:4px; padding:10px 12px; border-left:4px solid {C['accent']}; }}
[data-testid="stMetricValue"] {{ font-variant-numeric:tabular-nums; font-weight:700; }}
/* hero */
.ov-kicker {{ color:{C['accent']}; font-size:.82rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-top:1.4rem; }}
.ov-hero h1 {{ font-size:2.2rem !important; line-height:1.1 !important; margin:.25rem 0 .5rem !important; padding:0 !important; font-weight:700 !important; color:{C['fg']} !important; }}
.ov-lead {{ color:{C['fg2']}; font-size:1.08rem; line-height:1.5; }}
.ov-label {{ font-size:.8rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:{C['muted']}; margin:.6rem 0 .1rem; }}
.ov-note {{ color:{C['muted']}; font-size:.86rem; }}
.stApp ol.ov-how {{ padding-inline-start:0 !important; margin-inline-start:0 !important; }}
.stApp .ov-how li {{ margin:0 !important; }}
@media (max-width: 640px) {{ .ov-callout .more {{ display:none; }} }}
.ov-how {{ list-style:none; padding:0; margin:.9rem 0 .6rem; display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
.ov-how li {{ display:flex; gap:8px; align-items:flex-start; background:{C['surface']}; border-radius:4px; padding:10px 12px; font-size:.92rem; color:{C['fg']}; line-height:1.35; }}
.ov-how .n {{ flex:0 0 24px; height:24px; border-radius:50%; background:{C['accent_bg']}; color:#fff; font-weight:700; text-align:center; line-height:24px; font-size:.8rem; }}
@media (max-width: 640px) {{ .ov-how {{ grid-template-columns:1fr; gap:6px; }} .ov-how li {{ padding:7px 10px; }} }}
.ov-trust {{ color:{C['fg2']}; font-size:.86rem; border-left:3px solid {C['ok']}; padding:2px 10px; margin:.4rem 0 1rem; }}
.stApp p.ov-demo-line, .ov-demo-line {{ color:{C['muted']} !important; font-size:.84rem !important; margin:-.3rem 0 .5rem !important; line-height:1.4 !important; }}
.ov-summary-n {{ color:{C['fg']}; font-size:.95rem; margin:.35rem 0 .5rem; }}
details.ov-details {{ margin:2px 4px 10px; font-size:.86rem; color:{C['fg2']}; }}
details.ov-details summary {{ cursor:pointer; color:{C['muted']}; font-weight:600; }}
/* chat */
.ov-msg {{ display:flex; margin:12px 0 4px; }}
.ov-msg.user {{ justify-content:flex-end; }}
.ov-msg .ov-body {{ max-width:88%; }}
.ov-msg.user .ov-bubble {{ background:{C['user']}; color:#fff; border-radius:14px 14px 4px 14px; padding:10px 14px; }}
.ov-msg.bot .ov-bubble {{ background:{C['surface']}; color:{C['fg']}; border-radius:14px 14px 14px 4px; padding:12px 16px; border:1px solid {C['surface2']}; }}
.ov-msg .ov-bubble[dir="rtl"] {{ text-align:right; }}
.ov-bubble p {{ margin:0 0 .55em; line-height:1.5; }}
.ov-bubble p:last-child, .ov-bubble ul:last-child {{ margin-bottom:0; }}
.ov-bubble ul {{ margin:.2em 0 .55em; padding-inline-start:1.2em; }}
.ov-who {{ font-size:.78rem; font-weight:700; color:{C['muted']}; margin:0 4px 3px; }}
.ov-tag {{ font-weight:600; border:1px solid {C['line']}; border-radius:999px; padding:0 7px; margin-inline-start:6px; color:{C['muted']}; }}
.ov-from {{ font-size:.78rem; opacity:.85; display:block; margin-bottom:2px; }}
.ov-cite {{ display:inline-block; font-size:.78em; font-weight:600; padding:0 7px; margin:0 1px; border-radius:999px; background:{C['accent_soft']}; color:{C['accent']} !important;
  text-decoration:none !important; white-space:nowrap; vertical-align:baseline; border:1px solid transparent; }}
.ov-cite:hover {{ border-color:{C['accent']}; }}
.ov-meta {{ margin:6px 4px 0; font-size:.84rem; color:{C['fg2']}; display:grid; gap:4px; }}
.ov-fn-ref {{ display:inline-block; min-width:1.25em; padding:0 4px; margin-inline-start:2px; border-radius:999px; font-size:.72em; line-height:1.4;
  font-weight:700; text-align:center; vertical-align:super; background:{C['accent_soft']}; color:{C['accent']} !important; text-decoration:none !important; }}
.ov-fn {{ list-style:none; margin:2px 0 0; padding:0; display:grid; gap:2px; }}
.ov-fn li {{ font-size:.82rem; color:{C['fg2']}; }}
.ov-fn .n {{ display:inline-block; min-width:1.3em; margin-inline-end:6px; padding:0 4px; border-radius:999px; text-align:center; font-weight:700;
  font-size:.75rem; background:{C['accent_soft']}; color:{C['accent']}; }}
.ov-fn a {{ color:{C['fg2']} !important; }}
.ov-mt {{ font-size:.74rem; font-weight:600; color:{C['muted']}; border:1px dashed {C['line']}; border-radius:999px; padding:0 8px; display:inline-block; margin:2px 0 4px; }}
.ov-sum {{ background:{C['surface']}; border-radius:6px; padding:10px 14px; margin:4px 0 10px; }}
.ov-sum ol {{ margin:4px 0 0; padding-inline-start:1.4em; }}
.ov-sum li {{ margin:2px 0; color:{C['fg']}; font-size:.95rem; }}
.ov-sum li.done {{ color:{C['muted']}; text-decoration:line-through; }}
.ov-sum .sec {{ color:{C['muted']}; font-size:.8rem; }}
.ov-act {{ display:flex; gap:10px; padding:8px 0; border-bottom:1px solid {C['surface2']}; }}
.ov-act:last-child {{ border-bottom:0; }}
.ov-act .n {{ flex:0 0 28px; height:28px; border-radius:50%; background:{C['accent_bg']}; color:#fff; font-weight:700; text-align:center; line-height:28px; }}
.ov-act .why {{ color:{C['fg2']}; font-size:.86rem; }}
.ov-sec {{ font-weight:700; color:{C['fg']}; margin:12px 0 2px; }}
.ov-sec small {{ font-weight:400; color:{C['muted']}; }}
.ov-housing {{ border-left:4px solid {C['accent']}; background:{C['accent_soft']}; padding:6px 10px; border-radius:3px; margin:4px 0 6px; color:{C['fg']}; }}
.ov-route {{ margin:4px 0 0; padding-inline-start:1.1em; }}
.ov-route li {{ margin:2px 0; }}
.ov-step.done {{ opacity:.75; }}
.st-key-other-cases [data-testid^="stBaseButton"] {{ height:auto; text-align:start; }}
.st-key-other-cases [data-testid^="stBaseButton"] *, .st-key-other-cases [data-testid="stMarkdownContainer"] p {{
  white-space:normal !important; overflow:visible !important; text-overflow:clip !important; text-align:start; }}
.ov-step.done .n {{ background:{C['ok']}; }}
.ov-chips {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.ov-chip {{ display:inline-block; font-size:.8rem; padding:2px 9px; border-radius:4px; border:1px solid {C['line']}; background:{C['bg']}; color:{C['fg']} !important; text-decoration:none !important; }}
.ov-chip:hover {{ border-color:{C['accent']}; }}
.ov-chip small {{ color:{C['muted']}; }}
.ov-check {{ color:{C['ok']}; font-weight:600; }}
.ov-tool {{ margin:4px 0; font-size:.9rem; color:{C['fg']}; }}
.ov-tool code {{ font-size:.8rem; background:{C['surface']}; color:{C['fg2']}; padding:1px 6px; border-radius:3px; border:1px solid {C['surface2']}; }}
.ov-check.warn {{ color:{C['warn_line']}; }}
/* quotes of the official pages: one card per « » quote, with its page, publisher and date */
.ov-q {{ margin:10px 0 12px; padding:10px 14px 8px; background:{C['bg']}; border:1px solid {C['line']}; border-left:4px solid {C['accent']};
  border-radius:6px; text-align:start; }}
.ov-q-h {{ font-weight:700; font-size:.86rem; color:{C['fg2']}; margin:0 0 4px; line-height:1.35; }}
.stApp .ov-q blockquote.ov-q-t, .ov-q-t {{ margin:0 !important; padding:0 !important; border:0 !important; opacity:1 !important; font-style:normal; color:{C['fg']} !important;
  font-size:.95rem; line-height:1.5; overflow-wrap:anywhere; }}
.stApp .ov-q .ov-q-t p, .stApp .ov-q .ov-q-t li {{ color:{C['fg']} !important; }}
.stApp .ov-q [dir="ltr"], .stApp .ov-q [dir="ltr"] p, .stApp .ov-q [dir="ltr"] li, .stApp .ov-q [dir="ltr"] summary {{ text-align:left !important;
  direction:ltr; unicode-bidi:isolate; }}
.ov-q-t p {{ margin:0 0 .45em; }} .ov-q-t p:last-child {{ margin-bottom:0; }}
.ov-q-t ul {{ margin:.15em 0 .45em; padding-inline-start:1.2em; }} .ov-q-t li {{ margin:1px 0; }}
.ov-q-t li.sub {{ margin-inline-start:1.1em; list-style:circle; }}
.ov-q figcaption {{ font-size:.8rem; color:{C['muted']}; margin-top:7px; line-height:1.45; }}
.ov-q figcaption a {{ color:{C['accent']} !important; font-weight:600; }}
.ov-q-ok {{ color:{C['ok']}; font-weight:600; white-space:nowrap; }}
.ov-q-more {{ margin-top:4px; font-size:.86rem; }}
.ov-q-more summary {{ cursor:pointer; color:{C['accent']}; font-size:.8rem; font-weight:600; }}
.ov-q-more .ov-q-t {{ margin-top:6px; padding-top:6px; border-top:1px dashed {C['line']}; font-size:.9rem; color:{C['fg2']}; }}
[class*="st-key-qa-ex"] [data-testid^="stBaseButton-secondary"] {{ border-width:1px !important; border-radius:999px !important; min-height:36px;
  padding:4px 14px !important; }}
[class*="st-key-qa-ex"] [data-testid^="stBaseButton-secondary"] p {{ font-weight:600; font-size:.92rem; }}
/* checklist */
.ov-card-h {{ font-size:1.15rem; font-weight:700; color:{C['fg']}; margin:0; }}
.ov-card-sub {{ color:{C['muted']}; font-size:.88rem; margin:2px 0 6px; }}
.ov-bar {{ height:6px; background:{C['surface2']}; border-radius:3px; overflow:hidden; margin:6px 0 10px; }}
.ov-bar > span {{ display:block; height:100%; background:{C['ok']}; }}
.ov-src {{ font-size:.82rem; color:{C['muted']}; margin:-6px 0 10px 28px; }}
[dir="rtl"] .ov-src {{ margin:-6px 28px 10px 0; }}
.ov-src a {{ color:{C['accent']}; }}
.ov-src details summary {{ cursor:pointer; color:{C['fg2']}; display:inline; }}
.ov-src blockquote {{ margin:4px 0; padding:4px 10px; border-left:3px solid {C['line']}; color:{C['fg2']}; font-style:italic; }}
.ov-group {{ font-size:.86rem; color:{C['fg2']}; margin:12px 0 2px; padding-top:8px; border-top:1px solid {C['surface2']}; }}
.ov-cat {{ font-size:.82rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:{C['accent']}; margin:18px 0 0; padding-bottom:4px; border-bottom:2px solid {C['accent']}; }}
.ov-group a {{ color:{C['accent']}; }}
.ov-step {{ display:flex; gap:10px; padding:8px 0; border-bottom:1px solid {C['surface2']}; color:{C['fg']}; font-size:.95rem; }}
.ov-step:last-child {{ border-bottom:0; }}
.ov-step .n {{ flex:0 0 26px; height:26px; border-radius:50%; background:{C['accent_bg']}; color:#fff; font-weight:700; text-align:center; line-height:26px; font-size:.85rem; }}
.ov-step .who {{ font-size:.78rem; font-weight:700; letter-spacing:.03em; text-transform:uppercase; color:{C['muted']}; }}
.ov-todo {{ padding:6px 0; border-top:1px dashed {C['line']}; color:{C['fg']}; font-size:.95rem; }}
.ov-todo .q {{ display:inline-block; width:22px; height:22px; line-height:20px; text-align:center; border-radius:50%; border:1px dashed {C['muted']}; color:{C['muted']}; font-weight:700; margin-inline-end:8px; }}
.ov-final {{ border-left:4px solid {C['accent_bg']}; padding:4px 10px; margin-top:8px; font-weight:600; color:{C['fg']}; font-size:.92rem; }}
.ov-office b {{ font-size:1.05rem; }}
.ov-office {{ padding:6px 0 8px; border-bottom:1px solid {C['surface2']}; }}
.ov-office .ov-hours {{ color:{C['fg2']}; font-size:.9rem; }}
.ov-warn {{ border-left:3px solid {C['warn_line']}; background:{C['warn_bg']}; color:{C['fg']}; padding:4px 10px; font-size:.86rem; margin-top:6px; border-radius:3px; }}
/* city tab */
.ov-badge {{ display:inline-block; font-size:.72rem; font-weight:700; letter-spacing:.05em; padding:1px 8px; border-radius:3px; background:{C['warn_bg']}; color:{C['fg']}; border:1px solid {C['warn_line']}; }}
.ov-formula {{ background:{C['surface']}; border-radius:4px; padding:10px 14px; font-size:.95rem; color:{C['fg']}; border-left:4px solid {C['fg2']}; }}
.ov-mail {{ border:1px solid {C['line']}; border-radius:6px; overflow:hidden; background:{C['bg']}; }}
.ov-mail-h {{ background:{C['surface']}; padding:8px 14px; font-size:.86rem; color:{C['fg2']}; border-bottom:1px solid {C['line']}; }}
.ov-mail-b {{ padding:12px 14px; font-size:.95rem; color:{C['fg']}; }}
.ov-mail-b .old {{ color:{C['muted']}; font-style:italic; }}
.ov-mail-b .new {{ margin-top:10px; padding:10px 12px; border:2px dashed {C['accent']}; border-radius:4px; background:{C['accent_soft']}; }}
.ov-mail-b .new a {{ word-break:break-all; font-weight:600; }}
.ov-mock {{ display:inline-block; font-size:.72rem; font-weight:700; letter-spacing:.05em; padding:2px 8px; border-radius:3px; background:{C['fg']}; color:{C['bg']}; margin-bottom:6px; }}
.ov-table-wrap {{ overflow-x:auto; border:1px solid {C['line']}; border-radius:4px; }}
.ov-table {{ border-collapse:collapse; width:100%; min-width:640px; font-size:.86rem; }}
.ov-table th {{ background:{C['surface']}; color:{C['fg']}; text-align:start; padding:8px 10px; border-bottom:2px solid {C['line']}; }}
.ov-table td {{ padding:8px 10px; border-bottom:1px solid {C['surface2']}; vertical-align:top; color:{C['fg']}; }}
.ov-table td.when {{ font-weight:700; white-space:nowrap; }}
.ov-table tr.day1 td.when {{ color:{C['ok']}; }}
.ov-group-h {{ font-weight:700; color:{C['fg']}; }}
.ov-foot {{ color:{C['muted']}; font-size:.8rem; margin-top:2.5rem; border-top:1px solid {C['line']}; padding-top:10px; }}
{'.ov-bleed { left:auto; right:50%; margin-left:0; margin-right:-50vw; }' if RTL_UI else ''}
{'[data-testid="stMainBlockContainer"] { direction: rtl; } [data-testid="stMainBlockContainer"] p, [data-testid="stMainBlockContainer"] li { text-align: right; }' if RTL_UI else ''}
{'[data-testid="stMainBlockContainer"] :is(p, li, .ov-step > div, .ov-todo, .ov-group, .ov-office, .ov-hours, .ov-foot) { unicode-bidi: plaintext; }' if RTL_UI else ''}
</style>""", unsafe_allow_html=True)

# ---------- helpers ----------
KNOWN = kb.sources()


def esc(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def is_rtl(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text or ""))


def source_meta(sid: str) -> dict:
    return kb.get_source(sid) or {"id": sid, "title": sid, "url": "", "retrieved_at": ""}


def short_label(sid: str) -> str:
    """A human label for a source: who published it ("Comune di Milano", "Polizia di Stato"), or the open dataset."""
    s = source_meta(sid)
    if s.get("id", "").startswith("ds") and (KNOWN.get(sid) or {}).get("kind") == "opendata":
        return f"{L('open_data')} {sid}"
    return s.get("publisher") or s.get("title") or sid


def cite_html(sid: str) -> str:
    """A small link to the official source, labelled with who published it (the id is in the tooltip)."""
    s = source_meta(sid)
    tip = esc(f"{s.get('title', '')} · {s.get('retrieved_at', '')} · [{sid}]")
    if s.get("url"):
        return (f'<a class="ov-cite" href="{esc(s["url"])}" target="_blank" rel="noopener" title="{tip}">'
                f'{esc(short_label(sid))} ↗</a>')
    return f'<span class="ov-cite" title="{tip}">{esc(short_label(sid))}</span>'


_INLINE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)|(https?://[^\s<>()\]]+[^\s<>()\].,;:!?])|\[([^\[\]\n]{1,80})\]")


def inline_html(raw: str, notes: list[str] | None = None) -> str:
    """Escape, then bold, links and numbered source notes. Only what Claude's replies use.

    A cited source id ([cie]) becomes a small number linking to the official page; `notes`
    collects the ids in order so the sources can be listed under the reply by name.
    """
    notes = [] if notes is None else notes

    def sub(m: re.Match) -> str:
        if m.group(2):
            return f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>'
        if m.group(3):
            return f'<a href="{m.group(3)}" target="_blank" rel="noopener">{m.group(3)}</a>'
        ids = validator.cited_source_ids(f"[{html.unescape(m.group(4))}]", KNOWN)
        if ids and all(i in KNOWN for i in ids):
            refs = []
            for i in ids:
                if i not in notes:
                    notes.append(i)
                meta = source_meta(i)
                tip = esc(f"{meta.get('title', '')} · {meta.get('publisher', '')}")
                refs.append(f'<a class="ov-fn-ref" href="{esc(meta.get("url") or "#")}" target="_blank" rel="noopener" '
                            f'title="{tip}">{notes.index(i) + 1}</a>')
            return "".join(refs)
        return m.group(0)
    s = html.escape(raw, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return _INLINE.sub(sub, s)


def md_html(text: str, notes: list[str] | None = None) -> str:
    notes = [] if notes is None else notes
    out = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [ln for ln in para.split("\n") if ln.strip()]
        bullet = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
        if lines and all(bullet.match(ln) for ln in lines):
            out.append("<ul>" + "".join(f"<li>{inline_html(bullet.sub('', ln), notes)}</li>" for ln in lines) + "</ul>")
        elif lines and len(lines) > 1 and all(bullet.match(ln) for ln in lines[1:]):  # "intro:" + bullets
            out.append(f"<p>{inline_html(lines[0], notes)}</p><ul>"
                       + "".join(f"<li>{inline_html(bullet.sub('', ln), notes)}</li>" for ln in lines[1:]) + "</ul>")
        elif lines:
            out.append("<p>" + "<br>".join(inline_html(ln, notes) for ln in lines) + "</p>")
    return "".join(out)


def footnotes_html(notes: list[str]) -> str:
    """The sources a reply cites, numbered as in the text, by name and with the date they were read."""
    if not notes:
        return ""
    items = []
    for n, sid in enumerate(notes, start=1):
        s = source_meta(sid)
        name = f"{short_label(sid)} · {s.get('title') or sid}"
        link = (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(name)}</a>' if s.get("url") else esc(name))
        items.append(f'<li><span class="n">{n}</span>{link} <small>· {esc(demo.format_date(s.get("retrieved_at")))}</small></li>')
    return f'<ol class="ov-fn">{"".join(items)}</ol>'


def chips_html(ids: list[str]) -> str:
    out = []
    for sid in ids:
        s = source_meta(sid)
        label = f"{esc(s.get('title') or sid)} <small>· {esc(s.get('retrieved_at') or '')}</small>"
        if s.get("url"):
            out.append(f'<a class="ov-chip" href="{esc(s["url"])}" target="_blank" rel="noopener" title="{esc(sid)}">{label}</a>')
        else:
            out.append(f'<span class="ov-chip" title="{esc(sid)}">{label}</span>')
    return "".join(out)


# ---------- quotes of the official pages («…» [source_id]) as cards ----------
QUOTE_RE = re.compile(r"«([^«»]{1,3000})»(?:\s*[,.;:]?\s*\[([^\[\]\n]{1,120})\](?!\())?")
CARD_MIN_WORDS = 6  # a shorter quote is a term («Sblocca carta»): it stays in the sentence
_PASSAGE_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"\n]*\")?\)")  # [text](url "title")
_PASSAGE_ITEM = re.compile(r"^(\s*)(?:[-*+•]|\d+[.)])\s+")
_ELLIPSIS_SPLIT = re.compile(r"\s*(?:\[\s*(?:\.{3}|…)\s*\]|\.{3}|…)\s*")


def passages_in_trace(trace: list[dict] | None) -> list[dict]:
    """The passages of the official pages a turn's tools returned (search_official_pages results,
    read_source pages), each with its page's title, publisher, url and dates."""
    out: list[dict] = []
    for step in trace or []:
        o = step.get("output")
        if not isinstance(o, dict):
            continue
        if step.get("tool") == "search_official_pages":
            out += [r for r in o.get("results") or [] if isinstance(r, dict) and r.get("text")]
        elif step.get("tool") == "read_source":
            page = {k: o.get(k) for k in ("source_id", "title", "publisher", "url", "updated_at", "saved_at")}
            out += [{**page, **p} for p in o.get("passages") or [] if isinstance(p, dict) and p.get("text")]
    return out


def norm_quote(text: str) -> str:
    """Text as the validator compares quotes (Markdown, spacing, typographic quotes and case don't count)."""
    fn = getattr(validator, "normalize_quote", None)
    return fn(text) if fn else re.sub(r"\s+", " ", text or "").strip().casefold()


def quote_passage(quote: str, sid: str | None, passages: list[dict]) -> tuple[dict | None, bool]:
    """The passage a quote comes from (same source, holding the quote's first part) and True; else any
    passage of that page (for its title and dates) and False; else (None, False)."""
    parts = [p for p in (_ELLIPSIS_SPLIT.split(quote) or []) if p.strip(" .,;:")]
    key = norm_quote(parts[0]).strip(" .,;:") if parts else ""
    same = [p for p in passages if not sid or p.get("source_id") == sid]
    held = next((p for p in same if key and key in norm_quote(p.get("text") or "")), None)
    return (held, True) if held else ((same[0] if same else None), False)


def passage_hrefs(text: str, base: str = "") -> set[str]:
    """The links of a saved passage, made absolute against the page URL: the only ones a quote card links."""
    return {urljoin(base, m.group(3)) if base else m.group(3) for m in _PASSAGE_LINK.finditer(text or "")}


def _passage_inline(text: str, base: str, allowed: set[str] | None = None) -> str:
    """One line of a passage: escaped, **bold**, links made absolute against the page URL, images left out.
    With `allowed`, a link whose target is not among them (a quote that altered a link) is shown as text."""
    out, last = [], 0

    def plain(s: str) -> str:
        s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", s)  # Markdown escapes of the saved page: "\_\_" is "__"
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(s, quote=False))
    for m in _PASSAGE_LINK.finditer(text):
        out.append(plain(text[last:m.start()]))
        if not m.group(1):  # an image says nothing to read
            href = urljoin(base, m.group(3)) if base else m.group(3)
            label = plain(m.group(2)) or esc(href)
            linkable = href.startswith(("http://", "https://")) and (allowed is None or href in allowed)
            out.append(f'<a href="{esc(href)}" target="_blank" rel="noopener">{label}</a>' if linkable else label)
        last = m.end()
    out.append(plain(text[last:]))
    return "".join(out)


def passage_html(text: str, base: str = "", allowed: set[str] | None = None) -> str:
    """A verbatim passage as HTML: its paragraphs, its lists (one level of nesting) and its links (with
    `allowed`, only those links; the others as text)."""
    blocks = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [ln for ln in para.split("\n") if ln.strip()]
        if not lines:
            continue
        items, prose = [], []
        for ln in lines:
            m = _PASSAGE_ITEM.match(ln)
            if m:
                cls = ' class="sub"' if len(m.group(1)) >= 2 else ""
                items.append(f"<li{cls}>{_passage_inline(ln[m.end():], base, allowed)}</li>")
            elif items:  # a line that continues the previous item
                items[-1] = items[-1][:-5] + " " + _passage_inline(ln.strip(), base, allowed) + "</li>"
            else:
                prose.append(_passage_inline(ln.strip(), base, allowed))
        if prose:
            blocks.append("<p>" + "<br>".join(prose) + "</p>")
        if items:
            blocks.append("<ul>" + "".join(items) + "</ul>")
    return "".join(blocks)


def quote_card_html(quote: str, sid: str, passages: list[dict], verified: bool, exact: bool = True) -> str:
    """A « » quote as a card: the quoted words (verbatim, in the page's language), the question or section
    it answers, the page (title, publisher, the page's own date or the day it was saved, link) and,
    when the passage goes on, the whole passage. A link inside the quote is a link only when the passage
    it comes from has it (a quote can't bring its own URL); `exact` False (an ellipsis skips words)
    labels the quote as shortened."""
    found, holds = quote_passage(quote, sid, passages)
    p = found or {}
    meta = source_meta(sid)
    url = p.get("url") or meta.get("url") or ""
    title = p.get("title") or meta.get("title") or sid
    publisher = p.get("publisher") or meta.get("publisher") or ""
    updated, saved = p.get("updated_at"), p.get("saved_at") or meta.get("retrieved_at")
    when = (L("qa_updated", date=demo.format_date(updated)) if updated
            else (L("qa_saved", date=demo.format_date(saved)) if saved else ""))
    heading = (p.get("heading") or "").split(" > ")[-1].strip() if holds else ""
    starts = norm_quote(quote)[:40]
    head = (f'<div class="ov-q-h">{esc(heading)}</div>'
            if heading and not starts.startswith(norm_quote(heading)[:40]) else "")
    full = ""
    if holds and p.get("text") and len(norm_quote(p["text"])) > len(norm_quote(quote)) + 60:
        full = (f'<details class="ov-q-more"><summary>{esc(L("qa_full"))}</summary>'
                f'<div class="ov-q-t">{passage_html(p["text"], url)}</div></details>')
    link = f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(title)} ↗</a>' if url else esc(title)
    parts = [f"<bdi>{x}</bdi>" for x in (esc(publisher), link, esc(when)) if x]  # Italian names in an Arabic line
    badge = (f' · <bdi class="ov-q-ok">✓ {esc(L("qa_verbatim" if exact else "qa_verbatim_parts"))}</bdi>'
             if verified else "")
    allowed = passage_hrefs(p.get("text") or "", url) if holds else set()
    return (f'<figure class="ov-q" data-source="{esc(sid)}"><div dir="ltr">{head}<blockquote class="ov-q-t">'
            f'{passage_html(quote, url, allowed)}</blockquote>{full}</div>'
            f'<figcaption dir="auto">📄 {" · ".join(parts)}{badge}</figcaption></figure>')


def quote_checks(m: dict) -> list[dict]:
    """Every quote of a reply with what the validator says about it (status, sources holding it, exact):
    checked against the turn's passages, with the agent's own list of verified quotes (which also counts
    the passages of earlier turns) taking precedence."""
    if not hasattr(validator, "verify_quotes"):
        return []
    texts = validator.official_texts_in_trace(m.get("trace") or [])
    found = validator.verify_quotes(m.get("text") or "", texts, KNOWN)
    agent_quotes = {norm_quote(q.get("text", "")): q for q in m.get("quotes") or [] if isinstance(q, dict)}
    for q in found:
        mine = agent_quotes.get(norm_quote(q["text"]))
        if mine:
            q.update(status="verified", exact=mine.get("exact", q.get("exact", True)),
                     source_ids=[mine.get("source_id")] + [s for s in q["source_ids"] if s != mine.get("source_id")])
    return found


def verified_quotes(m: dict) -> set[str]:
    """The quotes of a reply found word for word in the official text the tools returned (normalized)."""
    return {norm_quote(q["text"]) for q in quote_checks(m) if q["status"] == "verified"}


def answer_html(text: str, notes: list[str], m: dict) -> str:
    """A reply as HTML, with each « » quote of an official page followed by its [source_id] shown as a
    card (see quote_card_html); short quotes and the rest of the text as md_html renders them."""
    passages = passages_in_trace(m.get("trace"))
    checks = {norm_quote(q["text"]): q for q in quote_checks(m)} if "«" in text else {}
    out, last = [], 0
    for q in QUOTE_RE.finditer(text):
        quote, cited = q.group(1).strip(), q.group(2)
        ids = [i for i in (validator.cited_source_ids(f"[{cited}]", KNOWN) if cited else []) if i in KNOWN]
        if not ids or len(quote.split()) < CARD_MIN_WORDS:
            continue
        check = checks.get(norm_quote(quote)) or {}
        verified = check.get("status") == "verified"
        # the card names the page that holds the quote: a cited one the validator found it in, else the
        # first cited page whose passages hold it, else the first cited page (then without the badge)
        sid = next((i for i in check.get("source_ids") or [] if i in ids), None) if verified else None
        sid = sid or next((i for i in ids if quote_passage(quote, i, passages)[1]), None)
        verified = verified and sid is not None
        sid = sid or ids[0]
        out.append(md_html(text[last:q.start()], notes))
        out.append(quote_card_html(quote, sid, passages, verified, check.get("exact", True)))
        last = q.end() + len(re.match(r"[\s.,;:]*", text[q.end():]).group())  # "». Quindi" → "Quindi"
    out.append(md_html(text[last:], notes))
    return "".join(out)


def check_line(m: dict) -> str:
    check = m.get("check") or {}
    why_lang = "it" if state.lang == "it" else "en"
    if check.get("fallback"):
        why = validator.describe(check.get("blocked_again") or check.get("blocked", []), why_lang)
        return f'<div class="ov-check warn">⚠ {esc(L("check_fallback", why=why))}</div>'
    if check.get("blocked") and check.get("attempts", 1) > 1:
        why = validator.describe(check["blocked"], why_lang)
        return f'<div class="ov-check">✓ {esc(L("check_retry", why=why))}</div>'
    if check.get("blocked"):
        return f'<div class="ov-check warn">⚠ {esc(L("check_blocked", why=validator.describe(check["blocked"], why_lang)))}</div>'
    quotes = quote_checks(m) if passages_in_trace(m.get("trace")) else []
    if quotes and all(q["status"] == "verified" for q in quotes):  # every quote, not just one, was found
        return f'<div class="ov-check">{esc(L("check_ok_qa"))}</div>'
    if m.get("qa") or (passages_in_trace(m.get("trace")) and not any(x.get("tool") == "get_checklist" for x in m.get("trace") or [])):
        return f'<div class="ov-check">{esc(L("check_ok_plain"))}</div>'
    return f'<div class="ov-check">{esc(L("check_ok") if m.get("cited") else L("check_ok_plain"))}</div>'


def step_text(step: dict) -> str:
    out, args, tool = step.get("output"), step.get("input") or {}, step.get("tool")
    if isinstance(out, dict) and "error" in out:
        return L("step_error", tool=tool)
    if tool == "list_services":
        return L("step_list_services", n=len(out) if isinstance(out, list) else 0)
    if tool == "get_service":
        title = (out.get("title") or {}).get("it" if state.lang == "it" else "en", out.get("id"))
        return L("step_get_service", service=title, q=len(out.get("deciding_questions", [])), s=len(out.get("steps", [])))
    if tool == "get_checklist":
        answers = ", ".join(f"{k}={v}" for k, v in (args.get("answers") or {}).items()) or L("no_answers")
        return L("step_get_checklist", answers=answers, v=len(out.get("requirements", [])),
                 t=len(out.get("not_yet_verified", [])), o=len(out.get("still_to_ask", [])))
    if tool == "get_form_guide":
        return L("step_get_form_guide", n=len(out.get("sections", [])),
                 f=sum(len(x.get("items", [])) for x in out.get("sections", [])))
    if tool == "find_offices":
        area = args.get("area") or (f"Municipio {args['municipio']}" if args.get("municipio") else "lat/lon")
        return L("step_find_offices", area=area, n=len(out) if isinstance(out, list) else 0)
    if tool == "get_source":
        return L("step_get_source", title=out.get("title", args.get("source_id")))
    if tool == "search_official_pages":
        results = [r for r in out.get("results") or [] if isinstance(r, dict)]
        pages = len({r.get("source_id") for r in results})
        key = "step_search_none" if not results else ("step_search" if out.get("reason", "ok") == "ok" else "step_search_weak")
        return L(key, query=args.get("query", ""), n=len(results), p=pages)
    if tool == "read_source":
        return L("step_read_source", title=out.get("title") or args.get("source_id"), n=len(out.get("passages") or []))
    return f"{tool}"


def absorb(reply: dict) -> None:
    """Keep the latest checklist and offices the tools returned (live or demo)."""
    for step in reply.get("trace", []):
        out = step.get("output")
        if step.get("tool") == "get_checklist" and isinstance(out, dict) and "requirements" in out:
            state.checklist = out
            state.service_id = out["service_id"]
            state.answers = dict((step.get("input") or {}).get("answers") or {})
        if step.get("tool") == "find_offices" and isinstance(out, list) and out:
            state.offices = out
            if state.office_id not in {o["id"] for o in out}:
                state.office_id = out[0]["id"]
    if state.get("demo_state"):
        state.urgent = bool(state.demo_state.get("urgent"))


def ics(appointment: dt.date, service_id: str | None) -> str:
    def event(day: dt.date, title: str) -> str:
        d, nxt = day.strftime("%Y%m%d"), (day + dt.timedelta(days=1)).strftime("%Y%m%d")
        return (f"BEGIN:VEVENT\r\nUID:{uuid.uuid4()}@onevisit\r\nDTSTAMP:{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}\r\n"
                f"DTSTART;VALUE=DATE:{d}\r\nDTEND;VALUE=DATE:{nxt}\r\nSUMMARY:{title}\r\nEND:VEVENT\r\n")
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//OneVisit//EN\r\n"
            + event(appointment - dt.timedelta(days=3), LV("ics_check", service_id))
            + event(appointment, LV("ics_appt", service_id))
            + "END:VCALENDAR\r\n")


@st.cache_data(show_spinner=False, max_entries=64)
def dossier_pdf(service_id: str, answers_json: str, office_id: str | None, date_iso: str | None,
                ticked: tuple[str, ...], today_iso: str, lang: str = "it") -> bytes:
    return dossier.build_pdf(service_id, json.loads(answers_json), office_id=office_id, appointment=date_iso,
                             ticked=set(ticked), today=dt.date.fromisoformat(today_iso), lang=lang)


def current_day() -> dt.date | None:
    """Appointment date: what the citizen picked, else the date from the booking link."""
    if state.get("appt_day"):
        return state.appt_day
    preset = (state.appointment or {}).get("date")
    return dt.date.fromisoformat(preset) if preset else None


def ticked_ids(cl: dict) -> set[str]:
    return {r["id"] for r in cl.get("requirements", []) if state.get(f"have-{cl['service_id']}-{r['id']}")}


def current_pdf(cl: dict, day: dt.date | None) -> bytes:
    return dossier_pdf(cl["service_id"], json.dumps(state.answers, sort_keys=True), state.office_id,
                       day.isoformat() if day else None, tuple(sorted(ticked_ids(cl))), dt.date.today().isoformat(),
                       state.lang)


def reset() -> None:
    for k in ("messages", "chat"):
        state[k] = []
    for k in ("checklist", "offices", "service_id", "demo_state", "appointment", "office_id", "pending", "notice"):
        state[k] = None
    state.answers = {}
    state.urgent = False
    state.pop("appt_day", None)


# ---------- processing a turn ----------
def queue(kind: str, **kw: object) -> None:
    state.pending = {"kind": kind, **kw}


def on_chat_submit() -> None:
    text = (state.get("chat_text") or "").strip()
    if text:
        queue("text", text=text)


def follow_language(text: str) -> str:
    """Switch the page to the language the person writes in (Arabic, Chinese, Spanish…), from the next run."""
    guessed = guess_lang(text) if len(text or "") >= 12 else None
    if "¿" in (text or "") or "¡" in (text or ""):  # Spanish, whatever words it shares with Italian
        guessed = "es"
    if guessed in LANGS and guessed != state.lang:
        state["_lang_next"] = guessed
        return guessed
    return state.lang


def run_live(text: str, origin: str | None = None) -> bool:
    """One turn with Claude. False when this session can't use Claude (cap reached or API down):
    the caller then answers the same message in demo mode, so the page never shows an error."""
    if not take_live_call():
        state.notice = "limit"
        return False
    state.chat.append({"role": "user", "text": text, "origin": origin})
    n = len(state.messages)
    state.messages.append({"role": "user", "content": text})
    try:
        extra = {"service_id": state.service_id} if TURN_TAKES_SERVICE and state.service_id else {}
        reply = run_turn(state.messages, client=client(), lang=state.get("_lang_next") or state.lang, **extra)
    except Exception:  # no key that works, no credit, no network: continue without Claude
        del state.messages[n:]
        state.chat.pop()
        state.live_off = "down"
        state.notice = "down"
        return False
    absorb(reply)
    state.chat.append({"role": "assistant", **reply})
    return True


def demo_text(text: str, origin: str | None = None) -> None:
    """A typed message without Claude: keyword rules pick the service and answers, the tools do the rest."""
    lang = state.get("_lang_next") or state.lang
    state.chat.append({"role": "user", "text": text, "origin": origin})
    # an answer, a new case, or a question answered from the saved official pages (the case is kept)
    state.demo_state, reply = demo.respond(state.demo_state, text, lang)
    # one detector: the page follows the language the replay answered in (the question's, or English for a
    # language the replay can't write), so the buttons and labels match the reply
    if reply.get("lang") in LANGS and reply.get("lang") != lang:
        state["_lang_next"] = reply["lang"]
    absorb(reply)
    state.chat.append({"role": "assistant", **reply})


def demo_question(text: str) -> None:
    """An example question (a chip) without Claude: always answered from the saved official pages,
    whatever its words; a case in progress is kept and its pending question offered again."""
    lang = state.get("_lang_next") or state.lang
    state.chat.append({"role": "user", "text": text})
    if state.demo_state is None:
        state.demo_state = demo.new_state(None, lang, persona=None, routing="keywords")
    reply = demo.ask(state.demo_state, text, lang)
    absorb(reply)
    state.chat.append({"role": "assistant", **reply})


def process(pending: dict) -> None:
    kind = pending["kind"]
    appt = state.appointment or {}
    if kind == "appointment":
        service = kb.get_service(appt["service_id"]) or {}
        title = demo.service_title(service, state.lang) if service else appt["service_id"]
        if LIVE:
            if appt.get("date") or appt.get("office_id"):
                msg = L("dl_user_msg", service=title, date=demo.format_date(appt.get("date")) or "—",
                        office=appt.get("office_address") or "—")
            else:
                msg = L("dl_user_msg_service", service=title)
            if run_live(msg, origin=link_origin(appt)):
                return
        state.demo_state, reply = demo.start_appointment(appt["service_id"], appt.get("office_id"),
                                                         appt.get("date"), state.lang)
        absorb(reply)
        state.chat.append({"role": "assistant", **reply})
        return
    if kind == "persona":
        persona = demo.personas()[pending["id"]]
        lang = pending.get("lang") or state.lang
        if lang != state.lang:
            state["_lang_next"] = lang  # "the same person writes in Arabic": the whole page follows
        if LIVE and run_live(persona["opening"].get(lang) or persona["opening"]["en"]):
            return
        state.demo_state, user_text, reply = demo.start_persona(pending["id"], lang)
        state.chat.append({"role": "user", "text": user_text})
        absorb(reply)
        state.chat.append({"role": "assistant", **reply})
        return
    text = pending["text"]
    follow_language(text)
    if LIVE and run_live(text):
        return
    if kind == "question":
        demo_question(text)
        return
    demo_text(text)


# ---------- header ----------
# Live: the badge names the model. Demo replay: a chip, not a banner across the first screen; its tooltip says
# what the replay is, and every replayed reply is signed "OneVisit · replica", never "Claude".
mode = (f'<span class="ov-live">{esc(L("live_badge", model=MODEL))}</span>' if LIVE
        else f'<span class="ov-mode" title="{esc(L("demo_banner") + ". " + L("demo_banner_more").strip())}">'
             f'{esc(L("demo_chip"))}</span>')
st.markdown(
    f'<div class="ov-bleed ov-slim"><div class="ov-shell" dir="{"rtl" if RTL_UI else "ltr"}"><span>{esc(L("slim"))}</span>{mode}</div></div>'
    f'<div class="ov-bleed ov-center"><div class="ov-shell" dir="{"rtl" if RTL_UI else "ltr"}"><div class="ov-brand">'
    f'<span class="ov-brand-name">OneVisit</span><span class="ov-brand-sub">{esc(L("brand_sub"))}</span></div></div></div>',
    unsafe_allow_html=True)

with st.container(horizontal=True, vertical_alignment="center", gap="small"):
    st.selectbox(L("lang_label"), list(LANGS), format_func=LANGS.get, key="lang", label_visibility="collapsed", width=150)
    st.segmented_control(L("theme_label"), ["light", "dark"], key="theme_mode", label_visibility="collapsed",
                         format_func=lambda m: ("☀ " + L("theme_light")) if m == "light" else ("☾ " + L("theme_dark")))
    st.toggle(L("big_text"), key="big_text")

if state.get("notice"):  # Claude went unreachable or the cap was reached: say so, then carry on in demo mode
    st.markdown(f'<div class="ov-callout" dir="{"rtl" if RTL_UI else "ltr"}"><b>{esc(L("notice_" + state.notice))}</b></div>',
                unsafe_allow_html=True)

citizen, panel = st.tabs([L("tab_citizen"), L("tab_city")])


def local_req(sid: str, r: dict, field: str = "text") -> tuple[str, bool]:
    """A requirement in the page language (Claude's translation for ar/es/zh, flagged)."""
    return kb.req_text(sid, r, state.lang, field)


def req_help(r: dict, sid: str, translated: bool) -> str:
    parts = []
    if translated:
        parts.append(f'{L("original_it")}: {r.get("text_it")}')
    if r.get("quote"):
        parts.append(f'{L("quote_label")} · {short_label(r["source_id"])} · {source_meta(r["source_id"]).get("title")}: «{r["quote"]}»')
    return "\n\n".join(parts)


def report_form(prefix: str, service_id: str) -> None:
    """A report after the appointment: personal details removed by code, then classified by Claude
    (live) or, in the demo, Claude's recorded classification of the example reports."""
    fb_labels = {L("fb_ok"): "ok", L("fb_missing"): "missing", L("fb_other"): "other"}
    choice = fb_labels[st.radio(L("fb_outcome"), list(fb_labels), horizontal=True, key=f"{prefix}-outcome", index=1)]
    examples = outcomes.example_notes("it" if state.lang == "it" else "en")
    if examples:
        st.caption(L("fb_examples"))
        with st.container(horizontal=True, gap="small"):
            for k, ex in enumerate(examples):
                st.button(ex[:70] + ("…" if len(ex) > 70 else ""), key=f"{prefix}-ex-{k}", type="tertiary",
                          on_click=lambda ex=ex: state.update({f"{prefix}_note": ex}))
    note = st.text_area(L("fb_note"), key=f"{prefix}_note", height=90)
    if not LIVE:
        st.caption(L("fb_demo"))
    if not st.button(L("fb_send"), key=f"{prefix}-send", disabled=not (note or "").strip()):
        return
    clean, removed = outcomes.scrub(note)
    if removed:
        st.info(L("fb_scrubbed", kinds=", ".join(dict.fromkeys(L("pii_" + k) for k in removed))))
    result, recorded = None, False
    if LIVE and take_live_call():
        with st.spinner(L("fb_spinner")):
            try:
                result = outcomes.classify(service_id, choice, clean, client=client())
            except Exception as e:
                st.error(L("error", e=type(e).__name__))
    else:
        result, recorded = outcomes.recorded_classification(note), True
    if result:
        row = outcomes.save_report(service_id, choice, result)
        label = (CAUSES_IT if state.lang == "it" else outcomes.CAUSES)[row["cause"]][0]
        st.success(L("fb_thanks", cause=label, summary=row["summary_it" if state.lang == "it" else "summary_en"]))
        if recorded:
            st.caption(L("fb_recorded"))
    elif not LIVE:
        st.warning(L("fb_need_claude"))


def route_actions(route: dict, sid: str, primary: bool = False) -> None:
    """The next step the case's route leads to (demo.case_route, from the data): not served in Milan (no
    booking, the procedures to do first), the home-service form, the PIN/PUK booking links, no visit or
    no appointment (a note), the online form, or the City's booking page."""
    kind = "primary" if primary else "secondary"
    links_now = kb.service_links(sid)
    if route["kind"] == "stop":
        st.markdown(f'<div class="ov-warn">{esc(L("route_stop"))}</div>', unsafe_allow_html=True)
        if route["services"]:
            st.caption(L("route_first"))
            for s in route["services"]:
                title = demo.service_title(kb.get_service(s["id"]) or {"id": s["id"]}, state.lang)
                st.link_button(title, s["url"], type=kind, icon=":material/open_in_new:")
    elif route["links"]:
        if route["kind"] == "home":
            st.caption(L("route_home"))
        with st.container(horizontal=True, gap="small"):
            for link in route["links"]:
                st.link_button(demo.link_label(link, state.lang), link["url"], type=kind, icon=":material/open_in_new:")
    elif links_now.get("online_form_url"):
        st.link_button(LV("online_btn", sid), links_now["online_form_url"]["url"], type=kind, icon=":material/open_in_new:")
    elif route["kind"] in ("info", "walk-in"):
        st.caption(L("route_info" if route["kind"] == "info" else "route_walkin"))
    elif route["booking"] and links_now.get("booking_url") and not state.appointment:
        st.link_button(L("book"), links_now["booking_url"]["url"], type=kind, icon=":material/open_in_new:")


def question_chips(key: str) -> None:
    """The example questions about the ID card, as chips in the page language: each one is asked as a
    question (Claude live; without a key, the replay's search of the saved official pages)."""
    with st.container(horizontal=True, gap="small", key=key):
        for ex in demo.example_questions(state.lang):
            st.button(ex["label"], key=f"{key}-{ex['id']}", on_click=queue, args=("question",),
                      kwargs={"text": ex["query"]}, help=ex["query"])


# ---------- citizen ----------
with citizen:
    appt = state.appointment
    if appt:
        service = kb.get_service(appt["service_id"]) or {}
        office = next((o for o in state.offices or [] if o["id"] == appt.get("office_id")), None)
        parts = [demo.service_title(service, state.lang), demo.format_date(appt.get("date")),
                 demo.office_where(office) if office else appt.get("office_address")]
        icon = "📅" if appt.get("channel") == "prenotazione" else "🔗"
        st.markdown(f'<div class="ov-callout appt"><b>{icon} {esc(link_origin(appt))}</b>{esc(" · ".join(p for p in parts if p))}</div>',
                    unsafe_allow_html=True)

    if not state.chat and not state.pending:
        st.markdown(f'<div class="ov-hero"><div class="ov-kicker">{esc(L("kicker"))}</div><h1>{esc(L("h1"))}</h1>'
                    f'<p class="ov-lead">{esc(L("lead"))}</p></div>', unsafe_allow_html=True)
        if not LIVE:  # one line, under the title: what the replay is (the header chip has the rest)
            live_link = (f' <a href="?lang={state.lang}" target="_self">{esc(L("live_link"))} →</a>'
                         if FORCE_DEMO and SERVER_KEY and not state.get("live_off") else "")
            st.markdown(f'<p class="ov-demo-line">{esc(L("demo_line"))}{live_link}</p>', unsafe_allow_html=True)
        catalogue = [r for r in KNOWN.values() if r.get("status") == "ok"]
        pages = [r for r in catalogue if r.get("kind") != "opendata"]
        publishers = ", ".join(dict.fromkeys(r["publisher"] for r in pages if r.get("publisher")))
        verified = sum(x["verified_requirements"] for x in kb.list_services())
        updated = max((r.get("retrieved_at") or "" for r in catalogue), default="")
        # The cases first: a juror (or a newcomer) can start in one tap without scrolling.
        st.markdown(f'<div class="ov-label">{esc(L("examples_title"))}</div>', unsafe_allow_html=True)
        everyone = demo.personas()
        for pid, persona in everyone.items():
            if not persona.get("featured"):
                continue
            with st.container(key=f"persona-{pid}"):
                st.markdown(f'<div class="ov-note" style="margin:.5rem 0 0;line-height:1.6">{esc(persona["label"].get(state.lang) or persona["label"]["en"])}</div>',
                            unsafe_allow_html=True)
                st.button(persona["opening"].get(state.lang) or persona["opening"]["en"], key=f"ex-{pid}",
                          on_click=queue, args=("persona",), kwargs={"id": pid, "lang": state.lang}, width="stretch")
                alt = persona.get("alt_lang")
                if alt and alt != state.lang:
                    st.button(f'{L("try_alt_" + alt)}: {persona["opening"][alt]}', key=f"ex-{pid}-{alt}", type="tertiary",
                              on_click=queue, args=("persona",), kwargs={"id": pid, "lang": alt})
        # Or just a question: answered from the saved official pages (Claude live, keyword search in the replay).
        st.markdown(f'<div class="ov-label">{esc(L("qa_examples_title"))}</div>', unsafe_allow_html=True)
        question_chips("qa-ex")
        st.caption(L("qa_examples_note" if LIVE else "qa_examples_note_demo"))
        others = [(pid, p) for pid, p in everyone.items() if not p.get("featured")]
        if others:
            st.markdown(f'<div class="ov-label">{esc(L("other_cases"))}</div>', unsafe_allow_html=True)
            with st.container(horizontal=True, gap="small", key="other-cases"):
                for pid, persona in others:
                    alt = persona.get("alt_lang")
                    lang = alt if alt else state.lang
                    label = persona["label"].get(state.lang) or persona["label"]["en"]
                    if alt and alt != state.lang:
                        label += f" · 🌐 {LANGS.get(alt, alt)}"
                    st.button(label, key=f"ex-{pid}", on_click=queue, args=("persona",), kwargs={"id": pid, "lang": lang})
        st.markdown(f'<p class="ov-note" style="margin-top:.8rem">{esc(L("type_hint" if LIVE else "type_hint_demo"))} '
                    f'{esc(L("note"))}</p><p class="ov-trust">🔎 {esc(L("trust", p=len(pages), pubs=publishers, d=len(catalogue) - len(pages), v=verified, date=demo.format_date(updated)))}</p>',
                    unsafe_allow_html=True)
        how = "".join(f'<li><span class="n">{n}</span><span>{esc(x)}</span></li>' for n, x in enumerate(L("how").split("|"), start=1))
        with st.expander(L("how_title")):
            st.markdown(f'<ol class="ov-how">{how}</ol>', unsafe_allow_html=True)

    last_assistant = max((i for i, m in enumerate(state.chat) if m["role"] == "assistant"), default=-1)

    def render_message(i: int, m: dict, folded: bool = False) -> None:
        """One chat message. A replayed reply is signed "OneVisit · replica" and says the tools read the sources:
        only a live reply is signed by Claude. Inside the folded conversation the trace is a <details>
        (Streamlit expanders can't be nested)."""
        if m["role"] == "user":
            origin = f'<span class="ov-from">↳ {esc(m["origin"])}</span>' if m.get("origin") else ""
            st.markdown(f'<div class="ov-msg user"><div class="ov-body"><div class="ov-bubble" dir="{"rtl" if is_rtl(m["text"]) else "auto"}">'
                        f'{origin}{esc(m["text"])}</div></div></div>', unsafe_allow_html=True)
            return
        by_demo = bool(m.get("demo"))
        if m.get("routing") == "search":
            tag = f'<span class="ov-tag">{esc(L("qa_tag"))}</span>'
        elif m.get("routing") == "keywords":
            tag = f'<span class="ov-tag">{esc(L("keywords_tag"))}</span>'
        else:
            tag = f'<span class="ov-tag">{esc(L("recorded"))}</span>' if by_demo else ""
        notes: list[str] = []
        body = answer_html(m["text"], notes, m) if "«" in (m.get("text") or "") else md_html(m["text"], notes)
        read = m.get("sources_read") or []
        suffix = "_demo" if by_demo else ""
        passages = passages_in_trace(m.get("trace"))
        pages = list(dict.fromkeys(p.get("source_id") for p in passages if p.get("source_id")))
        read_line = (f'<div>🔎 {esc(L("read_passages" + suffix, n=len(passages), p=len(pages)))}</div>' if passages else "")
        case_work = any(step.get("tool") == "get_checklist" for step in m.get("trace") or [])
        others = [r for r in read if r not in pages] if passages else read
        if others and (case_work or not passages):  # the sources of the case's tools, besides the pages searched
            read_line += f'<div>📚 {esc(L("read_1" + suffix) if len(others) == 1 else L("read_n" + suffix, n=len(others)))}</div>'
        meta = (f'<div class="ov-meta" dir="{"rtl" if RTL_UI else "ltr"}">{read_line}{footnotes_html(notes)}'
                f'{check_line(m) if m.get("check") else ""}</div>')
        st.markdown(f'<div class="ov-msg bot"><div class="ov-body">'
                    f'<div class="ov-who">{esc(L("assistant_demo") if by_demo else L("assistant"))}{tag}</div>'
                    f'<div class="ov-bubble" dir="{"rtl" if is_rtl(m["text"]) else "ltr"}">{body}</div>'
                    f'{meta}</div></div>', unsafe_allow_html=True)
        if m.get("trace"):
            label = L("checked_demo") if by_demo else L("what_checked")
            inner = ("".join(f"<div class='ov-tool'><code>{esc(s.get('tool'))}</code> {esc(step_text(s))}</div>" for s in m["trace"])
                     + (f'<div class="ov-chips" style="margin-top:8px">{chips_html(read)}</div>' if read else "")
                     + f'<p class="ov-note" style="margin-top:8px">{esc(L("validator_note"))}</p>')
            if folded:
                st.markdown(f'<details class="ov-details"><summary>{esc(label)}</summary>{inner}</details>', unsafe_allow_html=True)
            else:
                with st.expander(label):
                    st.markdown(inner, unsafe_allow_html=True)
        if i == last_assistant and m.get("options") and not state.pending:
            with st.container(horizontal=True, gap="small"):
                for j, opt in enumerate(m["options"]):
                    st.button(opt, key=f"opt-{i}-{j}", on_click=queue, args=("text",), kwargs={"text": opt})

    cl_now = state.checklist
    case_done = bool(cl_now and "requirements" in cl_now and not cl_now.get("still_to_ask")
                     and not state.pending and last_assistant >= 0)
    if case_done:
        # The case is clear: lead with what to do, fold the earlier turns (the last reply stays open).
        sid_now = cl_now["service_id"]
        files_now = kb.to_upload(cl_now)
        links_now = kb.service_links(sid_now)
        route_now = demo.case_route(sid_now, state.answers)
        with st.container(border=True, key="summary"):
            title = demo.service_title(kb.get_service(sid_now) or {"id": sid_now}, state.lang)
            # nothing to bring (a question only, or not served here): no "To bring: 0"
            bring = ("" if route_now["kind"] == "stop" or not files_now
                     else f'{LR("upload_title", sid_now, route_now["kind"], n=len(files_now))} · ')
            st.markdown(f'<p class="ov-card-h">✓ {esc(L("summary_title"))}</p>'
                        f'<p class="ov-card-sub">{esc(title)}</p>'
                        f'<p class="ov-summary-n">{esc(bring)}'
                        f'{esc(L("cl_counts", v=len(cl_now["requirements"]), t=len(cl_now.get("not_yet_verified", []))))}</p>',
                        unsafe_allow_html=True)
            # The one action that sends the case, as the answers' route says (see route_actions).
            route_actions(route_now, sid_now, primary=True)
        earlier = list(range(last_assistant))
        if len(earlier) >= 3:  # at least one question and its answer: fold them, keep the last reply open
            with st.expander(L("conv_title", n=len(earlier))):
                for i in earlier:
                    render_message(i, state.chat[i], folded=True)
        else:
            for i in earlier:
                render_message(i, state.chat[i])
        for i in range(last_assistant, len(state.chat)):
            render_message(i, state.chat[i])
    else:
        for i, m in enumerate(state.chat):
            render_message(i, m)

    if state.pending:
        pending = state.pending
        if pending["kind"] == "text":
            st.markdown(f'<div class="ov-msg user"><div class="ov-body"><div class="ov-bubble">{esc(pending["text"])}</div></div></div>',
                        unsafe_allow_html=True)
        with st.spinner(L("spinner") if LIVE else L("spinner_demo")):
            state.pending = None
            process(pending)
        st.rerun()

    # ---- path, next actions, checklist, online form, offices, dossier ----
    cl = state.checklist
    if cl and "requirements" in cl:
        sid = cl["service_id"]
        service = kb.get_service(sid) or {}
        links = service.get("links") or {}
        steps = service.get("steps") or []
        complete = not cl.get("still_to_ask")

        # Claude translates what the cache lacks (live only): the Italian stays the text that counts.
        if LIVE and state.lang not in ("it", "en") and (sid, state.lang) not in state.translated:
            state.translated.add((sid, state.lang))
            if kb.missing_translations(sid, state.lang) and take_live_call():
                with st.spinner(L("translating")):
                    try:
                        translate.ensure(sid, state.lang, client())
                    except Exception:
                        pass  # English stays on screen; nothing invented

        # The path follows the answers' route: no desk steps for someone not served in Milan or who needs no
        # visit; the home-service form or the PIN/PUK booking instead of "book online"; no booking step for a walk-in.
        case_rt = demo.case_route(sid, state.answers)
        if case_rt["kind"] in ("stop", "info"):
            steps = []
        elif case_rt["kind"] == "walk-in":
            steps = [x for x in steps if not x.get("booking")]
        if case_rt["links"]:
            items = "".join(f'<li><a href="{esc(link["url"])}" target="_blank" rel="noopener">{esc(demo.link_label(link, state.lang))}</a> '
                            f'{cite_html(link["source_id"])}</li>' for link in case_rt["links"])
            with st.container(border=True, key="steps"):
                st.markdown(f'<p class="ov-card-h">🧭 {esc(L("steps_title"))}</p>'
                            f'<div class="ov-step"><span class="n">1</span><div><div class="who">{esc(L("route_step_title"))}</div>'
                            f'<ul class="ov-route">{items}</ul></div></div>', unsafe_allow_html=True)
                if links.get("official_url"):
                    st.link_button(L("official_link"), links["official_url"]["url"], icon=":material/open_in_new:")
            steps = []
        if steps:
            with st.container(border=True, key="steps"):
                st.markdown(f'<p class="ov-card-h">🧭 {esc(L("steps_title"))}</p>'
                            f'<p class="ov-card-sub">{esc(L("steps_sub", n=len(steps)))}</p>', unsafe_allow_html=True)
                rows = []
                for n, step in enumerate(sorted(steps, key=lambda x: x.get("order", 0)), start=1):
                    title, _ = kb.step_text(sid, step, state.lang, "title")
                    bodies = [step.get("ente")] + [r.get("ente") for r in step.get("routes") or []]
                    who = " · ".join(f"<bdi>{esc(x)}</bdi>" for x in [title, " / ".join(dict.fromkeys(demo.ente_name(b) for b in bodies if b))] if x)
                    text, _ = kb.step_text(sid, step, state.lang)
                    if step.get("booking") and state.appointment and state.appointment.get("date"):
                        when = demo.format_date(state.appointment.get("date"))
                        rows.append(f'<div class="ov-step done"><span class="n">✓</span><div><div class="who">{who}</div>'
                                    f'{esc(L("step_booked", when=when))}</div></div>')
                        continue
                    if step.get("routes"):
                        items = [f'<li>{esc(text)} {cite_html(step["source_id"])}</li>']
                        for k, route in enumerate(step["routes"], start=1):
                            rtext, _ = kb.route_text(sid, step, k, state.lang)
                            items.append(f'<li>{esc(rtext)} {cite_html(route["source_id"])}</li>')
                        body = f'{esc(L("step_routes"))}<ul class="ov-route">{"".join(items)}</ul>'
                    else:
                        body = f'{esc(text)} {cite_html(step["source_id"]) if step.get("source_id") else ""}'
                    rows.append(f'<div class="ov-step"><span class="n">{n}</span><div><div class="who">{who}</div>{body}</div></div>')
                st.markdown("".join(rows), unsafe_allow_html=True)
                with st.container(horizontal=True, gap="small"):
                    if links.get("online_form_url") and not case_done:  # once done, the summary card has it
                        st.link_button(LV("online_btn", sid), links["online_form_url"]["url"], type="primary", icon=":material/open_in_new:")
                    if links.get("official_url"):
                        st.link_button(L("official_link"), links["official_url"]["url"], icon=":material/open_in_new:")

        reqs, todo = cl.get("requirements", []), cl.get("not_yet_verified", [])
        ticked = ticked_ids(cl)

        # The next 3 actions, once the case is clear: Claude orders the verified items; code checks every action.
        if reqs and complete:
            plan_key = json.dumps([sid, state.answers, state.lang, (state.appointment or {}).get("date")], sort_keys=True)
            result = state.plans.get(plan_key)
            if result is None and LIVE and take_live_call():
                with st.spinner(L("actions_spinner")):
                    try:
                        result = plan.claude_actions(sid, dict(state.answers), state.lang, client=client(),
                                                     appointment=(state.appointment or {}).get("date"))
                    except Exception:  # shown from the data instead; not retried on every rerun
                        result = {"actions": [], "rejected": [], "by": "claude", "failed": True}
                state.plans[plan_key] = result
            if not result or not result.get("actions"):
                result = plan.fallback_actions(sid, dict(state.answers), state.lang, ticked=ticked)
            by_id = {r["id"]: r for r in reqs}
            rows = []
            for n, a in enumerate(result["actions"], start=1):
                done = all(x in ticked for x in a["requirement_ids"])
                why = f'<div class="why">{esc(a["why"])}</div>' if a.get("why") else ""
                cites = "".join(cite_html(s) for s in a.get("source_ids", []))
                action = a["action"] if result["by"] == "claude" else local_req(sid, by_id[a["requirement_ids"][0]])[0]
                strike = ' style="text-decoration:line-through"' if done else ""
                rows.append(f'<div class="ov-act"><span class="n">{"✓" if done else n}</span><div>'
                            f'<div{strike}>{esc(action)} {cites}</div>{why}</div></div>')
            if result["by"] == "claude":
                with st.container(border=True, key="actions"):
                    st.markdown(f'<p class="ov-card-h">➡ {esc(L("actions_title"))}</p>'
                                f'<p class="ov-card-sub">{esc(L("actions_by_claude", model=result.get("model", MODEL)))}</p>'
                                + "".join(rows), unsafe_allow_html=True)
                    if result.get("rejected"):
                        st.caption(L("actions_rejected", n=len(result["rejected"])))
            elif rows:
                with st.expander(f'➡ {L("actions_title")} · {L("actions_demo_tag")}'):
                    st.markdown(f'<p class="ov-card-sub">{esc(L("actions_by_data"))}</p>' + "".join(rows), unsafe_allow_html=True)

        total = max(len(reqs) + len(todo), 1)
        with st.container(border=True, key="checklist"):
            n_sources = len({r["source_id"] for r in reqs})
            # Once the case is clear the summary card above already names the service and the counts.
            sub = [] if case_done else [demo.service_title(service, state.lang), L("cl_counts", v=len(reqs), t=len(todo))]
            sub += [L("cl_sources", n=n_sources)] if n_sources > 1 else []
            st.markdown(f'<p class="ov-card-h">✓ {esc(L("cl_title"))}</p>'
                        f'<p class="ov-card-sub">{esc(" · ".join(sub))}</p>'
                        f'<div class="ov-bar"><span style="width:{100 * len(reqs) / total:.0f}%"></span></div>', unsafe_allow_html=True)
            any_translated = state.lang not in ("it", "en") and any(local_req(sid, r)[1] for r in reqs)
            if any_translated:
                st.markdown(f'<span class="ov-mt">🌐 {esc(L("translated"))}</span>', unsafe_allow_html=True)
            if reqs and case_rt["kind"] != "stop":  # the one dossier download on the page (none if not served here)
                st.download_button(L("dossier_btn"), current_pdf(cl, current_day()),
                                   dossier.filename(sid, current_day()), "application/pdf",
                                   type="primary", icon=":material/download:", key="dossier-pdf-top", on_click="ignore")
                st.caption(f'{LR("dossier_title", sid, case_rt["kind"])}. {LR("dossier_cap", sid, case_rt["kind"])}')
            # The files to upload (online) or the things to bring (desk), at a glance.
            files = kb.to_upload(cl)
            if files:
                head = LR("upload_title", sid, case_rt["kind"], n=len(files))
                sections = {s["id"]: s for s in ((kb.form_guide(sid, state.answers) or {}).get("sections") or [])}
                items = []
                for r in files:
                    name, _ = local_req(sid, r, "short")
                    sec = sections.get(r.get("form_section") or "")
                    sec_label = f' <span class="sec">· {esc(kb.localized(sid, "section", sec["id"], "title", sec.get("title_it"), sec.get("title_en"), state.lang)[0])}</span>' if sec else ""
                    items.append(f'<li class="{"done" if r["id"] in ticked else ""}">{esc(name)}{sec_label}</li>')
                st.markdown(f'<div class="ov-sum"><b>{esc(head)}</b><ol>{"".join(items)}</ol></div>', unsafe_allow_html=True)
            if reqs and case_rt["kind"] != "stop":
                st.caption(L("cl_tick"))
            # Grouped by category (what to prepare, how it works, if urgent, afterwards), then by source,
            # so every item sits under the official page it was verified on.
            by_category: dict[str, list[dict]] = {}
            for r in reqs:
                by_category.setdefault(r.get("category") or "prepare", []).append(r)
            order = [c for c in kb.CATEGORIES if c in by_category] + [c for c in by_category if c not in kb.CATEGORIES]
            if state.urgent and "if-urgent" in order:  # in a hurry: the urgent options come first, open
                order = ["if-urgent"] + [c for c in order if c != "if-urgent"]

            def requirement_rows(items: list[dict]) -> None:
                by_source: dict[str, list[dict]] = {}
                for r in items:
                    by_source.setdefault(r["source_id"], []).append(r)
                for src, group in sorted(by_source.items(), key=lambda kv: -len(kv[1])):  # largest source first
                    s = source_meta(src)
                    title = (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s.get("title"))}</a>'
                             if s.get("url") else esc(s.get("title")))
                    checked = max((r.get("verified_at") or "" for r in group), default="")
                    st.markdown(f'<div class="ov-group">{L("source_line", title=f"{esc(short_label(src))} · {title}", date=esc(demo.format_date(checked)))}</div>',
                                unsafe_allow_html=True)
                    for r in group:
                        text, translated = local_req(sid, r)
                        st.checkbox(text, key=f"have-{sid}-{r['id']}", help=req_help(r, src, translated) or None)

            for category in order:
                items = by_category[category]
                label = f"{demo.category_label(category, state.lang)} · {len(items)}"
                if category == "prepare" or (category == "if-urgent" and state.urgent):
                    st.markdown(f'<div class="ov-cat">{esc(label)}</div>', unsafe_allow_html=True)
                    requirement_rows(items)
                else:
                    with st.expander(label):
                        requirement_rows(items)
            if todo:
                rows = []
                for item in kb.open_items(sid, todo):
                    text, _ = kb.localized(sid, "req", item["id"], "text", item.get("text_it"), item.get("text_en"), state.lang)
                    rows.append(f'<div class="ov-todo"><span class="q">?</span>{esc(text or item["id"])} · '
                                f'<a href="{esc(item["url"])}" target="_blank" rel="noopener">{esc(L("open_page"))}</a></div>')
                st.markdown(f'<p class="ov-label">{esc(L("todo_title"))}</p><p class="ov-note">{esc(L("todo_note"))}</p>' + "".join(rows),
                            unsafe_allow_html=True)
            if cl.get("still_to_ask"):
                qs = [demo.question_text(sid, q, state.lang) for q in service.get("deciding_questions", [])
                      if q["id"] in cl["still_to_ask"]]
                st.caption(L("still_ask", qs=" · ".join(qs)))
            if case_rt["kind"] != "stop":  # not served here: no desk, no final check at a desk
                st.markdown(f'<div class="ov-final">{esc(LV("final_check", sid))}</div>', unsafe_allow_html=True)

        # How to fill in the City's online application, section by section (residence from abroad).
        guide = kb.form_guide(sid, state.answers) if service.get("has_form_guide") and complete else None
        if guide and guide.get("sections"):
            with st.container(border=True, key="form-guide"):
                st.markdown(f'<p class="ov-card-h">📝 {esc(L("form_title"))}</p>'
                            f'<p class="ov-card-sub">{esc(L("form_sub"))}</p>', unsafe_allow_html=True)
                with st.expander(L("form_open", n=len(guide["sections"]))):
                    n_files = done_files = 0
                    for sec in guide["sections"]:
                        title, _ = kb.localized(sid, "section", sec["id"], "title", sec.get("title_it"), sec.get("title_en"), state.lang)
                        verbatim = state.lang != "it" and sec.get("title_it", "") in (sec.get("quote") or "")
                        st.markdown(f'<div class="ov-sec">{esc(title)} {cite_html(sec["source_id"])}'
                                    f'{" <small>· «" + esc(sec["title_it"]) + "»</small>" if verbatim else ""}</div>',
                                    unsafe_allow_html=True)
                        sec_text, _ = kb.localized(sid, "section", sec["id"], "text", sec.get("text_it"), sec.get("text_en"), state.lang)
                        if sec_text:
                            st.markdown(f'<div class="ov-note">{esc(sec_text)}</div>', unsafe_allow_html=True)
                        if sec["id"] == "abitazione" and guide.get("housing_option"):
                            h = guide["housing_option"]
                            label, _ = kb.localized(sid, "housing", h["answer"], "label", h.get("label_it"), h.get("label_en"), state.lang)
                            st.markdown(f'<div class="ov-housing">{esc(L("form_housing"))} <b>{esc(label)}</b>'
                                        f'{" (« " + esc(h["label_it"]) + " »)" if state.lang != "it" else ""} {cite_html(h["source_id"])}</div>',
                                        unsafe_allow_html=True)
                        for item in sec["items"]:
                            text, translated = local_req(sid, item)
                            if sec["id"] in ("nel-modulo", "invio"):
                                st.markdown(f'<div class="ov-tool">• {esc(text)} {cite_html(item["source_id"])}</div>', unsafe_allow_html=True)
                                continue
                            n_files += 1
                            short, _ = local_req(sid, item, "short")
                            if st.checkbox(f'{short or text} · {L("form_ready")}', key=f"form-{sid}-{item['id']}",
                                           help=f"{text}\n\n{L('original_it')}: {item.get('text_it')}" if translated else text):
                                done_files += 1
                    if n_files:
                        st.progress(done_files / n_files, text=L("form_done", d=done_files, n=n_files))
                st.caption(L("form_note"))

    office_route = demo.case_route(state.service_id, state.answers) if state.service_id else None
    if state.offices and not (office_route and office_route["kind"] == "stop"):  # not served in Milan: no office to go to
        service_booking = (kb.service_links(state.service_id).get("booking_url") if state.service_id else None) or {}
        booking = service_booking or kb.get_source("prenotazione") or {}
        if office_route and not (office_route["booking"] or office_route["kind"] == "none"):
            booking = {}  # the route has its own next step (home form, PIN/PUK booking, no appointment)
        with st.container(border=True, key="offices"):
            st.markdown(f'<p class="ov-card-h">📍 {esc(L("off_title"))} {cite_html(state.offices[0].get("source_id", "ds549"))}</p>'
                        f'<p class="ov-card-sub">{esc(L("off_src"))}</p>', unsafe_allow_html=True)
            for o in state.offices:
                where = o["address"] + (f" ({o['entrance_note']})" if o.get("entrance_note") else "")
                confirmed = (f' {cite_html(o["entrance_confirmed_by"]["source_id"])}' if o.get("entrance_confirmed_by") else "")
                extra = f'<div class="ov-note">{esc(L("off_no_spid"))}</div>' if o.get("booking_without_spid") else ""
                issues = "".join(f'<div class="ov-warn">{esc(L("off_note", issue=x))}</div>' for x in o.get("data_issues", []))
                st.markdown(f'<div class="ov-office"><b>{esc(where)}</b>{confirmed}{" · Municipio " + str(o["municipio"]) if o.get("municipio") else ""}'
                            f'<div class="ov-hours">{esc(o.get("hours_it"))}</div>{extra}{issues}</div>', unsafe_allow_html=True)
            if len(state.offices) > 1:
                by_address = {o["address"]: o["id"] for o in state.offices}
                current = next((a for a, i in by_address.items() if i == state.office_id), None)
                picked = st.radio(L("off_pick"), list(by_address), horizontal=True,
                                  index=list(by_address).index(current) if current else 0)
                state.office_id = by_address[picked]
            if booking.get("url") and not state.appointment:
                st.link_button(L("book"), booking["url"], icon=":material/open_in_new:")
            elif office_route and office_route["kind"] == "desk" and office_route["links"] and not state.appointment:
                with st.container(horizontal=True, gap="small"):
                    for link in office_route["links"]:
                        st.link_button(demo.link_label(link, state.lang), link["url"], icon=":material/open_in_new:")

    # No appointment and nothing to report afterwards when the case is not served here or needs no visit.
    if cl and "requirements" in cl and demo.case_route(cl["service_id"], state.answers)["kind"] not in ("stop", "info"):
        with st.container(border=True, key="reminder"):
            st.markdown(f'<p class="ov-card-h">📅 {esc(L("remind_title"))}</p>'
                        f'<p class="ov-card-sub">{esc(L("remind_cap"))}</p>', unsafe_allow_html=True)
            preset = (state.appointment or {}).get("date")
            preset_day = dt.date.fromisoformat(preset) if preset else None
            day = st.date_input(LV("appt_date", cl["service_id"]), value=preset_day, format="DD/MM/YYYY", key="appt_day",
                                min_value=min(dt.date.today(), preset_day or dt.date.today()))
            if day:
                st.download_button(L("ics_btn"), ics(day, cl["service_id"]), "onevisit.ics", "text/calendar", key="ics",
                                   icon=":material/event:", on_click="ignore")
                st.caption(L("ics_cap"))

        # After the appointment: one report, scrubbed of personal details, classified by Claude.
        with st.expander(LV("fb_title", cl["service_id"])):
            report_form("fb", state.service_id or cl["service_id"])

    if state.chat and state.service_id in (None, demo.QA_SERVICE):  # questions stay one tap away, also mid-case
        with st.expander(f'💬 {L("qa_examples_more")}'):
            question_chips("qa-ex2")
    st.chat_input(L("chat_placeholder") if LIVE else L("chat_placeholder_demo"), key="chat_text", on_submit=on_chat_submit,
                  max_chars=search.MAX_QUERY_CHARS)  # a message, not a pasted page
    if state.chat:
        st.button(L("new_conv"), on_click=reset, type="tertiary", icon=":material/refresh:")

    if not SERVER_KEY:
        with st.expander(L("key_title")):
            st.text_input(L("key_label"), type="password", key="api_key", help=L("key_help"))
            st.caption(L("key_cap"))

# ---------- City panel ----------
with panel:
    lang_city = "it" if state.lang == "it" else "en"
    st.markdown(f'<h2>{esc(L("city_title"))}</h2>', unsafe_allow_html=True)
    st.caption(L("city_cap"))

    ctx = kb.context_tables()
    arrivals = {r["year"]: r for r in ctx.get("arrivals-from-abroad", [])}
    res = {r["group"]: r for r in ctx.get("residence-2022-helped-by-group", [])}
    arrivals_2024 = int(arrivals.get("2024", {}).get("registrations_from_abroad", 0) or 0)
    other_comuni_2024 = int(arrivals.get("2024", {}).get("registrations_from_other_comuni", 0) or 0)
    c1, c2, c3 = st.columns(3)
    c1.metric(L("kpi1"), f"{arrivals_2024:,}".replace(",", "." if lang_city == "it" else ","), help=L("kpi1_help"))
    if res:
        c2.metric(L("kpi2"), f"{res['Straniero']['helped_little_or_not_pct']}%", help=L("kpi2_help"))
        c3.metric(L("kpi3"), f"{res['Italiano']['helped_little_or_not_pct']}%", help=L("kpi3_help"))

    # Expected impact: a formula with assumptions the staff can move, labelled as an estimate. The two bases are
    # the 2024 registrations the app's two residence procedures serve (ds1959); ID cards have no sourced volume.
    st.markdown(f'<h3>{esc(L("impact_title"))} <span class="ov-badge">{esc(L("impact_badge"))}</span></h3>'
                f'<div class="ov-formula">{esc(L("impact_formula"))}</div>', unsafe_allow_html=True)
    i1, i2 = st.columns(2)
    p1 = i1.slider(L("impact_p1a"), 5, 50, 20, 5, format="%d%%", key="impact-abroad")
    p1b = i2.slider(L("impact_p1b"), 0, 50, 10, 5, format="%d%%", key="impact-comuni")
    i3, i4 = st.columns(2)
    p2 = i3.slider(L("impact_p2"), 5, 80, 30, 5, format="%d%%", key="impact-use")
    p3 = i4.slider(L("impact_p3"), 10, 90, 50, 10, format="%d%%", key="impact-avoided")
    avoided = round((arrivals_2024 * p1 / 100 + other_comuni_2024 * p1b / 100) * p2 / 100 * p3 / 100)

    def num(n: int) -> str:
        return f"{n:,}".replace(",", "." if lang_city == "it" else ",")
    st.markdown(f'<div class="ov-formula" style="border-left-color:{C["accent"]}"><b style="font-size:1.4rem">≈ {num(avoided)}</b> '
                f'{esc(L("impact_result"))}<br><span class="ov-note">({num(arrivals_2024)} × {p1}% + {num(other_comuni_2024)} × {p1b}%)'
                f' × {p2}% × {p3}%. {esc(L("impact_scope"))}</span></div>', unsafe_allow_html=True)
    st.caption(L("impact_note"))

    # Day one: one line in the email the City already sends.
    st.markdown(f'<h3>{esc(L("day1_title"))}</h3>', unsafe_allow_html=True)
    st.markdown(f'<p>{esc(L("day1_lead"))}</p>', unsafe_allow_html=True)
    example_office = next((o for o in kb.find_offices(area="Isola", limit=1)), None)
    example_date = (dt.date.today() + dt.timedelta(days=16)).isoformat()
    shown = deeplink.build("carta-identita", example_office["id"] if example_office else None, example_date, lang_city)
    href = "?" + shown.split("?", 1)[1] + ("&demo=1" if FORCE_DEMO else "")
    st.markdown(
        f'<div class="ov-mock">{esc(L("mock_label"))}</div>'
        f'<div class="ov-mail"><div class="ov-mail-h">{esc(L("mock_subject"))}</div><div class="ov-mail-b">'
        f'<div class="old">{esc(L("mock_existing"))}</div>'
        f'<div class="new">{esc(L("mock_added"))}<br><a href="{esc(href)}" target="_self">{esc(shown)}</a></div>'
        f'</div></div><p class="ov-note" style="margin-top:6px">{esc(L("mock_try"))}</p>', unsafe_allow_html=True)

    # The same link, without office and date, in the YesMilano student guide (the student path the City runs).
    yes = deeplink.build("iscrizione-anagrafica-extra-ue", lang=lang_city, channel="yesmilano")
    yes_href = "?" + yes.split("?", 1)[1] + ("&demo=1" if FORCE_DEMO else "")
    st.markdown(
        f'<div class="ov-mock" style="margin-top:14px">{esc(L("mock_page_label"))}</div>'
        f'<div class="ov-mail"><div class="ov-mail-h">{esc(L("mock_yes_subject"))}</div><div class="ov-mail-b">'
        f'<div class="old">{esc(L("mock_yes_existing"))}</div>'
        f'<div class="new">{esc(L("mock_yes_added"))}<br><a href="{esc(yes_href)}" target="_self">{esc(yes)}</a></div>'
        f'</div></div><p class="ov-note" style="margin-top:6px">{esc(L("mock_yes_try"))}</p>', unsafe_allow_html=True)

    st.markdown(f'<h3>{esc(L("proactive_title"))}</h3><p class="ov-note">{esc(L("proactive_lead"))}</p>', unsafe_allow_html=True)
    head = "".join(f"<th>{esc(L(k))}</th>" for k in ("col_step", "col_data", "col_owner", "col_privacy", "col_when"))
    body = "".join(
        f'<tr class="{"day1" if n < 2 else ""}"><td><b>{esc(a)}</b></td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td><td class="when">{esc(e)}</td></tr>'
        for n, (a, b, c, d, e) in enumerate(PROACTIVE[lang_city]))
    st.markdown(f'<div class="ov-table-wrap"><table class="ov-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
                unsafe_allow_html=True)

    # Reports after appointments, grouped, with Claude's drafts for a person to approve.
    st.markdown(f'<h3>{esc(L("reports_title"))}</h3>', unsafe_allow_html=True)
    st.caption(L("reports_cap", k=outcomes.THRESHOLD))
    with st.expander(L("try_report")):
        services = {s["id"]: demo.service_title(kb.get_service(s["id"]) or {}, lang_city) for s in kb.list_services()}
        report_service = st.selectbox(L("try_report_service"), list(services), format_func=services.get, key="city-service")
        report_form("city", report_service)
    causes = CAUSES_IT if lang_city == "it" else outcomes.CAUSES
    for g in outcomes.groups():
        key = f"{g['service_id']}|{g['cause']}"
        tag = (f" · {L('simulated')}" if g["simulated"] == g["count"]
               else (f" · {L('n_simulated', n=g['simulated'])}" if g["simulated"] else ""))
        status = L("ready") if g["over_threshold"] else L("below")
        label, recipient = causes.get(g["cause"], (g["cause_label"], g["recipient"]))
        with st.container(border=True):
            st.markdown(f'<div class="ov-group-h">{esc(L("reports_n", n=g["count"]))} · {esc(label)}</div>'
                        f'<div class="ov-note">{esc(g["service_id"])}{esc(tag)} · {esc(L("to"))}: {esc(recipient)} · <b>{esc(status)}</b></div>',
                        unsafe_allow_html=True)
            for ex in g["examples_it" if lang_city == "it" else "examples_en"]:
                st.caption(f"“{ex}”")
            if key in state.approved:
                st.success(L("approved"))
            elif key in state.drafts:
                with st.container(border=True):
                    if not LIVE:
                        st.caption(L("draft_recorded"))
                    st.markdown(state.drafts[key])
                if st.button(L("approve"), key=f"ap-{key}", type="primary"):
                    state.approved.add(key)
                    st.rerun()
            elif LIVE:
                if st.button(L("draft_btn"), key=f"dr-{key}") and take_live_call():
                    with st.spinner(L("draft_spinner")):
                        try:
                            state.drafts[key] = outcomes.draft_fix(g, client=client())
                        except Exception as e:
                            st.error(L("error", e=type(e).__name__))
                    st.rerun()
            else:
                recorded = demo.draft(g)
                if st.button(L("draft_btn_demo"), key=f"dr-{key}", disabled=not recorded):
                    state.drafts[key] = recorded
                    st.rerun()

    st.markdown(f'<h3>{esc(L("data_title"))}</h3>', unsafe_allow_html=True)
    st.caption(L("data_cap"))
    for o in [o for o in kb.find_offices(limit=1000) if o.get("data_issues") or o.get("dataset_notes")]:
        st.markdown(f'**{esc(o["address"])}** {cite_html(o.get("source_id", "ds549"))}', unsafe_allow_html=True)
        for issue in o.get("data_issues", []) + o.get("dataset_notes", []):
            st.markdown(f"- {issue}")

st.markdown(f'<div class="ov-foot">{esc(L("foot"))}</div>', unsafe_allow_html=True)
