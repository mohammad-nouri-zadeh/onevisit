"""The app end to end (streamlit.testing): typed text, language switch, booked appointment, online
form guide, sourced footnotes, Claude's next actions, the fallback to demo and the request cap."""

from __future__ import annotations

import json
import pathlib

import pytest
from fakes import FakeClient, text, tool
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = str(ROOT / "app" / "streamlit_app.py")


def _app(**query) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def _md(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def _answer_all(at: AppTest, prefer: tuple[str, ...] = ()) -> None:
    for _ in range(6):
        options = [b for b in at.button if (b.key or "").startswith("opt-")]
        if not options:
            return
        wanted = [b for b in options if b.label in prefer]
        (wanted or options)[0].click().run()
        assert not at.exception


@pytest.fixture
def runtime_reports(tmp_path, monkeypatch):
    from onevisit import outcomes

    monkeypatch.setattr(outcomes, "RUNTIME", tmp_path / "outcomes.jsonl")
    return tmp_path / "outcomes.jsonl"


def test_typed_message_in_demo_builds_the_case_and_follows_the_language(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "Mi carta de identidad caducó y tengo que renovarla. Soy peruano y vivo en Bovisa."
    ).run()
    at.run()
    assert not at.exception
    assert at.session_state["lang"] == "es"
    assert at.session_state["checklist"]["service_id"] == "carta-identita"
    assert at.session_state["answers"] == {
        "motivo": "rinnovo",
        "eta": "adulto",
        "cittadinanza": "extra-ue",
    }
    assert at.session_state["offices"][0]["address"] == "via Baldinucci 76"
    md = _md(at)
    assert "leído por palabras clave; en directo lo lee Claude" in md
    assert "Traducción de Claude" in md and "Qué llevar a la ventanilla" in md


def test_same_person_in_arabic_switches_the_page_and_translates_the_checklist(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cairo-residenza-ar").click().run()
    at.run()
    assert not at.exception and at.session_state["lang"] == "ar"
    _answer_all(at)
    md = _md(at)
    assert "ترجمة Claude" in md  # Claude's translation, labelled
    assert "نسخة من جواز السفر" in " ".join(
        c.label for c in at.checkbox
    )  # the passport item, in Arabic
    help_texts = [c.help or "" for c in at.checkbox if (c.key or "").startswith("have-")]
    assert any(
        "Copia del passaporto" in h for h in help_texts
    )  # the Italian that counts, behind the (?)


def test_online_application_gets_the_upload_list_and_the_form_guide(no_key, no_network):
    at = _app(demo="1", lang="en")
    at.button(key="ex-cairo-residenza").click().run()
    _answer_all(
        at,
        (
            "Waiting for the first, for work",
            "Alone",
            "Renting · contract not registered yet, or I don't know",
        ),
    )
    md = _md(at)
    assert "To upload in the online application: 9 files" in md  # one rental contract, not two
    assert "How to fill in the online application" in md
    assert "Per chi ha un contratto di locazione" in md  # the City's own wording, quoted
    form_boxes = [c for c in at.checkbox if (c.key or "").startswith("form-")]
    assert len(form_boxes) == 9  # one confirmation per file to upload
    form_boxes[0].check().run()
    assert not at.exception and at.session_state[form_boxes[0].key] is True
    # replies cite with numbered notes and name the sources underneath, not raw ids
    bubbles = [m.value for m in at.markdown if 'class="ov-msg bot"' in m.value]
    assert bubbles and all('class="ov-fn-ref"' in b for b in bubbles[-1:])
    assert not any(
        ">[residenza-estero" in b or " [residenza-estero" in b for b in bubbles
    )  # no raw ids in the text
    assert "Comune di Milano · Modulistica" in md


def test_booking_link_shows_the_booking_step_as_done(no_key, no_network):
    at = _app(servizio="carta-identita", sede="ds549-11", data="2030-01-15", lang="en", demo="1")
    md = _md(at)
    assert "Appointment already booked: 15/01/2030" in md
    assert "Book the registry desk appointment online" not in md


def test_live_turn_then_claude_orders_the_next_actions(monkeypatch, no_network):
    import anthropic

    actions = {
        "actions": [
            {
                "requirement_ids": ["documento-precedente"],
                "action": "Bring the expired card.",
                "why": "The desk needs it.",
            },
            {
                "requirement_ids": ["stranieri"],
                "action": "Bring your residence permit.",
                "why": "You are not an EU citizen.",
            },
            {"requirement_ids": ["invented-item"], "action": "Bring a letter.", "why": ""},
        ]
    }
    fake = FakeClient(
        [
            tool(
                "get_checklist",
                service_id="carta-identita",
                answers={"motivo": "rinnovo", "eta": "adulto", "cittadinanza": "extra-ue"},
            ),
            text(
                "Your checklist is ready, each item with its source [cie]. "
                "The desk officer makes the final check."
            ),
            text(json.dumps(actions)),
        ]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = _app(lang="en")
    at.button(key="ex-cie-rinnovo-bovisa").click().run()
    at.run()
    assert not at.exception
    md = _md(at)
    assert at.session_state["lang"] == "es"  # this case writes in Spanish: the page follows
    assert "Tus próximas 3 acciones" in md and "Ordenadas por Claude" in md
    assert "Bring the expired card." in md and "Bring a letter." not in md
    assert any("dropped 1 of Claude's proposals" in c.value for c in at.caption)
    assert at.session_state["live_calls"] == 2


def test_when_claude_cannot_be_reached_the_session_continues_in_demo(monkeypatch, no_network):
    import anthropic

    class Down:
        def __init__(self, **kw):
            self.beta = self
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("no credit")

    monkeypatch.setattr(anthropic, "Anthropic", Down)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = _app()
    at.button(key="ex-cie-isola").click().run()
    at.run()
    assert not at.exception
    assert at.session_state["live_off"] == "down"
    assert (
        at.session_state["chat"][-1]["demo"] is True
        and at.session_state["checklist"]["requirements"]
    )
    assert "Claude non è raggiungibile" in _md(at)
    assert "error" not in at.session_state["chat"][-1]["text"].lower()


def test_request_cap_switches_the_session_to_demo(monkeypatch, no_network):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: FakeClient([]))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    monkeypatch.setenv("ONEVISIT_MAX_CALLS_PER_SESSION", "0")
    at = _app()
    at.button(key="ex-cairo-residenza").click().run()
    at.run()
    assert not at.exception
    assert at.session_state["live_off"] == "limit" and at.session_state["chat"][-1]["demo"] is True
    assert "limite di richieste" in _md(at)


def test_city_tab_report_is_scrubbed_and_classified(no_key, no_network, runtime_reports):
    at = _app(demo="1", lang="en")
    example = next(b for b in at.button if (b.key or "").startswith("city-ex-"))
    example.click().run()
    at.button(key="city-send").click().run()
    assert not at.exception
    infos = " ".join(i.value for i in at.info)
    assert "an email address" in infos and "a date" in infos
    assert any("Recorded as: Page incomplete" in s.value for s in at.success)
    saved = runtime_reports.read_text(encoding="utf-8")
    assert "example.org" not in saved and "12/09/2026" not in saved
