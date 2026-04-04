"""
Review, HITL, and evaluation graph nodes.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import agent.contracts.events as _events
import agent.runtime.nodes._shared as _shared
from agent.prompts import render_prompt

_apply_output_contract = _shared._apply_output_contract
_chat_model = _shared._chat_model
_configurable = _shared._configurable
_log_usage = _shared._log_usage
_model_for_task = _shared._model_for_task
project_state_updates = _shared.project_state_updates
logger = _shared.logger
settings = _shared.settings
ToolEventType = _events.ToolEventType
get_emitter_sync = _events.get_emitter_sync


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    return sys.modules[__name__]


def _hitl_checkpoints_enabled() -> set[str]:
    raw = (getattr(settings, "hitl_checkpoints", "") or "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _hitl_checkpoint_active(config: RunnableConfig, checkpoint: str) -> bool:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    allow_interrupts = bool(configurable.get("allow_interrupts"))
    if not allow_interrupts:
        return False
    return checkpoint.strip().lower() in _hitl_checkpoints_enabled()


def _parse_research_plan_content(value: Any) -> List[str] | None:
    """
    Parse a user-edited plan payload into a normalized list of queries.
    """
    if isinstance(value, list):
        raw = value
    elif isinstance(value, dict) and isinstance(value.get("queries"), list):
        raw = value["queries"]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            raw = [line.strip() for line in text.splitlines()]
        else:
            if isinstance(parsed, list):
                raw = parsed
            elif isinstance(parsed, dict) and isinstance(parsed.get("queries"), list):
                raw = parsed["queries"]
            else:
                return None
    else:
        return None

    seen = set()
    queries: List[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        q = item.strip()
        q = q.lstrip("-*•").strip()
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(q)
        if len(queries) >= 10:
            break

    return queries or None


def hitl_plan_review_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Optional HITL checkpoint: review/edit the research plan after it is generated.
    """
    if not _hitl_checkpoint_active(config, "plan"):
        return {}

    plan = state.get("research_plan", []) or []
    if not isinstance(plan, list) or not plan:
        return {}

    prompt = {
        "checkpoint": "plan",
        "instruction": (
            "Review the research plan. You can edit the query list.\n\n"
            "Return one of:\n"
            "- {\"content\": \"<JSON array of strings>\"}\n"
            "- {\"research_plan\": [\"q1\", ...]}\n"
            "- or a plain string (JSON array or newline-separated queries)."
        ),
        "content": json.dumps(plan, indent=2, ensure_ascii=False),
    }

    updated = interrupt(prompt)

    edited_value: Any = updated
    if isinstance(updated, dict):
        if "research_plan" in updated:
            edited_value = updated.get("research_plan")
        elif "content" in updated:
            edited_value = updated.get("content")

    parsed = _parse_research_plan_content(edited_value)
    if not parsed:
        return {}

    deps = _resolve_deps(_deps)
    return deps.project_state_updates(state, {"research_plan": parsed})


