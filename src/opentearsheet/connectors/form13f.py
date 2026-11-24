"""13F-HR institutional holdings: latest quarter, concentration, and quarter-over-quarter changes."""

from __future__ import annotations

from datetime import date

from ..edgar import company_page_url, folder_url, get_submissions, index_url, parse_date, recent_filings
from ..models import Fact, Section, Source
from ..registry import BaseConnector, register
from ..util import fmt_usd
from ..xmlutil import num, parse_xml, text

# Since 2023-01-03 the 13F <value> field is whole dollars; before that it was thousands.
VALUE_IN_DOLLARS_SINCE = date(2023, 1, 3)

COLUMNS = ["issuer", "class", "cusip", "put_call", "shares", "value_usd", "pct_portfolio", "status", "change_shares", "prev_shares"]


def parse_info_table(xml: bytes) -> list[dict]:
    root = parse_xml(xml)
    rows = []
    for it in root.iter("infoTable"):
        rows.append({
            "issuer": text(it, "nameOfIssuer") or "",
            "class": text(it, "titleOfClass") or "",
            "cusip": (text(it, "cusip") or "").upper(),
            "value": num(it, "value"),
            "shares": num(it, "shrsOrPrnAmt/sshPrnamt"),
            "share_type": text(it, "shrsOrPrnAmt/sshPrnamtType"),
            "put_call": text(it, "putCall") or "",
            "discretion": text(it, "investmentDiscretion"),
            "voting_sole": num(it, "votingAuthority/Sole"),
            "voting_shared": num(it, "votingAuthority/Shared"),
            "voting_none": num(it, "votingAuthority/None"),
        })
    return rows


def to_usd(value, filing_date) -> float:
    if value is None:
        return 0.0
    filed = parse_date(filing_date)
    return value * 1000.0 if filed and filed < VALUE_IN_DOLLARS_SINCE else float(value)


def aggregate(rows: list[dict], filing_date: str) -> dict[tuple, dict]:
    """Merge rows by (CUSIP, put/call); managers often split one position across several rows."""
    agg: dict[tuple, dict] = {}
    for r in rows:
        put_call = (r.get("put_call") or "").strip().title()
        key = (r["cusip"], put_call.upper())
        a = agg.setdefault(key, {"issuer": r["issuer"], "class": r["class"], "cusip": r["cusip"], "put_call": put_call, "shares": 0.0, "value_usd": 0.0})
        a["shares"] += r.get("shares") or 0.0
        a["value_usd"] += to_usd(r.get("value"), filing_date)
    total = sum(a["value_usd"] for a in agg.values())
    for a in agg.values():
        a["pct_portfolio"] = round(100.0 * a["value_usd"] / total, 2) if total else None
    return agg


def compare(current: dict[tuple, dict], prior: dict[tuple, dict]) -> list[dict]:
    rows = []
    for key, a in current.items():
        row = dict(a)
        before = prior.get(key)
        prev_shares = before["shares"] if before else 0.0
        change = a["shares"] - prev_shares
        row["prev_shares"] = prev_shares
        row["change_shares"] = change
        if before is None:
            row["status"] = "new"
        elif change > 0:
            row["status"] = "increased"
        elif change < 0:
            row["status"] = "decreased"
        else:
            row["status"] = "unchanged"
        price = a["value_usd"] / a["shares"] if a["shares"] else 0.0
        row["_flow_usd"] = change * price  # rough $ estimate of shares added/trimmed at quarter-end price
        rows.append(row)
    for key, b in prior.items():
        if key not in current:
            rows.append({**b, "shares": 0.0, "value_usd": 0.0, "pct_portfolio": 0.0, "prev_shares": b["shares"],
                         "change_shares": -b["shares"], "status": "exited", "_flow_usd": -b["value_usd"]})
    rows.sort(key=lambda r: (r["status"] == "exited", -r["value_usd"], -abs(r["_flow_usd"])))
    return rows


def info_table_candidates(index_json: dict) -> list[str]:
    items = ((index_json or {}).get("directory") or {}).get("item") or []
    names = [str(i.get("name", "")) for i in items]
    xmls = [n for n in names if n.lower().endswith(".xml") and n.lower() != "primary_doc.xml"]
    return sorted(xmls, key=lambda n: (0 if ("info" in n.lower() or "table" in n.lower()) else 1, n))


def _label(issuer: str, put_call: str) -> str:
    return f"{issuer} ({put_call.lower()})" if put_call else issuer


