import re

from opentearsheet.memo import LLMError, build_memo, facts_to_csv, memo_to_markdown, rows_to_csv, validate_citations
from opentearsheet.models import Entity, Section
from opentearsheet.registry import BaseConnector


class FakeLLM:
    label = "Fake local model"
    is_local = True

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.messages = reply, error, None

    def complete(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.reply


def test_template_memo_cites_every_fact(client, company, options):
    memo = build_memo(client, company, options=options)
    assert memo.narrative_source.startswith("template")
    assert [s.connector for s in memo.sections] == ["filings", "form4"]
    cited = set(re.findall(r"\[(F\d+)\]", memo.narrative))
    assert cited == {f.id for f in memo.facts}
    md = memo_to_markdown(memo)
    assert "## Sources" in md and "## Caveats" in md
    assert "Item 5.02 (director or officer departure/appointment)" in md
    assert not memo.warnings


def test_firm_memo_runs_13f_and_adv(client, firm, options):
    memo = build_memo(client, firm, options=options)
    assert [s.connector for s in memo.sections] == ["form13f", "form_adv"]
    assert "CRD 160001" in memo_to_markdown(memo)


def test_llm_narrative_with_citation_cleanup(client, company, options):
    llm = FakeLLM("## Summary\nInsiders were net sellers [F4]. Made-up claim [F999]. Combined [F1, F2].")
    memo = build_memo(client, company, options=options, llm=llm)
    assert memo.narrative_source == "Fake local model"
    assert "[F999]" not in memo.narrative and "[citation removed]" in memo.narrative
    assert "[F1][F2]" in memo.narrative
    assert any("F999" in w for w in memo.warnings)
    assert "[F1]" in llm.messages[1]["content"]  # facts are passed to the model with ids


def test_llm_without_citations_falls_back_to_template(client, company, options):
    memo = build_memo(client, company, options=options, llm=FakeLLM("Buy now! Guaranteed upside."))
    assert memo.narrative_source.startswith("template")
    assert "Guaranteed" not in memo.narrative
    assert any("no valid citations" in w for w in memo.warnings)


def test_llm_error_falls_back_to_template(client, company, options):
    memo = build_memo(client, company, options=options, llm=FakeLLM(error=LLMError("connection refused")))
    assert memo.narrative_source.startswith("template")
    assert any("connection refused" in w for w in memo.warnings)


def test_failing_connector_becomes_warning(client, company, options):
    class Broken(BaseConnector):
        name, title, entity_kinds = "broken", "Broken connector", ("company",)

        def run(self, client, entity, options):
            raise RuntimeError("boom")

    memo = build_memo(client, company, options=options, connectors=[Broken()])
    assert memo.facts == [] and "Broken connector failed: boom" in memo.warnings[0]


def test_validate_citations_counts_valid_ids():
    text, warnings, used = validate_citations("a [F1; F3] b [F2]", {"F1", "F2"})
    assert text == "a [F1] b [F2]" and used == 2 and "F3" in warnings[0]


def test_csv_exports_neutralize_formulas():
    out = rows_to_csv([{"owner": '=HYPERLINK("http://evil")', "shares": -5.0, "note": "@SUM(A1)"}])
    assert "'=HYPERLINK" in out and "'@SUM" in out and "-5.0" in out


def test_facts_csv_has_sources(client, company, options):
    memo = build_memo(client, company, options=options)
    out = facts_to_csv(memo.facts)
    assert out.splitlines()[0] == "id,key,text,value,sources,urls"
    assert "https://www.sec.gov/Archives/edgar/data/1999999/" in out


def test_markdown_escapes_link_labels():
    from opentearsheet.memo.builder import Memo
    from opentearsheet.models import Fact, Source

    fact = Fact("x", "t", sources=[Source("Owner [weird] name", "https://example.org")], id="F1")
    memo = Memo(Entity(kind="company", name="X"), [Section("x", "X", [fact])], [fact], "n", "template", "now")
    assert "Owner \\[weird\\] name" in memo_to_markdown(memo)
