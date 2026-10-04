"""Shared setup for the Streamlit app tests (no API key, no network).

python -m pytest tests/streamlit -q
"""

from __future__ import annotations

import pathlib
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in (str(ROOT), str(ROOT / "app"), str(pathlib.Path(__file__).resolve().parent)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def no_key(monkeypatch):
    """No Anthropic key in the environment (the .env placeholder doesn't count as one)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-...")


@pytest.fixture
def no_network(monkeypatch):
    """Fail any attempt to open an internet connection."""
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1") and not str(host).startswith("/"):
            raise AssertionError(f"network call attempted to {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
