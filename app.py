"""OpenTearsheet: local Streamlit UI.

Run with ``streamlit run app.py``. The server binds to localhost (see .streamlit/config.toml),
usage telemetry is off, and every query, cache entry and memo stays on this machine.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (ROOT / "src", ROOT):  # run straight from a fresh clone, no install needed
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from opentearsheet import __version__, entities, registry  # noqa: E402
from opentearsheet.cache import HttpCache  # noqa: E402
from opentearsheet.config import ConfigError, Settings, load_dotenv, validate_user_agent  # noqa: E402
from opentearsheet.memo import build_memo, facts_to_csv, make_llm, memo_to_markdown, section_to_csv  # noqa: E402
from opentearsheet.models import Entity  # noqa: E402
from opentearsheet.sec_client import HttpError, SecClient  # noqa: E402

st.set_page_config(page_title="OpenTearsheet", page_icon="📄", layout="wide")
load_dotenv(ROOT / ".env")
settings = Settings.from_env()
state = st.session_state


@st.cache_resource
def _bootstrap() -> list[str]:
    registry.load_builtin()
    return registry.load_plugins()


@st.cache_resource
def _cache(path: str) -> HttpCache:
    return HttpCache(path)


plugin_errors = _bootstrap()
cache = _cache(str(settings.cache_path))


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "memo"


def _render(memo) -> None:
    st.divider()
    markdown = memo_to_markdown(memo)
    slug = _slug(memo.entity.ticker or memo.entity.name)
    for warning in memo.warnings:
        st.warning(warning)
    tabs = st.tabs(["📝 Memo"] + [s.title for s in memo.sections] + ["🔗 Facts & sources"])
    with tabs[0]:
        st.download_button("⬇️ Download memo (.md)", markdown, file_name=f"{slug}-tearsheet.md", mime="text/markdown", key="dl-memo")
        st.markdown(markdown)
    for tab, section in zip(tabs[1:-1], memo.sections):
        with tab:
            if section.rows:
                st.dataframe(pd.DataFrame(section.rows, columns=section.columns or None), hide_index=True)
                st.download_button(f"⬇️ {section.title} (.csv)", section_to_csv(section), file_name=f"{slug}-{section.connector}.csv", mime="text/csv", key=f"dl-{section.connector}")
            else:
                st.info("No rows for this section.")
            for note in section.notes:
                st.caption(f"ℹ️ {note}")
    with tabs[-1]:
        facts = [{"id": f.id, "fact": f.text, "sources": " | ".join(s.label for s in f.sources), "first link": f.sources[0].url if f.sources else ""} for f in memo.facts]
        st.dataframe(pd.DataFrame(facts), hide_index=True)
        st.download_button("⬇️ Facts & sources (.csv)", facts_to_csv(memo.facts), file_name=f"{slug}-facts.csv", mime="text/csv", key="dl-facts")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    demo = st.toggle(
        "Offline demo (synthetic data)",
        value=os.environ.get("OPENTEARSHEET_DEMO", "").lower() in {"1", "true", "yes"},
        help="Try the app with bundled, fictional filings. No network, no User-Agent needed. Try ticker EXMP or firm 'Sample Capital'.",
    )
    user_agent = settings.sec_user_agent
    if not demo and not user_agent:
        user_agent = st.text_input(
            "SEC User-Agent (name + email)",
            placeholder="Jane Doe jane@yourfirm.com",
            help="The SEC asks API users to identify themselves. Kept in this browser session only; set SEC_USER_AGENT in .env to persist.",
        )

    st.subheader("Data")
    max_form4 = st.slider("Max Form 4 filings", 5, 100, 40, step=5)
    lookback = st.slider("Insider lookback (days)", 30, 730, 365, step=30)

    st.subheader("Narrative")
    try:
        llm, llm_error = make_llm(settings), None
    except ConfigError as exc:
        llm, llm_error = None, str(exc)
    use_llm = False
    if llm is not None:
        use_llm = st.checkbox(f"Write narrative with {llm.label}", value=True)
        st.caption("🔒 Local endpoint: memo data stays on this machine." if llm.is_local else "⚠️ Remote endpoint: facts are sent to that server.")
    else:
        st.caption("Template mode: deterministic, fully cited memo with no LLM. Set LLM_PROVIDER=ollama in .env for an AI-written narrative.")
    if llm_error:
        st.warning(llm_error)

    st.subheader("Local cache")
    stats = cache.stats()
    st.caption(f"{stats['entries']} responses · {stats['bytes'] / 1e6:.1f} MB · `{stats['path']}`")
    if st.button("Clear cache"):
        cache.clear()
        st.toast("Local cache cleared")
    if plugin_errors:
        st.warning("Plugin errors:\n\n" + "\n\n".join(plugin_errors))
    st.caption(f"OpenTearsheet v{__version__} · Apache-2.0 · no telemetry · not investment advice")


# ---------------------------------------------------------------- client
as_of = date.today()
if demo:
    from tests.fixture_transport import DEMO_AS_OF, FixtureTransport

    as_of = DEMO_AS_OF
    client = SecClient("OpenTearsheet Demo demo@opentearsheet.invalid", HttpCache(":memory:"), max_rps=10, transport=FixtureTransport())
else:
    try:
        client = SecClient(validate_user_agent(user_agent), cache, max_rps=settings.max_rps, ttl_hours=settings.cache_ttl_hours)
    except ConfigError as exc:
        client = None
        ua_problem = str(exc)

st.title("📄 OpenTearsheet")
st.caption("Free, open-source research memos from SEC filings: Form 4 insider trades, 13F holdings and Form ADV adviser records. Runs on your machine. Not investment advice.")

if client is None:
    st.info(f"👈 Enter your name and email in the sidebar, or switch on the offline demo.\n\n{ua_problem}")
    st.stop()

options = {"max_form4": max_form4, "form4_lookback_days": lookback, "as_of": as_of}


def _run(entity: Entity) -> None:
    with st.status(f"Researching {entity.name}…", expanded=True) as status:
        memo = build_memo(client, entity, options=options, llm=llm if use_llm else None, progress=lambda m: status.update(label=m))
        status.update(label=f"Memo ready: {len(memo.facts)} cited facts", state="complete", expanded=False)
    state["memo"] = memo


mode = st.radio("What are you researching?", ["Public company", "Investment firm"], horizontal=True)

if mode == "Public company":
    with st.form("company-form"):
        query = st.text_input("Ticker or CIK", placeholder="EXMP" if demo else "e.g. AAPL or 320193")
        submitted = st.form_submit_button("Generate memo", type="primary")
    if submitted and query.strip():
        try:
            entity = entities.resolve_company(client, query)
            if entity is None:
                st.error(f"No SEC registrant found for '{query}'.")
            else:
                _run(entity)
        except HttpError as exc:
            st.error(str(exc))
else:
    with st.form("firm-form"):
        query = st.text_input("Firm name, 13F filer CIK, or IAPD CRD", placeholder="Sample Capital" if demo else "e.g. Bridgewater")
        searched = st.form_submit_button("Search")
    if searched and query.strip():
        state["c13f"], state["cadv"], state["search_errors"] = [], [], []
        for key, finder in (("c13f", entities.search_13f_filers), ("cadv", entities.search_advisers)):
            try:
                state[key] = finder(client, query)
            except Exception as exc:
                state["search_errors"].append(f"{'EDGAR 13F' if key == 'c13f' else 'IAPD'} search failed: {exc}")
    for problem in state.get("search_errors", []):
        st.warning(problem)
    found_13f, found_adv = state.get("c13f", []), state.get("cadv", [])
    if found_13f or found_adv:
        skip = "— skip —"
        pick_13f = st.selectbox("13F filer (EDGAR)", [skip] + [c.label for c in found_13f])
        pick_adv = st.selectbox("Registered adviser (IAPD / Form ADV)", [skip] + [c.label for c in found_adv])
        if st.button("Generate memo", type="primary"):
            a = next((c for c in found_13f if c.label == pick_13f), None)
            b = next((c for c in found_adv if c.label == pick_adv), None)
            if not a and not b:
                st.warning("Pick at least one record.")
            else:
                _run(Entity(kind="firm", name=(a or b).name, cik=a.id if a else None, crd=b.id if b else None))
    elif searched:
        st.info("No matches. Try a shorter name, or paste a CIK / CRD number.")

if state.get("memo") is not None:
    _render(state["memo"])
