"""Form 4 insider transactions: parse every filing in the window and summarize open-market activity."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Iterable

from ..edgar import folder_url, get_submissions, insider_page_url, parse_date, recent_filings
from ..models import Fact, Section, Source
from ..registry import BaseConnector, register
from ..util import fmt_num, fmt_usd
from ..xmlutil import flag, num, parse_xml, text

# SEC Form 4 transaction codes (General Instructions, Item 8).
TRANSACTION_CODES = {
    "P": "Open-market or private purchase",
    "S": "Open-market or private sale",
    "V": "Voluntarily reported early",
    "A": "Grant or award",
    "D": "Disposition to the issuer",
    "F": "Tax or exercise-price withholding",
    "I": "Discretionary transaction",
    "M": "Exercise or conversion of derivative (Rule 16b-3)",
    "C": "Conversion of derivative",
    "E": "Expiration of short derivative position",
    "H": "Expiration of long derivative position",
    "O": "Exercise of out-of-the-money derivative",
    "X": "Exercise of in- or at-the-money derivative",
    "G": "Gift",
    "L": "Small acquisition (Rule 16a-6)",
    "W": "Will or laws of descent",
    "Z": "Voting trust deposit/withdrawal",
    "J": "Other acquisition or disposition",
    "K": "Equity swap",
    "U": "Tender in change of control",
}

COLUMNS = [
    "filing_date", "transaction_date", "owner", "relationship", "code", "code_desc", "acq_disp",
    "shares", "price", "value", "shares_owned_after", "ownership", "security", "is_derivative",
    "rule_10b5_1", "form", "accession", "url",
]


def raw_xml_name(primary_doc: str) -> str:
    """EDGAR lists the XSL-rendered path (e.g. ``xslF345X05/form4.xml``); the raw XML sits at the folder root."""
    return primary_doc.rsplit("/", 1)[-1]


def _relationship(owner) -> str:
    rel = owner.find("reportingOwnerRelationship")
    if rel is None:
        return ""
    roles = []
    if flag(rel, "isDirector"):
        roles.append("Director")
    if flag(rel, "isOfficer"):
        roles.append(text(rel, "officerTitle") or "Officer")
    if flag(rel, "isTenPercentOwner"):
        roles.append("10% owner")
    if flag(rel, "isOther"):
        roles.append(text(rel, "otherText") or "Other")
    return ", ".join(roles)


def parse_form4(xml: bytes, *, accession: str = "", filing_date: str = "", form: str = "4", url: str = "") -> list[dict]:
    root = parse_xml(xml)
    owners = root.findall("reportingOwner")
    owner_names = "; ".join(filter(None, (text(o, "reportingOwnerId/rptOwnerName") for o in owners)))
    relationship = "; ".join(filter(None, (_relationship(o) for o in owners)))
    footnotes = " ".join((f.text or "") for f in root.iter("footnote"))
    if root.find("aff10b5One") is not None:  # checkbox added to Form 4 in 2023
        plan = "yes" if flag(root, "aff10b5One") else "no"
    else:
        plan = "footnote mention" if "10b5-1" in footnotes else "not indicated"

    rows = []
    for path, is_derivative in (
        ("nonDerivativeTable/nonDerivativeTransaction", False),
        ("derivativeTable/derivativeTransaction", True),
    ):
        for tx in root.findall(path):
            shares = num(tx, "transactionAmounts/transactionShares")
            price = num(tx, "transactionAmounts/transactionPricePerShare")
            code = text(tx, "transactionCoding/transactionCode") or ""
            rows.append({
                "filing_date": filing_date,
                "transaction_date": (text(tx, "transactionDate") or "")[:10],
                "owner": owner_names,
                "relationship": relationship,
                "code": code,
                "code_desc": TRANSACTION_CODES.get(code, "Other"),
                "acq_disp": text(tx, "transactionAmounts/transactionAcquiredDisposedCode"),
                "shares": shares,
                "price": price,
                "value": round(shares * price, 2) if shares is not None and price is not None else None,
                "shares_owned_after": num(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction"),
                "ownership": text(tx, "ownershipNature/directOrIndirectOwnership"),
                "security": text(tx, "securityTitle"),
                "is_derivative": is_derivative,
                "rule_10b5_1": plan,
                "form": form,
                "accession": accession,
                "url": url,
            })
    return rows


def _sources(rows: Iterable[dict]) -> list[Source]:
    seen: dict[str, Source] = {}
    for r in rows:
        if r["accession"] not in seen:
            seen[r["accession"]] = Source(f"Form {r['form']} · filed {r['filing_date']} · {r['owner']}", r["url"])
    return list(seen.values())


def _total(rows: Iterable[dict]) -> float:
    return sum(r["value"] or 0.0 for r in rows)


def summarize(rows: list[dict], n_filings: int, cik: str) -> list[Fact]:
    overview = Source(f"EDGAR insider transactions page · CIK {cik}", insider_page_url(cik))
    if not rows:
        return [Fact("form4.coverage", f"No parseable Form 4 transactions in the {n_filings} filing(s) reviewed", value=0, sources=[overview])]

    dates = sorted(r["filing_date"] for r in rows if r["filing_date"])
    facts = [Fact(
        "form4.coverage",
        f"Reviewed {n_filings} Form 4 filing(s) filed {dates[0]} to {dates[-1]}, containing {len(rows)} reported transaction(s)",
        value=len(rows),
        sources=[overview],
    )]

    open_market = [r for r in rows if not r["is_derivative"] and r["code"] in ("P", "S") and r["shares"]]
    buys = [r for r in open_market if r["code"] == "P"]
    sells = [r for r in open_market if r["code"] == "S"]

    for key, label, group in (("form4.buys", "purchases (code P)", buys), ("form4.sells", "sales (code S)", sells)):
        if group:
            insiders = len({r["owner"] for r in group})
            shares = sum(r["shares"] or 0 for r in group)
            facts.append(Fact(key, f"Open-market {label}: {len(group)} transaction(s) by {insiders} insider(s), {fmt_num(shares)} shares, ≈{fmt_usd(_total(group))}", value=_total(group), sources=_sources(group)))
        else:
            facts.append(Fact(key, f"No open-market {label} in the reviewed filings", value=0.0, sources=[overview]))

    net = _total(buys) - _total(sells)
    facts.append(Fact("form4.net", f"Net open-market insider flow (purchases minus sales): {fmt_usd(net, signed=True)}", value=net, sources=_sources(open_market) or [overview]))

    priced = [r for r in open_market if r["value"]]
    if priced:
        top = max(priced, key=lambda r: r["value"])
        verb = "bought" if top["code"] == "P" else "sold"
        who = f"{top['owner']} ({top['relationship']})" if top["relationship"] else top["owner"]
        facts.append(Fact("form4.largest", f"Largest open-market trade: {who} {verb} {fmt_num(top['shares'])} shares at ${top['price']:,.2f} (≈{fmt_usd(top['value'])}) on {top['transaction_date']}", value=top["value"], sources=_sources([top])))

    sale_value = _total(sells)
    if sale_value:
        planned = _total(r for r in sells if r["rule_10b5_1"] == "yes")
        pct = 100.0 * planned / sale_value
        facts.append(Fact("form4.plan_share", f"{pct:.0f}% of open-market sale value was marked on the Form 4 as made under a Rule 10b5-1 trading plan", value=round(pct, 1), sources=_sources(sells)))

    other = [r for r in rows if r["code"] not in ("P", "S")]
    if other:
        counts = Counter(r["code"] for r in other)
        text_counts = "; ".join(f"{TRANSACTION_CODES.get(c, 'Other')} ({c}) ×{n}" for c, n in counts.most_common())
        facts.append(Fact("form4.other", f"Other reported activity: {text_counts}", value=sum(counts.values()), sources=_sources(other)))
    return facts


@register
class InsiderTrades(BaseConnector):
    name = "form4"
    title = "Insider trades (Form 4)"
    entity_kinds = ("company",)
    order = 20

    def applies(self, entity) -> bool:
        return entity.kind == "company" and bool(entity.cik)

    def run(self, client, entity, options) -> Section:
        as_of: date = options.get("as_of") or date.today()
        lookback = int(options.get("form4_lookback_days", 365))
        limit = int(options.get("max_form4", 40))
        progress = options.get("progress")
        cutoff = as_of - timedelta(days=lookback)

        subs = get_submissions(client, entity.cik)
        in_window = [f for f in recent_filings(subs, ("4", "4/A")) if (parse_date(f.get("filingDate")) or date.min) >= cutoff]
        filings = in_window[:limit]

        rows: list[dict] = []
        notes: list[str] = []
        for i, f in enumerate(filings, 1):
            if progress and (i == 1 or i % 5 == 0):
                progress(f"Reading Form 4 filings ({i}/{len(filings)})…")
            raw_url = f"{folder_url(entity.cik, f['accessionNumber'])}/{raw_xml_name(f.get('primaryDocument') or '')}"
            try:
                # Parse the raw XML, but cite the SEC's human-readable rendering of the same filing.
                rows.extend(parse_form4(client.get(raw_url), accession=f["accessionNumber"], filing_date=f["filingDate"], form=f["form"], url=f["url"]))
            except Exception as exc:  # one bad filing shouldn't sink the memo
                notes.append(f"Skipped {f['accessionNumber']}: {exc}")

        facts = summarize(rows, len(filings), entity.cik)
        notes += [
            f"Window: filings dated {cutoff.isoformat()} to {as_of.isoformat()}.",
            "Values are reported shares × reported price. Derivative transactions are excluded from open-market totals.",
            "Amendments (4/A) are included as filed and can duplicate the original filing.",
        ]
        if len(in_window) > limit:
            notes.append(f"Capped at the {limit} most recent of {len(in_window)} Form 4 filings in the window; raise the limit for a fuller picture.")
        return Section(self.name, self.title, facts, rows, notes, COLUMNS)
