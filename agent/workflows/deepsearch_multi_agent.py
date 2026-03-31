from __future__ import annotations

from agent.contracts.events import get_emitter_sync
from agent.core.llm_factory import create_chat_model
from agent.runtime.deep.multi_agent.runtime import (
    MultiAgentDeepSearchRuntime as _MultiAgentDeepSearchRuntime,
)
from agent.runtime.deep.multi_agent.runtime import (
    create_multi_agent_deepsearch_graph as _create_multi_agent_deepsearch_graph,
)
from agent.runtime.deep.multi_agent.runtime import (
    run_multi_agent_deepsearch as _run_multi_agent_deepsearch,
)
from agent.runtime.deep.multi_agent.schema import (
    AgentRunRecord,
    BranchBrief,
    EvidenceCard,
    FinalReportArtifact,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchTask,
    WorkerExecutionResult,
)
from agent.runtime.deep.multi_agent.store import ArtifactStore, ResearchTaskQueue
from agent.workflows.agents.coordinator import ResearchCoordinator
from agent.workflows.agents.planner import ResearchPlanner
from agent.workflows.agents.reporter import ResearchReporter
from agent.workflows.agents.researcher import ResearchAgent
from agent.workflows.knowledge_gap import GapAnalysisResult, KnowledgeGapAnalyzer

MultiAgentDeepSearchRuntime = _MultiAgentDeepSearchRuntime

_RUNTIME_COMPAT_EXPORTS = (
    AgentRunRecord,
    ArtifactStore,
    BranchBrief,
    EvidenceCard,
    FinalReportArtifact,
    GapAnalysisResult,
    KnowledgeGap,
    KnowledgeGapAnalyzer,
    MultiAgentDeepSearchRuntime,
    ReportSectionDraft,
    ResearchAgent,
    ResearchCoordinator,
    ResearchPlanner,
    ResearchReporter,
    ResearchTask,
    ResearchTaskQueue,
    WorkerExecutionResult,
    create_chat_model,
    get_emitter_sync,
)


def run_multi_agent_deepsearch(state, config):
    return _run_multi_agent_deepsearch(state, config)


def create_multi_agent_deepsearch_graph(state, config, *, checkpointer=None, interrupt_before=None):
    return _create_multi_agent_deepsearch_graph(
        state,
        config,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


__all__ = [
    "AgentRunRecord",
    "ArtifactStore",
    "BranchBrief",
    "EvidenceCard",
    "FinalReportArtifact",
    "GapAnalysisResult",
    "KnowledgeGap",
    "KnowledgeGapAnalyzer",
    "MultiAgentDeepSearchRuntime",
    "ReportSectionDraft",
    "ResearchAgent",
    "ResearchCoordinator",
    "ResearchPlanner",
    "ResearchReporter",
    "ResearchTask",
    "ResearchTaskQueue",
    "WorkerExecutionResult",
    "create_chat_model",
    "create_multi_agent_deepsearch_graph",
    "get_emitter_sync",
    "run_multi_agent_deepsearch",
]
