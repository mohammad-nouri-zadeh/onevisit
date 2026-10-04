"""Jury round 2 fixes: honest labels on demo replies, a short page once the case is clear,
a change of residence from another comune, and one rental contract per case."""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py")


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


def test_a_demo_reply_is_never_signed_by_claude(no_key, no_network):
    at = _app(demo="1", lang="en")
    at.button(key="ex-cie-isola").click().run()
    md = _md(at)
    assert "OneVisit · replay" in md and "OneVisit · Claude" not in md
    assert "The tools read" in md and "Claude read" not in md
    labels = [e.label for e in at.expander]
    assert "What the tools checked" in labels and "What Claude checked" not in labels


def test_typed_message_in_demo_is_signed_by_the_demo_too(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "Devo fare il cambio di residenza, mi sono trasferito da Torino"
    ).run()
    assert not at.exception
    md = _md(at)
    assert "OneVisit · replica" in md and "letto per parole chiave" in md
    assert "Gli strumenti hanno letto" in md and "Claude ha letto" not in md
    assert at.session_state["checklist"]["service_id"] == "cambio-residenza"
    option_labels = [b.label for b in at.button if (b.key or "").startswith("opt-")]
    assert option_labels == [
        "Italiana",
        "UE",
        "Extra-UE",
    ]  # citizenship, not the residence-permit options


LOST_IN_MILAN = {"residenza": "milano", "motivo": "smarrimento-furto"}


def test_a_live_reply_keeps_claudes_name(monkeypatch, no_network):
    import anthropic
    from fakes import FakeClient, text, tool

    from onevisit import kb

    fake = FakeClient(
        [
            tool(
                "get_checklist",
                service_id="carta-identita",
                answers=LOST_IN_MILAN,
            ),
            text(
                "Here is your checklist from the official sources [cie]. "
                "The desk officer makes the final check."
                "\nOPTIONS: Adult | Minor"
            ),
        ]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = _app(lang="en")
    at.button(key="ex-cie-isola").click().run()
    md = _md(at)
    # as many sources as the checklist tool returned for this case
    read = len(kb.checklist("carta-identita", LOST_IN_MILAN)["sources"])
    assert read > 1
    assert (
        "OneVisit · Claude" in md
        and f"Claude read {read} sources" in md
        and "OneVisit · replay" not in md
    )
    assert "What Claude checked" in [e.label for e in at.expander]


def test_first_screen_starts_with_the_cases_and_a_chip_not_a_banner(no_key, no_network):
    at = _app(demo="1", lang="en")
    md = _md(at)
    assert "Demo replay · real data and sources" in md and 'class="ov-callout"' not in md
    # the example cases come before the three-step explainer, which is folded
    assert md.index("Try a case") < md.index('class="ov-how"')
    assert "How OneVisit works · 3 steps" in [e.label for e in at.expander]


def test_once_the_case_is_clear_the_page_leads_with_the_summary_and_folds_the_chat(
    no_key, no_network
):
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
    assert "Your list is ready" in md and "To upload in the online application: 9 files" in md
    downloads = [d.key for d in at.get("download_button")]
    assert [k for k in downloads if k.startswith("dossier-pdf")] == [
        "dossier-pdf-top"
    ]  # one dossier download
    labels = [e.label for e in at.expander]
    folded = [x for x in labels if x.startswith("Conversation · ")]
    assert folded == [
        "Conversation · 7 messages"
    ]  # opening, 3 questions and 3 answers; the last reply stays open
    assert md.index("Your list is ready") < md.rindex('class="ov-msg bot"')
    assert any(
        x.startswith("Open the guide, section by section") for x in labels
    )  # form guide folded
    assert 'class="ov-details"' in md  # the folded turns keep their trace


def test_change_of_residence_from_another_comune_in_the_app(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-torino-milano").click().run()
    _answer_all(at)
    assert not at.exception
    cl = at.session_state["checklist"]
    assert cl["service_id"] == "cambio-residenza" and not cl["still_to_ask"]
    md = _md(at)
    assert "Da tenere pronti per la dichiarazione online" in md
    assert "Anagrafe Nazionale" in md
    links = [b for b in at.get("link_button")]
    assert any("anagrafenazionale.interno.it" in (b.proto.url or "") for b in links)


def test_the_evaluation_measures_requests_tokens_and_cost_per_turn():
    """docs/eval-results.md will say what a case costs: tokens from response.usage, list prices."""
    from fakes import FakeClient, Usage, text, tool

    from onevisit import evaluate

    scenario = next(s for s in evaluate.scenarios() if s["id"] == "residenza-da-altro-comune-it")
    answers = {"cittadinanza": "italiana", "alloggio": "non-proprietario"}
    first, second, third = (
        tool("get_service", service_id="cambio-residenza"),
        tool("get_checklist", service_id="cambio-residenza", answers=answers),
        text(
            "Si fa online sul sito dell'Anagrafe Nazionale con SPID o CIE, entro 20 giorni "
            "[cambio-residenza]. Ti trasferisci da solo?"
        ),
    )
    first.usage = Usage(input_tokens=3000, output_tokens=120, cache_creation_input_tokens=2500)
    second.usage = Usage(input_tokens=400, output_tokens=90, cache_read_input_tokens=2500)
    third.usage = Usage(input_tokens=900, output_tokens=200, cache_read_input_tokens=2500)
    fake = FakeClient([first, second, third])
    result = evaluate.run_one(scenario, fake)
    assert result.passed, result.failures
    assert result.usage == {
        "requests": 3,
        "input_tokens": 4300,
        "output_tokens": 410,
        "cache_read_input_tokens": 5000,
        "cache_creation_input_tokens": 2500,
    }
    assert all(
        call["cache_control"] == {"type": "ephemeral"} for call in fake.calls
    )  # system + tools cached
    cost = result.cost_usd("claude-sonnet-5-5")
    assert abs(cost - (4300 * 2 + 410 * 10 + 5000 * 0.2 + 2500 * 2.5) / 1e6) < 1e-9
    md = evaluate.report([result], "claude-sonnet-5-5", usd_to_eur=0.9)
    assert "3.0 API requests" in md and "4,300 / 5,000 / 410" in md and "€" in md
