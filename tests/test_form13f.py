import pytest

from opentearsheet.connectors.form13f import InstitutionalHoldings, aggregate, info_table_candidates, parse_info_table, to_usd
from tests.fixture_transport import FIXTURES


def test_parse_default_and_prefixed_namespaces():
    q3 = parse_info_table((FIXTURES / "infotable_q3.xml").read_bytes())
    q2 = parse_info_table((FIXTURES / "infotable_q2.xml").read_bytes())
    assert len(q3) == 6 and len(q2) == 4
    assert q3[0]["cusip"] == "30000A101"
    assert q2[-1]["issuer"] == "HOOLI MEDIA INC"


def test_values_before_2023_are_thousands():
    assert to_usd(100, "2022-11-14") == 100_000
    assert to_usd(100, "2023-02-14") == 100


def test_aggregate_merges_split_rows_and_keeps_options_separate():
    agg = aggregate(parse_info_table((FIXTURES / "infotable_q3.xml").read_bytes()), "2026-11-13")
    globex = agg[("37000B102", "")]
    assert globex["value_usd"] == 35_000_000 and globex["shares"] == 175_000
    assert agg[("37000B102", "PUT")]["put_call"] == "Put"
    assert sum(a["pct_portfolio"] for a in agg.values()) == pytest.approx(100, abs=0.05)


def test_info_table_candidates_skip_primary_doc():
    assert info_table_candidates({"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "x.xml"}, {"name": "infotable.xml"}]}}) == ["infotable.xml", "x.xml"]


def test_connector_quarter_over_quarter(client, firm):
    section = InstitutionalHoldings().run(client, firm, {})
    facts = {f.key: f for f in section.facts}
    assert facts["form13f.latest"].value == pytest.approx(76_500_000)
    assert facts["form13f.qoq"].value == {"new": 2, "exited": 1, "increased": 1, "decreased": 1}
    status = {(r["issuer"], r["put_call"]): r["status"] for r in section.rows}
    assert status[("UMBRELLA HEALTH CO", "")] == "new"
    assert status[("GLOBEX CORP", "Put")] == "new"
    assert status[("HOOLI MEDIA INC", "")] == "exited"
    assert status[("INITECH SOFTWARE INC", "")] == "increased"
    assert status[("EXAMPLE ROBOTICS INC", "")] == "decreased"
    assert status[("GLOBEX CORP", "")] == "unchanged"
    assert section.rows[0]["issuer"] == "GLOBEX CORP"  # sorted by value
    assert "_flow_usd" not in section.rows[0]
    assert all("13F-HR" in s.label for f in section.facts for s in f.sources)
