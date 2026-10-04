"""Jury round 4: the replay framed as a replay of a Claude product, the impact estimate on both
residence procedures, typed messages in languages the replay can't write, one dossier download,
and the tagline for online submissions and desk appointments."""

from __future__ import annotations

import csv
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from onevisit import agent, demo, kb

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


# ---------- 1. the replay is labelled as a replay; Claude is the product ----------
def test_first_screen_labels_the_replay_and_states_the_tagline(no_key, no_network):
    at = _app(demo="1", lang="en")
    md = _md(at)
    assert "Demo replay · real data and sources" in md
    assert "Done right the first time: first submission or first appointment." in md
    assert "Every reply passes an automatic check: every requirement has an official source." in md
    assert "without Claude" not in md and "Claude checks every requirement" not in md


def test_replay_links_to_the_live_version_when_the_server_has_a_key(monkeypatch, no_network):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 40)
    md = _md(_app(demo="1"))
    assert "Replica dimostrativa · dati e fonti reali" in md
    assert 'href="?lang=it" target="_self">Prova la versione dal vivo, con Claude' in md


def test_no_live_link_without_a_key(no_key, no_network):
    assert "Prova la versione dal vivo" not in _md(_app(demo="1"))


def test_replayed_replies_are_signed_as_the_replay(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cie-isola").click().run()
    md = _md(at)
    assert "OneVisit · replica" in md and "OneVisit · Claude" not in md


def test_no_interface_text_says_demo_without_claude():
    from i18n import STRINGS

    phrases = (
        "senza Claude",
        "without Claude",
        "sin Claude",
        "بدون Claude",
        "未使用 Claude",
        "OneVisit (demo)",
    )
    for lang, table in STRINGS.items():
        for key, text in table.items():
            assert not any(p in text for p in phrases), (lang, key, text)
    for lang, table in demo.script()["templates"].items():
        for key, text in table.items():
            assert not any(p in text for p in phrases), (lang, key, text)


# ---------- 2. impact: both residence procedures, sourced bases, ID cards left out ----------
def test_arrivals_table_has_both_bases_computed_from_ds1959():
    row = {r["year"]: r for r in kb.context_tables()["arrivals-from-abroad"]}["2024"]
    assert int(row["registrations_from_abroad"]) == 19755
    assert int(row["registrations_from_other_comuni"]) == 27184
    assert (
        (
            int(row["registrations_from_abroad"])
            + int(row["registrations_from_other_comuni"])
            + int(row["origin_not_stated"])
        )
        == int(row["all_registrations"])
        == 46953
    )
    raw = (
        ROOT
        / "data"
        / "opendata"
        / "ds1959-popolazione-iscrizioni-anagrafiche-per-luogo-di-provenienza.csv"
    )
    with raw.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter=";") if r["Anno_evento"] == "2024"]
    other = sum(int(r["Numerosità"]) for r in rows if r["Luogo_Prov"] not in ("Estero", "n.d."))
    assert other == 27184


def test_city_tab_impact_counts_both_residence_procedures(no_key, no_network):
    at = _app(demo="1")
    md = _md(at)
    # (19,755 x 20% + 27,184 x 10%) x 30% x 50% = 1,000 with the starting assumptions
    assert "≈ 1.000</b>" in md
    # the formula as the page prints it, with the multiplication sign
    assert "(19.755 × 20% + 27.184 × 10%) × 30% × 50%" in md  # noqa: RUF001
    assert "Carte d&#x27;identità escluse" in md or "Carte d'identità escluse" in md
    assert "STIMA" in md
    at.slider(key="impact-comuni").set_value(20).run()
    assert "≈ 1.408</b>" in _md(at)  # every assumption moves the estimate


