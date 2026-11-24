"""Command-line interface: ``opentearsheet company AAPL`` / ``opentearsheet firm "Some Capital"``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from . import __version__, entities, registry
from .cache import HttpCache
from .config import ConfigError, Settings, load_dotenv
from .edgar import pad_cik
from .memo import build_memo, facts_to_csv, make_llm, memo_to_markdown, section_to_csv
from .models import Entity
from .sec_client import HttpError, SecClient, Transport


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_firm(client: SecClient, args: argparse.Namespace) -> Optional[Entity]:
    cik, crd, name = args.cik, args.crd, None
    if not cik and args.query:
        found = entities.search_13f_filers(client, args.query)
        if found:
            cik, name = found[0].id, found[0].name
            _err(f"13F filer: {found[0].label}")
    if not crd and args.query:
        try:
            found = entities.search_advisers(client, args.query)
        except HttpError as exc:
            _err(f"IAPD search unavailable: {exc}")
            found = []
        if found:
            crd, name = found[0].id, name or found[0].name
            _err(f"Adviser: {found[0].label}")
    if not cik and not crd:
        return None
    return Entity(kind="firm", name=name or args.query or f"CIK {cik}", cik=pad_cik(cik) if cik else None, crd=crd)


def main(argv: Optional[list[str]] = None, transport: Optional[Transport] = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="opentearsheet", description="Cited research memos from public SEC filings. Runs locally.")
    parser.add_argument("--version", action="version", version=f"opentearsheet {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    company = sub.add_parser("company", help="memo for a public company (ticker or CIK)")
    company.add_argument("query", help="ticker (e.g. AAPL) or CIK")
    firm = sub.add_parser("firm", help="memo for an investment firm (13F filer and/or registered adviser)")
    firm.add_argument("query", nargs="?", default="", help="firm name (searches EDGAR 13F filers and IAPD)")
    firm.add_argument("--cik", help="13F filer CIK (skips the name search)")
    firm.add_argument("--crd", help="IAPD/CRD number (skips the name search)")
    for p in (company, firm):
        p.add_argument("--out", help="write the Markdown memo to this file (default: stdout)")
        p.add_argument("--csv-dir", help="also write one CSV per section plus facts.csv here")
        p.add_argument("--max-form4", type=int, default=40, help="max Form 4 filings to read (default 40)")
        p.add_argument("--lookback-days", type=int, default=365, help="insider-trade window in days (default 365)")
        p.add_argument("--as-of", type=date.fromisoformat, default=None, help="reference date YYYY-MM-DD (default: today)")
        p.add_argument("--no-llm", action="store_true", help="force the deterministic template memo")
    cache_cmd = sub.add_parser("cache", help="show or clear the local cache")
    cache_cmd.add_argument("--clear", action="store_true")

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.cmd == "cache":
        cache = HttpCache(settings.cache_path)
        if args.clear:
            cache.clear()
        stats = cache.stats()
        print(f"{stats['entries']} cached responses, {stats['bytes'] / 1e6:.1f} MB at {stats['path']}")
        return 0

    try:
        ua = settings.require_user_agent()
        client = SecClient(ua, HttpCache(settings.cache_path), max_rps=settings.max_rps, ttl_hours=settings.cache_ttl_hours, transport=transport)
        registry.load_builtin()
        for problem in registry.load_plugins():
            _err(f"plugin error: {problem}")
        llm = None if args.no_llm else make_llm(settings)

        entity = entities.resolve_company(client, args.query) if args.cmd == "company" else _resolve_firm(client, args)
        if entity is None:
            _err(f"No match for '{args.query}'.")
            return 2

        options = {"max_form4": args.max_form4, "form4_lookback_days": args.lookback_days, "as_of": args.as_of or date.today()}
        memo = build_memo(client, entity, options=options, llm=llm, progress=_err)
    except ConfigError as exc:
        _err(f"Configuration error: {exc}")
        return 2
    except HttpError as exc:
        _err(f"Request failed: {exc}")
        return 1

    markdown = memo_to_markdown(memo)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        _err(f"Memo written to {args.out}")
    else:
        print(markdown)
    if args.csv_dir:
        out_dir = Path(args.csv_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for section in memo.sections:
            (out_dir / f"{section.connector}.csv").write_text(section_to_csv(section), encoding="utf-8")
        (out_dir / "facts.csv").write_text(facts_to_csv(memo.facts), encoding="utf-8")
        _err(f"CSV files written to {out_dir}")
    for warning in memo.warnings:
        _err(f"warning: {warning}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
