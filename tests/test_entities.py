from opentearsheet import entities


def test_lookup_ticker_case_insensitive(client):
    entity = entities.lookup_ticker(client, "exmp")
    assert entity.cik == "0001999999"
    assert entity.name == "Example Robotics Inc."


def test_share_class_tickers_use_dashes(client):
    assert entities.normalize_ticker("brk.b") == "BRK-B"
    assert entities.lookup_ticker(client, "demo.b").cik == "0001777777"


def test_unknown_ticker(client):
    assert entities.lookup_ticker(client, "NOPE") is None


def test_resolve_company_by_cik(client):
    entity = entities.resolve_company(client, "1999999")
    assert entity.ticker == "EXMP"


def test_13f_search_filters_non_matching_filers(client):
    found = entities.search_13f_filers(client, "Sample Capital")
    assert [c.id for c in found] == ["0001888888"]
    assert found[0].name == "Sample Capital Management LLC"


def test_adviser_search(client):
    found = entities.search_advisers(client, "Sample Capital")
    assert found[0].id == "160001"
    assert "NEW YORK, NY" in found[0].detail
    assert "801-120001" in found[0].label


def test_direct_crd(client):
    assert entities.search_advisers(client, "160001")[0].id == "160001"
