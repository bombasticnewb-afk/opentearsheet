import pytest

from opentearsheet.cache import HttpCache
from opentearsheet.edgar import TICKERS_URL
from opentearsheet.sec_client import HttpError, SecClient
from tests.conftest import UA


def test_cache_respects_max_age():
    cache = HttpCache()
    cache.put("u", 200, "application/json", b"1", now=1000)
    assert cache.get("u", max_age=10, now=1005).body == b"1"
    assert cache.get("u", max_age=10, now=1011) is None
    assert cache.get("u", max_age=None, now=10**9) is not None


def test_cache_persists_and_clears(tmp_path):
    path = tmp_path / "data" / "cache.sqlite3"
    cache = HttpCache(path)
    cache.put("u", 200, "text/xml", b"<x/>")
    cache.close()
    reopened = HttpCache(path)
    assert reopened.get("u").body == b"<x/>"
    assert reopened.stats()["entries"] == 1
    reopened.clear()
    assert reopened.stats()["entries"] == 0


def test_client_serves_second_request_from_cache(client, transport):
    client.get(TICKERS_URL)
    client.get(TICKERS_URL)
    assert transport.calls.count(TICKERS_URL) == 1
    assert client.stats == {"network": 1, "cache_hits": 1}


def test_client_sends_declared_user_agent(client, transport):
    client.get(TICKERS_URL)
    assert transport.headers[0]["User-Agent"] == UA


def test_client_retries_transient_errors():
    responses = [(503, "", b""), (429, "", b""), (200, "text/plain", b"ok")]
    sleeps = []
    client = SecClient(UA, None, transport=lambda u, h, t: responses.pop(0), sleep=sleeps.append)
    assert client.get("https://data.sec.gov/x") == b"ok"
    assert [s for s in sleeps if s >= 1] == [1, 2]


def test_client_403_explains_user_agent():
    client = SecClient(UA, None, transport=lambda u, h, t: (403, "", b""), sleep=lambda _: None)
    with pytest.raises(HttpError, match="SEC_USER_AGENT"):
        client.get("https://www.sec.gov/files/company_tickers.json")


def test_client_network_failure_becomes_http_error():
    def boom(url, headers, timeout):
        raise OSError("connection reset")

    client = SecClient(UA, None, transport=boom, sleep=lambda _: None, max_retries=1)
    with pytest.raises(HttpError, match="connection reset"):
        client.get("https://data.sec.gov/x")


def test_errors_are_not_cached(transport):
    cache = HttpCache()
    client = SecClient(UA, cache, transport=transport, sleep=lambda _: None)
    with pytest.raises(HttpError):
        client.get("https://www.sec.gov/does-not-exist")
    assert cache.stats()["entries"] == 0


def test_ttl_policy():
    client = SecClient(UA, None, ttl_hours=6)
    assert client.ttl_for("https://www.sec.gov/Archives/edgar/data/1999999/000199999926000101/form4.xml") is None
    assert client.ttl_for(TICKERS_URL) == 24 * 3600
    assert client.ttl_for("https://data.sec.gov/submissions/CIK0001999999.json") == 6 * 3600


def test_user_agent_required():
    with pytest.raises(ValueError):
        SecClient("", None)
