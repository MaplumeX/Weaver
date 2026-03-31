"""
Research Planner Agent.

Generates and refines structured research plans.
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """
# 角色
你是一名研究规划专家, 擅长为复杂话题制定全面的研究计划。

# 任务
为以下主题制定研究计划, 生成结构化的 branch objective 列表。

# 主题
{topic}

# 已批准的研究范围
{approved_scope}

# 已有信息
{existing_knowledge}

# 已执行的查询
{existing_queries}

# 要求
1. 生成 {num_queries} 个 branch objective
2. 每个 objective 应覆盖主题的不同方面
3. objective 不能与已有 branch objective 重复
4. objective 需要表达目标、验收标准、允许工具类别和必要的 query hints
5. 保持 researcher 的执行边界清晰，避免把完整执行过程写死

# 输出格式
按优先级排序，输出 JSON 列表：
```json
[
    {{
        "title": "分支标题1",
        "objective": "该 branch 需要回答的问题",
        "task_kind": "branch_research",
        "aspect": "覆盖的方面",
        "acceptance_criteria": ["完成该分支必须满足的标准"],
        "allowed_tools": ["search", "read", "extract", "synthesize"],
        "query_hints": ["可选的查询提示"],
        "output_artifact_types": ["branch_synthesis", "evidence_passage"],
        "priority": 1
    }}
]
```
"""


class ResearchPlanner:
    """
    Plans research by generating structured query sets.

    Responsibilities:
    - Decompose topics into searchable queries
    - Prioritize queries by importance
    - Refine plans based on findings
    """

    def __init__(self, llm: BaseChatModel, config: dict[str, Any] | None = None):
        self.llm = llm
        self.config = config or {}

    def create_plan(
        self,
        topic: str,
        num_queries: int = 5,
        existing_knowledge: str = "",
        existing_queries: list[str] | None = None,
        approved_scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Create a research plan.

        Returns:
            List of branch objective dicts.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", PLANNER_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            approved_scope=self._format_scope_for_prompt(approved_scope),
            existing_knowledge=existing_knowledge or "暂无",
            existing_queries=", ".join(existing_queries or []) or "无",
            num_queries=num_queries,
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_plan(content)

    def refine_plan(
        self,
        topic: str,
        gaps: list[str],
        existing_queries: list[str],
        num_queries: int = 3,
        approved_scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Refine research plan based on identified knowledge gaps.

        Args:
            topic: Research topic
            gaps: Identified knowledge gaps
            existing_queries: Already executed queries
            num_queries: Number of new queries to generate

        Returns:
            List of new branch objective dicts
        """
        gap_text = "\n".join(f"- {g}" for g in gaps) if gaps else "无明确缺口"

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
基于以下知识缺口, 补充研究计划。

# 主题: {topic}

# 知识缺口
{gaps}

# 已有查询
{existing_queries}

# 已批准的研究范围
{approved_scope}

# 要求
生成 {num_queries} 个针对知识缺口的 branch objective。

# 输出格式
```json
[{{
    "title": "补充分支标题",
    "objective": "需要补齐的研究目标",
    "task_kind": "gap_follow_up",
    "aspect": "方面",
    "acceptance_criteria": ["补齐什么信息才算完成"],
    "allowed_tools": ["search", "read", "extract", "synthesize"],
    "query_hints": ["查询提示"],
    "priority": 1
}}]
```
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            gaps=gap_text,
            existing_queries=", ".join(existing_queries),
            num_queries=num_queries,
            approved_scope=self._format_scope_for_prompt(approved_scope),
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_plan(content)

    def _parse_plan(self, content: str) -> list[dict[str, Any]]:
        """Parse plan from LLM output."""
        import json
        import re

        # Find JSON in response
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.I)
        if json_match:
            content = json_match.group(1)

        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            content = content[start:end]

        try:
            data = json.loads(content)
            if isinstance(data, list):
                normalized = [
                    self._normalize_plan_item(item, fallback_priority=index)
                    for index, item in enumerate(data, 1)
                    if isinstance(item, dict)
                ]
                return [item for item in normalized if item]
        except json.JSONDecodeError:
            pass

        # Fallback: extract lines as branch objectives
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        normalized = [
            self._normalize_plan_item(
                {"title": line, "objective": line, "query_hints": [line], "priority": i},
                fallback_priority=i,
            )
            for i, line in enumerate(lines, 1)
        ]
        return [item for item in normalized if item]

    def _normalize_plan_item(
        self,
        item: dict[str, Any],
        *,
        fallback_priority: int,
    ) -> dict[str, Any] | None:
        title = str(item.get("title") or item.get("aspect") or item.get("objective") or item.get("query") or "").strip()
        objective = str(item.get("objective") or title or item.get("query") or "").strip()
        query_hints = self._coerce_string_list(item.get("query_hints"))
        query = str(item.get("query") or "").strip()
        if query and query not in query_hints:
            query_hints.insert(0, query)
        if not objective:
            return None

        task_kind = str(item.get("task_kind") or "branch_research").strip() or "branch_research"
        acceptance_criteria = self._coerce_string_list(item.get("acceptance_criteria"))
        if not acceptance_criteria:
            acceptance_criteria = [objective]
        allowed_tools = self._coerce_string_list(item.get("allowed_tools")) or [
            "search",
            "read",
            "extract",
            "synthesize",
        ]
        output_artifact_types = self._coerce_string_list(item.get("output_artifact_types")) or [
            "branch_synthesis",
            "evidence_passage",
        ]

        return {
            "title": title or objective,
            "objective": objective,
            "task_kind": task_kind,
            "aspect": str(item.get("aspect") or "").strip(),
            "acceptance_criteria": acceptance_criteria,
            "allowed_tools": allowed_tools,
            "input_artifact_ids": self._coerce_string_list(item.get("input_artifact_ids")),
            "output_artifact_types": output_artifact_types,
            "query_hints": query_hints or [objective],
            "priority": int(item.get("priority") or fallback_priority),
        }

    def _coerce_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _format_scope_for_prompt(self, approved_scope: dict[str, Any] | None) -> str:
        if not isinstance(approved_scope, dict) or not approved_scope:
            return "暂无已批准 scope, 请仅在必要时基于主题做最小范围规划."

        sections = [
            f"- research_goal: {approved_scope.get('research_goal', '')}",
            "- research_steps:",
        ]
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("research_steps", [])
            if isinstance(item, str) and item.strip()
        )
        sections.extend([
            "- core_questions:",
        ])
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("core_questions", [])
            if isinstance(item, str) and item.strip()
        )
        sections.append("- in_scope:")
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("in_scope", [])
            if isinstance(item, str) and item.strip()
        )
        sections.append("- out_of_scope:")
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("out_of_scope", [])
            if isinstance(item, str) and item.strip()
        )
        sections.append("- constraints:")
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("constraints", [])
            if isinstance(item, str) and item.strip()
        )
        sections.append("- source_preferences:")
        sections.extend(
            f"  - {item}"
            for item in approved_scope.get("source_preferences", [])
            if isinstance(item, str) and item.strip()
        )
        return "\n".join(sections)
