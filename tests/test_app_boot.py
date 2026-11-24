"""Boots the real Streamlit app headlessly. Skipped when Streamlit isn't installed."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_boots_without_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("OPENTEARSHEET_DEMO", raising=False)
    monkeypatch.setenv("OPENTEARSHEET_DATA_DIR", str(tmp_path))
    at = st_testing.AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception


def test_app_boots_in_offline_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENTEARSHEET_DEMO", "1")
    monkeypatch.setenv("OPENTEARSHEET_DATA_DIR", str(tmp_path))
    at = st_testing.AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("OpenTearsheet" in t.value for t in at.title)
