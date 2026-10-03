"""La riga di comando espone i comandi previsti dal backlog."""

from typer.testing import CliRunner

from onevisit_cli.main import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("ingest", "catalog-check", "seed-demo", "eval"):
        assert command in result.output


def test_unimplemented_command_points_to_its_story() -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 1
    assert "A1" in result.output
