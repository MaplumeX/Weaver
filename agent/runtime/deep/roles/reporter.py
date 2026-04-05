"""
Research Reporter Agent.

Synthesizes research findings into comprehensive reports.
"""

import logging
import re
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agent.prompts.runtime_templates import (
    DEEP_REPORTER_EXEC_SUMMARY_PROMPT,
    DEEP_REPORTER_PROMPT as REPORTER_PROMPT,
)
from agent.research.source_url_utils import canonicalize_source_url

logger = logging.getLogger(__name__)


@dataclass
class ReportSource:
    url: str
    title: str = ""
    provider: str = ""
    published_date: str | None = None


@dataclass
class ReportSectionContext:
    title: str
    summary: str
    branch_summaries: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    citation_urls: list[str] = field(default_factory=list)


@dataclass
class ReportContext:
    topic: str
    sections: list[ReportSectionContext] = field(default_factory=list)
    sources: list[ReportSource] = field(default_factory=list)


_SOURCE_SECTION_RE = re.compile(r"(?im)^#{2,6}\s*(参考来源|来源|sources)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


class ResearchReporter:
    """
    Synthesizes research findings into comprehensive reports.

    Responsibilities:
    - Aggregate and organize findings
    - Write structured reports
    - Ensure citation accuracy
    - Review and refine reports
    """

    def __init__(self, llm: BaseChatModel, config: dict[str, object] | None = None):
        self.llm = llm
        self.config = config or {}

    def _normalize_sources(self, sources: list[ReportSource]) -> list[ReportSource]:
        normalized: list[ReportSource] = []
        seen: set[str] = set()
        for source in sources or []:
            url = canonicalize_source_url(getattr(source, "url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            title = str(getattr(source, "title", "") or "").strip() or url
            provider = str(getattr(source, "provider", "") or "").strip()
            published_date = getattr(source, "published_date", None)
            normalized.append(
                ReportSource(
                    url=url,
                    title=title,
                    provider=provider,
                    published_date=str(published_date).strip() if published_date else None,
                )
            )
        return normalized

    def _coerce_report_context(
        self,
        topic_or_context: str | ReportContext,
        findings: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> ReportContext:
        if isinstance(topic_or_context, ReportContext):
            return ReportContext(
                topic=topic_or_context.topic,
                sections=list(topic_or_context.sections),
                sources=self._normalize_sources(list(topic_or_context.sources)),
            )

        normalized_sources = self._normalize_sources(
            [ReportSource(url=str(url or "").strip(), title=str(url or "").strip()) for url in sources or []]
        )
        section = ReportSectionContext(
            title="核心发现",
            summary="\n".join(item for item in findings or [] if item).strip() or "暂无充分发现",
            findings=[item for item in findings or [] if item],
            citation_urls=[item.url for item in normalized_sources],
        )
        return ReportContext(
            topic=str(topic_or_context or "").strip(),
            sections=[section],
            sources=normalized_sources,
        )

    def _format_sections(
        self,
        sections: list[ReportSectionContext],
        source_index_by_url: dict[str, int],
    ) -> str:
        blocks: list[str] = []
        for index, section in enumerate(sections, 1):
            title = section.title.strip() or f"章节 {index}"
            summary = section.summary.strip() or "无章节摘要"
            branch_text = "\n".join(f"- {item}" for item in section.branch_summaries if item)
            finding_text = "\n".join(f"- {item}" for item in section.findings if item)
            citations = [
                f"[{source_index_by_url[url]}] {url}"
                for url in section.citation_urls
                if url in source_index_by_url
            ]
            source_text = "\n".join(f"- {item}" for item in citations) if citations else "- 无可用来源"
            block = [
                f"## 章节 {index}: {title}",
                f"章节摘要:\n{summary}",
                "关联分支结论:",
                branch_text or "- 无分支补充",
                "可展开细节:",
                finding_text or "- 无额外细节",
                "本章节可引用来源:",
                source_text,
            ]
            blocks.append("\n".join(block))
        return "\n\n".join(blocks) if blocks else "暂无章节素材"

    def _format_sources(self, sources: list[ReportSource]) -> str:
        if not sources:
            return "无来源"
        lines: list[str] = []
        for index, source in enumerate(sources, 1):
            label = source.title.strip() or source.url
            lines.append(f"- [{index}] {label}: {source.url}")
        return "\n".join(lines)

    def _strip_source_section(self, report_markdown: str) -> str:
        matches = list(_SOURCE_SECTION_RE.finditer(report_markdown or ""))
        if not matches:
            return (report_markdown or "").strip()
        return (report_markdown or "")[: matches[-1].start()].rstrip()

    def _replace_markdown_links_with_citations(
        self,
        report_markdown: str,
        source_index_by_url: dict[str, int],
    ) -> str:
        def _replace(match: re.Match[str]) -> str:
            label = str(match.group(1) or "").strip()
            url = canonicalize_source_url(match.group(2))
            index = source_index_by_url.get(url)
            if index is None:
                return match.group(0)
            return f"{label} [{index}]"

        return _MARKDOWN_LINK_RE.sub(_replace, report_markdown)

    def normalize_report(
        self,
        report_markdown: str,
        sources: list[ReportSource],
        *,
        title: str | None = None,
    ) -> tuple[str, list[str]]:
        normalized_sources = self._normalize_sources(list(sources or []))
        source_index_by_url = {
            source.url: index
            for index, source in enumerate(normalized_sources, 1)
        }
        body = self._replace_markdown_links_with_citations(report_markdown or "", source_index_by_url).strip()
        body = self._strip_source_section(body)
        if title and not body:
            body = f"# {title}"
        elif title and not body.lstrip().startswith("#"):
            body = f"# {title}\n\n{body}"
        source_lines = self._format_sources(normalized_sources)
        if normalized_sources:
            body = f"{body}\n\n## 来源\n\n{source_lines}".strip()
        return body, [source.url for source in normalized_sources]

    def generate_report(
        self,
        topic: str | ReportContext,
        findings: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> str:
        """
        Generate a comprehensive research report.

        Args:
            topic: Research topic or structured report context
            findings: Legacy finding summaries when passing a string topic
            sources: Legacy source URLs when passing a string topic

        Returns:
            Markdown formatted report
        """
        report_context = self._coerce_report_context(topic, findings=findings, sources=sources)
        normalized_sources = self._normalize_sources(list(report_context.sources))
        source_index_by_url = {
            source.url: index
            for index, source in enumerate(normalized_sources, 1)
        }

        prompt = ChatPromptTemplate.from_messages([
            ("user", REPORTER_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=report_context.topic,
            sections=self._format_sections(report_context.sections, source_index_by_url),
            sources=self._format_sources(normalized_sources),
        )

        response = self.llm.invoke(msg, config=self.config)
        report = getattr(response, "content", "") or ""

        logger.info(f"[Reporter] Generated report: {len(report)} chars")
        return report

    def generate_executive_summary(
        self,
        report: str,
        topic: str,
    ) -> str:
        """
        Generate an executive summary for the report.

        Returns:
            Executive summary text
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", DEEP_REPORTER_EXEC_SUMMARY_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            report=report[:5000],
        )

        response = self.llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""
