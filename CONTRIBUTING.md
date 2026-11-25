# Contributing to OpenTearsheet

Thanks for helping! OpenTearsheet is built by and for analysts, wealth managers, quants and open-source developers. Bug reports, filing-format edge cases, new connectors, docs and UX tweaks are all valuable.

## Ground rules

1. **Everything stays free and open.** No paywalls, license keys, proprietary modules, telemetry or "pro" tiers, ever.
2. **Free, keyless data only** in core connectors: SEC endpoints or other public sources that need no paid key.
3. **Cite everything.** Every `Fact` a connector emits carries at least one `Source` with a public URL.
4. **Local-first.** Don't add calls to third-party services, and don't send user data anywhere.
5. **The core library is stdlib-only.** `src/opentearsheet` must keep working with plain Python 3.10+. UI-only dependencies belong in `requirements.txt` / the `app` extra.
6. **Tests never touch the network.** Use synthetic fixtures.
7. Be kind. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Dev setup

```bash
git clone https://github.com/bombasticnewb-afk/opentearsheet.git && cd opentearsheet
python -m venv .venv && source .venv/bin/activate
pip install -e ".[app,dev]"
pytest -q                          # ~1 second, fully offline
OPENTEARSHEET_DEMO=1 streamlit run app.py
```

## Project layout

```
src/opentearsheet/
  config.py        env/.env settings, User-Agent check, remote-LLM guard
  sec_client.py    rate-limited HTTP client (injectable transport)
  cache.py         SQLite HTTP cache
  edgar.py         EDGAR URLs + submissions helpers
  entities.py      ticker / CIK / firm-name / CRD resolution
  registry.py      BaseConnector, @register, entry-point plugin loading
  connectors/      one module per data source / form
  memo/            builder (fact numbering, citations), llm (local-first), export
  cli.py
app.py             Streamlit UI
tests/             fixtures/ + fixture_transport.py + tests
```

## Writing a connector

A connector receives an `Entity` and returns a `Section` made of facts (for the memo), rows (for CSV) and notes (caveats).

```python
# src/opentearsheet/connectors/form144.py
from ..edgar import company_page_url, get_submissions, recent_filings
from ..models import Fact, Section, Source
from ..registry import BaseConnector, register


@register
class ProposedSales(BaseConnector):
    name = "form144"
    title = "Proposed insider sales (Form 144)"
    entity_kinds = ("company",)
    order = 25  # runs after Form 4

    def applies(self, entity):
        return entity.kind == "company" and bool(entity.cik)

    def run(self, client, entity, options):
        filings = recent_filings(get_submissions(client, entity.cik), ("144",))[:20]
        rows = [{"filed": f["filingDate"], "url": f["index_url"]} for f in filings]
        facts = [Fact(
            "form144.count",
            f"{len(filings)} Form 144 notice(s) of proposed sale in the recent filing list",
            value=len(filings),
            sources=[Source(f"Form 144 · filed {f['filingDate']}", f["index_url"]) for f in filings]
            or [Source("EDGAR company page", company_page_url(entity.cik))],  # a fact always cites something
        )]
        return Section(self.name, self.title, facts, rows, notes=["Form 144 is a notice of intent, not a completed sale."])
```

Then:

1. Import it in `connectors/__init__.py`.
2. Add a **synthetic** fixture to `tests/fixtures/` and a route in `tests/fixture_transport.py`.
3. Write a test (see `tests/test_form4.py` for the pattern).

Tips:

- Use `client.get()` / `client.get_json()`. They handle the User-Agent, rate limiting, retries and caching for you.
- Use `xmlutil.parse_xml` / `text` / `num`. They strip namespaces and unwrap Form-4-style `<value>` nodes.
- Report progress for slow loops with `options.get("progress")`.
- Raise on fatal problems. The memo builder turns exceptions into warnings, so other sections still render.
- Put caveats (units, lags, amendments) in `notes`. They appear in the memo's Caveats section.

## Shipping a connector as your own package

You don't need to merge into this repo. Publish a package that exposes a connector class through an entry point:

```toml
# your package's pyproject.toml
[project.entry-points."opentearsheet.connectors"]
form144 = "my_package.form144:ProposedSales"
```

`pip install` it next to OpenTearsheet and it appears automatically in the app and the CLI. Broken plugins are reported in the sidebar and never crash the app.

## Fixtures and real data

Keep fixtures **synthetic**: fictional issuers, people and CUSIPs, in the same structure as the real document. If you're reproducing a parsing bug from a real filing, trim it down to the relevant elements and replace names and identifiers.

## SEC fair access

Never raise the rate limit above 10 requests/second, always send the user's declared User-Agent, and cache aggressively. Filing documents are immutable and are cached forever by design.

## Pull requests

- Keep PRs focused, and describe the analyst-facing change in plain English.
- `pytest -q` must pass. CI runs on Python 3.10 and 3.13.
- Update the README / docs if you change behaviour or configuration.
- By contributing, you agree your work is released under the Apache-2.0 license.
