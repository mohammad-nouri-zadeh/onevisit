"""Calcolo degli orari di promemoria e follow-up (storie C8, B7, B8).

Funzioni pure: nessun accesso al database ne' all'orologio di sistema.
Il fuso e' ``Europe/Rome`` con ``zoneinfo``, quindi l'ora legale e' gestita.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")

# Ora locale di invio del promemoria (backlog B7: alle 10:00 ora di Roma).
REMINDER_LOCAL_TIME = time(10, 0)
# Ora locale del follow-up, il giorno dopo l'appuntamento (backlog C8).
FOLLOWUP_LOCAL_TIME = time(18, 0)
# Giorni dopo l'appuntamento per il follow-up e per il sollecito (backlog C8).
FOLLOWUP_DAYS_AFTER = 1
NUDGE_DAYS_AFTER = 4

SECONDS_PER_REAL_DAY = 86_400


def _at_local(day_dt: datetime, local_time: time, days: int) -> datetime:
    """Giorno di ``day_dt`` (ora di Roma) spostato di ``days``, all'ora locale indicata."""
    local_day = day_dt.astimezone(ROME).date() + timedelta(days=days)
    return datetime.combine(local_day, local_time, tzinfo=ROME)


def plan_notifications(
    *,
    appointment_at: datetime,
    now: datetime,
    reminder_days_before: int = 3,
    seconds_per_day: int | None = None,
) -> list[tuple[str, datetime]]:
    """Restituisce ``[(kind, due_at)]`` per ``reminder``, ``followup`` e ``followup_nudge``.

    - ``reminder``: ``reminder_days_before`` giorni prima alle 10:00 di Roma; subito
      (``now``) se quell'istante e' gia' passato o l'appuntamento e' piu' vicino.
    - ``followup``: il giorno dopo l'appuntamento alle 18:00 di Roma.
    - ``followup_nudge``: 4 giorni dopo l'appuntamento, alle 18:00 di Roma.

    Con ``seconds_per_day`` (modalita' demo) gli scarti rispetto a ``now`` vengono
    compressi: un giorno dura ``seconds_per_day`` secondi.
    """
    if appointment_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("appointment_at e now devono avere il fuso orario")
    reminder = _at_local(appointment_at, REMINDER_LOCAL_TIME, -reminder_days_before)
    if reminder <= now or appointment_at - now <= timedelta(days=reminder_days_before):
        reminder = now
    plan: list[tuple[str, datetime]] = [
        ("reminder", reminder),
        ("followup", _at_local(appointment_at, FOLLOWUP_LOCAL_TIME, FOLLOWUP_DAYS_AFTER)),
        ("followup_nudge", _at_local(appointment_at, FOLLOWUP_LOCAL_TIME, NUDGE_DAYS_AFTER)),
    ]
    if seconds_per_day is None:
        return plan
    factor = seconds_per_day / SECONDS_PER_REAL_DAY
    compressed: list[tuple[str, datetime]] = []
    for kind, due in plan:
        offset_s = max((due - now).total_seconds(), 0.0) * factor
        compressed.append((kind, now + timedelta(seconds=offset_s)))
    return compressed
