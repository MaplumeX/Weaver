"""
Public API surface for the agent package.

Keep this list small and stable; everything else should be imported from the
specific submodules (agent.runtime.*, agent.contracts.*, agent.prompts.*, etc.).
"""

from agent.builders import build_agent_tools, build_tool_agent, build_writer_agent
from agent.contracts.research import (
    ClaimStatus,
    ClaimVerifier,
    ResultAggregator,
    extract_message_sources,
)
from agent.contracts.search_cache import clear_search_cache, get_search_cache
from agent.core import (
    AgentState,
    ContextWindowManager,
    QueryState,
    QueryDeduplicator,
    ResearchPlan,
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
from agent.prompts import (
    PromptManager,
    get_deep_agent_prompt,
    get_agent_prompt,
    get_deep_research_prompt,
    get_default_agent_prompt,
    get_prompt_manager,
    get_writer_prompt,
    set_prompt_manager,
)
from agent.runtime.deep import (
    run_deepsearch,
    run_deepsearch_auto,
    run_multi_agent_deepsearch,
    run_deepsearch_runtime,
)
from agent.runtime.graph import create_research_graph
from agent.runtime.nodes import initialize_enhanced_tools
from agent.runtime.graph import create_checkpointer

__all__ = [
    # Core graph/state
    "create_research_graph",
    "create_checkpointer",
    "AgentState",
    "QueryState",
    "ResearchPlan",
    "smart_route",
    "ContextWindowManager",
    "get_context_window_manager",
    "QueryDeduplicator",
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
    "get_prompt_manager",
    "set_prompt_manager",
    # Runtime/builders/tools
    "get_deep_agent_prompt",
    "run_deepsearch",
    "run_multi_agent_deepsearch",
    "build_writer_agent",
    "build_tool_agent",
    "build_agent_tools",
    "initialize_enhanced_tools",
    "summarize_messages",
    "run_deepsearch_auto",
    "run_deepsearch_runtime",
    # Shared contracts
    "get_search_cache",
    "clear_search_cache",
    "extract_message_sources",
    "ClaimStatus",
    "ClaimVerifier",
    "ResultAggregator",
]
