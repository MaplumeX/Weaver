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
)
from agent.prompts.runtime_templates import (
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
    confidence_level: str = "low"
    limitation_summary: str = ""
    risk_highlights: list[str] = field(default_factory=list)
    manual_review_items: list[str] = field(default_factory=list)


@dataclass
class ReportContext:
    topic: str
    sections: list[ReportSectionContext] = field(default_factory=list)
    sources: list[ReportSource] = field(default_factory=list)


_SOURCE_SECTION_RE = re.compile(r"(?im)^#{2,6}\s*(参考来源|来源|sources)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_SOURCE_HEADING_RE = re.compile(
    r"(?i)^(?:#+\s*)?(?:\d+[\.\)\u3001]\s*|[一二三四五六七八九十]+[\u3001\.]\s*)?"
    r"(?:参考来源|参考资料|参考文献|来源|sources?|references?)\s*[:\uFF1A]?\s*$"
)
_NUMBERED_SECTION_RE = re.compile(r"^\s*\d+[\.\)\u3001]\s*(.+?)\s*$")
_CHINESE_NUMBERED_SECTION_RE = re.compile(r"^\s*[一二三四五六七八九十]+[\u3001\.]\s*(.+?)\s*$")
_PROMPT_ECHO_PATTERNS = (
    re.compile(r"^(好的|当然|下面|以下)[,\uFF0C:\uFF1A]?\s*"),
    re.compile(r"^作为.{0,40}(研究|报告|分析).{0,30}[,\uFF0C:\uFF1A]"),
    re.compile(r"^(我将|本文将|本报告将|以下将)"),
    re.compile(r"^(基于|根据)(您|你)提供"),
)
_PROMPT_ECHO_TOKENS = (
    "研究报告撰写者",
    "经过整理和验证的研究材料",
    "为您撰写一份",
    "全面深度研究报告",
    "以下是一份",
)
_TITLE_INSTRUCTION_PREFIX_RE = re.compile(
    r"^(?:请(?:你)?|帮(?:我)?|麻烦你|需要你|想请你)?\s*(?:分析|研究|调研|撰写|写(?:一份)?|生成(?:一份)?|输出|总结|对比|比较|评估)\s*",
    re.IGNORECASE,
)
_TRAILING_TITLE_REQUIREMENT_RE = re.compile(
    r"[，,。.;；:：]\s*(?:并|并且|请|要求|需要|同时|输出|给出|附上|包含|提供).*$"
)


def _normalize_title_key(text: str) -> str:
    normalized = re.sub(
        r"[\s`'\"\u201c\u201d\u2018\u2019\u300a\u300b<>\u3010\u3011\[\]()\uFF08\uFF09,"
        r"\uFF0C.\u3002:\uFF1A;\uFF1B!\uFF01?\uFF1F\u00B7/\\-]+",
        "",
        str(text or ""),
    )
    return normalized.lower()


def _sanitize_title_text(text: str) -> str:
    candidate = str(text or "").strip().strip("#").strip()
    if not candidate:
        return ""
    candidate = _TITLE_INSTRUCTION_PREFIX_RE.sub("", candidate).strip()
    candidate = re.sub(r"^(?:关于|围绕)\s*", "", candidate)
    candidate = _TRAILING_TITLE_REQUIREMENT_RE.sub("", candidate).strip()
    candidate = re.sub(r"\s+", " ", candidate)
    if len(candidate) > 36:
        parts = [part.strip() for part in re.split(r"[，,:：;；]", candidate) if part.strip()]
        if parts:
            shortened = parts[0]
            if 8 <= len(shortened) <= 36:
                candidate = shortened
    return candidate.strip("：:;；,.，。")


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

    def _normalize_citation_urls(self, values: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values or []:
            url = canonicalize_source_url(item)
            if not url or url in seen:
                continue
            seen.add(url)
            normalized.append(url)
        return normalized

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
                sections=[
                    ReportSectionContext(
                        title=str(section.title or "").strip(),
                        summary=str(section.summary or "").strip(),
                        branch_summaries=[str(item).strip() for item in section.branch_summaries if str(item).strip()],
                        findings=[str(item).strip() for item in section.findings if str(item).strip()],
                        citation_urls=self._normalize_citation_urls(list(section.citation_urls or [])),
                        confidence_level=str(getattr(section, "confidence_level", "low") or "low").strip(),
                        limitation_summary=str(getattr(section, "limitation_summary", "") or "").strip(),
                        risk_highlights=[
                            str(item).strip()
                            for item in list(getattr(section, "risk_highlights", []) or [])
                            if str(item).strip()
                        ],
                        manual_review_items=[
                            str(item).strip()
                            for item in list(getattr(section, "manual_review_items", []) or [])
                            if str(item).strip()
                        ],
                    )
                    for section in topic_or_context.sections
                ],
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
                "可展开细节:",
                finding_text or "- 无额外细节",
                "本章节可引用来源:",
                source_text,
            ]
            if branch_text:
                block[2:2] = ["补充上下文:", branch_text]
            blocks.append("\n".join(block))
        return "\n\n".join(blocks) if blocks else "暂无章节素材"

    def _format_source_mapping(self, sources: list[ReportSource]) -> str:
        if not sources:
            return "无来源"
        lines: list[str] = []
        for index, source in enumerate(sources, 1):
            label = source.title.strip() or source.url
            lines.append(f"- [{index}] {label}: {source.url}")
        return "\n".join(lines)

    def _format_source_section(self, sources: list[ReportSource]) -> str:
        if not sources:
            return ""
        lines: list[str] = []
        for index, source in enumerate(sources, 1):
            label = source.title.strip() or source.url
            metadata = [item for item in [source.provider.strip(), source.published_date or ""] if item]
            meta_text = f" | {' | '.join(metadata)}" if metadata else ""
            lines.append(f"- [{index}] [{label}]({source.url}){meta_text}")
        return "\n".join(lines)

    def _strip_source_section(self, report_markdown: str) -> str:
        lines = (report_markdown or "").splitlines()
        for index, line in enumerate(lines):
            if _SOURCE_HEADING_RE.match(line.strip()):
                return "\n".join(lines[:index]).rstrip()

        matches = list(_SOURCE_SECTION_RE.finditer(report_markdown or ""))
        if not matches:
            return (report_markdown or "").strip()
        return (report_markdown or "")[: matches[-1].start()].rstrip()

    def _strip_prompt_echo(self, report_markdown: str, *, title: str | None = None) -> str:
        lines = (report_markdown or "").splitlines()
        title_key = _normalize_title_key(_sanitize_title_text(title or ""))
        start = 0
        while start < len(lines):
            stripped = lines[start].strip()
            if not stripped:
                start += 1
                continue
            if stripped.startswith("#"):
                break

            line_key = _normalize_title_key(stripped)
            if title_key and line_key == title_key:
                start += 1
                continue
            if any(pattern.search(stripped) for pattern in _PROMPT_ECHO_PATTERNS):
                start += 1
                continue
            if any(token in stripped for token in _PROMPT_ECHO_TOKENS):
                start += 1
                continue
            break
        return "\n".join(lines[start:]).strip()

    def _citation_link(self, index: int, url: str) -> str:
        return f"[\\[{index}\\]]({url})"

    def _derive_report_title(self, report_markdown: str, fallback_title: str | None = None) -> str:
        lines = (report_markdown or "").splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                if level > 1:
                    continue
                candidate = _sanitize_title_text(stripped[level:].strip())
                if candidate:
                    return candidate
                continue
            if any(pattern.search(stripped) for pattern in _PROMPT_ECHO_PATTERNS):
                continue
            if any(token in stripped for token in _PROMPT_ECHO_TOKENS):
                continue
            if _NUMBERED_SECTION_RE.match(stripped) or _CHINESE_NUMBERED_SECTION_RE.match(stripped):
                continue
            if stripped.endswith(("。", ".", "！", "?", "？", "!")):
                continue
            candidate = _sanitize_title_text(stripped)
            if candidate and len(candidate) <= 40:
                return candidate
        fallback = _sanitize_title_text(fallback_title or "")
        return fallback or "研究报告"

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

    def _linkify_numeric_citations(self, report_markdown: str, sources: list[ReportSource]) -> str:
        index_to_url = {
            index: source.url
            for index, source in enumerate(sources, 1)
        }

        def _replace(match: re.Match[str]) -> str:
            index = int(match.group(1))
            url = index_to_url.get(index)
            if not url:
                return match.group(0)
            return self._citation_link(index, url)

        return re.sub(r"(?<!\\)\[(\d{1,3})\](?!\()", _replace, report_markdown)

    def _restrict_to_cited_sources(
        self,
        report_markdown: str,
        sources: list[ReportSource],
    ) -> tuple[str, list[ReportSource]]:
        used_indexes = [
            int(match.group(1))
            for match in re.finditer(r"(?<!\\)\[(\d{1,3})\](?!\()", report_markdown or "")
            if 1 <= int(match.group(1)) <= len(sources)
        ]
        if not used_indexes:
            return report_markdown, sources

        ordered_unique_indexes: list[int] = []
        seen_indexes: set[int] = set()
        for index in used_indexes:
            if index in seen_indexes:
                continue
            seen_indexes.add(index)
            ordered_unique_indexes.append(index)

        index_map = {
            old_index: new_index
            for new_index, old_index in enumerate(ordered_unique_indexes, 1)
        }
        filtered_sources = [sources[index - 1] for index in ordered_unique_indexes]

        def _replace(match: re.Match[str]) -> str:
            old_index = int(match.group(1))
            new_index = index_map.get(old_index)
            if new_index is None:
                return match.group(0)
            return f"[{new_index}]"

        normalized_body = re.sub(r"(?<!\\)\[(\d{1,3})\](?!\()", _replace, report_markdown or "")
        return normalized_body, filtered_sources

    def _normalize_heading_hierarchy(self, report_markdown: str, *, title: str | None = None) -> str:
        lines = (report_markdown or "").splitlines()
        resolved_title = self._derive_report_title(report_markdown, fallback_title=title)
        if not lines:
            return f"# {resolved_title}".strip()

        normalized: list[str] = [f"# {resolved_title}", ""]
        inside_code_block = False
        title_key = _normalize_title_key(resolved_title)

        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_code_block = not inside_code_block
                normalized.append(line)
                continue
            if inside_code_block:
                normalized.append(line)
                continue

            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                heading_text = stripped[level:].strip()
                heading_key = _normalize_title_key(heading_text)
                if title_key and heading_key == title_key:
                    continue
                adjusted_level = min(6, max(2, level))
                normalized.append(f"{'#' * adjusted_level} {heading_text}".rstrip())
                continue

            promoted = None
            if stripped and (index == 0 or not lines[index - 1].strip()):
                match = _NUMBERED_SECTION_RE.match(stripped) or _CHINESE_NUMBERED_SECTION_RE.match(stripped)
                if match:
                    promoted = match.group(1).strip()

            if title_key and _normalize_title_key(stripped) == title_key:
                continue
            if promoted and len(promoted) <= 60 and not _SOURCE_HEADING_RE.match(stripped):
                normalized.append(f"## {promoted}")
                continue

            normalized.append(line)

        body = "\n".join(normalized).strip()
        return body

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
        body = (report_markdown or "").strip()
        resolved_title = self._derive_report_title(body, fallback_title=title)
        body = self._strip_source_section(body)
        body = self._strip_prompt_echo(body, title=resolved_title)
        body = self._replace_markdown_links_with_citations(body, source_index_by_url).strip()
        body, normalized_sources = self._restrict_to_cited_sources(body, normalized_sources)
        body = self._linkify_numeric_citations(body, normalized_sources)
        body = self._normalize_heading_hierarchy(body, title=resolved_title)
        source_lines = self._format_source_section(normalized_sources)
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
            sources=self._format_source_mapping(normalized_sources),
        )

        response = self.llm.invoke(msg, config=self.config)
        report = getattr(response, "content", "") or ""

        logger.info(f"[Reporter] Generated report: {len(report)} chars")
        return report

    def generate_executive_summary(
        self,
        report: str,
        topic: str,
        *,
        report_context: ReportContext | None = None,
    ) -> str:
        """
        Generate an executive summary for the report.

        Returns:
            Executive summary text
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", DEEP_REPORTER_EXEC_SUMMARY_PROMPT)
        ])

        summary_source = report[:5000]
        if report_context is not None and report_context.sections:
            lines: list[str] = []
            for section in report_context.sections:
                summary = str(section.summary or "").strip()
                if summary:
                    lines.append(summary)
                lines.extend(
                    str(item).strip()
                    for item in section.findings[:2]
                    if str(item).strip()
                )
            context_summary = "\n".join(lines).strip()
            if context_summary:
                summary_source = context_summary[:5000]

        msg = prompt.format_messages(
            topic=topic,
            report=summary_source,
        )

        response = self.llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""
