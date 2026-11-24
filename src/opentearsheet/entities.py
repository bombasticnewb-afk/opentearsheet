"""Resolve user input (ticker, CIK, firm name, CRD) to SEC identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from .edgar import EFTS_URL, TICKERS_URL, get_submissions, pad_cik
from .models import Entity
from .util import maybe_json

IAPD_SEARCH_URL = "https://api.adviserinfo.sec.gov/search/firm"

_CIK_SUFFIX = re.compile(r"\s*\(CIK \d+\)\s*$")


@dataclass(frozen=True)
class Candidate:
    source: str  # "13F" (EDGAR CIK) or "ADV" (IAPD CRD)
    id: str
    name: str
    detail: str = ""

    @property
    def label(self) -> str:
        kind = "CIK" if self.source == "13F" else "CRD"
        extra = f" · {self.detail}" if self.detail else ""
        return f"{self.name} ({kind} {self.id}){extra}"


def normalize_ticker(ticker: str) -> str:
    # EDGAR writes share classes with a dash: BRK.B -> BRK-B
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def lookup_ticker(client, ticker: str) -> Optional[Entity]:
    wanted = normalize_ticker(ticker)
    if not wanted:
        return None
    data = client.get_json(TICKERS_URL)
    rows = data.values() if isinstance(data, dict) else data
    for row in rows:
        if str(row.get("ticker", "")).upper() == wanted:
            return Entity(kind="company", name=row.get("title") or wanted, cik=pad_cik(row["cik_str"]), ticker=wanted)
    return None


def company_from_cik(client, cik: str) -> Entity:
    subs = get_submissions(client, cik)
    tickers = subs.get("tickers") or []
    return Entity(kind="company", name=subs.get("name") or f"CIK {cik}", cik=pad_cik(cik), ticker=tickers[0] if tickers else None)


def resolve_company(client, query: str) -> Optional[Entity]:
    q = query.strip()
    if not q:
        return None
    if q.isdigit():
        return company_from_cik(client, q)
    return lookup_ticker(client, q)


def clean_display_name(value: str) -> str:
    return re.sub(r"\s+", " ", _CIK_SUFFIX.sub("", value or "")).strip()


def search_13f_filers(client, name: str, limit: int = 10) -> list[Candidate]:
    """Find 13F filers by name via EDGAR full-text search (or accept a CIK directly)."""
    q = name.strip()
    if not q:
        return []
    if q.isdigit():
        subs = get_submissions(client, q)
        return [Candidate("13F", pad_cik(q), subs.get("name") or q, "entered CIK")]
    params = {"q": f'"{q}"', "forms": "13F-HR", "entityName": q}
    data = client.get_json(f"{EFTS_URL}?{urlencode(params)}")
    tokens = [t for t in re.split(r"\W+", q.lower()) if t]
    found: dict[str, Candidate] = {}
    for hit in (data.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        for cik, display in zip(src.get("ciks") or [], src.get("display_names") or []):
            cname = clean_display_name(display)
            # Full-text hits can come from any document text; keep only filers whose name matches.
            if not all(t in cname.lower() for t in tokens):
                continue
            key = pad_cik(cik)
            if key not in found:
                filed = src.get("file_date")
                found[key] = Candidate("13F", key, cname, f"13F-HR filed {filed}" if filed else "")
        if len(found) >= limit:
            break
    return list(found.values())[:limit]


def search_advisers(client, name: str, limit: int = 10) -> list[Candidate]:
    """Find registered investment advisers via the public IAPD search (or accept a CRD)."""
    q = name.strip()
    if not q:
        return []
    if q.isdigit():
        return [Candidate("ADV", q, f"Adviser CRD {q}", "entered CRD")]
    params = {"query": q, "start": 0, "nrows": limit, "wt": "json"}
    data = client.get_json(f"{IAPD_SEARCH_URL}?{urlencode(params)}")
    out = []
    for hit in (data.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        crd = str(src.get("firm_source_id") or "").strip()
        if not crd:
            continue
        addr = maybe_json(src.get("firm_address_details")).get("officeAddress") or {}
        location = ", ".join(x for x in (addr.get("city"), addr.get("state")) if x)
        scope = src.get("firm_ia_scope") or src.get("firm_scope") or ""
        detail = " · ".join(x for x in (src.get("firm_ia_full_sec_number") or "", scope, location) if x)
        out.append(Candidate("ADV", crd, src.get("firm_name") or crd, detail))
    return out[:limit]
