"""
Linear orchestration for the legacy deep-research runtime.
"""

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage


def _resolve_deps(explicit_deps: Any = None) -> Any:
    if explicit_deps is not None:
        return explicit_deps
    compat = sys.modules.get("agent.workflows.deepsearch_optimized")
    if compat is None:
        import agent.workflows.deepsearch_optimized as compat
    return compat
def run_deepsearch_optimized(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    deps = _resolve_deps()
    topic = state.get("input", "")
    deps._check_cancel(state)

    max_epochs = deps._configurable_int(
        config,
        "deepsearch_max_epochs",
        int(getattr(deps.settings, "deepsearch_max_epochs", 3)),
    )
    query_num = deps._configurable_int(
        config,
        "deepsearch_query_num",
        int(getattr(deps.settings, "deepsearch_query_num", 5)),
    )
    per_query_results = deps._configurable_int(
        config,
        "deepsearch_results_per_query",
        int(getattr(deps.settings, "deepsearch_results_per_query", 5)),
    )
    top_urls = max(3, min(5, per_query_results))
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

    planning_model = deps._model_for_task("planning", config)
    research_model = deps._model_for_task("research", config)
    writing_model = deps._model_for_task("writing", config)

    planner_llm = deps._chat_model(planning_model, temperature=0.8)
    critic_llm = deps._chat_model(research_model, temperature=0.2)
    writer_llm = deps._chat_model(writing_model, temperature=0.5)

    have_query: List[str] = []
    summary_notes: List[str] = []
    search_runs: List[Dict[str, Any]] = []
    provider_profile = deps._resolve_provider_profile(state)

    all_searched_urls: List[str] = []
    all_searched_urls_set: set[str] = set()
    selected_urls: List[str] = []
    selected_urls_set: set[str] = set()
    fetched_pages: List[Dict[str, Any]] = []
    passages: List[Dict[str, Any]] = []

    deps.logger.info("[deepsearch] topic='%s' epochs=%s", topic, max_epochs)
    deps.logger.info("[deepsearch] 开始优化版深度搜索")

    start_ts = time.time()
    tokens_used = deps._estimate_tokens_from_text(topic)
    budget_stop_reason = ""
    emitter = deps._resolve_event_emitter(state, config)
    visualize_browser = deps._browser_visualization_enabled(config)

    try:
        for epoch in range(max_epochs):
            try:
                deps._check_cancel(state)
                epoch_start = time.time()
                budget_stop_reason = deps._budget_stop_reason(
                    start_ts=start_ts,
                    tokens_used=tokens_used,
                    max_seconds=max_seconds,
                    max_tokens=max_tokens,
                )
                if budget_stop_reason:
                    deps.logger.info("[deepsearch] 预算触发提前停止: %s", budget_stop_reason)
                    break
                deps.logger.info("[deepsearch] ===== Epoch %s/%s =====", epoch + 1, max_epochs)
                epoch_node_id = f"deepsearch_epoch_{epoch + 1}"
                deps._emit_event(
                    emitter,
                    "research_node_start",
                    {
                        "node_id": epoch_node_id,
                        "topic": topic,
                        "depth": 1,
                        "parent_id": "deepsearch",
                        "epoch": epoch + 1,
                    },
                )

                query_start = time.time()
                missing_topics = state.get("missing_topics", []) if epoch > 0 else []
                queries = deps._generate_queries(
                    planner_llm,
                    topic,
                    have_query,
                    summary_notes,
                    query_num,
                    config,
                    missing_topics=missing_topics,
                )
                if epoch == 0 and query_num > 1 and topic not in queries:
                    queries.append(topic)
                if not queries:
                    queries = [topic]
                queries = queries[: max(1, query_num)]
                tokens_used += sum(deps._estimate_tokens_from_text(q) for q in queries)
                have_query.extend(q for q in queries if q not in have_query)
                deps.logger.info(
                    "[deepsearch] Epoch %s: 生成 %s 个查询 | 耗时 %.2fs",
                    epoch + 1,
                    len(queries),
                    time.time() - query_start,
                )
                deps.logger.debug("[deepsearch] 查询列表: %s", queries)

                search_start = time.time()
                combined_results: List[Dict[str, Any]] = []
                for q in queries:
                    deps._check_cancel(state)
                    budget_stop_reason = deps._budget_stop_reason(
                        start_ts=start_ts,
                        tokens_used=tokens_used,
                        max_seconds=max_seconds,
                        max_tokens=max_tokens,
                    )
                    if budget_stop_reason:
                        deps.logger.info("[deepsearch] 搜索阶段触发预算停止: %s", budget_stop_reason)
                        break

                    if visualize_browser:
                        try:
                            from agent.workflows.browser_visualizer import show_browser_status_page

                            show_browser_status_page(
                                state=state,
                                config=config,
                                title="Searching the web…",
                                detail=q,
                            )
                        except Exception:
                            pass

                    results = deps._search_query(
                        q,
                        per_query_results,
                        config,
                        provider_profile=provider_profile,
                    )
                    tokens_used += deps._estimate_tokens_from_results(results)
                    combined_results.extend(results)
                    search_runs.append(
                        {
                            "query": q,
                            "results": results,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    provider_breakdown = deps._provider_breakdown(results)
                    provider_name = "unknown"
                    if len(provider_breakdown) > 1:
                        provider_name = "multi"
                    elif len(provider_breakdown) == 1:
                        provider_name = next(iter(provider_breakdown))
                    deps._emit_event(
                        emitter,
                        "search",
                        {
                            "query": q,
                            "provider": provider_name,
                            "provider_breakdown": provider_breakdown,
                            "results": deps._compact_search_results(
                                results,
                                limit=deps._event_results_limit(),
                            ),
                            "count": len(results),
                            "epoch": epoch + 1,
                        },
                    )

                    if visualize_browser:
                        try:
                            from agent.workflows.browser_visualizer import (
                                visualize_urls_from_results,
                            )

                            visualize_urls_from_results(
                                state=state,
                                config=config,
                                results=results if isinstance(results, list) else [],
                                max_urls=1,
                                reason=f"deepsearch:search:epoch{epoch + 1}",
                            )
                        except Exception:
                            pass

                    for result in results:
                        url = deps.canonicalize_source_url(result.get("url"))
                        if url and url not in all_searched_urls_set:
                            all_searched_urls.append(url)
                            all_searched_urls_set.add(url)

                if budget_stop_reason:
                    break

                deps.logger.info(
                    "[deepsearch] Epoch %s: 搜索到 %s 个结果 | 累计 URL: %s | 耗时 %.2fs",
                    epoch + 1,
                    len(combined_results),
                    len(all_searched_urls),
                    time.time() - search_start,
                )

                if not combined_results:
                    deps.logger.info("[deepsearch] Epoch %s: 无搜索结果，跳过本轮", epoch + 1)
                    epoch_diagnostics = deps._build_quality_diagnostics(topic, have_query, search_runs)
                    deps._emit_event(
                        emitter,
                        "quality_update",
                        {"epoch": epoch + 1, "stage": "epoch", **epoch_diagnostics},
                    )
                    deps._emit_event(
                        emitter,
                        "research_node_complete",
                        {
                            "node_id": epoch_node_id,
                            "summary": "",
                            "sources": [],
                            "quality": epoch_diagnostics,
                            "epoch": epoch + 1,
                        },
                    )
                    continue

                pick_start = time.time()
                chosen_urls = deps._pick_relevant_urls(
                    critic_llm,
                    topic,
                    summary_notes,
                    combined_results,
                    top_urls,
                    config,
                    selected_urls_set,
                )
                normalized_chosen_urls: List[str] = []
                normalized_chosen_set = set()
                for url in chosen_urls:
                    canonical_url = deps.canonicalize_source_url(url)
                    if (
                        not canonical_url
                        or canonical_url in normalized_chosen_set
                        or canonical_url in selected_urls_set
                    ):
                        continue
                    normalized_chosen_urls.append(canonical_url)
                    normalized_chosen_set.add(canonical_url)
                chosen_urls = normalized_chosen_urls

                if not chosen_urls:
                    deps.logger.warning("[deepsearch] Epoch %s: No new URLs available, skipping", epoch + 1)
                    epoch_diagnostics = deps._build_quality_diagnostics(topic, have_query, search_runs)
                    deps._emit_event(
                        emitter,
                        "quality_update",
                        {"epoch": epoch + 1, "stage": "epoch", **epoch_diagnostics},
                    )
                    deps._emit_event(
                        emitter,
                        "research_node_complete",
                        {
                            "node_id": epoch_node_id,
                            "summary": "",
                            "sources": [],
                            "quality": epoch_diagnostics,
                            "epoch": epoch + 1,
                        },
                    )
                    continue

                selected_urls.extend(chosen_urls)
                selected_urls_set.update(chosen_urls)

                if visualize_browser:
                    try:
                        from agent.workflows.browser_visualizer import visualize_urls

                        visualize_urls(
                            state=state,
                            config=config,
                            urls=chosen_urls,
                            max_urls=min(3, len(chosen_urls)),
                            reason=f"deepsearch:selected:epoch{epoch + 1}",
                        )
                    except Exception:
                        pass

                new_pages, new_passages = deps._build_fetcher_evidence(chosen_urls)
                fetched_pages.extend(new_pages)
                passages.extend(new_passages)

                chosen_urls_set = set(chosen_urls)
                chosen_results = [
                    result
                    for result in combined_results
                    if deps.canonicalize_source_url(result.get("url")) in chosen_urls_set
                ]
                if not chosen_results:
                    chosen_results = sorted(
                        combined_results,
                        key=lambda result: result.get("score", 0),
                        reverse=True,
                    )[:top_urls]

                deps.logger.info(
                    "[deepsearch] Epoch %s: 选择 %s 个 URL | 已选总数: %s | 耗时 %.2fs",
                    epoch + 1,
                    len(chosen_urls),
                    len(selected_urls),
                    time.time() - pick_start,
                )

                if deps.settings.deepsearch_enable_crawler:
                    crawl_start = time.time()
                    deps._hydrate_with_crawler(chosen_results)
                    deps.logger.info(
                        "[deepsearch] Epoch %s: 爬虫增强完成 | 耗时 %.2fs",
                        epoch + 1,
                        time.time() - crawl_start,
                    )

                summary_start = time.time()
                enough, summary_text = deps._summarize_new_knowledge(
                    critic_llm,
                    topic,
                    summary_notes,
                    chosen_results,
                    config,
                )
                if summary_text:
                    summary_notes.append(summary_text)
                    tokens_used += deps._estimate_tokens_from_text(summary_text)

                deps.logger.info(
                    "[deepsearch] Epoch %s: 摘要完成 | 足够: %s | 摘要长度: %s | 耗时 %.2fs",
                    epoch + 1,
                    enough,
                    len(summary_text),
                    time.time() - summary_start,
                )
                budget_stop_reason = deps._budget_stop_reason(
                    start_ts=start_ts,
                    tokens_used=tokens_used,
                    max_seconds=max_seconds,
                    max_tokens=max_tokens,
                )
                if budget_stop_reason:
                    deps.logger.info("[deepsearch] 摘要后触发预算停止: %s", budget_stop_reason)
                    break

                use_gap_analysis = getattr(deps.settings, "deepsearch_use_gap_analysis", True)
                if use_gap_analysis and not enough and epoch < max_epochs - 1:
                    gap_start = time.time()
                    try:
                        gap_model = deps._model_for_task("gap_analysis", config)
                        gap_llm = deps._chat_model(gap_model, temperature=0.3)
                        gap_analyzer = deps.KnowledgeGapAnalyzer(
                            gap_llm,
                            config,
                            coverage_threshold=0.8,
                        )

                        collected_knowledge = "\n\n".join(summary_notes)
                        gap_result = gap_analyzer.analyze(topic, have_query, collected_knowledge)

                        deps.logger.info(
                            "[deepsearch] Epoch %s: 知识空白分析完成 | 覆盖率: %.2f | 空白数: %s | 耗时 %.2fs",
                            epoch + 1,
                            gap_result.overall_coverage,
                            len(gap_result.gaps),
                            time.time() - gap_start,
                        )

                        if gap_analyzer.is_research_sufficient(gap_result):
                            deps.logger.info("[deepsearch] Epoch %s: 知识空白分析判定信息足够", epoch + 1)
                            enough = True

                        high_priority_aspects = gap_analyzer.get_high_priority_aspects(gap_result)
                        if high_priority_aspects:
                            deps.logger.info(
                                "[deepsearch] 高优先级空白: %s",
                                ", ".join(high_priority_aspects[:3]),
                            )
                            state["missing_topics"] = high_priority_aspects

                    except Exception as exc:
                        deps.logger.warning("[deepsearch] 知识空白分析失败，继续常规流程: %s", exc)

                epoch_duration = time.time() - epoch_start
                deps.logger.info("[deepsearch] Epoch %s: 总耗时 %.2fs", epoch + 1, epoch_duration)
                epoch_diagnostics = deps._build_quality_diagnostics(topic, have_query, search_runs)
                deps._emit_event(
                    emitter,
                    "quality_update",
                    {"epoch": epoch + 1, "stage": "epoch", **epoch_diagnostics},
                )
                deps._emit_event(
                    emitter,
                    "research_node_complete",
                    {
                        "node_id": epoch_node_id,
                        "summary": summary_text[:1200] if isinstance(summary_text, str) else "",
                        "sources": deps._compact_search_results(
                            chosen_results,
                            limit=deps._event_results_limit(),
                        ),
                        "quality": epoch_diagnostics,
                        "epoch": epoch + 1,
                    },
                )

                if enough:
                    deps.logger.info("[deepsearch] Epoch %s: 信息已足够，提前结束", epoch + 1)
                    break

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                deps.logger.error("[deepsearch] Epoch %s 失败: %s", epoch + 1, str(exc), exc_info=True)
                deps.logger.error(traceback.format_exc())
                deps.logger.info("[deepsearch] 继续下一轮搜索...")
                continue

        citation_runs = deps._reorder_search_runs_for_citations(
            search_runs,
            preferred_urls=selected_urls,
        )

        report_sources_limit = int(
            getattr(deps.settings, "deepsearch_report_sources_limit", 20) or 20
        )
        all_sources: List[Dict[str, Any]] = []
        try:
            from agent.contracts.research import extract_message_sources

            all_sources = extract_message_sources(citation_runs)
        except Exception:
            all_sources = []
        report_sources = all_sources[: max(1, report_sources_limit)]
        sources_block = deps._format_sources_for_writer(
            report_sources,
            citation_runs,
            limit=report_sources_limit,
        )

        report_start = time.time()
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
        deps.logger.info(
            "[deepsearch] 最终报告生成完成 | 字数: %s | 耗时 %.2fs",
            len(final_report),
            time.time() - report_start,
        )

        elapsed = time.time() - start_ts
        deps.logger.info(
            "[deepsearch] ===== 完成 =====\n"
            "  总耗时: %.2fs\n"
            "  总轮次: %s\n"
            "  总查询: %s\n"
            "  总 URL: %s\n"
            "  已爬取: %s\n"
            "  摘要数: %s\n"
            "  估算Token: %s\n"
            "  预算停止原因: %s",
            elapsed,
            epoch + 1,
            len(have_query),
            len(all_searched_urls),
            len(selected_urls),
            len(summary_notes),
            tokens_used,
            budget_stop_reason or "none",
        )

        diagnostics = deps._build_quality_diagnostics(topic, have_query, citation_runs)
        quality_summary = {
            "epochs_completed": epoch + 1,
            "summary_count": len(summary_notes),
            "source_count": len(all_searched_urls),
            "selected_url_count": len(selected_urls),
            "budget_stop_reason": budget_stop_reason or "",
            "tokens_used": tokens_used,
            "elapsed_seconds": elapsed,
            **diagnostics,
        }
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
                citation_runs,
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
            "mode": "linear",
            "queries": have_query,
            "research_tree": None,
            "quality_summary": quality_summary,
            "query_coverage": diagnostics.get("query_coverage", {}),
            "freshness_summary": diagnostics.get("freshness_summary", {}),
            "fetched_pages": fetched_pages,
            "passages": passages,
            "sources": all_sources,
            "claims": claims,
        }

        save_path = deps._save_deepsearch_data(
            topic,
            have_query,
            summary_notes,
            citation_runs,
            final_report,
            epoch=epoch + 1,
        )

        messages = [AIMessage(content=final_report)]
        if save_path:
            messages.append(AIMessage(content=f"(数据已保存: {save_path})"))
        if budget_stop_reason:
            messages.append(
                AIMessage(
                    content=(
                        "（由于预算限制提前收敛："
                        f"{budget_stop_reason}; tokens={tokens_used}; elapsed={elapsed:.2f}s）"
                    )
                )
            )
        if diagnostics.get("freshness_warning"):
            messages.append(
                AIMessage(content="（时间敏感问题的新鲜来源占比较低，建议补充近30天来源并重试。）")
            )

        return {
            "research_plan": have_query,
            "scraped_content": citation_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "quality_summary": quality_summary,
            "sources": all_sources,
            "deepsearch_artifacts": deepsearch_artifacts,
            "deepsearch_mode": "linear",
            "messages": messages,
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": elapsed,
        }

    except asyncio.CancelledError:
        deps.logger.warning("[deepsearch] 收到取消信号，停止任务")
        return {
            "is_cancelled": True,
            "is_complete": True,
            "errors": ["DeepSearch was cancelled"],
            "final_report": "任务已被取消",
        }


__all__ = ["run_deepsearch_optimized"]
