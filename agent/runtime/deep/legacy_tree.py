"""
Tree orchestration for the legacy deep-research runtime.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.deepsearch_optimized")
    if compat is None:
        import agent.workflows.deepsearch_optimized as compat
    return compat
def run_deepsearch_tree(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    deps = _resolve_deps()
    topic = state.get("input", "")
    deps._check_cancel(state)

    planning_model = deps._model_for_task("planning", config)
    research_model = deps._model_for_task("research", config)
    writing_model = deps._model_for_task("writing", config)

    planner_llm = deps._chat_model(planning_model, temperature=0.8)
    critic_llm = deps._chat_model(research_model, temperature=0.2)
    writer_llm = deps._chat_model(writing_model, temperature=0.5)

    max_depth = int(getattr(deps.settings, "tree_max_depth", 2))
    max_branches = int(getattr(deps.settings, "tree_max_branches", 4))
    queries_per_branch = int(getattr(deps.settings, "tree_queries_per_branch", 3))
    per_query_results = int(getattr(deps.settings, "deepsearch_results_per_query", 5))
    parallel_branches = int(getattr(deps.settings, "tree_parallel_branches", 3))
    max_seconds = max(
        0.0,
        deps._configurable_float(
            config,
            "deepsearch_max_seconds",
            float(getattr(deps.settings, "deepsearch_max_seconds", 0.0)),
        ),
    )
    max_tokens = max(
        0,
        deps._configurable_int(
            config,
            "deepsearch_max_tokens",
            int(getattr(deps.settings, "deepsearch_max_tokens", 0)),
        ),
    )
    max_searches = max(
        0,
        deps._configurable_int(
            config,
            "deepsearch_tree_max_searches",
            int(getattr(deps.settings, "deepsearch_tree_max_searches", 30) or 30),
        ),
    )

    deps.logger.info(
        "[deepsearch-tree] Starting tree exploration: topic='%s' depth=%s branches=%s parallel=%s",
        topic,
        max_depth,
        max_branches,
        parallel_branches,
    )
    provider_profile = deps._resolve_provider_profile(state)
    emitter = deps._resolve_event_emitter(state, config)
    search_runs: List[Dict[str, Any]] = []
    live_search_events_emitted = 0
    deps._emit_event(
        emitter,
        "research_node_start",
        {
            "node_id": "deepsearch_tree",
            "topic": topic,
            "depth": 0,
            "parent_id": "deepsearch",
        },
    )

    start_ts = time.time()
    budget_stop_reason = ""
    tokens_used = deps._estimate_tokens_from_text(topic)
    searches_used = 0

    budget_stop_reason = deps._budget_stop_reason(
        start_ts=start_ts,
        tokens_used=tokens_used,
        max_seconds=max_seconds,
        max_tokens=max_tokens,
    )
    if budget_stop_reason:
        diagnostics = deps._build_quality_diagnostics(topic, [], [])
        quality_summary = {
            "epochs_completed": 0,
            "summary_count": 0,
            "source_count": 0,
            "budget_stop_reason": budget_stop_reason,
            "tokens_used": tokens_used,
            "elapsed_seconds": 0.0,
            **diagnostics,
        }
        deps._emit_event(
            emitter,
            "quality_update",
            {"epoch": 0, "stage": "budget_stop", **diagnostics},
        )
        deps._emit_event(
            emitter,
            "research_node_complete",
            {
                "node_id": "deepsearch_tree",
                "summary": "",
                "sources": [],
                "quality": diagnostics,
                "epoch": 0,
            },
        )
        return {
            "research_plan": [],
            "scraped_content": [],
            "draft_report": deps.summary_text_prompt,
            "final_report": deps.summary_text_prompt,
            "messages": [
                AIMessage(content=f"（预算限制触发，未执行树搜索：{budget_stop_reason}）")
            ],
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": 0.0,
            "quality_summary": quality_summary,
            "deepsearch_artifacts": {
                "mode": "tree",
                "queries": [],
                "research_tree": None,
                "quality_summary": quality_summary,
                "query_coverage": diagnostics.get("query_coverage", {}),
                "freshness_summary": diagnostics.get("freshness_summary", {}),
            },
            "deepsearch_mode": "tree",
        }

    try:
        def _tree_budget_reason() -> Optional[str]:
            nonlocal budget_stop_reason
            if budget_stop_reason:
                return budget_stop_reason
            reason = deps._budget_stop_reason(
                start_ts=start_ts,
                tokens_used=tokens_used,
                max_seconds=max_seconds,
                max_tokens=max_tokens,
            )
            if reason:
                return reason
            if max_searches > 0 and searches_used >= max_searches:
                return "search_budget_exceeded"
            return None

        def _tree_search(payload, config_payload=None, **kwargs):
            nonlocal live_search_events_emitted, budget_stop_reason, tokens_used, searches_used
            stop_reason = _tree_budget_reason()
            if stop_reason:
                budget_stop_reason = stop_reason
                raise deps.TreeExplorationBudgetExceeded(stop_reason)
            query = (payload or {}).get("query", "")
            max_results = int((payload or {}).get("max_results", per_query_results))
            effective_config = (
                kwargs.get("config")
                if isinstance(kwargs.get("config"), dict)
                else config_payload
                if isinstance(config_payload, dict)
                else config
            )
            tokens_used += deps._estimate_tokens_from_text(query)
            results = deps._search_query(
                query,
                max_results,
                effective_config,
                provider_profile=provider_profile,
            )
            searches_used += 1
            if isinstance(results, list):
                tokens_used += deps._estimate_tokens_from_results(results)
            search_runs.append(
                {
                    "query": query,
                    "results": results if isinstance(results, list) else [],
                    "timestamp": datetime.now().isoformat(),
                }
            )
            provider_breakdown = deps._provider_breakdown(results if isinstance(results, list) else [])
            provider_name = "unknown"
            if len(provider_breakdown) > 1:
                provider_name = "multi"
            elif len(provider_breakdown) == 1:
                provider_name = next(iter(provider_breakdown))
            deps._emit_event(
                emitter,
                "search",
                {
                    "query": query,
                    "provider": provider_name,
                    "provider_breakdown": provider_breakdown,
                    "results": deps._compact_search_results(
                        results if isinstance(results, list) else [],
                        limit=deps._event_results_limit(),
                    ),
                    "count": len(results) if isinstance(results, list) else 0,
                    "mode": "tree",
                    "epoch": 1,
                },
            )
            live_search_events_emitted += 1
            post_budget_reason = deps._budget_stop_reason(
                start_ts=start_ts,
                tokens_used=tokens_used,
                max_seconds=max_seconds,
                max_tokens=max_tokens,
            )
            if post_budget_reason:
                budget_stop_reason = post_budget_reason
            return results

        explorer = deps.TreeExplorer(
            planner_llm=planner_llm,
            researcher_llm=critic_llm,
            writer_llm=writer_llm,
            search_func=_tree_search,
            config=config,
            max_depth=max_depth,
            max_branches=max_branches,
            queries_per_branch=queries_per_branch,
        )

        tree = None
        if parallel_branches > 0:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            lambda: asyncio.run(explorer.run_async(topic, state, decompose_root=True))
                        )
                        tree = future.result()
                else:
                    tree = loop.run_until_complete(explorer.run_async(topic, state, decompose_root=True))
                deps.logger.info("[deepsearch-tree] Used async parallel exploration")
            except deps.TreeExplorationBudgetExceeded as exc:
                budget_stop_reason = budget_stop_reason or getattr(exc, "reason", "") or str(exc)
                tree = getattr(explorer, "tree", None)
            except RuntimeError:
                try:
                    tree = asyncio.run(explorer.run_async(topic, state, decompose_root=True))
                    deps.logger.info("[deepsearch-tree] Used async parallel exploration")
                except deps.TreeExplorationBudgetExceeded as exc:
                    budget_stop_reason = budget_stop_reason or getattr(exc, "reason", "") or str(exc)
                    tree = getattr(explorer, "tree", None)
        else:
            try:
                tree = explorer.run(topic, state, decompose_root=True)
            except deps.TreeExplorationBudgetExceeded as exc:
                budget_stop_reason = budget_stop_reason or getattr(exc, "reason", "") or str(exc)
                tree = getattr(explorer, "tree", None)

        if tree is None:
            tree = getattr(explorer, "tree", None)

        merged_summary = explorer.get_final_summary()
        if not merged_summary and search_runs:
            try:
                flat_results: List[Dict[str, Any]] = []
                for run in search_runs[-min(10, len(search_runs)) :]:
                    if not isinstance(run, dict):
                        continue
                    results = run.get("results")
                    if isinstance(results, list):
                        for result in results:
                            if isinstance(result, dict):
                                flat_results.append(result)
                            if len(flat_results) >= 10:
                                break
                    if len(flat_results) >= 10:
                        break
                merged_summary = deps._format_results(flat_results) if flat_results else ""
            except Exception:
                merged_summary = ""
        raw_sources = explorer.get_all_sources()
        all_sources: List[str] = []
        all_sources_set = set()
        for source in raw_sources:
            canonical_source = deps.canonicalize_source_url(source)
            if canonical_source and canonical_source not in all_sources_set:
                all_sources.append(canonical_source)
                all_sources_set.add(canonical_source)
        all_findings = explorer.get_all_findings()

        summary_notes = [merged_summary] if merged_summary else []
        have_query: List[str] = []
        for node in tree.nodes.values():
            have_query.extend(node.queries)
        if not search_runs:
            for node in tree.nodes.values():
                for finding in node.findings:
                    search_runs.append(
                        {
                            "query": finding.get("query", ""),
                            "results": [finding.get("result", {})],
                            "timestamp": finding.get("timestamp", ""),
                            "branch_id": node.id,
                            "branch_topic": node.topic,
                        }
                    )

        report_sources_limit = int(
            getattr(deps.settings, "deepsearch_report_sources_limit", 20) or 20
        )
        extracted_sources: List[Dict[str, Any]] = []
        try:
            from agent.contracts.research import extract_message_sources

            extracted_sources = extract_message_sources(search_runs)
        except Exception:
            extracted_sources = []
        report_sources = extracted_sources[: max(1, report_sources_limit)]
        sources_block = deps._format_sources_for_writer(
            report_sources,
            search_runs,
            limit=report_sources_limit,
        )

        final_report = (
            deps._final_report(writer_llm, topic, summary_notes, config, sources=sources_block)
            if summary_notes
            else deps.summary_text_prompt
        )
        final_report = deps._append_auto_references(
            final_report,
            report_sources,
            limit=report_sources_limit,
        )

        elapsed = time.time() - start_ts
        tokens_used += deps._estimate_tokens_from_text(merged_summary)
        tokens_used += deps._estimate_tokens_from_text(final_report)
        post_budget_reason = deps._budget_stop_reason(
            start_ts=start_ts,
            tokens_used=tokens_used,
            max_seconds=max_seconds,
            max_tokens=max_tokens,
        )
        if post_budget_reason:
            budget_stop_reason = post_budget_reason

        deps.logger.info(
            "[deepsearch-tree] ===== Completed =====\n"
            "  Total time: %.2fs\n"
            "  Tree nodes: %s\n"
            "  Total sources: %s\n"
            "  Report length: %s chars",
            elapsed,
            len(tree.nodes),
            len(all_sources),
            len(final_report),
        )

        save_path = deps._save_deepsearch_data(
            topic,
            have_query,
            summary_notes,
            search_runs,
            final_report,
            epoch=1,
        )
        diagnostics = deps._build_quality_diagnostics(topic, have_query, search_runs)
        if live_search_events_emitted == 0:
            for run in search_runs:
                results = run.get("results") if isinstance(run, dict) else []
                provider_breakdown = deps._provider_breakdown(results if isinstance(results, list) else [])
                provider_name = "unknown"
                if len(provider_breakdown) > 1:
                    provider_name = "multi"
                elif len(provider_breakdown) == 1:
                    provider_name = next(iter(provider_breakdown))
                deps._emit_event(
                    emitter,
                    "search",
                    {
                        "query": run.get("query", "") if isinstance(run, dict) else "",
                        "provider": provider_name,
                        "provider_breakdown": provider_breakdown,
                        "results": deps._compact_search_results(
                            results if isinstance(results, list) else [],
                            limit=deps._event_results_limit(),
                        ),
                        "count": len(results) if isinstance(results, list) else 0,
                        "mode": "tree",
                        "epoch": 1,
                    },
                )

        quality_summary = {
            "epochs_completed": 1,
            "summary_count": len(summary_notes),
            "source_count": len(all_sources),
            "tree_node_count": len(tree.nodes),
            "budget_stop_reason": budget_stop_reason or "",
            "tokens_used": tokens_used,
            "elapsed_seconds": elapsed,
            **diagnostics,
        }
        fetched_pages, passages = deps._build_fetcher_evidence(all_sources[:10])

        claims = []
        try:
            from agent.contracts.research import ClaimVerifier

            min_overlap = int(
                getattr(deps.settings, "deepsearch_claim_verifier_min_overlap_tokens", 2) or 2
            )
            max_evidence = int(
                getattr(deps.settings, "deepsearch_claim_verifier_max_evidence_per_claim", 3) or 3
            )
            use_passages = bool(
                getattr(deps.settings, "deepsearch_claim_verifier_use_passages", True)
            )

            verifier = ClaimVerifier(
                min_overlap_tokens=min_overlap,
                max_evidence_per_claim=max_evidence,
            )
            checks = verifier.verify_report(
                final_report,
                search_runs,
                passages=passages if use_passages else None,
            )
            claims = [
                {
                    "claim": claim.claim,
                    "status": claim.status.value,
                    "evidence_urls": claim.evidence_urls,
                    "evidence_passages": claim.evidence_passages,
                    "score": claim.score,
                    "notes": claim.notes,
                }
                for claim in checks
            ]
        except Exception:
            claims = []
        deepsearch_artifacts = {
            "mode": "tree",
            "queries": have_query,
            "research_tree": tree.to_dict(),
            "quality_summary": quality_summary,
            "query_coverage": diagnostics.get("query_coverage", {}),
            "freshness_summary": diagnostics.get("freshness_summary", {}),
            "fetched_pages": fetched_pages,
            "passages": passages,
            "sources": extracted_sources,
            "claims": claims,
        }
        deps._emit_event(emitter, "quality_update", {"epoch": 1, "stage": "final", **diagnostics})
        deps._emit_event(
            emitter,
            "research_tree_update",
            {"tree": tree.to_dict(), "quality": diagnostics},
        )
        deps._emit_event(
            emitter,
            "research_node_complete",
            {
                "node_id": "deepsearch_tree",
                "summary": final_report[:1200] if isinstance(final_report, str) else "",
                "sources": deps._compact_search_results(
                    [result.get("result", {}) for result in all_findings],
                    limit=deps._event_results_limit(),
                ),
                "quality": diagnostics,
            },
        )

        messages = [AIMessage(content=final_report)]
        if save_path:
            messages.append(AIMessage(content=f"(数据已保存: {save_path})"))
        if budget_stop_reason:
            messages.append(AIMessage(content=f"（预算限制提示：{budget_stop_reason}）"))
        if diagnostics.get("freshness_warning"):
            messages.append(
                AIMessage(content="（时间敏感问题的新鲜来源占比较低，建议补充近30天来源并重试。）")
            )

        return {
            "research_plan": have_query,
            "scraped_content": search_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "quality_summary": quality_summary,
            "sources": extracted_sources,
            "deepsearch_artifacts": deepsearch_artifacts,
            "deepsearch_mode": "tree",
            "messages": messages,
            "research_tree": tree.to_dict(),
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": elapsed,
        }

    except asyncio.CancelledError:
        deps.logger.warning("[deepsearch-tree] 收到取消信号，停止任务")
        return {
            "is_cancelled": True,
            "is_complete": True,
            "errors": ["DeepSearch was cancelled"],
            "final_report": "任务已被取消",
        }
    except Exception as exc:
        deps.logger.error("[deepsearch-tree] Failed: %s", exc, exc_info=True)
        deps.logger.info("[deepsearch-tree] Falling back to linear deepsearch...")
        from agent.runtime.deep.legacy_linear import run_deepsearch_optimized

        return run_deepsearch_optimized(state, config)


__all__ = ["run_deepsearch_tree"]
