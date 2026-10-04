"""Deep link from the City's booking confirmation email (app/deeplink.py)."""

from __future__ import annotations

import deeplink


def test_full_link_is_parsed():
    link = deeplink.parse(
        {"servizio": "carta-identita", "sede": "ds549-11", "data": "2030-01-15", "lang": "en"}
    )
    assert link == {
        "service_id": "carta-identita",
        "office_id": "ds549-11",
        "office_address": "Largo De Benedetti 1",
        "date": "2030-01-15",
        "lang": "en",
        "channel": "prenotazione",
    }


def test_unknown_values_are_dropped_not_guessed():
    link = deeplink.parse(
        {"servizio": "carta-identita", "sede": "ds549-99", "data": "15/01/2030", "lang": "xx"}
    )
    assert link["office_id"] is None and link["date"] is None and link["lang"] is None


def test_unknown_service_means_no_link():
    assert deeplink.parse({"servizio": "passaporto"}) is None
    assert deeplink.parse({}) is None
    assert deeplink.parse({"servizio": "<script>"}) is None


def test_personal_data_in_the_query_is_ignored():
    link = deeplink.parse({"servizio": "carta-identita", "nome": "Mario", "cf": "RSSMRA80A01F205X"})
    assert "Mario" not in str(link) and "RSSMRA" not in str(link)


def test_build_then_parse_round_trip():
    url = deeplink.build("carta-identita", "ds549-11", "2030-01-15", "it")
    assert url.startswith("https://onevisit.streamlit.app/?servizio=carta-identita")
    query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
    assert deeplink.parse(query)["office_id"] == "ds549-11"


def test_link_from_the_yesmilano_student_guide_opens_the_service_only():
    url = deeplink.build("iscrizione-anagrafica-extra-ue", lang="en", channel="yesmilano")
    query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
    link = deeplink.parse(query)
    assert link["channel"] == "yesmilano" and link["office_id"] is None and link["date"] is None
    assert deeplink.parse({"servizio": "carta-identita", "canale": "spam"})["channel"] is None
