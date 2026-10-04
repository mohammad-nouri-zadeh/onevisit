"""The guide to the online form, the files to upload, Claude's translations and the dossier in the
citizen's language."""

from __future__ import annotations

import io

import pytest
from fakes import FakeClient, Response, text
from pypdf import PdfReader

from onevisit import dossier, kb, tools, translate

RESIDENCE = "iscrizione-anagrafica-extra-ue"
CAIRO = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}


def test_form_guide_follows_the_city_sections_and_quotes_the_housing_option():
    guide = kb.form_guide(RESIDENCE, CAIRO)
    ids = [s["id"] for s in guide["sections"]]
    assert ids == ["dichiarazione", "base", "cittadinanza", "abitazione", "nel-modulo", "invio"]
    assert guide["form"]["source_id"] == "residenza-estero-modulo"
    assert guide["housing_option"]["label_it"] == "Per chi ha un contratto di locazione"
    assert guide["housing_option"]["quote"] in kb._page_text(
        kb.sources()["residenza-estero-modulistica"]
    )
    listed = {i["id"] for s in guide["sections"] for i in s["items"]}
    assert listed <= {r["id"] for r in kb.checklist(RESIDENCE, CAIRO)["requirements"]}
    assert {"contratto-soggiorno", "ricevuta-poste", "alloggio-affitto", "patente"} <= listed
    assert (
        kb.form_guide("carta-identita", {})["sections"] == []
    )  # a desk procedure has no online form


def test_form_guide_is_a_tool_claude_can_call():
    assert "get_form_guide" in {t["name"] for t in tools.TOOLS}
    out = tools.run_tool("get_form_guide", {"service_id": RESIDENCE, "answers": CAIRO})
    assert "Documentazione relativa all'abitazione" in out


def test_files_to_upload_come_in_the_order_of_the_city_page():
    files = kb.to_upload(kb.checklist(RESIDENCE, CAIRO))
    order = [r["form_section"] for r in files]
    assert order == sorted(order, key=kb.UPLOAD_SECTIONS.index)
    assert files[0]["id"] == "modulo-firmato" and all(
        r.get("short_it") and r.get("short_en") for r in files
    )
    desk = kb.to_upload(
        kb.checklist(
            "carta-identita",
            {"motivo": "smarrimento-furto", "eta": "adulto", "cittadinanza": "extra-ue"},
        )
    )
    assert {"denuncia", "stranieri", "costo"} <= {r["id"] for r in desk}


@pytest.mark.parametrize("lang", ["ar", "es", "zh"])
@pytest.mark.parametrize("service_id", [s["id"] for s in kb.list_services()])
def test_every_text_has_a_current_translation_by_claude(service_id, lang):
    assert kb.missing_translations(service_id, lang) == {}
    req = kb.checklist(service_id, {})["requirements"][0]
    text_local, translated = kb.req_text(service_id, req, lang)
    assert translated and text_local != req["text_en"]


def test_a_stale_translation_falls_back_to_english(monkeypatch):
    req = next(r for r in kb.checklist("carta-identita", {})["requirements"] if r["id"] == "costo")
    changed = {**req, "text_it": req["text_it"] + " (testo cambiato)"}
    shown, translated = kb.req_text("carta-identita", changed, "ar")
    assert (shown, translated) == (req["text_en"], False)


def test_runtime_translation_with_claude_drops_unknown_keys_and_promises(monkeypatch):
    key = kb.text_key("carta-identita", "req", "costo")
    other = kb.text_key("carta-identita", "req", "impronte")
    reply = (
        f'{{"items": [{{"key": "{key}", "text": "Costo: 22,20 euro."}}, '
        f'{{"key": "{other}", "text": "Sei in regola."}}, {{"key": "invented", "text": "x"}}]}}'
    )
    fake = FakeClient([text(reply)])
    sources = kb.translatable("carta-identita")
    out = translate.translate(
        "carta-identita", "fr", fake, {key: sources[key], other: sources[other]}
    )
    assert set(out) == {key}  # "in regola" is a promise: dropped, not repaired
    assert out[key]["it"] == sources[key]["it"]
    call = fake.calls[0]
    assert (
        call["model"] == translate.FAST_MODEL
        and call["output_config"]["format"]["type"] == "json_schema"
    )
    kb.add_runtime_translations("fr", out)
    shown, translated = kb.localized(
        "carta-identita", "req", "costo", "text", sources[key]["it"], sources[key]["en"], "fr"
    )
    assert translated and shown == "Costo: 22,20 euro."


def test_runtime_translation_skips_a_refusal():
    fake = FakeClient([Response([], stop_reason="refusal")])
    key = kb.text_key("carta-identita", "req", "costo")
    assert (
        translate.translate(
            "carta-identita", "es", fake, {key: kb.translatable("carta-identita")[key]}
        )
        == {}
    )


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


@pytest.mark.parametrize("lang,needle", [("zh", "护照"), ("es", "Copia del pasaporte")])
def test_dossier_prints_italian_with_the_citizens_language(lang, needle):
    pdf = dossier.build_pdf(RESIDENCE, CAIRO, lang=lang)
    text = _pdf_text(pdf)
    assert (
        "Copia del passaporto (o documento equivalente) in corso di validità." in text
    )  # the Italian counts
    assert needle in text
    assert dossier.LOCAL[lang]["translated"].split(":")[0] in text


def test_dossier_in_arabic_embeds_an_arabic_font():
    pdf = dossier.build_pdf(RESIDENCE, CAIRO, lang="ar")
    assert b"NotoNaskhArabic" in pdf and len(pdf) < 400_000
    assert "Copia del passaporto" in _pdf_text(pdf)
