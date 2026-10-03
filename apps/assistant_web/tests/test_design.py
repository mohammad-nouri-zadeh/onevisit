"""Design system condiviso: fogli di stile e script locali, nessuna CDN, menu della lingua."""

from collections.abc import Callable

from fastapi.testclient import TestClient

THIRD_PARTY = ("unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis", "fonts.gstatic")


def test_base_template_uses_local_design_system(make_client: Callable[..., TestClient]) -> None:
    response = make_client().get("/")

    assert '<link rel="stylesheet" href="/ui/fonts.css">' in response.text
    assert '<link rel="stylesheet" href="/ui/onevisit.css">' in response.text
    assert '<script src="/ui/vendor/htmx.min.js"' in response.text
    for host in THIRD_PARTY:
        assert host not in response.text


def test_design_system_assets_are_served(make_client: Callable[..., TestClient]) -> None:
    client = make_client()

    for path in ("/ui/onevisit.css", "/ui/fonts.css", "/ui/vendor/htmx.min.js"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert "--ink" in client.get("/ui/onevisit.css").text


def test_language_menu_overrides_accept_language_and_is_remembered(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()

    chosen = client.get("/?lang=en", headers={"Accept-Language": "it-IT,it;q=0.9"})
    remembered = client.get("/", headers={"Accept-Language": "it-IT,it;q=0.9"})

    assert 'lang="en"' in chosen.text and "I help you prepare" in chosen.text
    assert chosen.cookies.get("ov_lang") == "en"
    assert "I help you prepare" in remembered.text
    assert '<select name="lang"' in remembered.text


def test_unknown_language_falls_back_to_accept_language(
    make_client: Callable[..., TestClient],
) -> None:
    response = make_client().get("/?lang=xx", headers={"Accept-Language": "en"})

    assert "I help you prepare" in response.text
    assert "ov_lang" not in response.cookies
