"""
Multi-agent deep-research runtime contracts and entrypoints.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "AgentRunRecord",
    "ArtifactStore",
    "BranchBrief",
    "CoordinationRequest",
    "EvidenceCard",
    "FinalReportArtifact",
    "KnowledgeGap",
    "MultiAgentDeepSearchRuntime",
    "ReportSectionDraft",
    "ResearchSubmission",
    "ResearchTask",
    "ResearchTaskQueue",
    "SupervisorDecisionArtifact",
    "WorkerExecutionResult",
    "create_deepsearch_runtime_graph",
    "create_multi_agent_deepsearch_graph",
    "run_deepsearch_runtime",
    "run_multi_agent_deepsearch",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    "AgentRunRecord": "agent.runtime.deep.multi_agent.schema",
    "ArtifactStore": "agent.runtime.deep.multi_agent.store",
    "BranchBrief": "agent.runtime.deep.multi_agent.schema",
    "CoordinationRequest": "agent.runtime.deep.multi_agent.schema",
    "EvidenceCard": "agent.runtime.deep.multi_agent.schema",
    "FinalReportArtifact": "agent.runtime.deep.multi_agent.schema",
    "KnowledgeGap": "agent.runtime.deep.multi_agent.schema",
    "MultiAgentDeepSearchRuntime": "agent.runtime.deep.multi_agent.runtime",
    "ReportSectionDraft": "agent.runtime.deep.multi_agent.schema",
    "ResearchSubmission": "agent.runtime.deep.multi_agent.schema",
    "ResearchTask": "agent.runtime.deep.multi_agent.schema",
    "ResearchTaskQueue": "agent.runtime.deep.multi_agent.store",
    "SupervisorDecisionArtifact": "agent.runtime.deep.multi_agent.schema",
    "WorkerExecutionResult": "agent.runtime.deep.multi_agent.schema",
    "create_deepsearch_runtime_graph": "agent.runtime.deep.multi_agent.runtime",
    "create_multi_agent_deepsearch_graph": "agent.runtime.deep.multi_agent.runtime",
    "run_deepsearch_runtime": "agent.runtime.deep.multi_agent.runtime",
    "run_multi_agent_deepsearch": "agent.runtime.deep.multi_agent.runtime",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
