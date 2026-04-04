"""
Public API surface for the agent package.

Keep this list small and stable; everything else should be imported from the
specific submodules (agent.runtime.*, agent.contracts.*, agent.prompts.*, etc.).
"""

from agent.application import build_execution_request, build_initial_agent_state
from agent.contracts.research import (
    ClaimStatus,
    ClaimVerifier,
    ResultAggregator,
    extract_message_sources,
)
from agent.contracts.search_cache import clear_search_cache, get_search_cache
from agent.domain import (
    AgentProfileConfig,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ReviewDecision,
    ToolCapability,
)
from agent.core import (
    AgentState,
    ConversationState,
    ContextWindowManager,
    ExecutionState,
    QueryState,
    QueryDeduplicator,
    ResearchState,
    ResearchPlan,
    RuntimeSnapshot,
    ToolEvent,
    ToolEventType,
    event_stream_generator,
    get_emitter,
    get_emitter_sync,
    get_context_window_manager,
    remove_emitter,
    smart_route,
)
from agent.core.message_utils import summarize_messages
from agent.infrastructure.agents import build_tool_agent, build_writer_agent
from agent.infrastructure.tools import build_agent_toolset
from agent.prompts import (
    PromptManager,
    PromptRegistry,
    get_deep_agent_prompt,
    get_agent_prompt,
    get_deep_research_prompt,
    get_default_agent_prompt,
    get_prompt_manager,
    get_prompt_registry,
    render_prompt,
    get_writer_prompt,
    set_prompt_manager,
)
from agent.runtime.deep import run_deep_research
from agent.runtime.graph import create_research_graph
from agent.runtime.nodes import initialize_enhanced_tools
from agent.runtime.graph import create_checkpointer

__all__ = [
    # Core graph/state
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "ConversationState",
    "ExecutionState",
    "QueryState",
    "ResearchPlan",
    "ResearchState",
    "RuntimeSnapshot",
    "smart_route",
    "ContextWindowManager",
    "get_context_window_manager",
    "QueryDeduplicator",
    "ExecutionMode",
    "ExecutionRequest",
    "ExecutionResult",
    "ReviewDecision",
    "ToolCapability",
    "AgentProfileConfig",
    "build_execution_request",
    "build_initial_agent_state",
    # Events / streaming
    "event_stream_generator",
    "get_emitter",
    "get_emitter_sync",
    "remove_emitter",
    "ToolEvent",
    "ToolEventType",
    # Prompts
    "get_default_agent_prompt",
    "get_agent_prompt",
    "get_writer_prompt",
    "get_deep_research_prompt",
    "PromptManager",
    "PromptRegistry",
    "get_prompt_manager",
    "get_prompt_registry",
    "render_prompt",
    "set_prompt_manager",
    # Runtime/tools
    "get_deep_agent_prompt",
    "run_deep_research",
    "build_writer_agent",
    "build_tool_agent",
    "build_agent_toolset",
    "initialize_enhanced_tools",
    "summarize_messages",
    # Shared contracts
    "get_search_cache",
    "clear_search_cache",
    "extract_message_sources",
    "ClaimStatus",
    "ClaimVerifier",
    "ResultAggregator",
]
