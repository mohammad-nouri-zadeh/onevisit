"""Comando ``onevisit ingest``: Markdown con front matter, hash, riga di sources.csv (A1, C4)."""

import shutil
from datetime import date
from pathlib import Path

import httpx
import pytest

from onevisit_cli import ingest
from onevisit_knowledge import check_catalog, content_hash, split_front_matter

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 3)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES / "dataset", root)
    return root


def _run(data_dir: Path, html: str = "pagina-v1.html", url: str = "") -> int:
    return ingest.run(
        source_id="pagina-demo",
        url=url,
        html_path=FIXTURES / html,
        data_dir=data_dir,
        today=TODAY,
    )


def test_html_becomes_markdown_with_front_matter(data_dir: Path) -> None:
    code = _run(data_dir, url="https://example.org/carta")

    assert code == 0
    meta, body = split_front_matter(
        (data_dir / "pages" / "pagina-demo.md").read_text(encoding="utf-8")
    )
    assert meta["url"] == "https://example.org/carta"
    assert meta["ente"] == "Comune di Prova"
    assert meta["servizio"] == ["servizio-demo"]
    assert meta["verified_at"] == "2026-10-03"
    assert meta["content_hash"] == content_hash(body)
    assert "# Rinnovo della carta finta" in body
    assert "carta d\u2019identità scaduta" in body
    assert "- Una fototessera recente" in body
    for dropped in ("tracker", "color: red", "Menu principale", "Logo del sito", "Piè di pagina"):
        assert dropped not in body


def test_sources_row_updated_and_other_rows_untouched(data_dir: Path) -> None:
    before = (data_dir / "sources.csv").read_text(encoding="utf-8").splitlines()

    _run(data_dir, url="https://example.org/carta")

    after = (data_dir / "sources.csv").read_text(encoding="utf-8").splitlines()
    assert after[0] == before[0]
    assert after[2] == before[2]
    assert after[1] == (
        "pagina-demo,Pagina demo,https://example.org/carta,Comune di Prova,page,"
        'pages/pagina-demo.md,2026-10-03,ok,"Nota con virgola, da non toccare"'
    )


def test_quote_found_in_page_with_front_matter(data_dir: Path) -> None:
    _run(data_dir)
    service = data_dir / "services" / "servizio-demo.json"
    service.write_text(
        service.read_text(encoding="utf-8").replace(
            '"quote": "", "verified_at": null, "status": "todo"',
            '"quote": "Per il rinnovo serve la carta d\'identità scaduta.", '
            '"verified_at": "2026-10-03", "status": "verified"',
        ),
        encoding="utf-8",
    )

    assert check_catalog(data_dir) == []


def test_changed_page_lists_requirements_to_reverify(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(data_dir)
    first_hash = split_front_matter(
        (data_dir / "pages" / "pagina-demo.md").read_text(encoding="utf-8")
    )[0]["content_hash"]
    capsys.readouterr()

    _run(data_dir)
    assert "invariato" in capsys.readouterr().out

    _run(data_dir, html="pagina-v2.html")
    out = capsys.readouterr().out
    meta, _ = split_front_matter((data_dir / "pages" / "pagina-demo.md").read_text("utf-8"))
    assert meta["content_hash"] != first_hash
    assert "cambiato" in out
    assert "servizio-demo/carta-scaduta" in out


def test_unknown_source_fails(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = ingest.run(
        source_id="non-esiste", url="", html_path=FIXTURES / "pagina-v1.html", data_dir=data_dir
    )

    assert code == 1
    assert "non-esiste" in capsys.readouterr().out


def test_source_without_url_and_html_fails(data_dir: Path) -> None:
    assert ingest.run(source_id="pagina-demo", url="", html_path=None, data_dir=data_dir) == 1


def _transport(robots: str | None, page_status: int = 200) -> tuple[httpx.MockTransport, list[str]]:
    seen: list[str] = []
    html = (FIXTURES / "pagina-v1.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.path}|{request.headers['user-agent']}")
        if request.url.path == "/robots.txt":
            if robots is None:
                return httpx.Response(404)
            return httpx.Response(200, text=robots)
        return httpx.Response(page_status, text=html)

    return httpx.MockTransport(handler), seen


def test_fetch_respects_robots_and_rate_limit(data_dir: Path) -> None:
    transport, seen = _transport(robots=None)
    sleeps: list[float] = []

    code = ingest.run(
        source_id="pagina-demo",
        url="https://example.org/servizi/carta",
        html_path=None,
        data_dir=data_dir,
        transport=transport,
        today=TODAY,
        sleep=sleeps.append,
    )

    assert code == 0
    assert [s.split("|")[0] for s in seen] == ["/robots.txt", "/servizi/carta"]
    assert all(s.endswith(ingest.USER_AGENT) for s in seen)
    assert len(sleeps) == 1 and 0 < sleeps[0] <= ingest.MIN_REQUEST_INTERVAL_S
    assert (data_dir / "pages" / "pagina-demo.md").exists()


def test_fetch_blocked_by_robots(data_dir: Path) -> None:
    transport, seen = _transport(robots=(FIXTURES / "robots-disallow.txt").read_text("utf-8"))

    code = ingest.run(
        source_id="pagina-demo",
        url="https://example.org/privato/carta",
        html_path=None,
        data_dir=data_dir,
        transport=transport,
        sleep=lambda _: None,
    )

    assert code == 1
    assert [s.split("|")[0] for s in seen] == ["/robots.txt"]
    assert not (data_dir / "pages" / "pagina-demo.md").exists()


def test_fetch_http_error(data_dir: Path) -> None:
    transport, _ = _transport(robots=None, page_status=403)

    with pytest.raises(ingest.IngestError, match="403"):
        ingest.fetch("https://example.org/carta", transport=transport, sleep=lambda _: None)
    assert "carta" not in (data_dir / "sources.csv").read_text("utf-8").split("\n")[1]
