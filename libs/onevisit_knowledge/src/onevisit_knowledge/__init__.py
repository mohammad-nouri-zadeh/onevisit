"""Fonti ufficiali, catalogo delle procedure, caricamento e validazione (storie A1, A2, C4).

Legge i file del livello dati del team (``data/``) sul posto: vedi docs/contracts.md §1.
"""

from onevisit_knowledge.catalog import Catalog, haversine_km, load_catalog
from onevisit_knowledge.check import CatalogReport, check_catalog, inspect_catalog
from onevisit_knowledge.errors import CatalogError, KnowledgeError
from onevisit_knowledge.models import (
    APPROVED_CORRECTION_SOURCE_ID,
    ApprovedCorrection,
    Checklist,
    ChecklistItem,
    DecidingQuestion,
    Ente,
    Office,
    Requirement,
    Service,
    ServiceSummary,
    Source,
    Step,
)
from onevisit_knowledge.text import content_hash, normalize, render_page, split_front_matter

__all__ = [
    "APPROVED_CORRECTION_SOURCE_ID",
    "ApprovedCorrection",
    "Catalog",
    "CatalogError",
    "CatalogReport",
    "Checklist",
    "ChecklistItem",
    "DecidingQuestion",
    "Ente",
    "KnowledgeError",
    "Office",
    "Requirement",
    "Service",
    "ServiceSummary",
    "Source",
    "Step",
    "check_catalog",
    "content_hash",
    "haversine_km",
    "inspect_catalog",
    "load_catalog",
    "normalize",
    "render_page",
    "split_front_matter",
]
