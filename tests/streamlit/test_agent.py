"""The agent loop with the validator: regenerate once, then a safe fallback (fake client)."""

from __future__ import annotations

import itertools

from fakes import FakeClient, text, tool

from onevisit import agent

# A lost card, Milan resident, at the desk: the checklist has the booking rule, from dataset ds549.
LOST_IN_MILAN = {"residenza": "milano", "motivo": "smarrimento-furto", "presenza": "sportello"}


def _alternates(messages: list) -> bool:
    roles = [m["role"] for m in messages]
    return all(a != b for a, b in itertools.pairwise(roles))


def test_clean_answer_passes_first_time():
    client = FakeClient(
        [
            tool("get_checklist", service_id="carta-identita", answers=LOST_IN_MILAN),
            text("These are the items the sources list [ds549]. The desk officer decides."),
        ]
    )
    messages = [{"role": "user", "content": "I lost my ID card"}]
    reply = agent.run_turn(messages, client=client)
    assert reply["check"] == {"attempts": 1, "blocked": [], "fallback": False, "ok": True}
    assert "ds549" in reply["sources_read"] and reply["cited"] == ["ds549"]
    assert reply["trace"][0]["tool"] == "get_checklist"
    assert _alternates(messages)


def test_blocked_answer_is_regenerated_with_the_reasons():
    client = FakeClient(
        [
            tool("get_checklist", service_id="carta-identita", answers=LOST_IN_MILAN),
            text("Good news: you are eligible [ds549]."),
            text("These are the items the sources list [ds549]; the officer at the desk decides."),
        ]
    )
    messages = [{"role": "user", "content": "Can I get the card?"}]
    reply = agent.run_turn(messages, client=client)
    assert reply["check"]["attempts"] == 2 and not reply["check"]["fallback"]
    assert any(r.startswith("eligibility_claim:") for r in reply["check"]["blocked"])
    assert "officer at the desk decides" in reply["text"]
    retry_prompt = client.calls[2]["messages"][-1]["content"]
    assert "AUTOMATIC CHECK" in retry_prompt and "eligibility_claim" in retry_prompt
    # the blocked reply and the retry instruction don't stay in the history
    flat = str(messages)
    assert "you are eligible" not in flat and "AUTOMATIC CHECK" not in flat
    assert _alternates(messages)


def test_blocked_twice_gives_a_safe_fallback_with_the_official_page():
    client = FakeClient(
        [
            tool("get_checklist", service_id="carta-identita", answers={}),
            text("Bring your documents [ds999]."),
            text("You're all set, it's guaranteed."),
        ]
    )
    messages = [{"role": "user", "content": "Ho perso la carta d'identità"}]
    reply = agent.run_turn(messages, client=client, lang="it")
    assert reply["check"]["fallback"] and not reply["check"]["ok"]
    assert "unknown_source:ds999" in reply["check"]["blocked"]
    assert reply["text"].startswith("Non riesco") and "https://" in reply["text"]
    assert messages[-1] == {"role": "assistant", "content": reply["text"]}
    assert _alternates(messages)


def test_fallback_follows_the_script_of_the_citizen():
    client = FakeClient([text("You are eligible."), text("Still eligible.")])
    reply = agent.run_turn(
        [{"role": "user", "content": "فقدت بطاقة هويتي"}], client=client, lang="it"
    )
    assert reply["check"]["fallback"]
    assert reply["text"].startswith("لا أستطيع")


def test_refusal_rolls_back_the_turn():
    from fakes import Response

    client = FakeClient([Response([], stop_reason="refusal")])
    messages = [{"role": "user", "content": "something"}]
    reply = agent.run_turn(messages, client=client)
    assert reply["refused"] and messages == []
