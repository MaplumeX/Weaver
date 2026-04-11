"""
Public shared contracts for code outside the agent runtime internals.

External callers should prefer these modules over importing from
`agent.execution.*`, `agent.chat.*`, `agent.deep_research.*`,
`agent.tooling.*`, `agent.execution.intake.*`, or `agent.foundation.*`
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
    extract_message_sources,
)
from agent.contracts.search_cache import (
    QueryDeduplicator,
    SearchCache,
    clear_search_cache,
    get_search_cache,
)
from agent.contracts.source_registry import SourceRecord, SourceRegistry

__all__ = [
    "Event",
    "EventEmitter",
    "QueryDeduplicator",
    "SearchCache",
    "SourceRecord",
    "SourceRegistry",
    "ToolEvent",
    "ToolEventType",
    "clear_search_cache",
    "event_stream_generator",
    "extract_message_sources",
    "get_emitter",
    "get_emitter_sync",
    "get_search_cache",
    "remove_emitter",
]