def hitl_draft_review_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Optional HITL checkpoint: review/edit the draft report before evaluation/finalization.
    """
    if not _hitl_checkpoint_active(config, "draft"):
        return {}

    draft = state.get("draft_report") or state.get("final_report", "")
    if not isinstance(draft, str) or not draft.strip():
        return {}

    prompt = {
        "checkpoint": "draft",
        "instruction": (
            "Review and optionally edit the draft report. Return:\n"
            "- {\"content\": \"<updated report>\"}\n"
            "- or a plain string."
        ),
        "content": draft,
    }

    updated = interrupt(prompt)

    content: str | None = None
    if isinstance(updated, dict) and isinstance(updated.get("content"), str):
        content = updated["content"]
    elif isinstance(updated, str):
        content = updated

    if content is None or not content.strip():
        return {}

    deps = _resolve_deps(_deps)
    return deps.project_state_updates(
        state,
        {"draft_report": content, "final_report": content},
    )


def _format_sources_snapshot_for_instruction(state: Dict[str, Any]) -> str:
    """
    Build a compact, human-readable snapshot of sources + compressed knowledge.
    """
    scraped_content = state.get("scraped_content", []) or []
    compressed = state.get("compressed_knowledge", {}) or {}

    urls: List[str] = []
    seen = set()
    try:
        for item in scraped_content:
            if not isinstance(item, dict):
                continue
            for r in (item.get("results") or [])[:10]:
                if not isinstance(r, dict):
                    continue
                url = r.get("url")
                if not isinstance(url, str):
                    continue
                url = url.strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                urls.append(url)
                if len(urls) >= 12:
                    raise StopIteration
    except StopIteration:
        pass

    facts = compressed.get("facts") if isinstance(compressed, dict) else None
    facts_preview: List[str] = []
    if isinstance(facts, list):
        for f in facts[:8]:
            if not isinstance(f, dict):
                continue
            fact = f.get("fact")
            source = f.get("source") or f.get("source_url")
            if isinstance(fact, str) and fact.strip():
                if isinstance(source, str) and source.strip():
                    facts_preview.append(f"- {fact.strip()} ({source.strip()})")
                else:
                    facts_preview.append(f"- {fact.strip()}")

    summary = compressed.get("summary") if isinstance(compressed, dict) else ""
    if not isinstance(summary, str):
        summary = ""

    entities = compressed.get("key_entities") if isinstance(compressed, dict) else None
    entities_list: List[str] = []
    if isinstance(entities, list):
        for e in entities[:10]:
            if isinstance(e, str) and e.strip():
                entities_list.append(e.strip())

    lines: List[str] = []
    lines.append(f"- Sources collected: {sum(len((i or {}).get('results', []) or []) for i in scraped_content if isinstance(i, dict))}")
    if summary.strip():
        lines.append(f"- Compressed summary: {summary.strip()}")
    if facts_preview:
        lines.append("- Key facts (preview):")
        lines.extend(facts_preview)
    if entities_list:
        lines.append(f"- Key entities: {', '.join(entities_list)}")
    if urls:
        lines.append("- Example URLs:")
        lines.extend(f"- {u}" for u in urls[:8])

    snapshot = "\n".join(lines).strip()
    if len(snapshot) > 4000:
        snapshot = snapshot[:3999] + "…"
    return snapshot


def hitl_sources_review_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Optional HITL checkpoint: review sources/compressed knowledge, add guidance.
    """
    if not _hitl_checkpoint_active(config, "sources"):
        return {}

    has_sources = bool(state.get("scraped_content"))
    has_compressed = bool(state.get("compressed_knowledge"))
    if not (has_sources or has_compressed):
        return {}

    snapshot = _format_sources_snapshot_for_instruction(state)
    prompt = {
        "checkpoint": "sources",
        "instruction": (
            "Review sources and compressed knowledge (snapshot below).\n\n"
            f"{snapshot}\n\n"
            "Optionally add guidance for the writer in `content`, then approve to continue.\n"
            "Return:\n"
            "- {\"content\": \"<guidance>\"}\n"
            "- or a plain string."
        ),
        "content": (state.get("human_guidance") or "").strip(),
    }

    updated = interrupt(prompt)

    content: str | None = None
    if isinstance(updated, dict) and isinstance(updated.get("content"), str):
        content = updated["content"]
    elif isinstance(updated, str):
        content = updated

    if content is None:
        return {}

    guidance = content.strip()
    if not guidance:
        return {}

    deps = _resolve_deps(_deps)
    return deps.project_state_updates(state, {"human_guidance": guidance})


def should_continue_research(state: Dict[str, Any]) -> str:
    """
    Conditional edge: Decide if more research is needed.
    """
    current_step = state.get("current_step", 0)
    plan_length = len(state.get("research_plan", []))

    if current_step < plan_length:
        return "continue"
    return "write"


