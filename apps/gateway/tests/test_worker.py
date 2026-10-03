"""Il worker si importa senza connettersi e riceve la URL nel formato giusto."""

import procrastinate

from gateway.worker import app, libpq_conninfo


def test_worker_app_is_a_procrastinate_app() -> None:
    assert isinstance(app, procrastinate.App)


def test_sqlalchemy_url_is_converted_to_libpq() -> None:
    url = "postgresql+psycopg://app_notifier:secret@postgres:5432/onevisit"

    assert libpq_conninfo(url) == "postgresql://app_notifier:secret@postgres:5432/onevisit"


def test_libpq_url_is_left_untouched() -> None:
    url = "postgresql://app_notifier:secret@postgres:5432/onevisit"

    assert libpq_conninfo(url) == url
