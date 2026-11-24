"""Offline transport serving synthetic SEC/IAPD responses from ``tests/fixtures``.

Used by the test suite and by the app's "Offline demo" toggle. Every company, fund,
person and identifier in the fixtures is fictional.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Reference date that keeps every demo filing inside the default lookback windows.
DEMO_AS_OF = date(2026, 11, 20)

# (substring of the requested URL, fixture file). First match wins, so specific routes go first.
ROUTES = [
    ("/files/company_tickers.json", "company_tickers.json"),
    ("/submissions/CIK0001999999.json", "submissions_exmp.json"),
    ("/submissions/CIK0001888888.json", "submissions_sample_capital.json"),
    ("/1999999/000199999926000101/form4.xml", "form4_ceo_sale.xml"),
    ("/1999999/000199999926000095/form4.xml", "form4_director_buy.xml"),
    ("/1999999/000199999926000080/form4.xml", "form4_cfo_exercise.xml"),
    ("/1888888/000188888826000004/index.json", "index_13f_q3.json"),
    ("/1888888/000188888826000004/sample_infotable_q3.xml", "infotable_q3.xml"),
    ("/1888888/000188888826000002/index.json", "index_13f_q2.json"),
    ("/1888888/000188888826000002/sample_infotable_q2.xml", "infotable_q2.xml"),
    ("efts.sec.gov/LATEST/search-index", "efts_13f.json"),
    ("api.adviserinfo.sec.gov/search/firm/160001", "iapd_firm.json"),
    ("api.adviserinfo.sec.gov/search/firm?", "iapd_search.json"),
]


class FixtureTransport:
    """Callable with the same signature as ``sec_client.urllib_transport``."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.headers: list[dict] = []

    def __call__(self, url: str, headers: dict, timeout: float):
        self.calls.append(url)
        self.headers.append(dict(headers))
        for needle, name in ROUTES:
            if needle in url:
                content_type = "application/json" if name.endswith(".json") else "application/xml"
                return 200, content_type, (FIXTURES / name).read_bytes()
        return 404, "text/plain", b"not found"