def evaluator_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """
    Evaluate the draft report with structured, multi-dimensional feedback.
    """
    deps = _resolve_deps(_deps)
    logger.info("Executing evaluator node (structured)")
    llm = deps._chat_model(deps._model_for_task("evaluation", config), temperature=0)
    t0 = time.time()

    class EvalDimensions(BaseModel):
        coverage: float = Field(
            ge=0.0,
            le=1.0,
            description="How well the report addresses all aspects of the question (0-1)",
        )
        accuracy: float = Field(
            ge=0.0, le=1.0, description="How well claims are supported by cited sources (0-1)"
        )
        freshness: float = Field(
            ge=0.0, le=1.0, description="How current and up-to-date the information is (0-1)"
        )
        coherence: float = Field(
            ge=0.0, le=1.0, description="How well-structured and logical the report is (0-1)"
        )

    class EvalResponse(BaseModel):
        verdict: str = Field(description='Evaluation verdict: "pass", "revise", or "incomplete"')
        dimensions: EvalDimensions = Field(description="Scores for each evaluation dimension")
        feedback: str = Field(description="Concise, actionable feedback for improvement")
        missing_topics: List[str] = Field(
            default_factory=list,
            description="Topics or aspects that should be covered but are missing",
        )
        suggested_queries: List[str] = Field(
            default_factory=list, description="Search queries that would help fill gaps"
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                render_prompt("review.evaluate"),
            ),
            ("human", "Question:\n{question}\n\nReport:\n{report}"),
        ]
    )

    report = state.get("draft_report") or state.get("final_report", "")

    try:
        response = llm.with_structured_output(EvalResponse).invoke(
            prompt.format_messages(report=report, question=state["input"]), config=config
        )
        deps._log_usage(response, "evaluator")
        logger.info(f"[timing] evaluator {(time.time() - t0):.3f}s")

        verdict = (response.verdict or "pass").lower().strip()
        if verdict not in ("pass", "revise", "incomplete"):
            verdict = "revise" if "revise" in verdict else "pass"

        if hasattr(response, "dimensions") and response.dimensions:
            dims = response.dimensions
            dimensions = {
                "coverage": getattr(dims, "coverage", 0.7),
                "accuracy": getattr(dims, "accuracy", 0.7),
                "freshness": getattr(dims, "freshness", 0.7),
                "coherence": getattr(dims, "coherence", 0.7),
            }
        else:
            dimensions = {"coverage": 0.7, "accuracy": 0.7, "freshness": 0.7, "coherence": 0.7}

        feedback = getattr(response, "feedback", "") or ""
        missing_topics = list(getattr(response, "missing_topics", []) or [])
        suggested_queries = list(getattr(response, "suggested_queries", []) or [])

        min_score = min(dimensions.values())
        avg_score = sum(dimensions.values()) / len(dimensions)

        if verdict == "pass" and min_score < 0.6:
            verdict = "revise"
            logger.info(f"Adjusted verdict to 'revise' due to low dimension score: {min_score:.2f}")
        elif verdict == "pass" and missing_topics:
            verdict = "revise"
            logger.info(f"Adjusted verdict to 'revise' due to missing topics: {missing_topics}")

        eval_summary = f"Dimensions: {dimensions}\n"
        if missing_topics:
            eval_summary += f"Missing topics: {', '.join(missing_topics)}\n"
        if feedback:
            eval_summary += f"Feedback: {feedback}"

        logger.info(f"Evaluator verdict: {verdict} (avg={avg_score:.2f}, min={min_score:.2f})")
        quality_overall_score = avg_score
        quality_gap_count = len(missing_topics)
        citation_coverage_score = float(dimensions.get("accuracy", 0.0))

        try:
            from agent.research.quality_assessor import QualityAssessor

            quality_llm = deps._chat_model(deps._model_for_task("evaluation", config), temperature=0)
            assessor = QualityAssessor(quality_llm, config)

            scraped_content = state.get("scraped_content", [])
            sources = [s.get("url") for s in state.get("sources", []) if s.get("url")]

            quality_report = assessor.assess(report, scraped_content, sources)
            quality_overall_score = quality_report.overall_score

            dimensions["claim_support"] = quality_report.claim_support_score
            dimensions["source_diversity"] = quality_report.source_diversity_score
            dimensions["contradiction_free"] = quality_report.contradiction_free_score
            dimensions["citation_coverage"] = quality_report.citation_coverage_score
            citation_coverage_score = quality_report.citation_coverage_score
            quality_gap_count = len(missing_topics) + len(quality_report.missing_citations)

            if quality_report.overall_score < 0.5 and verdict == "pass":
                verdict = "revise"
                logger.info(f"Adjusted verdict due to quality issues: {quality_report.overall_score:.2f}")

            citation_gate_threshold = float(
                getattr(settings, "citation_gate_min_coverage", 0.6)
            )
            if (
                verdict == "pass"
                and quality_report.citation_coverage_score < citation_gate_threshold
            ):
                verdict = "revise"
                logger.info(
                    "Adjusted verdict due to citation gate: "
                    f"{quality_report.citation_coverage_score:.2f} < {citation_gate_threshold:.2f}"
                )
                eval_summary += (
                    f"\nCitation gate: coverage {quality_report.citation_coverage_score:.2f} "
                    f"below threshold {citation_gate_threshold:.2f}."
                )

            if quality_report.recommendations:
                eval_summary += f"\nQuality recommendations: {'; '.join(quality_report.recommendations)}"

            logger.info(
                f"Quality assessment: overall={quality_report.overall_score:.2f}, "
                f"claims={quality_report.claim_support_score:.2f}"
            )

        except Exception as e:
            logger.warning(f"Quality assessment skipped: {e}")

        claim_verifier_counts: Optional[Dict[str, Any]] = None
        try:
            from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier

            scraped_content = state.get("scraped_content", [])
            scraped_list = scraped_content if isinstance(scraped_content, list) else []
            deep_research_artifacts = state.get("deep_research_artifacts", {}) or {}
            if not isinstance(deep_research_artifacts, dict):
                deep_research_artifacts = {}
            passages_payload = deep_research_artifacts.get("passages")
            passages_list = passages_payload if isinstance(passages_payload, list) else None

            if (scraped_list or passages_list) and isinstance(report, str) and report.strip():
                verifier = ClaimVerifier()
                checks = verifier.verify_report(
                    report,
                    scraped_list,
                    passages=passages_list,
                )

                contradicted = [c for c in checks if c.status == ClaimStatus.CONTRADICTED]
                unsupported = [c for c in checks if c.status == ClaimStatus.UNSUPPORTED]
                verified = [c for c in checks if c.status == ClaimStatus.VERIFIED]

                claim_verifier_counts = {
                    "claim_verifier_total": len(checks),
                    "claim_verifier_verified": len(verified),
                    "claim_verifier_unsupported": len(unsupported),
                    "claim_verifier_contradicted": len(contradicted),
                }

                max_contradicted = int(getattr(settings, "claim_verifier_gate_max_contradicted", 0) or 0)
                max_unsupported = int(getattr(settings, "claim_verifier_gate_max_unsupported", 0) or 0)

                if verdict == "pass" and (
                    len(contradicted) > max_contradicted or len(unsupported) > max_unsupported
                ):
                    verdict = "revise"
                    logger.info(
                        "Adjusted verdict due to claim verifier gate: "
                        f"contradicted={len(contradicted)} (max={max_contradicted}), "
                        f"unsupported={len(unsupported)} (max={max_unsupported})"
                    )
                    eval_summary += (
                        "\nClaim verifier gate: "
                        f"{len(contradicted)} contradicted, {len(unsupported)} unsupported "
                        f"(thresholds {max_contradicted}/{max_unsupported})."
                    )

        except Exception as e:
            logger.warning(f"Claim verifier gate skipped: {e}")

        thread_id = str(
            deps._configurable(config).get("thread_id")
            or state.get("cancel_token_id")
            or ""
        ).strip()
        if thread_id:
            try:
                emitter = deps.get_emitter_sync(thread_id)
                payload: Dict[str, Any] = {
                    "stage": "evaluation",
                    "verdict": verdict,
                    "quality_overall_score": quality_overall_score,
                    "quality_gap_count": quality_gap_count,
                    "citation_coverage": citation_coverage_score,
                }
                if claim_verifier_counts:
                    payload.update(claim_verifier_counts)
                emitter.emit_sync(deps.ToolEventType.QUALITY_UPDATE, payload)
            except Exception as e:
                logger.debug(f"[evaluator] failed to emit quality_update: {e}")

        quality_patch: Dict[str, Any] = {
            "citation_coverage": citation_coverage_score,
            "citation_coverage_score": citation_coverage_score,
            **(claim_verifier_counts or {}),
        }

        quality_summary_state = state.get("quality_summary")
        quality_summary: Dict[str, Any] = quality_summary_state if isinstance(quality_summary_state, dict) else {}

        state_deep_research_artifacts = state.get("deep_research_artifacts")
        deep_research_artifacts: Optional[Dict[str, Any]] = None
        if isinstance(state_deep_research_artifacts, dict):
            artifact_quality_state = state_deep_research_artifacts.get("quality_summary")
            artifact_quality = artifact_quality_state if isinstance(artifact_quality_state, dict) else {}
            deep_research_artifacts = {
                **state_deep_research_artifacts,
                "quality_summary": {
                    **artifact_quality,
                    **quality_patch,
                },
            }

        result: Dict[str, Any] = {
            "evaluation": eval_summary,
            "verdict": verdict,
            "eval_dimensions": dimensions,
            "missing_topics": missing_topics,
            "suggested_queries": suggested_queries if verdict != "pass" else [],
            "quality_overall_score": quality_overall_score,
            "quality_gap_count": quality_gap_count,
            "citation_coverage_score": citation_coverage_score,
            "claim_verifier_counts": claim_verifier_counts or {},
            "quality_summary": {
                **quality_summary,
                **quality_patch,
            },
        }
        if deep_research_artifacts is not None:
            result["deep_research_artifacts"] = deep_research_artifacts

        return deps.project_state_updates(state, result)

    except Exception as e:
        logger.error(f"Evaluator error: {e}")
        return deps.project_state_updates(
            state,
            {"evaluation": f"Evaluation failed: {e}", "verdict": "pass"},
        )


