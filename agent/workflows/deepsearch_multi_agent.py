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
    BranchSynthesis,
    CoordinationRequest,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
    FinalReportArtifact,
    KnowledgeGap,
    ReportSectionDraft,
    ResearchSubmission,
    ResearchTask,
    SourceCandidate,
    ScopeDraft,
    SupervisorDecisionArtifact,
    VerificationResult,
    WorkerExecutionResult,
)
from agent.runtime.deep.multi_agent.store import ArtifactStore, ResearchTaskQueue
from agent.workflows.agent_factory import build_deep_research_tool_agent
from agent.workflows.agents.clarify import DeepResearchClarifyAgent
from agent.workflows.agents.coordinator import ResearchCoordinator
from agent.workflows.agents.planner import ResearchPlanner
from agent.workflows.agents.reporter import ResearchReporter
from agent.workflows.agents.researcher import ResearchAgent
from agent.workflows.agents.scope import DeepResearchScopeAgent
from agent.workflows.agents.supervisor import ResearchSupervisor, SupervisorAction, SupervisorDecision
from agent.workflows.knowledge_gap import GapAnalysisResult, KnowledgeGapAnalyzer

MultiAgentDeepSearchRuntime = _MultiAgentDeepSearchRuntime

_RUNTIME_COMPAT_EXPORTS = (
    DeepResearchClarifyAgent,
    DeepResearchScopeAgent,
    AgentRunRecord,
    ArtifactStore,
    BranchBrief,
    BranchSynthesis,
    CoordinationRequest,
    EvidenceCard,
    EvidencePassage,
    FetchedDocument,
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
    ResearchSubmission,
    ResearchSupervisor,
    ResearchTask,
    ResearchTaskQueue,
    SourceCandidate,
    ScopeDraft,
    SupervisorAction,
    SupervisorDecision,
    SupervisorDecisionArtifact,
    VerificationResult,
    WorkerExecutionResult,
    build_deep_research_tool_agent,
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
    "DeepResearchClarifyAgent",
    "DeepResearchScopeAgent",
    "AgentRunRecord",
    "ArtifactStore",
    "BranchBrief",
    "BranchSynthesis",
    "CoordinationRequest",
    "EvidenceCard",
    "EvidencePassage",
    "FetchedDocument",
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
    "ResearchSubmission",
    "ResearchSupervisor",
    "ResearchTask",
    "ResearchTaskQueue",
    "SourceCandidate",
    "ScopeDraft",
    "SupervisorAction",
    "SupervisorDecision",
    "SupervisorDecisionArtifact",
    "VerificationResult",
    "WorkerExecutionResult",
    "build_deep_research_tool_agent",
    "create_chat_model",
    "create_multi_agent_deepsearch_graph",
    "get_emitter_sync",
    "run_multi_agent_deepsearch",
]
