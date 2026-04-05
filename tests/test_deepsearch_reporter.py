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

5. 来源

- [99] old source
"""

    normalized_report, citation_urls = reporter.normalize_report(
        report,
        [
            ReportSource(url="https://example.com/report", title="Annual Report"),
            ReportSource(url="https://example.com/report?utm_medium=x", title="Duplicate"),
            ReportSource(url="https://example.com/blog", title="Industry Blog"),
        ],
        title="分析 AI chips 市场趋势",
    )

    assert normalized_report.startswith("# AI chips overview")
    assert "Annual Report [\\[1\\]](https://example.com/report)" in normalized_report
    assert "## 来源" in normalized_report
    assert "- [1] [Annual Report](https://example.com/report)" in normalized_report
    assert "- [2] [Industry Blog](https://example.com/blog)" not in normalized_report
    assert citation_urls == ["https://example.com/report"]


def test_normalize_report_strips_prompt_echo_and_promotes_numbered_headings():
    reporter = ResearchReporter(_RecordingLLM(), {})
    report = (
        "AI chips\n"
        "好的\uFF0C作为一名专业的研究报告撰写者\uFF0C我将基于您提供的经过整理和验证的研究材料\uFF0C"
        "为您撰写一份全面深度研究报告。\n\n"
        "1. 背景\n"
        "AI chips demand is accelerating. [1]\n\n"
        "## 结论\n"
        "Capacity remains constrained. [1]\n"
    )

    normalized_report, citation_urls = reporter.normalize_report(
        report,
        [
            ReportSource(url="https://example.com/report", title="Annual Report"),
        ],
        title="分析 AI chips 的供需变化",
    )

    assert normalized_report.startswith("# AI chips")
    assert "研究报告撰写者" not in normalized_report
    assert "## 背景" in normalized_report
    assert "## 结论" in normalized_report
    assert "[\\[1\\]](https://example.com/report)" in normalized_report
    assert citation_urls == ["https://example.com/report"]


def test_normalize_report_uses_sanitized_fallback_title_when_query_is_instructional():
    reporter = ResearchReporter(_RecordingLLM(), {})

    normalized_report, _ = reporter.normalize_report(
        "正文第一段。\n\n## 影响\n细节说明。",
        [ReportSource(url="https://example.com/report", title="Annual Report")],
        title="分析2026年NIPS和CCF的冲突，NIPS禁止部分中国机构投稿",
    )

    assert normalized_report.startswith("# 2026年NIPS和CCF的冲突")
    assert "## 影响" in normalized_report