def revise_report_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """Revise the report based on evaluator feedback."""
    deps = _resolve_deps(_deps)
    logger.info("Executing revise report node")
    llm = deps._chat_model(deps._model_for_task("writing", config), temperature=0.5)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                render_prompt("review.revise"),
            ),
            (
                "human",
                "Question:\n{question}\n\nFeedback:\n{feedback}\n\nCurrent report:\n{report}",
            ),
        ]
    )

    report = state.get("draft_report") or state.get("final_report", "")
    feedback = state.get("evaluation", "")
    response = llm.invoke(
        prompt.format_messages(question=state["input"], feedback=feedback, report=report),
        config=config,
    )
    content = response.content if hasattr(response, "content") else str(response)

    revision_count = int(state.get("revision_count", 0)) + 1
    return deps.project_state_updates(
        state,
        {
            "draft_report": content,
            "final_report": content,
            "revision_count": revision_count,
            "messages": [AIMessage(content=content)],
            "is_complete": False,
        },
    )


def human_review_node(
    state: Dict[str, Any],
    config: RunnableConfig,
    *,
    _deps: Any = None,
) -> Dict[str, Any]:
    """Optional human review step using LangGraph interrupt."""
    deps = _resolve_deps(_deps)
    logger.info("Executing human review node")
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    allow_interrupts = bool(configurable.get("allow_interrupts"))
    force_final_checkpoint = "final" in _hitl_checkpoints_enabled()
    require_review = bool(configurable.get("human_review")) or force_final_checkpoint

    report = state.get("final_report") or state.get("draft_report", "")

    if not (allow_interrupts and require_review):
        report = deps._apply_output_contract(state.get("input", ""), report)
        return deps.project_state_updates(
            state,
            {
                "final_report": report,
                "is_complete": True,
                "messages": [AIMessage(content=report)],
            },
        )

    updated = interrupt(
        {
            "checkpoint": "final",
            "instruction": "Review and edit the report if needed. Return the updated content or approve as-is.",
            "content": report,
        }
    )

    if isinstance(updated, dict):
        if updated.get("content"):
            report = updated["content"]
    elif isinstance(updated, str) and updated.strip():
        report = updated

    report = deps._apply_output_contract(state.get("input", ""), report)

    return deps.project_state_updates(
        state,
        {"final_report": report, "is_complete": True, "messages": [AIMessage(content=report)]},
    )


__all__ = [
    "_format_sources_snapshot_for_instruction",
    "_hitl_checkpoint_active",
    "_hitl_checkpoints_enabled",
    "_parse_research_plan_content",
    "evaluator_node",
    "hitl_draft_review_node",
    "hitl_plan_review_node",
    "hitl_sources_review_node",
    "human_review_node",
    "revise_report_node",
    "should_continue_research",
]
