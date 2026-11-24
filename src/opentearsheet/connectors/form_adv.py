"""Investment adviser snapshot from the SEC's public IAPD records (Form ADV registration data).

Experimental: the JSON endpoints behind adviserinfo.sec.gov are public and keyless but
undocumented, so parsing is defensive and every field is optional.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..models import Fact, Section, Source
from ..registry import BaseConnector, register
from ..util import first_of, maybe_json

IAPD_FIRM_URL = "https://api.adviserinfo.sec.gov/search/firm/{crd}"
IAPD_SUMMARY_URL = "https://adviserinfo.sec.gov/firm/summary/{crd}"
ADV_REPORT_URL = "https://reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf"


def parse_iapd_firm(payload: dict) -> dict:
    """Normalize an IAPD firm payload (detail or search shape) into a flat dict."""
    hits = ((payload or {}).get("hits") or {}).get("hits") or []
    if not hits:
        return {}
    src = hits[0].get("_source") or {}
    content = maybe_json(first_of(src, "iacontent", "content"))
    basic = content.get("basicInformation") or {}
    address = (content.get("iaFirmAddressDetails") or {}).get("officeAddress") or maybe_json(src.get("firm_address_details")).get("officeAddress") or {}

    sec_no, sec_type = first_of(basic, "iaSECNumber"), first_of(basic, "iaSECNumberType")
    sec_number = f"{sec_type}-{sec_no}" if sec_no and sec_type else (sec_no or first_of(src, "firm_ia_full_sec_number"))
    registrations = [
        {
            "jurisdiction": first_of(r, "secJurisdiction", "jurisdiction"),
            "status": r.get("status"),
            "effective": first_of(r, "effectiveDate", "statusDate"),
        }
        for r in (content.get("registrationStatus") or [])
        if isinstance(r, dict)
    ]
    notice = [first_of(n, "jurisdiction", "state") for n in (content.get("noticeFilings") or []) if isinstance(n, dict)]
    return {
        "crd": str(first_of(basic, "firmId") or first_of(src, "firm_source_id") or ""),
        "name": first_of(basic, "firmName") or first_of(src, "firm_name"),
        "other_names": first_of(basic, "otherNames") or first_of(src, "firm_other_names") or [],
        "sec_number": sec_number,
        "scope": first_of(basic, "iaScope") or first_of(src, "firm_ia_scope", "firm_scope"),
        "adv_filing_date": first_of(basic, "advFilingDate"),
        "branches": first_of(src, "firm_branches_count"),
        "office": ", ".join(str(x) for x in (address.get("street1"), address.get("city"), address.get("state"), address.get("postalCode"), address.get("country")) if x),
        "registrations": registrations,
        "notice_filings": [n for n in notice if n],
    }


@register
class AdviserSnapshot(BaseConnector):
    name = "form_adv"
    title = "Adviser snapshot (Form ADV)"
    entity_kinds = ("firm",)
    experimental = True
    order = 40

    def applies(self, entity) -> bool:
        return entity.kind == "firm" and bool(entity.crd)

    def run(self, client, entity, options) -> Section:
        crd = str(entity.crd)
        query = urlencode({"hl": "true", "nrows": 12, "query": "", "r": 25, "wt": "json"})
        info = parse_iapd_firm(client.get_json(f"{IAPD_FIRM_URL.format(crd=crd)}?{query}"))
        summary = Source(f"IAPD firm summary · CRD {crd}", IAPD_SUMMARY_URL.format(crd=crd))
        report = Source(f"Form ADV Part 1 report (PDF) · CRD {crd}", ADV_REPORT_URL.format(crd=crd))
        notes = [
            "Experimental: uses the public JSON endpoints behind adviserinfo.sec.gov, which are undocumented and may change.",
            "Regulatory AUM, client counts and fee data (Form ADV Items 5–7) are not parsed yet; see the linked Form ADV report. Good first contribution!",
        ]
        if not info:
            return Section(self.name, self.title, [Fact("form_adv.missing", f"No IAPD adviser record returned for CRD {crd}", sources=[summary])], [], notes, ["field", "value"])

        facts = [Fact("form_adv.identity", f"{info['name']}: IAPD CRD {info['crd'] or crd}" + (f", SEC file number {info['sec_number']}" if info["sec_number"] else ""), value=info["crd"] or crd, sources=[summary])]
        if info["scope"]:
            facts.append(Fact("form_adv.scope", f"Adviser registration scope on IAPD: {info['scope']}", value=info["scope"], sources=[summary]))
        if info["adv_filing_date"]:
            facts.append(Fact("form_adv.filing_date", f"Most recent Form ADV filing date shown on IAPD: {info['adv_filing_date']}", value=info["adv_filing_date"], sources=[summary, report]))
        if info["office"]:
            facts.append(Fact("form_adv.office", f"Main office: {info['office']}" + (f" ({info['branches']} branch office(s) listed)" if info["branches"] else ""), value=info["office"], sources=[summary]))
        if info["registrations"]:
            regs = "; ".join(f"{r['jurisdiction']}: {r['status']}" + (f" since {r['effective']}" if r["effective"] else "") for r in info["registrations"][:6])
            facts.append(Fact("form_adv.registrations", f"Registration status: {regs}", value=len(info["registrations"]), sources=[summary]))
        if info["notice_filings"]:
            shown = ", ".join(info["notice_filings"][:8]) + (" …" if len(info["notice_filings"]) > 8 else "")
            facts.append(Fact("form_adv.notice", f"State notice filings: {len(info['notice_filings'])} ({shown})", value=len(info["notice_filings"]), sources=[summary]))
        if info["other_names"]:
            facts.append(Fact("form_adv.aka", "Other names on file: " + ", ".join(info["other_names"][:5]), value=len(info["other_names"]), sources=[summary]))

        rows = [{"field": k, "value": v} for k, v in (
            ("name", info["name"]), ("crd", info["crd"] or crd), ("sec_number", info["sec_number"]), ("scope", info["scope"]),
            ("adv_filing_date", info["adv_filing_date"]), ("office", info["office"]), ("branches", info["branches"]),
            ("other_names", "; ".join(info["other_names"])), ("notice_filings", "; ".join(info["notice_filings"])),
            ("iapd_summary", summary.url), ("adv_report_pdf", report.url),
        )]
        rows += [{"field": f"registration: {r['jurisdiction']}", "value": f"{r['status']} ({r['effective']})"} for r in info["registrations"]]
        return Section(self.name, self.title, facts, rows, notes, ["field", "value"])
