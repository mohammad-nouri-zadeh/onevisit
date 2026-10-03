"""Worker dello scheduler (storia C8), basato su Procrastinate.

Avvio: ``procrastinate --app=gateway.worker.app worker --queues=notifications``.
I lavori (reminder, followup, retention_purge, ...) vanno definiti in moduli
dedicati e importati qui, in modo che il worker li registri all'avvio.

Prima di attivare i worker (profilo ``workers`` in compose.yaml) la storia C8
deve applicare lo schema di Procrastinate e concedere i permessi ai ruoli.
"""

import os

import procrastinate

_SQLALCHEMY_PREFIX = "postgresql+psycopg://"
_LIBPQ_PREFIX = "postgresql://"


def libpq_conninfo(database_url: str) -> str:
    """Converte una URL SQLAlchemy (``postgresql+psycopg://``) nel formato libpq.

    Tutti i servizi ricevono la stessa variabile ``ONEVISIT_DATABASE_URL`` in formato
    SQLAlchemy; Procrastinate usa direttamente psycopg e vuole il formato libpq.
    """
    if database_url.startswith(_SQLALCHEMY_PREFIX):
        return _LIBPQ_PREFIX + database_url.removeprefix(_SQLALCHEMY_PREFIX)
    return database_url


app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=libpq_conninfo(os.environ.get("ONEVISIT_DATABASE_URL", "")),
    ),
)
