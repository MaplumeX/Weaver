from types import SimpleNamespace

from agent.runtime.deep.roles.reporter import (
    ReportContext,
    ReportSectionContext,
    ReportSource,
    ResearchReporter,
)


class _RecordingLLM:
    def __init__(self, content: str = "# report"):
        self.content = content
        self.messages = None

    def invoke(self, messages, config=None):
        self.messages = messages
        return SimpleNamespace(content=self.content)


def test_generate_report_accepts_structured_report_context():
    llm = _RecordingLLM(content="# AI chips\n\nStructured report")
    reporter = ResearchReporter(llm, {})
    context = ReportContext(
        topic="AI chips",
        sections=[
            ReportSectionContext(
                title="市场概览",
                summary="市场仍在高速扩张。",
                branch_summaries=["branch-1: 官方披露显示需求上升"],
                findings=["资本开支持续增加"],
                citation_urls=["https://example.com/report"],
            )
        ],
        sources=[ReportSource(url="https://example.com/report", title="Annual Report")],
    )

    report = reporter.generate_report(context)

    assert report.startswith("# AI chips")
    assert llm.messages is not None
    prompt_text = llm.messages[0].content
    assert "市场概览" in prompt_text
    assert "[1] Annual Report: https://example.com/report" in prompt_text


def test_normalize_report_rewrites_source_section_and_dedupes_urls():
    reporter = ResearchReporter(_RecordingLLM(), {})
    report = """AI chips overview

According to [Annual Report](https://example.com/report?utm_source=test), demand improved.

## 参考来源

- [99] old source
"""

    normalized_report, citation_urls = reporter.normalize_report(
        report,
        [
            ReportSource(url="https://example.com/report", title="Annual Report"),
            ReportSource(url="https://example.com/report?utm_medium=x", title="Duplicate"),
            ReportSource(url="https://example.com/blog", title="Industry Blog"),
        ],
        title="AI chips",
    )

    assert normalized_report.startswith("# AI chips")
    assert "Annual Report [1]" in normalized_report
    assert "## 来源" in normalized_report
    assert "- [1] Annual Report: https://example.com/report" in normalized_report
    assert "- [2] Industry Blog: https://example.com/blog" in normalized_report
    assert citation_urls == [
        "https://example.com/report",
        "https://example.com/blog",
    ]
