"""Accesso al database: modelli SQLAlchemy, migrazioni Alembic, ruoli (storia C2).

Schemi Postgres:

- ``pii``: contatti e appuntamenti. Lo leggono solo l'assistente e il notificatore.
- ``core``: sessioni, casi, lacune, interventi, notifiche.
- ``analytics``: viste aggregate con soglia k. L'unico schema letto dal pannello.
"""
