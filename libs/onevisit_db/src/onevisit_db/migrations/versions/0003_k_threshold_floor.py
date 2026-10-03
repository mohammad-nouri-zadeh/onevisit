"""Soglia k mai sotto 5 a livello di database (storie A5, C11).

app_dashboard puo' aggiornare analytics.config: il vincolo impedisce di abbassare
k_threshold sotto 5, cosi' nessuna vista puo' mostrare gruppi di meno di 5 casi
qualunque cosa faccia l'interfaccia.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valore minimo di k (C11: "Nessuna cella mostra meno di 5 casi").
MIN_K = 5


def upgrade() -> None:
    op.execute(
        "ALTER TABLE analytics.config ADD CONSTRAINT config_k_threshold_floor "
        f"CHECK (key <> 'k_threshold' OR value >= {MIN_K})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE analytics.config DROP CONSTRAINT IF EXISTS config_k_threshold_floor")
