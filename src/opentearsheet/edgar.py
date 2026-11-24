"""EDGAR endpoints and helpers. Every endpoint here is free, public and keyless."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

SEC_WWW = "https://www.sec.gov"
TICKERS_URL = f"{SEC_WWW}/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


def pad_cik(cik: object) -> str:
    return str(int(str(cik).strip())).zfill(10)


def folder_url(cik: object, accession: str) -> str:
    return f"{SEC_WWW}/Archives/edgar/data/{int(str(cik))}/{accession.replace('-', '')}"


def index_url(cik: object, accession: str) -> str:
    """Human-readable filing index page (best link to cite)."""
    return f"{folder_url(cik, accession)}/{accession}-index.htm"


def company_page_url(cik: object) -> str:
    return f"{SEC_WWW}/cgi-bin/browse-edgar?action=getcompany&CIK={pad_cik(cik)}"


def insider_page_url(cik: object) -> str:
    return f"{SEC_WWW}/cgi-bin/own-disp?action=getissuer&CIK={pad_cik(cik)}"


def get_submissions(client, cik: object) -> dict:
    return client.get_json(SUBMISSIONS_URL.format(cik=pad_cik(cik)))


def recent_filings(subs: dict, forms: Optional[Iterable[str]] = None) -> list[dict]:
    """Rows from ``filings.recent`` (newest first), optionally filtered by form type."""
    wanted = set(forms) if forms else None
    recent = ((subs or {}).get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber") or []
    cik = subs.get("cik")
    columns = {k: v for k, v in recent.items() if isinstance(v, list)}
    out = []
    for i, acc in enumerate(accessions):
        row = {k: (v[i] if i < len(v) else None) for k, v in columns.items()}
        if wanted and row.get("form") not in wanted:
            continue
        row["url"] = f"{folder_url(cik, acc)}/{row.get('primaryDocument') or ''}"
        row["index_url"] = index_url(cik, acc)
        out.append(row)
    return out


def parse_date(value: object) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
