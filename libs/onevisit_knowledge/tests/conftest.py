"""Dati di prova sintetici per la libreria della conoscenza (storie A1, A2, C4)."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

SOURCES_CSV = (
    "id,title,url,publisher,kind,snapshot,retrieved_at,status,notes\n"
    "pagina-demo,Pagina demo,https://example.org/demo,Comune di Prova,page,"
    "pages/pagina-demo.md,2026-09-01,ok,\n"
    "dataset-demo,Dataset demo,https://example.org/ds,Comune di Prova,opendata,"
    'opendata/demo.csv,2026-10-01,ok,"nota, con virgola"\n'
    "senza-data,Fonte senza data,,Comune di Prova,page,,,todo,\n"
)

PAGE_MD = """---
url: https://example.org/demo
ente: Comune di Prova
content_hash: sha256:abc
---

# Carta finta

Per il rinnovo serve la carta d\u2019identità   scaduta.

I minori vengono con entrambi i genitori.
"""

SERVICE = {
    "id": "servizio-demo",
    "title": {"it": "Servizio demo", "en": "Demo service"},
    "ente": "comune-prova",
    "source_ids": ["pagina-demo"],
    "deciding_questions": [
        {"id": "motivo", "ask_it": "Perché?", "ask_en": "Why?", "options": ["prima", "rinnovo"]},
        {"id": "eta", "ask_it": "Età?", "ask_en": "Age?", "options": ["adulto", "minore"]},
        {"id": "scadenza", "ask_it": "Entro quando?", "ask_en": "By when?", "kind": "date"},
    ],
    "requirements": [
        {
            "id": "sempre",
            "text_it": "Serve un appuntamento.",
            "text_en": "You need an appointment.",
            "when": {},
            "source_id": "dataset-demo",
            "quote": "Solo su appuntamento.",
            "verified_at": "2026-10-01",
            "status": "verified",
            "lead_time_days": 7,
        },
        {
            "id": "vecchia-carta",
            "text_it": "Porta la carta scaduta.",
            "when": {"motivo": ["rinnovo"]},
            "source_id": "pagina-demo",
            "quote": "Per il rinnovo serve la carta d'identità scaduta.",
            "verified_at": "2026-09-01",
            "status": "verified",
        },
        {
            "id": "genitori",
            "text_it": "Vengono entrambi i genitori.",
            "when": {"eta": ["minore"]},
            "source_id": "pagina-demo",
            "quote": "I minori vengono con entrambi i genitori.",
            "verified_at": "2026-09-01",
            "status": "verified",
        },
        {
            "id": "costo",
            "text_it": "TODO costo",
            "when": {},
            "source_id": "senza-data",
            "quote": "",
            "verified_at": None,
            "status": "todo",
        },
    ],
    "steps": [
        {
            "order": 2,
            "ente": "comune-prova",
            "text_it": "Vai allo sportello.",
            "source_id": "pagina-demo",
            "status": "todo",
        },
        {
            "order": 1,
            "ente": "comune-prova",
            "text_it": "Prenota.",
            "source_id": "dataset-demo",
            "quote": "Solo su appuntamento.",
            "verified_at": "2026-10-01",
            "status": "verified",
        },
    ],
    "unknowns_it": ["Il costo non è ancora verificato."],
}

OFFICES = [
    {
        "id": "ds549-01",
        "municipio": 1,
        "address": "via Finta 1",
        "nil": {"id": 1, "name": "DUOMO"},
        "lat": 45.4642,
        "lon": 9.1900,
        "source_id": "dataset-demo",
        "data_issues": [],
    },
    {
        "id": "ds549-02",
        "municipio": 2,
        "address": "via Prova 2",
        "nil": {"id": 2, "name": "GRECO"},
        "lat": 45.5000,
        "lon": 9.2100,
        "source_id": "dataset-demo",
        "data_issues": ["Orari non aggiornati"],
    },
    {
        "id": "ds549-03",
        "municipio": 2,
        "address": "piazza Esempio 3",
        "nil": {"id": 3, "name": "LORETO"},
        "lat": 45.4860,
        "lon": 9.2160,
        "source_id": "dataset-demo",
        "data_issues": [],
    },
]

ENTI = [
    {
        "id": "comune-prova",
        "name": "Comune di Prova",
        "role_it": "Anagrafe",
        "source_ids": ["dataset-demo"],
        "status": "verified",
    }
]


def write_dataset(root: Path, service: Mapping[str, Any] | None = None) -> Path:
    """Scrive un catalogo sintetico completo in ``root`` e lo restituisce."""
    (root / "services").mkdir(parents=True)
    (root / "pages").mkdir()
    (root / "opendata").mkdir()
    (root / "context").mkdir()
    (root / "sources.csv").write_text(SOURCES_CSV, encoding="utf-8")
    (root / "pages" / "pagina-demo.md").write_text(PAGE_MD, encoding="utf-8")
    (root / "opendata" / "demo.csv").write_text(
        'id,note\n1,"Solo su appuntamento."\n', encoding="utf-8"
    )
    (root / "context" / "arrivi.csv").write_text("anno,arrivi\n2024,100\n", encoding="utf-8")
    (root / "services" / "servizio-demo.json").write_text(
        json.dumps(service or SERVICE, ensure_ascii=False), encoding="utf-8"
    )
    (root / "offices.json").write_text(json.dumps(OFFICES), encoding="utf-8")
    (root / "enti.json").write_text(json.dumps(ENTI), encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Catalogo sintetico valido."""
    return write_dataset(tmp_path / "data")


@pytest.fixture
def make_dataset(tmp_path: Path) -> object:
    """Fabbrica: scrive un catalogo con un servizio modificato e ne restituisce la cartella."""
    import copy

    counter = iter(range(1000))

    def factory(mutate: object = None) -> Path:
        service = copy.deepcopy(SERVICE)
        if callable(mutate):
            mutate(service)
        return write_dataset(tmp_path / f"data{next(counter)}", service)

    return factory
