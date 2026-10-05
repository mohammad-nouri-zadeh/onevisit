"""Quote cards in live mode (Claude is a fake): the card names the page that holds the quote,
links only
what that page links, and the check line says "word for word" only when every quote was found."""

from __future__ import annotations

import html
import pathlib

from streamlit.testing.v1 import AppTest

from onevisit import search

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = str(ROOT / "app" / "streamlit_app.py")
CIE = "carta-identita"
PORTAL = (
    "Per prenotare un appuntamento per ottenere o rinnovare la Carta di identità (CIE) a Milano è "
    "necessario utilizzare il servizio messo a disposizione sul sito comune.milano.it"
)


def _live(monkeypatch, steps: list) -> AppTest:
    import anthropic
    from fakes import FakeClient

    fake = FakeClient(steps)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.chat_input[0].set_value("Posso prenotare dal portale nazionale?").run()
    assert not at.exception
    return at


def _md(at: AppTest) -> str:
    return html.unescape("\n".join(m.value for m in at.markdown))


def test_a_card_cited_with_two_ids_names_the_page_that_holds_the_quote(monkeypatch, no_network):
    from fakes import text, tool

    at = _live(
        monkeypatch,
        [
            tool("read_source", source_id="cie-faq-03767"),
            tool("read_source", source_id="cie"),
            text(f"No: «{PORTAL}» [cie, cie-faq-03767]."),
        ],
    )
    assert at.session_state["chat"][-1]["check"]["ok"]
    md = _md(at)
    assert 'data-source="cie-faq-03767"' in md and 'data-source="cie"' not in md
    assert "testo identico alla pagina salvata" in md


def test_a_card_links_only_what_the_page_links(monkeypatch, no_network):
    """The page's own booking link stays a link; the reply can't add one (the validator blocks
    a link
    no tool returned, so the citizen gets the regenerated reply)."""
    from fakes import text, tool

    linked = PORTAL.replace(
        "appuntamento",
        "[appuntamento](https://servizicrm.comune.milano.it/spec/appuntamenti/anagrafecie"
        "?knowledgeArticleId=5fa56948-62aa-f011-bbd2-7ced8d2d5da5)",
        1,
    )
    attacker = PORTAL.replace("appuntamento", "[appuntamento](https://pay-cie.example.com)", 1)
    at = _live(
        monkeypatch,
        [
            tool("read_source", source_id="cie-faq-03767"),
            text(f"No: «{attacker}» [cie-faq-03767]."),
            text(f"No: «{linked}» [cie-faq-03767]."),
        ],
    )
    reply = at.session_state["chat"][-1]
    assert reply["check"]["blocked"] == ["ungrounded_url"] and not reply["check"]["fallback"]
    md = _md(at)
    assert "pay-cie.example.com" not in md
    assert 'href="https://servizicrm.comune.milano.it/spec/appuntamenti/anagrafecie' in md


def test_the_word_for_word_line_needs_every_quote_found(monkeypatch, no_network):
    from fakes import text, tool

    top = search.best_answer("Quanto costa la carta d'identità?", service_id=CIE)["passages"][0]
    sentence = next(s for s in top["text"].split("\n") if "€" in s).strip()
    at = _live(
        monkeypatch,
        [
            tool(
                "search_official_pages", query="Quanto costa la carta d'identità?", service_id=CIE
            ),
            text(
                f"La pagina dice: «{sentence}» [{top['source_id']}]. "
                "Sul sito scegli «Prenota un appuntamento» sulla pagina di prenotazione."
            ),
        ],
    )
    assert at.session_state["chat"][-1]["check"]["ok"]
    md = _md(at)
    assert "le citazioni sono identiche alle pagine salvate" not in md
