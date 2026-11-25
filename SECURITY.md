# Security & privacy

OpenTearsheet is designed so that **your research stays on your machine**. This page explains exactly what stays local, what touches the network, and how to report a problem.

## What stays on your computer

| Data | Where it lives |
|---|---|
| Tickers / firms you search, settings | In memory and your local `.env` (git-ignored) |
| Downloaded filings and API responses | SQLite cache at `~/.opentearsheet/cache.sqlite3` (folder set to owner-only `0700`; override with `OPENTEARSHEET_DATA_DIR`) |
| Generated memos and CSV exports | Only where you save them |
| LLM prompts and outputs | Your local model (Ollama / LM Studio / llama.cpp), if you enable one |

There is no OpenTearsheet server, account, analytics or telemetry. Streamlit's anonymous usage statistics are disabled in `.streamlit/config.toml`, and the UI binds to `localhost` only.

## What uses the network

1. **Public SEC data.** Requests go to `www.sec.gov`, `data.sec.gov`, `efts.sec.gov` and `api.adviserinfo.sec.gov`, carrying the User-Agent you configure (an SEC requirement). As with any visit to EDGAR, the SEC can see which filings you download. Cached responses are reused, so repeat lookups need no network at all.
2. **An LLM endpoint, only if you configure one.** Endpoints that are not `localhost` / `127.0.0.1` / `::1` are **refused** unless you set `ALLOW_REMOTE_LLM=true`. If you opt in, the provider's data-retention policy applies: OpenTearsheet cannot guarantee zero retention on someone else's server. Requests to local endpoints deliberately bypass any configured HTTP proxy. Only public filing facts and the entity name are ever sent.

## Secrets

- The SEC APIs need no key. `OPENAI_COMPAT_API_KEY` is optional and only for a server you choose.
- No secrets are hardcoded. Configuration comes from environment variables or `.env`, which is listed in `.gitignore`. Use `.env.example` as the template.
- API keys are excluded from settings `repr` and are never logged.

## Hardening already in place

- XML is parsed with `defusedxml` when installed (it is in `requirements.txt`). The stdlib fallback never resolves external entities.
- CSV exports neutralize spreadsheet formula injection (cells starting with `= + - @`).
- Markdown link labels from filings are escaped.
- LLM output can only cite known fact ids; anything else is stripped or rejected.
- No `eval`, no shell calls, and no dynamic code loading other than the plugins you install yourself.
- Requests are rate-limited to at most 10/s, in line with SEC fair-access rules.

## Your responsibilities

- Don't expose the Streamlit server beyond `localhost` (for example by changing `server.address`) without putting authentication in front of it.
- Only install plugins you trust. A plugin is ordinary Python code that runs with your permissions.
- Treat `.env` like any credentials file.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead: go to the repository's **Security** tab and choose **Report a vulnerability**. We aim to acknowledge reports within 72 hours and will credit you in the fix unless you prefer otherwise.

## Supported versions

Security fixes land on `main` and in the latest release.
