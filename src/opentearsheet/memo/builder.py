"""Turn connector output into a cited, one-page memo.

Every fact gets an id (F1, F2, ...). The narrative, whether written by the deterministic
template or by an LLM, may only reference those ids; unknown citations are stripped,
and LLM output with no valid citations is discarded in favour of the template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .. import __version__
from ..models import Entity, Fact, Section
from ..registry import connectors_for

CITE_GROUP = re.compile(r"\[\s*(F\d+(?:\s*[,;]\s*F\d+)*)\s*\]")

SYSTEM_PROMPT = """You are a meticulous buy-side research assistant writing a one-page memo.
Rules:
- Use ONLY the numbered facts provided. Do not add outside knowledge, prices, forecasts or ratings.
- End every sentence that states a number, date, name or claim with its citation(s), e.g. [F3] or [F2][F5].
- Do not give investment advice or recommendations.
- If the facts are thin or mixed, say so plainly.
- Format (Markdown): '## Summary' (2-3 sentences), '## Key observations' (3-6 bullets), '## What to verify next' (2-4 bullets).
- At most 350 words."""


@dataclass
class Memo:
    entity: Entity
    sections: list[Section]
    facts: list[Fact]
    narrative: str
    narrative_source: str
    generated_at: str
    warnings: list[str] = field(default_factory=list)
    version: str = __version__


def number_facts(sections: list[Section]) -> list[Fact]:
    facts: list[Fact] = []
    for section in sections:
        for fact in section.facts:
            fact.id = f"F{len(facts) + 1}"
            facts.append(fact)
    return facts


def template_narrative(entity: Entity, sections: list[Section], facts: list[Fact]) -> str:
    n_docs = len({s.url for f in facts for s in f.sources})
    lines = [
        "## Summary",
        f"This tearsheet compiles {len(facts)} facts about **{entity.name}** from {n_docs} public SEC record(s). "
        "Each line cites its source below. It was generated deterministically (no LLM) and contains no opinions or recommendations.",
        "",
    ]
    for section in sections:
        if not section.facts:
            continue
        lines.append(f"## {section.title}")
        lines += [f"- {f.text} [{f.id}]" for f in section.facts]
        lines.append("")
    return "\n".join(lines).strip()


def build_messages(entity: Entity, facts: list[Fact]) -> list[dict]:
    fact_lines = "\n".join(f"[{f.id}] {f.text}" for f in facts)
    user = (
        f"Entity: {entity.display}\n"
        f"Today: {datetime.now(timezone.utc).date().isoformat()}\n\n"
        f"Facts:\n{fact_lines}\n\nWrite the memo now."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def validate_citations(text: str, valid_ids: set[str]) -> tuple[str, list[str], int]:
    """Normalize ``[F1, F2]`` to ``[F1][F2]``, drop unknown ids. Returns (text, warnings, valid_count)."""
    unknown: set[str] = set()
    used = 0

    def replace(match: re.Match) -> str:
        nonlocal used
        ids = [i.strip() for i in re.split(r"[,;]", match.group(1))]
        good = [i for i in ids if i in valid_ids]
        unknown.update(i for i in ids if i not in valid_ids)
        used += len(good)
        return "".join(f"[{i}]" for i in good) if good else "[citation removed]"

    cleaned = CITE_GROUP.sub(replace, text)
    warnings = [f"Removed citations to facts that do not exist: {', '.join(sorted(unknown))}"] if unknown else []
    return cleaned, warnings, used


def build_memo(
    client: Any,
    entity: Entity,
    *,
    options: Optional[dict] = None,
    connectors: Optional[list] = None,
    llm: Any = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Memo:
    opts = dict(options or {})
    if progress:
        opts.setdefault("progress", progress)
    chosen = connectors if connectors is not None else connectors_for(entity)

    sections: list[Section] = []
    warnings: list[str] = []
    for connector in chosen:
        if progress:
            progress(f"Fetching {connector.title}…")
        try:
            sections.append(connector.run(client, entity, opts))
        except Exception as exc:  # report and keep going: partial memos beat no memo
            warnings.append(f"{connector.title} failed: {exc}")

    facts = number_facts(sections)
    narrative = template_narrative(entity, sections, facts)
    source = "template (no LLM)"

    if llm is not None and facts:
        if progress:
            progress(f"Writing narrative with {llm.label}…")
        try:
            text = llm.complete(build_messages(entity, facts))
            text, cite_warnings, used = validate_citations(text, {f.id for f in facts})
            if used == 0:
                warnings.append("The LLM response had no valid citations, so the deterministic template memo is shown instead.")
            else:
                narrative, source = text.strip(), llm.label
                warnings += cite_warnings
        except Exception as exc:
            warnings.append(f"LLM narrative failed ({exc}); showing the template memo instead.")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return Memo(entity, sections, facts, narrative, source, generated, warnings)
