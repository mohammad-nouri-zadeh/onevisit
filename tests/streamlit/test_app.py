"""The Streamlit app in demo mode, without a key and without network (streamlit.testing)."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = str(ROOT / "app" / "streamlit_app.py")


def _app(**query) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def _markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_modules_import_without_key_and_network():
    """Fresh interpreter, no key, every socket connect fails: the app's modules still import."""
    code = (
        "import socket, sys\n"
        "def blocked(*a, **k): raise OSError('network blocked in test')\n"
        "socket.socket.connect = blocked\n"
        f"sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'app')!r}]\n"
        "import onevisit.kb, onevisit.tools, onevisit.validator, onevisit.agent, onevisit.demo\n"
        "import onevisit.dossier, onevisit.outcomes, onevisit.plan, onevisit.translate\n"
        "import onevisit.evaluate\n"
        "import deeplink, i18n\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    out = subprocess.run(  # noqa: S603 (fixed command: this interpreter running a constant script)
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT, timeout=120
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_app_starts_in_demo_mode_without_key(no_key, no_network):
    at = _app()
    assert not at.exception
    text = _markdown(at)
    assert "Replica dimostrativa · dati e fonti reali" in text  # a chip in the header, not a banner
    assert (
        "Replica dimostrativa, per chi non ha la chiave API" in text
        and 'class="ov-callout"' not in text
    )
    assert "senza Claude" not in text and "Claude controlla ogni requisito" not in text
    assert "Ogni risposta passa un controllo automatico: ogni requisito ha una fonte" in text
    assert [t.label for t in at.tabs] == ["Per i cittadini", "Per il Comune"]
    assert "Design preview" not in text


def test_example_button_builds_a_checklist_and_offers_the_dossier(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cie-isola").click().run()
    assert not at.exception
    cl = at.session_state["checklist"]
    assert cl["service_id"] == "carta-identita" and cl["requirements"]
    assert len([c for c in at.checkbox if (c.key or "").startswith("have-")]) == len(
        cl["requirements"]
    )
    assert "dossier-pdf-top" in {d.key for d in at.get("download_button")}
    assert "Controllo automatico" in _markdown(at)
    # answer every question with the first option until the checklist is complete
    for _ in range(6):
        options = [b for b in at.button if (b.key or "").startswith("opt-")]
        if not options:
            break
        options[0].click().run()
        assert not at.exception
    assert at.session_state["demo_state"]["done"]


def test_booking_link_presets_service_office_and_date(no_key, no_network):
    at = _app(servizio="carta-identita", sede="ds549-11", data="2030-01-15", lang="en", demo="1")
    assert not at.exception
    assert at.session_state["office_id"] == "ds549-11"
    assert at.session_state["appointment"]["date"] == "2030-01-15"
    assert "From the link in the booking confirmation email" in _markdown(at)
    assert (
        at.session_state["chat"][0]["role"] == "assistant"
        and at.session_state["checklist"]["requirements"]
    )


def test_city_panel_shows_a_recorded_draft_and_the_approval(no_key, no_network):
    at = _app(demo="1")
    key = next(b.key for b in at.button if (b.key or "").startswith("dr-"))
    at.button(key=key).click().run()
    assert not at.exception
    group_key = key[3:]
    assert at.session_state["drafts"][group_key].startswith("BOZZA DA APPROVARE")
    at.button(key=f"ap-{group_key}").click().run()
    assert group_key in at.session_state["approved"]
    text = _markdown(at)
    assert "FAC-SIMILE" in text and "Per renderlo proattivo" in text and "STIMA" in text


def test_language_menu_switches_the_interface(no_key, no_network):
    at = _app(demo="1")
    at.selectbox(key="lang").set_value("en").run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["For citizens", "For the City"]
    at.selectbox(key="lang").set_value("ar").run()
    assert not at.exception
    assert "عرض تجريبي" in _markdown(at)


@pytest.mark.parametrize("lang", ["it", "en", "ar", "es", "zh"])
def test_every_language_runs_the_first_example(no_key, no_network, lang):
    at = _app(demo="1", lang=lang)
    at.button(key="ex-cairo-residenza").click().run()
    assert not at.exception
    assert at.session_state["checklist"]["service_id"] == "iscrizione-anagrafica-extra-ue"


def test_live_path_wiring_with_a_fake_claude(monkeypatch, no_network):
    """With a key the example goes to a (fake) Claude: tools run live, the reply is checked."""
    import anthropic
    from fakes import FakeClient, text, tool

    fake = FakeClient(
        [
            tool("get_service", service_id="carta-identita"),
            tool(
                "get_checklist",
                service_id="carta-identita",
                answers={"motivo": "smarrimento-furto"},
            ),
            tool("find_offices", area="Isola"),
            text(
                "Here is your checklist from the official sources [cie] [ds549]. "
                "The desk officer makes the final check."
                "\nOPTIONS: Adult | Minor"
            ),
        ]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = _app()
    assert "Replica dimostrativa" not in _markdown(at)
    at.button(key="ex-cie-isola").click().run()
    assert not at.exception
    reply = at.session_state["chat"][-1]
    assert (
        reply["role"] == "assistant"
        and reply["check"]["ok"]
        and reply["options"] == ["Adult", "Minor"]
    )
    assert at.session_state["answers"] == {"motivo": "smarrimento-furto"}
    assert at.session_state["offices"][0]["id"] == "ds549-11"
    assert fake.calls[0]["messages"][0]["content"].startswith("Ho perso la carta")


def test_checklist_is_grouped_by_category_with_open_items_explained(no_key, no_network):
    at = _app(demo="1", lang="en")
    at.button(key="ex-cie-isola").click().run()
    for _ in range(6):
        options = [b for b in at.button if (b.key or "").startswith("opt-")]
        if not options:
            break
        # adult, non-EU: one item stays open
        wanted = [b for b in options if b.label in ("Adult", "Non-EU")]
        (wanted or options)[0].click().run()
    assert not at.exception
    assert at.session_state["answers"] == {
        "motivo": "smarrimento-furto",
        "eta": "adulto",
        "cittadinanza": "extra-ue",
    }
    text = _markdown(at)
    reqs = at.session_state["checklist"]["requirements"]
    n = sum(r["category"] == "prepare" for r in reqs)
    assert f'<div class="ov-cat">{demo_label("prepare")} · {n}</div>' in text
    labels = [e.label for e in at.expander]
    for category in ("how", "after"):  # folded, like "Afterwards", so the page stays short
        n = sum(r["category"] == category for r in reqs)
        assert f"{demo_label(category)} · {n}" in labels
    assert at.session_state["checklist"]["not_yet_verified"]
    assert "To be checked:" in text  # the open item says what is unknown, not just its id


def demo_label(category: str) -> str:
    from onevisit import demo

    return demo.category_label(category, "en")


def test_online_procedure_wording_in_the_app(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cairo-residenza").click().run()
    for _ in range(6):
        options = [b for b in at.button if (b.key or "").startswith("opt-")]
        if not options:
            break
        options[0].click().run()
    assert not at.exception
    text = _markdown(at)
    assert any(
        "Il tuo dossier per la domanda online" in c.value for c in at.caption
    )  # under the one download
    assert (
        "ufficio anagrafe del Comune.</div>" in text
    )  # the final-check line (HTML-escaped apostrophe)
    assert "allo sportello.</div>" not in text
    assert [d.label for d in at.date_input] == ["Quando pensi di inviare la domanda (facoltativo)"]


def test_link_from_the_yesmilano_student_guide(no_key, no_network):
    """The study-permit case is not in the official list: the app says so and links the City."""
    at = _app(servizio="iscrizione-anagrafica-extra-ue", canale="yesmilano", lang="en", demo="1")
    assert not at.exception
    assert "From the link in the YesMilano student guide" in _markdown(at)
    assert at.session_state["checklist"]["service_id"] == "iscrizione-anagrafica-extra-ue"
    other = next(
        b for b in at.button if (b.key or "").startswith("opt-") and b.label == "Something else"
    )
    other.click().run()
    assert not at.exception
    assert at.session_state["answers"] == {"permesso": "altro"}
    assert (
        "To be checked: which documents are needed by people waiting for a first permit for study"
        in (_markdown(at))
    )


def test_city_panel_shows_both_day_one_links(no_key, no_network):
    at = _app(demo="1", lang="en")
    text = _markdown(at)
    assert "servizio=carta-identita&amp;sede=" in text  # booking confirmation email
    assert "servizio=iscrizione-anagrafica-extra-ue&amp;lang=en&amp;canale=yesmilano" in text
