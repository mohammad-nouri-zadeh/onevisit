"""Le pagine del gateway usano il design system locale e nessuna risorsa di terzi."""

import asyncio
import re
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from gateway.deps import GatewayDeps
from gateway.main import create_app

from .conftest import PHONE

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "gateway" / "templates"
THIRD_PARTY = ("unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis", "fonts.gstatic")


def test_base_template_loads_local_design_system_only() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")

    assert "ui_stylesheets" in base
    assert "/static/style.css" in base
    for name in TEMPLATES.glob("*.html"):
        text = name.read_text(encoding="utf-8")
        for host in THIRD_PARTY:
            assert host not in text, f"{name.name} chiama {host}"
        for src in re.findall(r'<script[^>]*src="([^"]+)"', text):
            assert src.startswith("/ui/vendor/"), f"{name.name} carica {src}"


def test_rendered_pages_reference_ui_stylesheets(
    make_deps: Callable[..., GatewayDeps],
) -> None:
    client = TestClient(create_app(deps=make_deps(environment="development")))
    client.post("/sms/inbound", data={"From": PHONE, "Body": "aiuto", "MessageSid": "SM9"})

    for page in (client.get("/demo/phone"), client.get("/r/not-a-token?choice=1")):
        assert '<link rel="stylesheet" href="/ui/fonts.css">' in page.text
        assert '<link rel="stylesheet" href="/ui/onevisit.css">' in page.text
        assert page.text.index("/ui/fonts.css") < page.text.index("/ui/onevisit.css")
        for host in THIRD_PARTY:
            assert host not in page.text
        for src in re.findall(r'<script[^>]*src="([^"]+)"', page.text):
            assert src.startswith("/ui/vendor/")


def test_design_system_and_app_static_files_are_served() -> None:
    client = TestClient(create_app())

    css = client.get("/ui/onevisit.css")
    assert css.status_code == 200
    assert "--ink" in css.text
    assert client.get("/ui/fonts.css").status_code == 200
    assert client.get("/ui/vendor/htmx.min.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_demo_phone_links_in_sms_are_tappable(
    make_deps: Callable[..., GatewayDeps],
) -> None:
    deps = make_deps(environment="development")
    assert deps.fake_sms is not None
    asyncio.run(deps.fake_sms.send(PHONE, "Apri la lista: https://assistant.test/c/abc <b>"))
    client = TestClient(create_app(deps=deps))

    page = client.get("/demo/phone")

    assert 'class="msg ai"' in page.text
    assert 'href="https://assistant.test/c/abc"' in page.text
    assert "&lt;b&gt;" in page.text
    assert 'http-equiv="refresh"' in page.text
    assert PHONE not in page.text


def test_demo_phone_empty_state_and_english(make_deps: Callable[..., GatewayDeps]) -> None:
    client = TestClient(create_app(deps=make_deps(environment="development")))

    it = client.get("/demo/phone")
    en = client.get("/demo/phone", headers={"Accept-Language": "en-GB"})

    assert 'class="notice"' in it.text and "Nessun SMS ancora." in it.text
    assert "No SMS yet." in en.text and "Messages" in en.text
