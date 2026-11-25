# 📄 OpenTearsheet

**Free, open-source, local-first research tearsheets from SEC filings.**

Type a ticker or a fund name and get a one-page memo covering insider trades (Form 4), institutional holdings (13F) and adviser registration (Form ADV). Every number is cited to the public filing it came from, and you can export the result as Markdown or CSV.

[![CI](https://github.com/bombasticnewb-afk/opentearsheet/actions/workflows/ci.yml/badge.svg)](https://github.com/bombasticnewb-afk/opentearsheet/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![No paid tier](https://img.shields.io/badge/paid%20tier-never-brightgreen)

> No accounts, no API keys, no telemetry, no paid tier, ever. It runs on your machine against the SEC's free public APIs, and every line of code is here for you to read, change and run.

## Why

Analysts, boutique wealth managers and individual investors spend hours clicking through EDGAR to answer basic questions. Are insiders buying or selling? Were the sales pre-planned? What did this fund add last quarter? Is this adviser still registered? OpenTearsheet does that first pass in seconds and shows its work, so you can check every figure before you rely on it.

## What you get

| Module | Free data source | Highlights |
|---|---|---|
| **Company profile & recent filings** | `data.sec.gov` submissions API | SIC, exchange, fiscal year; latest 10-K / 10-Q; 8-K count with notable items flagged (5.02 exec changes, 4.02 restatements, 1.05 cyber incidents…) |
| **Insider trades (Form 4)** | EDGAR Archives (XML) | Open-market buys vs. sells, net $ flow, largest trade, % of sales made under Rule 10b5-1 plans, every transaction as CSV |
| **Institutional holdings (13F-HR)** | EDGAR Archives (XML) | Positions, concentration, top holdings, options exposure, and quarter-over-quarter new / exited / added / trimmed |
| **Adviser snapshot (Form ADV)** · *experimental* | SEC IAPD public records | CRD and SEC file number, registration status, last ADV filing date, office, state notice filings, link to the full ADV |

Plus:

- **Cited by construction.** Facts are numbered `[F1]`, `[F2]`… and each one links to its source document. An optional LLM narrative may cite only those ids. Invented citations are stripped, and output with no valid citations is thrown away in favour of the deterministic memo.
- **Local-first AI (optional).** Use Ollama, LM Studio or llama.cpp on your own machine. Remote endpoints are refused unless you explicitly opt in.
- **Exports.** Markdown memo, one CSV per section (protected against spreadsheet formula injection), and a facts-and-sources CSV for your audit trail.
- **Offline demo** with bundled synthetic filings, so you can try everything with no network access.
- **CLI** for scripts, notebooks and cron jobs.
- **Plugin system.** New forms and data sources are small, self-contained connectors (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Quick start (3 commands)

```bash
git clone https://github.com/bombasticnewb-afk/opentearsheet.git && cd opentearsheet
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens at <http://localhost:8501>. Enter your name and email in the sidebar (the SEC asks every API user to identify themselves), or switch on **Offline demo** and try ticker `EXMP` or firm `Sample Capital`.

> Tip: work in a virtualenv (`python -m venv .venv && source .venv/bin/activate`), and run `cp .env.example .env` to save your settings.

## Sample output

This excerpt comes from the offline demo. The company and the people in it are fictional.

```markdown
## Insider trades (Form 4)
- Open-market purchases (code P): 1 transaction(s) by 1 insider(s), 5,000 shares, ≈$241.0K [F7]
- Open-market sales (code S): 2 transaction(s) by 1 insider(s), 35,000 shares, ≈$1.83M [F8]
- Net open-market insider flow (purchases minus sales): -$1.59M [F9]
- Largest open-market trade: Founder Jane Q (Director, Chief Executive Officer) sold 20,000 shares at $52.10 (≈$1.04M) on 2026-11-12 [F10]
- 100% of open-market sale value was marked on the Form 4 as made under a Rule 10b5-1 trading plan [F11]

## Sources
- **[F7]** [Form 4 · filed 2026-11-05 · Example-Smith Robert](https://www.sec.gov/Archives/edgar/data/...)
```

Full company and fund memos: **[docs/sample-memo.md](docs/sample-memo.md)**.

## Optional: AI-written narrative, still on your machine

```bash
ollama pull llama3.1:8b
```

Then change `LLM_PROVIDER=none` to `LLM_PROVIDER=ollama` in your `.env`. For LM Studio or llama.cpp, set `LLM_PROVIDER=openai_compatible` and `OPENAI_COMPAT_BASE_URL=http://localhost:1234/v1`. Only public filing facts and the entity name are sent to the model, and requests to local endpoints bypass any HTTP proxy. Template mode (no LLM) stays the default.

## CLI

```bash
pip install -e .
opentearsheet company NVDA --out nvda.md --csv-dir exports/
opentearsheet firm "Sample Capital"            # searches 13F filers + registered advisers
opentearsheet firm --cik 0001067983            # a 13F filer by CIK
opentearsheet firm --crd 160001                # an adviser by IAPD CRD number
opentearsheet cache --clear
```

## How it works

```
ticker / firm ──▶ entities.py ──▶ connectors: filings · form4 · form13f · form_adv · <your plugin>
                                     │   SecClient: SEC User-Agent, ≤10 req/s, retries
                                     │   HttpCache: SQLite in ~/.opentearsheet (filings cached forever)
                                     ▼
                       Sections = facts (with Sources) + table rows + caveats
                                     ▼
       memo builder: number facts F1..Fn ─▶ template or local LLM ─▶ citation validator
                                     ▼
                  Markdown memo · CSV exports · Streamlit UI · CLI
```

## Privacy & security

- Your searches, memos, exports and cache never leave your computer. There is no backend, no account and no analytics, and Streamlit's usage stats are disabled in `.streamlit/config.toml`.
- The only network traffic is to public SEC servers (`sec.gov`, `data.sec.gov`, `efts.sec.gov`, `adviserinfo.sec.gov`) to download filings. As with any EDGAR visitor, the SEC can see which filings you request. Cached filings are reused offline.
- No API keys are needed. `.env` is git-ignored, and secrets are never logged.

Details and how to report a vulnerability: **[SECURITY.md](SECURITY.md)**.

## Data notes & limitations

- **Form 4:** by default the 40 most recent filings within 365 days (adjustable). Values are reported shares × reported price. Amendments are included as filed.
- **13F:** long positions in 13(f) securities only, as of quarter-end, filed up to 45 days later. Amendments and confidential-treatment holdings are not merged. A reverse lookup ("who holds ticker X?") isn't built yet.
- **Form ADV:** reads the public but undocumented IAPD endpoints. Regulatory AUM (Item 5F) is not parsed yet.
- **Submissions API:** lists roughly the most recent 1,000 filings per entity.
- OpenTearsheet is a research aid. **It is not investment advice**, and it is not affiliated with the SEC.

## Contributing

Pull requests are very welcome, from finance people and engineers alike. Good first issues:

- 13F reverse lookup: which managers hold a given CUSIP or ticker
- Form ADV AUM, client and fee data (Items 5–7) from the SEC's free bulk ADV files
- Schedule 13D/13G (activist and passive 5% stakes) connector
- Form 144 (proposed insider sales) connector
- XBRL financials from the free `companyfacts` API
- 13F-HR/A amendment merging, CUSIP→ticker mapping, PDF export

Read **[CONTRIBUTING.md](CONTRIBUTING.md)**. A new connector is about 60 lines plus a test.

## License

[Apache-2.0](LICENSE). Free to use, modify and redistribute, including commercially, with an explicit patent grant.
