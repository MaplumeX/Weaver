"""
Shared helpers for the supported Deep Research runtime surface.
"""

from __future__ import annotations

import re

_SIMPLE_FACT_PATTERNS = (
    r"\bwhat\s+is\b",
    r"\bwho\s+is\b",
    r"\bwhen\s+(?:is|was|did)\b",
    r"\bwhere\s+(?:is|was)\b",
    r"\bwhich\s+is\b",
    r"\bhow\s+many\b",
    r"\bcapital\s+of\b",
    r"\bpopulation\s+of\b",
    r"\breply\s+with\b",
    r"\bone\s+word\b",
    r"是什么",
    r"谁是",
    r"何时",
    r"哪里",
    r"在哪",
    r"多少",
    r"首都",
    r"人口",
    r"只回答",
    r"一个词",
)
_BROAD_RESEARCH_CUES = (
    "analysis",
    "analyze",
    "assess",
    "case study",
    "cases",
    "compare",
    "comparison",
    "deep research",
    "evaluate",
    "framework",
    "histor",
    "impact",
    "investigate",
    "latest",
    "market",
    "overview",
    "policy",
    "regulation",
    "report",
    "research",
    "survey",
    "timeline",
    "trend",
    "updates",
    "versus",
    "vs",
    "分析",
    "影响",
    "报告",
    "对比",
    "挑战",
    "政策",
    "框架",
    "比较",
    "法规",
    "深度",
    "研究",
    "综述",
    "调研",
    "趋势",
    "历史",
)


def auto_mode_prefers_direct_answer(topic: str) -> bool:
    text = re.sub(r"\s+", " ", str(topic or "")).strip()
    if not text:
        return False

    lowered = text.lower()
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in _SIMPLE_FACT_PATTERNS):
        return True

    if any(cue in lowered for cue in _BROAD_RESEARCH_CUES):
        return False
    return False


# Keep the old helper name as a private alias while callers migrate.
_auto_mode_prefers_linear = auto_mode_prefers_direct_answer

__all__ = ["auto_mode_prefers_direct_answer", "_auto_mode_prefers_linear"]
