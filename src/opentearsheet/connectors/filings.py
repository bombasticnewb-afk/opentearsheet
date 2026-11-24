"""Company profile, latest periodic reports and notable 8-K items (from the submissions API)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from ..edgar import company_page_url, get_submissions, parse_date, recent_filings
from ..models import Fact, Section, Source
from ..registry import BaseConnector, register

KEY_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "20-F", "40-F", "6-K", "DEF 14A", "S-1", "S-3")

# 8-K items an analyst usually wants surfaced.
NOTABLE_8K_ITEMS = {
    "1.03": "bankruptcy or receivership",
    "1.05": "material cybersecurity incident",
    "2.01": "completed acquisition or disposition",
    "2.05": "exit or restructuring costs",
    "2.06": "material impairment",
    "3.01": "delisting or listing-standard notice",
    "4.01": "change of auditor",
    "4.02": "non-reliance on prior financials (restatement)",
    "5.01": "change in control",
    "5.02": "director or officer departure/appointment",
}

COLUMNS = ["filingDate", "form", "reportDate", "items", "primaryDocDescription", "accessionNumber", "index_url"]


def _source(row: dict) -> Source:
    items = f" · items {row['items']}" if row.get("items") else ""
    return Source(f"{row['form']} · filed {row['filingDate']}{items}", row["index_url"])


@register
class RecentFilings(BaseConnector):
    name = "filings"
    title = "Company profile & recent filings"
    entity_kinds = ("company",)
    order = 10

    def applies(self, entity) -> bool:
        return entity.kind == "company" and bool(entity.cik)

    def run(self, client, entity, options) -> Section:
        as_of: date = options.get("as_of") or date.today()
        subs = get_submissions(client, entity.cik)
        rows = recent_filings(subs, KEY_FORMS)[: int(options.get("max_filings", 25))]
        company_src = Source(f"EDGAR company page · CIK {entity.cik}", company_page_url(entity.cik))
        facts: list[Fact] = []

        profile = []
        if subs.get("sicDescription"):
            profile.append(f"industry (SIC {subs.get('sic')}): {subs['sicDescription']}")
        if subs.get("exchanges"):
            profile.append("listed on " + ", ".join(x for x in subs["exchanges"] if x))
        fye = str(subs.get("fiscalYearEnd") or "")
        if len(fye) == 4 and fye.isdigit() and 1 <= int(fye[:2]) <= 12:
            profile.append(f"fiscal year ends {calendar.month_name[int(fye[:2])]} {int(fye[2:])}")
        if subs.get("stateOfIncorporation"):
            profile.append(f"incorporated in {subs['stateOfIncorporation']}")
        if profile:
            facts.append(Fact("filings.profile", f"{subs.get('name') or entity.name}: " + "; ".join(profile), sources=[company_src]))

        for key, forms, label in (
            ("filings.latest_annual", ("10-K", "20-F", "40-F"), "annual report"),
            ("filings.latest_quarterly", ("10-Q",), "quarterly report"),
        ):
            row = next((r for r in rows if r.get("form") in forms), None)
            if row:
                facts.append(Fact(key, f"Latest {label}: {row['form']} for the period ended {row.get('reportDate') or 'n/a'}, filed {row['filingDate']}", value=row["filingDate"], sources=[_source(row)]))

        window_start = as_of - timedelta(days=90)
        eight_ks = [r for r in rows if str(r.get("form", "")).startswith("8-K") and (parse_date(r.get("filingDate")) or date.min) >= window_start]
        facts.append(Fact(
            "filings.8k_count_90d",
            f"{len(eight_ks)} Form 8-K current report(s) filed in the 90 days to {as_of.isoformat()}",
            value=len(eight_ks),
            sources=[_source(r) for r in eight_ks] or [company_src],
        ))
        notable = []
        for r in eight_ks:
            for item in str(r.get("items") or "").split(","):
                item = item.strip()
                if item in NOTABLE_8K_ITEMS:
                    notable.append((item, r))
        if notable:
            text = "; ".join(f"Item {i} ({NOTABLE_8K_ITEMS[i]}) on {r['filingDate']}" for i, r in notable)
            facts.append(Fact("filings.notable_8k", f"Notable 8-K items in that window: {text}", value=len(notable), sources=list(dict.fromkeys(_source(r) for _, r in notable))))

        notes = ["Based on the most recent filings listed by the SEC submissions API (up to ~1,000 per company)."]
        return Section(self.name, self.title, facts, rows, notes, COLUMNS)
