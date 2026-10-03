"""Lacune, metriche, sintesi settimanale e dati demo (storie C10, C11, B13, D1).

Interfaccia pubblica fissata in docs/contracts.md sezione 6. Ogni funzione che usa
Claude accetta un client opzionale (:class:`TextClient`) e, senza client, usa una
regola deterministica: cosi' i test e la demo senza chiave API funzionano.
"""

from onevisit_analytics.causes import CAUSES, RECIPIENTS, Cause
from onevisit_analytics.classify import Classification, OutcomeInput, classify_outcome
from onevisit_analytics.claude import DEFAULT_MODEL, AnthropicTextClient, TextClient
from onevisit_analytics.demo import generate_demo_data, wipe_synthetic
from onevisit_analytics.demo_script import DemoSummary
from onevisit_analytics.drafts import Draft, GapForDraft, draft_correction
from onevisit_analytics.errors import AnalyticsError, ClaudeOutputError, ProperNameError
from onevisit_analytics.gaps import (
    GapDecision,
    GapGrouping,
    GapProposal,
    NegativeOutcome,
    OpenGap,
    group_into_gaps,
)
from onevisit_analytics.names import ensure_no_proper_names, find_proper_names
from onevisit_analytics.summary import (
    CauseCount,
    Effect,
    ServiceTrend,
    WeeklyData,
    weekly_summary,
)

__all__ = [
    "CAUSES",
    "DEFAULT_MODEL",
    "RECIPIENTS",
    "AnalyticsError",
    "AnthropicTextClient",
    "Cause",
    "CauseCount",
    "Classification",
    "ClaudeOutputError",
    "DemoSummary",
    "Draft",
    "Effect",
    "GapDecision",
    "GapForDraft",
    "GapGrouping",
    "GapProposal",
    "NegativeOutcome",
    "OpenGap",
    "OutcomeInput",
    "ProperNameError",
    "ServiceTrend",
    "TextClient",
    "WeeklyData",
    "classify_outcome",
    "draft_correction",
    "ensure_no_proper_names",
    "find_proper_names",
    "generate_demo_data",
    "group_into_gaps",
    "weekly_summary",
    "wipe_synthetic",
]
