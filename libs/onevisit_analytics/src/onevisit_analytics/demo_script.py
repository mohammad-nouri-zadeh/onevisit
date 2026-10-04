"""Copione dello scenario demo: servizi, lacune programmate, distribuzioni (storia D1).

Separato da ``demo.py`` per tenere i due moduli sotto le 300 righe. Le distribuzioni di
lingue e categorie sono plausibili per Milano (lingue: it, en, es, ar, zh, uk, pt), ma
inventate: servono solo a rendere credibile il pannello.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from onevisit_analytics.causes import Cause

CIE = "carta-identita"
ISCRIZIONE = "iscrizione-anagrafica-extra-ue"

# Enti non comunali titolari di alcune fonti del catalogo (data/sources.csv, publisher).
NATIONAL_OWNERS = {
    "permesso-soggiorno": "Polizia di Stato",
    "codice-fiscale": "Agenzia delle Entrate",
}

OFFICES = tuple(f"ds549-{n:02d}" for n in range(1, 14))

# Pesi delle lingue per servizio (somma 1).
LANGUAGES = {
    CIE: (
        ("it", 0.6),
        ("en", 0.1),
        ("es", 0.08),
        ("ar", 0.08),
        ("zh", 0.06),
        ("uk", 0.04),
        ("pt", 0.04),
    ),
    ISCRIZIONE: (
        ("en", 0.25),
        ("es", 0.2),
        ("ar", 0.2),
        ("zh", 0.12),
        ("uk", 0.08),
        ("pt", 0.08),
        ("it", 0.07),
    ),
}
CIE_CATEGORIES = (("italiana", 0.7), ("ue", 0.1), ("extra-ue", 0.2))
# "deteriorata" prende la sua quota solo da "rinnovo": la soglia cumulata di "smarrimento-furto"
# resta 0,8, quindi lo stesso seme estrae gli stessi casi di smarrimento (e le stesse scadenze).
CIE_VARIANTS = (
    ("prima", 0.25),
    ("rinnovo", 0.5),
    ("deteriorata", 0.05),
    ("smarrimento-furto", 0.2),
)
# Risposte fisse alle domande della carta d'identita' che il generatore non varia:
# residenza a Milano, richiesta allo sportello (non a domicilio).
CIE_FIXED_ANSWERS = (("residenza", "milano"), ("presenza", "sportello"))
# Quota di minori tra i casi della carta d'identita'.
MINOR_RATE = 0.1
PERMIT = (("permesso", 0.7), ("ricevuta-rinnovo", 0.25), ("nessuno", 0.05))
FAMILY = (("solo", 0.6), ("con-familiari", 0.4))
HOUSING = (("affitto", 0.7), ("ospite", 0.2), ("proprieta", 0.1))
# Esiti negativi non legati a lacune ("other"): quota per servizio, prima e dopo la correzione.
OTHER_FAILURE = {CIE: (0.08, 0.08), ISCRIZIONE: (0.16, 0.06)}


@dataclass(frozen=True)
class ScriptedGap:
    """Una lacuna programmata: quanti casi in ogni settimana."""

    service_id: str
    service_title: str
    cause: Cause
    source_id: str | None
    page_title: str | None
    requirement_id: str | None
    requirement_label: str | None
    title: str
    status: str
    by_week: dict[int, int] = field(default_factory=dict)
    office_id: str | None = None
    # Testo del requisito come lo legge il cittadino nella checklist (intervento approvato),
    # distinto dalla bozza per la redazione che spiega come modificare la pagina.
    requirement_text_it: str | None = None
    requirement_text_en: str | None = None

    @property
    def key(self) -> tuple[str, str, str | None]:
        """Chiave usata per ritrovare la lacuna dopo il raggruppamento."""
        return (self.service_id, self.cause.value, self.requirement_id)

    def cases_in_week(self, week: int) -> int:
        """Casi negativi programmati nella settimana (1-based)."""
        return self.by_week.get(week, 0)


SCRIPTED_GAPS: tuple[ScriptedGap, ...] = (
    ScriptedGap(
        ISCRIZIONE,
        "Iscrizione anagrafica (extra-UE)",
        Cause.PROCEDURA_MANCANTE,
        "residenza-estero",
        "Residenza dall'estero",
        "documenti-esteri",
        "traduzione e legalizzazione dei documenti esteri",
        "Documenti esteri: traduzione e legalizzazione non descritte",
        "nuova",
        {2: 1, 3: 2, 4: 3},
        requirement_text_it="Traduzione e legalizzazione dei documenti rilasciati all'estero.",
        requirement_text_en="Translation and legalisation of documents issued abroad.",
    ),
    ScriptedGap(
        CIE,
        "Carta d'identità elettronica",
        Cause.PAGINA_INCOMPLETA,
        "cie",
        "Carta d'identità elettronica",
        "fototessera",
        "fototessera recente con sfondo chiaro",
        "Fototessera: requisiti non chiari",
        "nuova",
        {1: 1, 3: 1, 5: 1, 6: 1, 7: 2, 8: 1},
    ),
    ScriptedGap(
        ISCRIZIONE,
        "Iscrizione anagrafica (extra-UE)",
        Cause.ENTE_O_UFFICIO_SBAGLIATO,
        "permesso-soggiorno",
        "Permesso di soggiorno",
        "permesso",
        "rinnovo del permesso presso la Questura",
        "Permesso di soggiorno: ufficio competente non chiaro",
        "in-revisione",
        {3: 1, 4: 1, 6: 1, 7: 1, 8: 1},
    ),
    ScriptedGap(
        CIE,
        "Carta d'identità elettronica",
        Cause.PAGINA_CHIARA_NON_SEGUITA,
        "cie",
        "Carta d'identità elettronica",
        "denuncia",
        "denuncia di smarrimento o furto",
        "Denuncia di smarrimento: indicazione presente ma non seguita",
        "nuova",
        {2: 1, 5: 1, 7: 1},
    ),
    ScriptedGap(
        CIE,
        "Carta d'identità elettronica",
        Cause.RICHIESTA_NON_PREVISTA,
        None,
        None,
        None,
        None,
        "Richiesta allo sportello non prevista dalla procedura",
        "nuova",
        {4: 1, 6: 1},
        "ds549-03",
    ),
)
MAIN_GAP_KEY = SCRIPTED_GAPS[0].key


class DemoSummary(BaseModel):
    """Riepilogo del generatore: solo conteggi, nessun dato personale."""

    model_config = ConfigDict(frozen=True)

    seed: int
    weeks: int
    cases: int
    cases_with_outcome: int
    gaps: int
    gaps_above_threshold: int
    interventions: int
    main_gap_cases_by_week: list[int]
    threshold_week: int | None
    intervention_week: int


@dataclass(frozen=True)
class CaseProfile:
    """Attributi strutturati estratti per un caso sintetico."""

    variant: str | None
    category: str
    language: str
    office_id: str
    deadline_days: int | None
    answers: tuple[tuple[str, str], ...]


def _pick(rng: random.Random, options: Sequence[tuple[str, float]]) -> str:
    values = [o for o, _ in options]
    weights = [w for _, w in options]
    return rng.choices(values, weights=weights, k=1)[0]


def case_profile(rng: random.Random, service: str) -> CaseProfile:
    """Estrae lingua, categoria, variante e risposte per un caso del servizio."""
    language = _pick(rng, LANGUAGES[service])
    office = rng.choice(OFFICES)
    if service == CIE:
        variant = _pick(rng, CIE_VARIANTS)
        category = _pick(rng, CIE_CATEGORIES)
        age = "minore" if rng.random() < MINOR_RATE else "adulto"
        deadline = rng.choice((None, 14, 30)) if variant == "smarrimento-furto" else None
        answers: tuple[tuple[str, str], ...] = (
            ("motivo", variant),
            ("eta", age),
            ("cittadinanza", category),
            *CIE_FIXED_ANSWERS,
        )
        return CaseProfile(variant, category, language, office, deadline, answers)
    answers = (
        ("permesso", _pick(rng, PERMIT)),
        ("famiglia", _pick(rng, FAMILY)),
        ("alloggio", _pick(rng, HOUSING)),
    )
    deadline = rng.choice((None, 30, 60))
    return CaseProfile(None, "extra-ue", language, office, deadline, answers)


def other_failure_rate(service: str, week: int, intervention_week: int) -> float:
    """Quota di esiti negativi non legati a lacune programmate."""
    before, after = OTHER_FAILURE[service]
    return before if week < intervention_week else after


def threshold_week(cases_by_week: Sequence[int], *, k: int, window: int = 4) -> int | None:
    """Prima settimana (1-based) in cui la finestra mobile di ``window`` settimane arriva a k."""
    for index in range(len(cases_by_week)):
        if sum(cases_by_week[max(0, index - window + 1) : index + 1]) >= k:
            return index + 1
    return None
