"""
Public shared contracts for code outside the agent runtime internals.

External callers should prefer these modules over importing from
`agent.runtime.*`, `agent.infrastructure.*`, or `agent.research.*`
implementation files directly.
"""

from agent.contracts.events import (
    Event,
    EventEmitter,
    ToolEvent,
    ToolEventType,
    event_stream_generator,
    get_emitter,
    get_emitter_sync,
    remove_emitter,
)
from agent.contracts.research import (
    ClaimStatus,
    ClaimVerifier,
    ResultAggregator,
    extract_message_sources,
)
from agent.contracts.search_cache import (
    QueryDeduplicator,
    SearchCache,
    clear_search_cache,
    get_search_cache,
)
from agent.contracts.source_registry import SourceRecord, SourceRegistry
from agent.contracts.worker_context import (
    ResearchWorkerContext,
    SubAgentContext,
    WorkerContextStore,
    build_research_worker_context,
    get_worker_context_store,
    merge_research_worker_context,
)

__all__ = [
    "ClaimStatus",
    "ClaimVerifier",
    "Event",
    "EventEmitter",
    "QueryDeduplicator",
    "ResearchWorkerContext",
    "ResultAggregator",
    "SearchCache",
    "SourceRecord",
    "SourceRegistry",
    "SubAgentContext",
    "ToolEvent",
    "ToolEventType",
    "WorkerContextStore",
    "build_research_worker_context",
    "clear_search_cache",
    "event_stream_generator",
    "extract_message_sources",
    "get_emitter",
    "get_emitter_sync",
    "get_search_cache",
    "get_worker_context_store",
    "merge_research_worker_context",
    "remove_emitter",
]
