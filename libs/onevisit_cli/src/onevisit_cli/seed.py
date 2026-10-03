"""Comando ``onevisit seed-demo``: dati sintetici dello scenario demo (storia D1).

Usa la URL del proprietario del database (``ONEVISIT_DATABASE_URL`` letta da ``main``).
Stampa solo conteggi, mai dati personali (i dati sono comunque tutti sintetici).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from onevisit_analytics import generate_demo_data
from onevisit_db.engine import create_db_engine, create_session_factory

ROME = ZoneInfo("Europe/Rome")
# Codice d'uscita per configurazione mancante.
EXIT_CONFIG = 2


def run(*, database_url: str, seed: int, weeks: int, today: date | None = None) -> int:
    """Genera i dati demo e stampa un riepilogo. Restituisce il codice d'uscita."""
    if not database_url:
        print(
            "ONEVISIT_DATABASE_URL non impostata: serve la URL del proprietario del database "
            "(per esempio postgresql+psycopg://onevisit_owner:...@localhost:5432/onevisit)."
        )
        return EXIT_CONFIG

    day = today or datetime.now(ROME).date()
    engine = create_db_engine(database_url)
    try:
        with create_session_factory(engine)() as session:
            summary = generate_demo_data(session, seed=seed, weeks=weeks, today=day)
            session.commit()
    finally:
        engine.dispose()
    print(
        f"Dati demo generati (seme {summary.seed}, {summary.weeks} settimane): "
        f"{summary.cases} casi sintetici, {summary.cases_with_outcome} con esito, "
        f"{summary.gaps} lacune ({summary.gaps_above_threshold} sopra soglia), "
        f"{summary.interventions} intervento approvato. Lacuna principale sopra soglia nella "
        f"settimana {summary.threshold_week}, corretta nella settimana "
        f"{summary.intervention_week}."
    )
    return 0