@register
class InstitutionalHoldings(BaseConnector):
    name = "form13f"
    title = "Institutional holdings (13F)"
    entity_kinds = ("firm",)
    order = 30

    def applies(self, entity) -> bool:
        return entity.kind == "firm" and bool(entity.cik)

    def _load(self, client, cik: str, filing: dict) -> list[dict]:
        folder = folder_url(cik, filing["accessionNumber"])
        index = client.get_json(f"{folder}/index.json")
        for name in info_table_candidates(index):
            rows = parse_info_table(client.get(f"{folder}/{name}"))
            if rows:
                return rows
        raise ValueError(f"no information table found in {filing['accessionNumber']}")

    def run(self, client, entity, options) -> Section:
        subs = get_submissions(client, entity.cik)
        filings = recent_filings(subs, ("13F-HR",))[:2]
        notes = [
            "13F-HR covers long positions in 13(f) securities only (no shorts or cash) as of quarter-end, filed up to 45 days later.",
            "Positions are merged by CUSIP and put/call. Values filed before 2023-01-03 (reported in $ thousands) are converted to dollars.",
            "Amendments (13F-HR/A) and holdings granted confidential treatment are not merged.",
        ]
        if not filings:
            src = Source(f"EDGAR company page · CIK {entity.cik}", company_page_url(entity.cik))
            return Section(self.name, self.title, [Fact("form13f.none", f"No 13F-HR filings found for CIK {entity.cik}", sources=[src])], [], notes, COLUMNS)

        latest = filings[0]
        prior = filings[1] if len(filings) > 1 else None
        if options.get("progress"):
            options["progress"]("Reading 13F information tables…")
        current = aggregate(self._load(client, entity.cik, latest), latest["filingDate"])
        previous = aggregate(self._load(client, entity.cik, prior), prior["filingDate"]) if prior else {}

        def src(f: dict) -> Source:
            return Source(f"13F-HR · period {f.get('reportDate') or 'n/a'} · filed {f['filingDate']}", index_url(entity.cik, f["accessionNumber"]))

        latest_src = src(latest)
        both = [latest_src] + ([src(prior)] if prior else [])
        total = sum(a["value_usd"] for a in current.values())
        ranked = sorted(current.values(), key=lambda a: -a["value_usd"])

        facts = [Fact("form13f.latest", f"Latest 13F-HR (period ended {latest.get('reportDate') or 'n/a'}, filed {latest['filingDate']}): {len(current)} positions with total reported value ≈{fmt_usd(total)}", value=total, sources=[latest_src])]
        if ranked:
            top10 = sum(a["value_usd"] for a in ranked[:10])
            facts.append(Fact("form13f.concentration", f"Top {min(10, len(ranked))} positions = {100 * top10 / total:.1f}% of reported value" if total else "Reported value is zero", value=round(100 * top10 / total, 1) if total else None, sources=[latest_src]))
            top5 = ", ".join(f"{_label(a['issuer'], a['put_call'])} {a['pct_portfolio']:.1f}%" for a in ranked[:5])
            facts.append(Fact("form13f.top", f"Largest positions: {top5}", value=ranked[0]["value_usd"], sources=[latest_src]))
        options_rows = [a for a in current.values() if a["put_call"]]
        if options_rows:
            facts.append(Fact("form13f.options", f"{len(options_rows)} listed-option position(s) (puts/calls) with ≈{fmt_usd(sum(a['value_usd'] for a in options_rows))} reported value (underlying exposure)", value=len(options_rows), sources=[latest_src]))

        rows = compare(current, previous)
        if prior:
            counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("new", "exited", "increased", "decreased")}
            facts.append(Fact("form13f.qoq", f"Versus the prior 13F (period ended {prior.get('reportDate') or 'n/a'}): {counts['new']} new, {counts['exited']} exited, {counts['increased']} increased and {counts['decreased']} decreased positions (by share count)", value=counts, sources=both))
            for key, status, label, sort_key in (
                ("form13f.new", "new", "Largest new positions", lambda r: -r["value_usd"]),
                ("form13f.exits", "exited", "Largest exits (prior-quarter value)", lambda r: r["_flow_usd"]),
                ("form13f.adds", "increased", "Largest adds (est. at quarter-end price)", lambda r: -r["_flow_usd"]),
                ("form13f.trims", "decreased", "Largest trims (est. at quarter-end price)", lambda r: r["_flow_usd"]),
            ):
                group = sorted((r for r in rows if r["status"] == status), key=sort_key)[:3]
                if group:
                    listing = ", ".join(f"{_label(r['issuer'], r['put_call'])} {fmt_usd(abs(r['_flow_usd']) if status != 'new' else r['value_usd'])}" for r in group)
                    facts.append(Fact(key, f"{label}: {listing}", value=len(group), sources=both))
        else:
            notes.append("Only one 13F-HR found, so quarter-over-quarter changes are unavailable.")

        for r in rows:
            r.pop("_flow_usd", None)
        return Section(self.name, self.title, facts, rows, notes, COLUMNS)