# ---------- 3. typed messages in other languages ----------
@pytest.mark.parametrize(
    "text, code",
    [
        ("J'ai perdu ma carte d'identité, j'habite à Isola", "fr"),
        # Ukrainian, with its own Cyrillic letters on purpose
        ("Я щойно приїхала до Мілана і мені потрібна реєстрація місця проживання", "uk"),  # noqa: RUF001
        ("আমি মিলানে নতুন এসেছি, আমার আবাসিক নিবন্ধন দরকার", "bn"),
        ("Kailangan ko ng tulong para sa aking residence sa Milano, bago lang ako dito", "tl"),
    ],
)
def test_the_replay_answers_other_languages_in_english_and_names_them(text, code):
    assert agent.guess_lang(text) == code
    state, reply = demo.start_text(text, "it")
    assert state["lang"] == "en" and reply["lang"] == "en" and reply["other_language"] == code
    first = reply["text"].split("\n\n")[0]
    assert first.startswith("I'm answering in English") and demo.LANGUAGE_NAMES[code] in first
    assert "with Claude, answers in" in first
    assert (
        reply["check"]["ok"] and reply["options"]
    )  # something to do next: the case, or a question


def test_french_is_read_by_keywords_too():
    state, reply = demo.start_text("J'ai perdu ma carte d'identité, j'habite à Isola", "it")
    assert state["service_id"] == "carta-identita"
    assert state["answers"]["motivo"] == "smarrimento-furto"
    assert reply["sources_read"]
    found = demo.understand(
        "Je viens d'arriver du Maroc avec un titre de séjour, je dois m'inscrire à la mairie"
    )
    assert found["service_id"] == "iscrizione-anagrafica-extra-ue"


@pytest.mark.parametrize(
    "text, lang",
    [
        ("Ho perso la carta d'identità e abito in Isola", "it"),
        ("I lost my ID card and I live in Isola", "en"),
        ("Perdí mi carta de identidad y vivo en Isola", "es"),
        ("فقدت بطاقة الهوية وأسكن في إيزولا", "ar"),
        ("我的身份证丢了，我住在 Isola", "zh"),  # noqa: RUF001 (Chinese punctuation on purpose)
    ],
)
def test_languages_the_replay_writes_get_their_own_reply(text, lang):
    state, reply = demo.start_text(text, "it")
    assert state["lang"] == lang and not reply["other_language"]


def test_volevo_is_not_read_as_stolen():
    assert demo.understand("Volevo rinnovare la carta d'identità")["answers"]["motivo"] == "rinnovo"


def test_french_message_in_the_app_switches_the_page_to_english(no_key, no_network):
    at = _app(demo="1")
    at.chat_input(key="chat_text").set_value(
        "J'ai perdu ma carte d'identité, j'habite à Isola"
    ).run()
    at.run()
    assert not at.exception
    assert at.session_state["lang"] == "en"
    md = _md(at)
    assert "French (français)" in md and "OneVisit · replay" in md
    assert at.session_state["checklist"]["service_id"] == "carta-identita"


# ---------- 4. the finished case: one dossier download, the online form once ----------
def test_finished_cairo_case_has_one_dossier_download_and_one_form_button(no_key, no_network):
    at = _app(demo="1")
    at.button(key="ex-cairo-residenza").click().run()
    _answer_all(
        at,
        (
            "Aspetto il primo, per lavoro",
            "Da solo/a",
            "Affitto · contratto non ancora registrato, o non lo so",
        ),
    )
    downloads = [d for d in at.get("download_button")]
    dossiers = [d for d in downloads if (d.key or "").startswith("dossier-pdf")]
    assert [d.key for d in dossiers] == ["dossier-pdf-top"]
    form_buttons = [
        b for b in at.get("link_button") if "Apri la domanda online" in (b.proto.label or "")
    ]
    assert len(form_buttons) == 1
    md = _md(at)
    summary = next(m.value for m in at.markdown if "La tua lista è pronta" in m.value)
    header = next(
        m.value for m in at.markdown if "La tua checklist, dalle fonti ufficiali" in m.value
    )
    assert (
        "24 requisiti verificati" in summary and "requisiti verificati" not in header
    )  # counts said once
    assert "Data e promemoria" in md and [d.label for d in at.date_input]
