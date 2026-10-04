"""The desk dossier PDF (onevisit/dossier.py)."""

from __future__ import annotations

import io
import re

import pytest

from onevisit import dossier, kb

pypdf = pytest.importorskip("pypdf")


def _text(pdf: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    return re.sub(r"\s+", " ", " ".join(page.extract_text() for page in reader.pages))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def test_dossier_contains_verified_requirements_and_their_sources():
    answers = {
        "residenza": "milano",
        "motivo": "smarrimento-furto",
        "eta": "adulto",
        "cittadinanza": "extra-ue",
        "presenza": "sportello",
    }
    pdf = dossier.build_pdf(
        "carta-identita", answers, office_id="ds549-11", appointment="2030-01-15"
    )
    assert pdf.startswith(b"%PDF")
    text = _text(pdf)
    cl = kb.checklist("carta-identita", answers)
    assert cl["requirements"]
    for req in cl["requirements"]:
        assert _norm(req["text_it"])[:40] in text, req["id"]
        assert req["source_id"] in text
    for sid in {r["source_id"] for r in cl["requirements"]}:
        assert _norm(kb.get_source(sid)["title"])[:30] in text
    assert "La verifica finale spetta all'operatore allo sportello" in text
    assert "15/01/2030" in text and "Largo De Benedetti 1" in text
    assert "Dossier per lo sportello" in text and "Your desk dossier" in text


def test_dossier_for_an_online_procedure_lists_the_path_across_offices():
    answers = {"permesso": "ricevuta-lavoro", "famiglia": "solo", "alloggio": "affitto"}
    text = _text(dossier.build_pdf("iscrizione-anagrafica-extra-ue", answers))
    for step in kb.get_service("iscrizione-anagrafica-extra-ue")["steps"]:
        assert _norm(step["text_it"])[:35] in text


def test_dossier_has_no_free_text_fields():
    pdf = dossier.build_pdf("carta-identita", {"motivo": "rinnovo", "nome": "Mario Rossi"})
    assert "Mario" not in _text(pdf)  # only known deciding questions are printed


def test_unknown_service_is_refused():
    with pytest.raises(ValueError):
        dossier.build_pdf("non-esiste", {})
