import pytest

from opentearsheet import registry
from opentearsheet.cli import main
from opentearsheet.models import Entity, Fact, Section, Source
from opentearsheet.registry import BaseConnector
from tests.fixture_transport import FixtureTransport


def test_builtin_connectors_registered():
    assert {"filings", "form4", "form13f", "form_adv"} <= {c.name for c in registry.all_connectors()}


def test_connectors_follow_available_identifiers():
    names = lambda e: [c.name for c in registry.connectors_for(e)]  # noqa: E731
    assert names(Entity(kind="firm", name="x", crd="1")) == ["form_adv"]
    assert names(Entity(kind="firm", name="x", cik="1")) == ["form13f"]
    assert names(Entity(kind="company", name="x", cik="1")) == ["filings", "form4"]


def test_custom_connector_plugs_in():
    @registry.register
    class Dummy(BaseConnector):
        name, title, entity_kinds, order = "dummy", "Dummy", ("company",), 5

        def run(self, client, entity, options):
            return Section(self.name, self.title, [Fact("dummy.hello", "hello", sources=[Source("s", "https://example.org")])])

    try:
        assert registry.connectors_for(Entity(kind="company", name="x", cik="1"))[0].name == "dummy"
    finally:
        registry.unregister("dummy")


def test_register_rejects_nameless_connector():
    with pytest.raises(ValueError):
        registry.register(BaseConnector())


def test_cli_company_memo_and_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner tests@opentearsheet.dev")
    monkeypatch.setenv("OPENTEARSHEET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_PROVIDER", "none")
    out = tmp_path / "memo.md"
    code = main(["company", "EXMP", "--as-of", "2026-11-20", "--out", str(out), "--csv-dir", str(tmp_path / "csv")], transport=FixtureTransport())
    assert code == 0
    assert "Example Robotics Inc.: research tearsheet" in out.read_text()
    assert {p.name for p in (tmp_path / "csv").iterdir()} == {"filings.csv", "form4.csv", "facts.csv"}


def test_cli_firm_search(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner tests@opentearsheet.dev")
    monkeypatch.setenv("OPENTEARSHEET_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert main(["firm", "Sample Capital", "--as-of", "2026-11-20"], transport=FixtureTransport()) == 0
    printed = capsys.readouterr().out
    assert "Institutional holdings (13F)" in printed and "Adviser snapshot (Form ADV)" in printed


def test_cli_requires_user_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setenv("OPENTEARSHEET_DATA_DIR", str(tmp_path / "data"))
    assert main(["company", "EXMP"], transport=FixtureTransport()) == 2
