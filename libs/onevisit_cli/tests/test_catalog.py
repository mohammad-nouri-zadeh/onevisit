"""Comando ``onevisit catalog-check`` (storia A2)."""

import json
import shutil
from pathlib import Path

import pytest

from onevisit_cli import catalog

FIXTURES = Path(__file__).parent / "fixtures"
REAL_DATA = Path(__file__).resolve().parents[3] / "data"


def test_real_data_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert catalog.run(data_dir=REAL_DATA) == 0
    out = capsys.readouterr().out
    assert "Requirements and steps:" in out
    assert out.strip().endswith("OK")


def test_fixture_dataset_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert catalog.run(data_dir=FIXTURES / "dataset") == 0
    assert "1 verified" in capsys.readouterr().out


def test_bad_quote_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES / "dataset", root)
    path = root / "services" / "servizio-demo.json"
    service = json.loads(path.read_text(encoding="utf-8"))
    service["requirements"][0]["quote"] = "Questa frase non è nella pagina."
    path.write_text(json.dumps(service), encoding="utf-8")

    assert catalog.run(data_dir=root) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out and "quote not found" in out
    assert "1 error(s)" in out
