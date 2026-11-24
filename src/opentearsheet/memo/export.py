"""Markdown and CSV exports."""

from __future__ import annotations

import csv
import io
from typing import Iterable, Optional

from ..models import Fact, Section
from ..util import csv_safe, md_escape
from .builder import Memo

MAX_SOURCES_SHOWN = 5


def memo_to_markdown(memo: Memo) -> str:
    e = memo.entity
    ids = [x for x in (f"Ticker {e.ticker}" if e.ticker else None, f"CIK {e.cik}" if e.cik else None, f"CRD {e.crd}" if e.crd else None) if x]
    out = [
        f"# {e.name}: research tearsheet",
        "",
        f"> {' · '.join(ids)}  " if ids else ">  ",
        f"> Generated {memo.generated_at} with OpenTearsheet v{memo.version} · Narrative: {memo.narrative_source}  ",
        "> Source data: public SEC EDGAR / IAPD records. For research only, not investment advice. Verify against the linked filings.",
        "",
        memo.narrative,
        "",
        "## Sources",
        "",
    ]
    # The template narrative already lists every fact verbatim; an LLM narrative paraphrases,
    # so in that case the exact fact text is repeated here for verification.
    show_text = not memo.narrative_source.startswith("template")
    for f in memo.facts:
        links = [f"[{md_escape(s.label)}]({s.url})" for s in f.sources[:MAX_SOURCES_SHOWN]]
        extra = len(f.sources) - MAX_SOURCES_SHOWN
        if extra > 0:
            links.append(f"+{extra} more in the CSV export")
        prefix = f"- **[{f.id}]** {f.text}: " if show_text else f"- **[{f.id}]** "
        out.append(prefix + ("; ".join(links) if links else "derived from the sections above"))

    notes = [(s.title, n) for s in memo.sections for n in s.notes]
    if notes or memo.warnings:
        out += ["", "## Caveats", ""]
        out += [f"- *{title}:* {note}" for title, note in notes]
        out += [f"- ⚠️ {w}" for w in memo.warnings]
    return "\n".join(out).rstrip() + "\n"


def rows_to_csv(rows: Iterable[dict], columns: Optional[list[str]] = None) -> str:
    rows = list(rows)
    cols = columns or list(dict.fromkeys(k for r in rows for k in r))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: csv_safe(r.get(k)) for k in cols})
    return buf.getvalue()


def section_to_csv(section: Section) -> str:
    return rows_to_csv(section.rows, section.columns)


def facts_to_csv(facts: list[Fact]) -> str:
    rows = [
        {
            "id": f.id,
            "key": f.key,
            "text": f.text,
            "value": f.value,
            "sources": " | ".join(s.label for s in f.sources),
            "urls": " | ".join(s.url for s in f.sources),
        }
        for f in facts
    ]
    return rows_to_csv(rows, ["id", "key", "text", "value", "sources", "urls"])
