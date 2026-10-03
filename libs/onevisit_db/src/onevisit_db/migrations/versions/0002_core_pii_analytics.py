"""Tabelle di core e pii, configurazione e viste di analytics, permessi (storie C2, C11).

Le viste di analytics leggono la soglia k da analytics.config dentro la vista:
i gruppi sotto soglia sono esclusi (first_visit_rate, weekly_first_visit) oppure
hanno i numeri a NULL (gaps_by_cause, intervention_effect, avoided_visits).
Le viste non sono security_invoker: girano con i privilegi del proprietario, cosi'
app_dashboard le legge senza poter leggere core.cases.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAUSES_SQL = (
    "'pagina-incompleta', 'procedura-non-aggiornata', 'procedura-mancante', "
    "'ente-o-ufficio-sbagliato', 'pagina-chiara-non-seguita', 'richiesta-non-prevista'"
)

TABLES = f"""
CREATE TABLE core.cases (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    service_id text NOT NULL,
    variant text,
    category text CHECK (category IN ('italiana', 'ue', 'extra-ue')),
    language text NOT NULL,
    office_id text,
    appointment_week date,
    deadline_days integer,
    outcome text CHECK (outcome IN ('ok', 'missing', 'other')),
    cause text CHECK (cause IN ({CAUSES_SQL})),
    missing_requirement_id text,
    closed_in_time boolean,
    rating integer CHECK (rating BETWEEN 1 AND 5),
    outcome_at timestamptz,
    contact_ref uuid,
    synthetic boolean NOT NULL DEFAULT false
);
CREATE INDEX ix_cases_service_week ON core.cases (service_id, appointment_week);
CREATE INDEX ix_cases_contact_ref ON core.cases (contact_ref) WHERE contact_ref IS NOT NULL;

CREATE TABLE core.case_answers (
    case_id uuid NOT NULL REFERENCES core.cases (id) ON DELETE CASCADE,
    question_id text NOT NULL,
    answer text NOT NULL,
    PRIMARY KEY (case_id, question_id)
);

