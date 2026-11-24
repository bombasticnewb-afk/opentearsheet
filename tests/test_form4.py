import pytest

from opentearsheet.connectors.form4 import InsiderTrades, parse_form4, raw_xml_name
from tests.fixture_transport import FIXTURES


def test_raw_xml_name_strips_xsl_folder():
    assert raw_xml_name("xslF345X05/form4.xml") == "form4.xml"
    assert raw_xml_name("form4.xml") == "form4.xml"


def test_parse_sale_with_10b5_1_checkbox():
    rows = parse_form4((FIXTURES / "form4_ceo_sale.xml").read_bytes(), accession="a", filing_date="2026-11-14", url="u")
    assert len(rows) == 2
    first = rows[0]
    assert first["owner"] == "Founder Jane Q"
    assert first["relationship"] == "Director, Chief Executive Officer"
    assert first["url"] == "u"
    assert (first["code"], first["acq_disp"], first["rule_10b5_1"]) == ("S", "D", "yes")
    assert first["value"] == pytest.approx(20000 * 52.10)
    assert first["shares_owned_after"] == 1_180_000


def test_parse_true_false_flags_and_unchecked_plan():
    rows = parse_form4((FIXTURES / "form4_director_buy.xml").read_bytes())
    assert rows[0]["relationship"] == "Director"
    assert rows[0]["rule_10b5_1"] == "no"


def test_parse_derivatives_and_old_schema():
    rows = parse_form4((FIXTURES / "form4_cfo_exercise.xml").read_bytes())
    assert [r["code"] for r in rows] == ["M", "F", "M"]
    assert [r["is_derivative"] for r in rows] == [False, False, True]
    assert all(r["rule_10b5_1"] == "not indicated" for r in rows)


def test_connector_summary(client, company, options):
    section = InsiderTrades().run(client, company, options)
    facts = {f.key: f for f in section.facts}
    sales = 20000 * 52.10 + 15000 * 52.85
    assert facts["form4.sells"].value == pytest.approx(sales)
    assert facts["form4.buys"].value == pytest.approx(5000 * 48.20)
    assert facts["form4.net"].value == pytest.approx(5000 * 48.20 - sales)
    assert facts["form4.plan_share"].value == 100.0
    assert "Founder Jane Q" in facts["form4.largest"].text
    assert len(section.rows) == 6
    assert all(f.sources for f in section.facts)
    # Citations point at the SEC's rendered (XSL) view, not the raw XML.
    assert all("/xslF345X0" in r["url"] for r in section.rows)
    # The 2025 filing falls outside the 365-day window and is never fetched.
    assert not any("000199999925000300" in r["url"] for r in section.rows)


def test_connector_respects_cap(client, company, options):
    section = InsiderTrades().run(client, company, {**options, "max_form4": 1})
    assert len({r["accession"] for r in section.rows}) == 1
    assert any("Capped" in n for n in section.notes)
