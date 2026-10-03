"""La riga di comando espone i comandi previsti dal backlog e li collega ai moduli."""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from onevisit_cli.main import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"
REAL_DATA = Path(__file__).resolve().parents[3] / "data"


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("ingest", "catalog-check", "seed-demo", "eval"):
        assert command in result.output


def test_catalog_check_on_real_data() -> None:
    result = runner.invoke(app, ["catalog-check", "--data-dir", str(REAL_DATA)])

    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_ingest_requires_source_id() -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code != 0


def test_ingest_from_saved_html(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES / "dataset", root)

    result = runner.invoke(
        app,
        [
            "ingest",
            "pagina-demo",
            "--html",
            str(FIXTURES / "pagina-v1.html"),
            "--url",
            "https://example.org/carta",
            "--data-dir",
            str(root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (root / "pages" / "pagina-demo.md").exists()
    assert "https://example.org/carta" in (root / "sources.csv").read_text(encoding="utf-8")
