"""
Engine selection for deep-research runtimes.
"""

from __future__ import annotations

from typing import Any

from langgraph.errors import GraphBubbleUp

from agent.workflows import deepsearch_optimized as _legacy_runtime
from common.config import settings


def run_multi_agent_deepsearch(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    Compatibility wrapper so callers can patch either the selector-local entrypoint
    or the legacy workflow module during the migration window.
    """

    return _legacy_runtime.run_multi_agent_deepsearch(state, config)


def run_deepsearch_auto(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    Select the concrete deep runtime without mixing selector logic into
    individual runtime modules.
    """

    def _with_event_marker(result: dict[str, Any]) -> dict[str, Any]:
        if isinstance(result, dict) and not bool(result.get("is_cancelled")):
            result.setdefault("_deepsearch_events_emitted", True)
        return result

    def _run_legacy_deepsearch() -> dict[str, Any]:
        mode = _legacy_runtime._resolve_deepsearch_mode(config)

        if mode == "tree":
            _legacy_runtime.logger.info("[deepsearch] Using tree-based exploration mode (override)")
            return _with_event_marker(_legacy_runtime.run_deepsearch_tree(state, config))

        if mode == "linear":
            _legacy_runtime.logger.info("[deepsearch] Using linear exploration mode (override)")
            return _with_event_marker(_legacy_runtime.run_deepsearch_optimized(state, config))

        use_tree = getattr(settings, "tree_exploration_enabled", True)
        topic = str(state.get("input") or state.get("topic") or "").strip()
        if use_tree and _legacy_runtime._auto_mode_prefers_linear(topic):
            _legacy_runtime.logger.info(
                "[deepsearch] Auto mode selected linear exploration for simple factual query"
            )
            simple_config = dict(config) if isinstance(config, dict) else {"configurable": {}}
            existing_cfg = simple_config.get("configurable")
            simple_cfg = dict(existing_cfg) if isinstance(existing_cfg, dict) else {}
            simple_config["configurable"] = simple_cfg
            simple_cfg.setdefault("deepsearch_max_epochs", 1)
            simple_cfg.setdefault("deepsearch_query_num", 1)
            simple_cfg.setdefault("deepsearch_results_per_query", 5)
            simple_cfg.setdefault("deepsearch_visualize_browser", False)
            return _with_event_marker(_legacy_runtime.run_deepsearch_optimized(state, simple_config))
        if use_tree:
            _legacy_runtime.logger.info("[deepsearch] Using tree-based exploration mode")
            return _with_event_marker(_legacy_runtime.run_deepsearch_tree(state, config))

        _legacy_runtime.logger.info("[deepsearch] Using linear exploration mode")
        return _with_event_marker(_legacy_runtime.run_deepsearch_optimized(state, config))

    engine = _legacy_runtime._resolve_deepsearch_engine(config)
    if engine == "multi_agent":
        try:
            _legacy_runtime.logger.info("[deepsearch] Using multi-agent runtime")
            return _with_event_marker(run_multi_agent_deepsearch(state, config))
        except GraphBubbleUp:
            raise
        except Exception as exc:
            _legacy_runtime.logger.error(
                "[deepsearch] multi-agent runtime failed: %s", exc, exc_info=True
            )
            raise

    return _run_legacy_deepsearch()


__all__ = ["run_deepsearch_auto", "run_multi_agent_deepsearch"]