CREATE TABLE core.gaps (
    id uuid PRIMARY KEY,
    service_id text NOT NULL,
    cause text NOT NULL CHECK (cause IN ({CAUSES_SQL})),
    source_id text,
    title text NOT NULL,
    summary text,
    examples jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'nuova'
        CHECK (status IN ('nuova', 'in-revisione', 'corretta', 'archiviata')),
    recipient text NOT NULL
        CHECK (recipient IN ('redazione', 'ufficio', 'ente-nazionale', 'assistente')),
    owner_ente text,
    requirement_id text,
    draft_it text,
    draft_easy_it text,
    draft_en text,
    case_count integer NOT NULL DEFAULT 0,
    first_seen timestamptz,
    last_seen timestamptz,
    archived_reason text,
    synthetic boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_gaps_status ON core.gaps (status, service_id);

CREATE TABLE core.gap_cases (
    gap_id uuid NOT NULL REFERENCES core.gaps (id) ON DELETE CASCADE,
    case_id uuid NOT NULL REFERENCES core.cases (id) ON DELETE CASCADE,
    PRIMARY KEY (gap_id, case_id)
);

CREATE TABLE core.interventions (
    id uuid PRIMARY KEY,
    gap_id uuid REFERENCES core.gaps (id) ON DELETE SET NULL,
    service_id text NOT NULL,
    requirement_id text,
    text_it text NOT NULL,
    text_easy_it text,
    text_en text,
    approved_by text NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_interventions_service ON core.interventions (service_id, approved_at);

CREATE TABLE core.notifications (
    id uuid PRIMARY KEY,
    case_id uuid NOT NULL REFERENCES core.cases (id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('reminder', 'followup', 'followup_nudge',
        'correction_notice', 'revocation_confirm', 'email_confirm')),
    channel text NOT NULL CHECK (channel IN ('email', 'sms')),
    due_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'sent', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0,
    sent_at timestamptz
);
CREATE INDEX ix_notifications_due ON core.notifications (status, due_at);
CREATE INDEX ix_notifications_case ON core.notifications (case_id);

CREATE TABLE core.access_log (
    id uuid PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    role text NOT NULL,
    action text NOT NULL,
    object_id text
);

CREATE TABLE pii.contacts (
    id uuid PRIMARY KEY,
    email_enc bytea,
    email_hmac text,
    phone_enc bytea,
    phone_hmac text,
    preferred_channel text NOT NULL CHECK (preferred_channel IN ('email', 'sms')),
    fallback_channel text CHECK (fallback_channel IN ('email', 'sms')),
    language text NOT NULL,
    consents jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    confirmed_at timestamptz,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_contacts_email_hmac ON pii.contacts (email_hmac);
CREATE INDEX ix_contacts_phone_hmac ON pii.contacts (phone_hmac);
CREATE INDEX ix_contacts_expires ON pii.contacts (expires_at);

CREATE TABLE pii.appointments (
    id uuid PRIMARY KEY,
    contact_id uuid NOT NULL REFERENCES pii.contacts (id) ON DELETE CASCADE,
    case_id uuid NOT NULL,
    starts_at timestamptz NOT NULL,
    office_id text NOT NULL
);
CREATE INDEX ix_appointments_case ON pii.appointments (case_id);

CREATE TABLE analytics.config (
    key text PRIMARY KEY,
    value numeric NOT NULL
);
INSERT INTO analytics.config (key, value) VALUES
    ('k_threshold', 5), ('cost_per_slot_eur', 0), ('window_weeks', 4);
"""

# Soglia k e parametri letti dentro ogni vista; default se la riga manca.
VIEWS = """
CREATE VIEW analytics.first_visit_rate AS
WITH cfg AS (
    SELECT COALESCE((SELECT value FROM analytics.config WHERE key = 'k_threshold'), 5) AS k
), agg AS (
    SELECT service_id, category, language,
           count(*) AS cases,
           count(*) FILTER (WHERE outcome = 'ok') AS closed_first_visit
    FROM core.cases
    WHERE outcome IS NOT NULL
    GROUP BY service_id, category, language
)
SELECT agg.service_id, agg.category, agg.language, agg.cases, agg.closed_first_visit,
       round(agg.closed_first_visit::numeric / agg.cases, 4) AS rate
FROM agg, cfg
WHERE agg.cases >= cfg.k;

CREATE VIEW analytics.weekly_first_visit AS
WITH cfg AS (
    SELECT COALESCE((SELECT value FROM analytics.config WHERE key = 'k_threshold'), 5) AS k
), agg AS (
    SELECT service_id, appointment_week AS week,
           count(*) AS cases,
           count(*) FILTER (WHERE outcome = 'ok') AS closed_first_visit
    FROM core.cases
    WHERE outcome IS NOT NULL AND appointment_week IS NOT NULL
    GROUP BY service_id, appointment_week
)
SELECT agg.service_id, agg.week, agg.cases, agg.closed_first_visit,
       round(agg.closed_first_visit::numeric / agg.cases, 4) AS rate
FROM agg, cfg
WHERE agg.cases >= cfg.k;

CREATE VIEW analytics.gaps_by_cause AS
WITH cfg AS (
    SELECT COALESCE((SELECT value FROM analytics.config WHERE key = 'k_threshold'), 5) AS k
), agg AS (
    SELECT cause,
           count(*) AS gaps,
           count(*) FILTER (WHERE status IN ('nuova', 'in-revisione')) AS open_gaps,
           COALESCE(sum(case_count), 0) AS cases
    FROM core.gaps
    WHERE status <> 'archiviata'
    GROUP BY cause
)
SELECT agg.cause, agg.gaps, agg.open_gaps,
       CASE WHEN agg.cases >= cfg.k THEN agg.cases END AS cases
FROM agg, cfg;

CREATE VIEW analytics.intervention_effect AS
WITH cfg AS (
    SELECT COALESCE((SELECT value FROM analytics.config WHERE key = 'k_threshold'), 5) AS k,
           COALESCE((SELECT value FROM analytics.config WHERE key = 'window_weeks'), 4)::int
               AS weeks
), agg AS (
    SELECT i.id AS intervention_id, i.gap_id, i.service_id, i.requirement_id, i.approved_at,
           count(c.id) FILTER (WHERE c.appointment_week < i.approved_at::date) AS cases_before,
           count(c.id) FILTER (WHERE c.appointment_week < i.approved_at::date
                                 AND c.outcome = 'ok') AS closed_before,
           count(c.id) FILTER (WHERE c.appointment_week >= i.approved_at::date) AS cases_after,
           count(c.id) FILTER (WHERE c.appointment_week >= i.approved_at::date
                                 AND c.outcome = 'ok') AS closed_after
    FROM core.interventions i
    CROSS JOIN cfg
    LEFT JOIN core.cases c
      ON c.service_id = i.service_id
     AND c.outcome IS NOT NULL
     AND c.appointment_week >= (i.approved_at::date - cfg.weeks * 7)
     AND c.appointment_week < (i.approved_at::date + cfg.weeks * 7)
    GROUP BY i.id, i.gap_id, i.service_id, i.requirement_id, i.approved_at
)
SELECT agg.intervention_id, agg.gap_id, agg.service_id, agg.requirement_id, agg.approved_at,
       cfg.weeks AS window_weeks,
       CASE WHEN agg.cases_before >= cfg.k THEN agg.cases_before END AS cases_before,
       CASE WHEN agg.cases_before >= cfg.k
            THEN round(agg.closed_before::numeric / agg.cases_before, 4) END AS rate_before,
       CASE WHEN agg.cases_after >= cfg.k THEN agg.cases_after END AS cases_after,
       CASE WHEN agg.cases_after >= cfg.k
            THEN round(agg.closed_after::numeric / agg.cases_after, 4) END AS rate_after
FROM agg, cfg;

CREATE VIEW analytics.avoided_visits AS
WITH cfg AS (
    SELECT COALESCE((SELECT value FROM analytics.config WHERE key = 'cost_per_slot_eur'), 0)
               AS cost_per_slot_eur
), est AS (
    SELECT service_id,
           count(*) AS interventions,
           sum(GREATEST(rate_after - rate_before, 0) * cases_after) AS avoided
    FROM analytics.intervention_effect
    GROUP BY service_id
)
SELECT est.service_id, est.interventions,
       round(est.avoided, 0) AS avoided_visits,
       cfg.cost_per_slot_eur,
       round(est.avoided * cfg.cost_per_slot_eur, 2) AS avoided_cost_eur
FROM est, cfg;
"""

ANALYTICS_VIEWS = (
    "analytics.first_visit_rate",
    "analytics.weekly_first_visit",
    "analytics.gaps_by_cause",
    "analytics.intervention_effect",
    "analytics.avoided_visits",
)

GRANTS = f"""
GRANT USAGE ON SCHEMA core TO app_notifier;
GRANT USAGE ON SCHEMA analytics TO app_assistant;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    core.cases, core.case_answers, core.notifications TO app_assistant;
GRANT INSERT ON core.access_log TO app_assistant;
GRANT SELECT ON core.interventions TO app_assistant;
GRANT SELECT, INSERT, UPDATE, DELETE ON pii.contacts, pii.appointments TO app_assistant;
GRANT SELECT ON analytics.config TO app_assistant;

GRANT SELECT ON pii.contacts, pii.appointments TO app_notifier;
GRANT SELECT ON core.cases TO app_notifier;
GRANT SELECT, UPDATE ON core.notifications TO app_notifier;

GRANT SELECT ON core.cases, core.case_answers, core.interventions TO app_analysis;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.gaps, core.gap_cases TO app_analysis;
GRANT SELECT ON analytics.config, {", ".join(ANALYTICS_VIEWS)} TO app_analysis;

GRANT SELECT ON analytics.config, {", ".join(ANALYTICS_VIEWS)} TO app_dashboard;
GRANT UPDATE ON analytics.config TO app_dashboard;
GRANT SELECT, UPDATE ON core.gaps TO app_dashboard;
GRANT SELECT, INSERT ON core.interventions TO app_dashboard;
GRANT INSERT ON core.access_log TO app_dashboard;
"""


def _statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


def upgrade() -> None:
    for block in (TABLES, VIEWS, GRANTS):
        for statement in _statements(block):
            op.execute(statement)


def downgrade() -> None:
    for view in reversed(ANALYTICS_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {view}")
    op.execute("DROP TABLE IF EXISTS analytics.config")
    for table in (
        "pii.appointments",
        "pii.contacts",
        "core.access_log",
        "core.notifications",
        "core.interventions",
        "core.gap_cases",
        "core.gaps",
        "core.case_answers",
        "core.cases",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("REVOKE USAGE ON SCHEMA core FROM app_notifier")
    op.execute("REVOKE USAGE ON SCHEMA analytics FROM app_assistant")
