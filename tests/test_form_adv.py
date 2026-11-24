import json

from opentearsheet.connectors.form_adv import AdviserSnapshot, parse_iapd_firm
from opentearsheet.models import Entity
from tests.fixture_transport import FIXTURES


def test_parse_detail_payload_with_json_string_content():
    info = parse_iapd_firm(json.loads((FIXTURES / "iapd_firm.json").read_text()))
    assert info["crd"] == "160001"
    assert info["sec_number"] == "801-120001"
    assert info["adv_filing_date"] == "03/28/2026"
    assert info["notice_filings"] == ["New York", "Florida", "Texas"]
    assert info["registrations"][0]["status"] == "Approved"


def test_parse_search_payload_shape_too():
    info = parse_iapd_firm(json.loads((FIXTURES / "iapd_search.json").read_text()))
    assert info["name"] == "SAMPLE CAPITAL MANAGEMENT LLC"
    assert info["sec_number"] == "801-120001"
    assert "NEW YORK" in info["office"]


def test_parse_empty_payload():
    assert parse_iapd_firm({}) == {}


def test_connector_facts_cite_iapd(client):
    section = AdviserSnapshot().run(client, Entity(kind="firm", name="x", crd="160001"), {})
    texts = " ".join(f.text for f in section.facts)
    assert "801-120001" in texts and "Approved" in texts and "3 (" in texts
    assert all("adviserinfo.sec.gov" in s.url for f in section.facts for s in f.sources)
    assert {"field": "crd", "value": "160001"} in section.rows
