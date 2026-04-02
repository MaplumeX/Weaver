"""
Session Manager for Weaver.

Provides high-level CRUD operations for research sessions.
Wraps the LangGraph checkpointer for persistence and recovery.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent.runtime.deep.artifacts.public_artifacts import build_public_deepsearch_artifacts_from_state
from agent.runtime.deep.state import resolve_deep_runtime_mode
from common.checkpoint_ops import adelete_checkpoint, aget_checkpoint_tuple, alist_checkpoints

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Summary information about a research session."""
    thread_id: str
    status: str  # pending, running, completed, cancelled, failed
    topic: str
    created_at: str
    updated_at: str
    route: str
    has_report: bool
    revision_count: int
    message_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "status": self.status,
            "topic": self.topic,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "route": self.route,
            "has_report": self.has_report,
            "revision_count": self.revision_count,
            "message_count": self.message_count,
        }


@dataclass
class SessionState:
    """Full state snapshot of a research session."""
    thread_id: str
    state: Dict[str, Any]
    checkpoint_ts: str
    parent_checkpoint_id: Optional[str]
    deepsearch_artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "checkpoint_ts": self.checkpoint_ts,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "state": self._sanitize_state(self.state),
            "deepsearch_artifacts": self.deepsearch_artifacts,
        }

    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize state for JSON serialization."""
        sanitized = {}
        for k, v in state.items():
            if k == "messages":
                # Convert messages to serializable format
                sanitized[k] = [
                    {"type": getattr(m, "type", "unknown"), "content": getattr(m, "content", str(m))[:500]}
                    for m in v[:20]  # Limit to last 20 messages
                ] if isinstance(v, list) else []
            elif k in ("scraped_content", "pending_tool_calls"):
                # Summarize large lists
                sanitized[k] = f"[{len(v)} items]" if isinstance(v, list) else v
            elif k == "deepsearch_artifacts" and isinstance(v, dict):
                sanitized[k] = {
                    "mode": v.get("mode"),
                    "queries_count": len(v.get("queries", []) or []),
                    "has_tree": bool(v.get("research_tree")),
                    "quality_summary": v.get("quality_summary", {}),
                }
            else:
                # Try to include as-is, fall back to string representation
                try:
                    import json
                    json.dumps(v)
                    sanitized[k] = v
                except (TypeError, ValueError):
                    sanitized[k] = str(v)[:200]
        return sanitized


class SessionManager:
    """
    Manages research sessions using LangGraph checkpointer.

    Provides:
    - List all sessions
    - Get session state
    - Resume session
    - Delete session
    """

    def __init__(self, checkpointer):
        """
        Initialize the session manager.

        Args:
            checkpointer: LangGraph checkpointer instance
        """
        self.checkpointer = checkpointer

    def list_sessions(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        user_id_filter: Optional[str] = None,
    ) -> List[SessionInfo]:
        """
        List all sessions.

        Args:
            limit: Maximum sessions to return
            status_filter: Filter by status (optional)

        Returns:
            List of SessionInfo objects
        """
        try:
            checkpoints = self._list_checkpoints_sync()
            return self._build_sessions(
                checkpoints,
                limit=limit,
                status_filter=status_filter,
                user_id_filter=user_id_filter,
            )

        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return []

    async def alist_sessions(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
        user_id_filter: Optional[str] = None,
    ) -> List[SessionInfo]:
        """Asynchronously list all sessions."""
        try:
            checkpoints = await self._list_checkpoints_async()
            return self._build_sessions(
                checkpoints,
                limit=limit,
                status_filter=status_filter,
                user_id_filter=user_id_filter,
            )
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return []

    def get_session(self, thread_id: str) -> Optional[SessionInfo]:
        """
        Get session info by thread ID.

        Args:
            thread_id: Thread identifier

        Returns:
            SessionInfo or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = self.checkpointer.get_tuple(config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            return self._build_session_info(thread_id, state, checkpoint_tuple)

        except Exception as e:
            logger.error(f"Error getting session {thread_id}: {e}")
            return None

    async def aget_session(self, thread_id: str) -> Optional[SessionInfo]:
        """Asynchronously get session info by thread ID."""
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = await aget_checkpoint_tuple(self.checkpointer, config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            return self._build_session_info(thread_id, state, checkpoint_tuple)
        except Exception as e:
            logger.error(f"Error getting session {thread_id}: {e}")
            return None

    def get_session_state(self, thread_id: str) -> Optional[SessionState]:
        """
        Get full session state.

        Args:
            thread_id: Thread identifier

        Returns:
            SessionState or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = self.checkpointer.get_tuple(config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            checkpoint_ts = ""
            parent_id = None

            if hasattr(checkpoint_tuple, "metadata"):
                metadata = checkpoint_tuple.metadata or {}
                checkpoint_ts = metadata.get("created_at", "")

            if hasattr(checkpoint_tuple, "parent_config"):
                parent_config = checkpoint_tuple.parent_config
                if parent_config:
                    parent_id = parent_config.get("configurable", {}).get("checkpoint_id")

            deepsearch_artifacts = self._extract_deepsearch_artifacts(state)

            return SessionState(
                thread_id=thread_id,
                state=state,
                checkpoint_ts=checkpoint_ts,
                parent_checkpoint_id=parent_id,
                deepsearch_artifacts=deepsearch_artifacts,
            )

        except Exception as e:
            logger.error(f"Error getting session state {thread_id}: {e}")
            return None

    async def aget_session_state(self, thread_id: str) -> Optional[SessionState]:
        """Asynchronously get full session state."""
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = await aget_checkpoint_tuple(self.checkpointer, config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            checkpoint_ts = ""
            parent_id = None

            if hasattr(checkpoint_tuple, "metadata"):
                metadata = checkpoint_tuple.metadata or {}
                checkpoint_ts = metadata.get("created_at", "")

            if hasattr(checkpoint_tuple, "parent_config"):
                parent_config = checkpoint_tuple.parent_config
                if parent_config:
                    parent_id = parent_config.get("configurable", {}).get("checkpoint_id")

            deepsearch_artifacts = self._extract_deepsearch_artifacts(state)

            return SessionState(
                thread_id=thread_id,
                state=state,
                checkpoint_ts=checkpoint_ts,
                parent_checkpoint_id=parent_id,
                deepsearch_artifacts=deepsearch_artifacts,
            )
        except Exception as e:
            logger.error(f"Error getting session state {thread_id}: {e}")
            return None

    def delete_session(self, thread_id: str) -> bool:
        """
        Delete a session and all its checkpoints.

        Args:
            thread_id: Thread identifier

        Returns:
            True if deleted, False otherwise
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}

            # Check if checkpointer supports deletion
            if hasattr(self.checkpointer, "delete"):
                self.checkpointer.delete(config)
                logger.info(f"Deleted session: {thread_id}")
                return True
            elif hasattr(self.checkpointer, "put"):
                # Soft delete by marking as deleted
                checkpoint_tuple = self.checkpointer.get_tuple(config)
                if checkpoint_tuple:
                    state = checkpoint_tuple.checkpoint.get("channel_values", {})
                    state["status"] = "deleted"
                    state["is_complete"] = True
                    # Note: Can't actually delete, just mark
                    logger.info(f"Marked session as deleted: {thread_id}")
                    return True

            logger.warning(f"Checkpointer does not support deletion: {thread_id}")
            return False

        except Exception as e:
            logger.error(f"Error deleting session {thread_id}: {e}")
            return False

    async def adelete_session(self, thread_id: str) -> bool:
        """Asynchronously delete a session and all its checkpoints."""
        try:
            config = {"configurable": {"thread_id": thread_id}}

            if await adelete_checkpoint(self.checkpointer, config):
                logger.info(f"Deleted session: {thread_id}")
                return True

            if hasattr(self.checkpointer, "put") or hasattr(self.checkpointer, "aput"):
                checkpoint_tuple = await aget_checkpoint_tuple(self.checkpointer, config)
                if checkpoint_tuple:
                    logger.info(f"Marked session as deleted: {thread_id}")
                    return True

            logger.warning(f"Checkpointer does not support deletion: {thread_id}")
            return False
        except Exception as e:
            logger.error(f"Error deleting session {thread_id}: {e}")
            return False

    def can_resume(self, thread_id: str) -> Tuple[bool, str]:
        """
        Check if a session can be resumed.

        Args:
            thread_id: Thread identifier

        Returns:
            Tuple of (can_resume, reason)
        """
        session = self.get_session(thread_id)
        if not session:
            return False, "Session not found"

        if session.status == "completed":
            return False, "Session already completed"

        if session.status == "deleted":
            return False, "Session has been deleted"

        if session.status == "running":
            return False, "Session is currently running"

        return True, "Session can be resumed"

    async def acan_resume(self, thread_id: str) -> Tuple[bool, str]:
        """Asynchronously check if a session can be resumed."""
        session = await self.aget_session(thread_id)
        if not session:
            return False, "Session not found"

        if session.status == "completed":
            return False, "Session already completed"

        if session.status == "deleted":
            return False, "Session has been deleted"

        if session.status == "running":
            return False, "Session is currently running"

        return True, "Session can be resumed"

    def build_resume_state(
        self,
        thread_id: str,
        additional_input: Optional[str] = None,
        update_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a restored state payload for session resumption.

        Rehydrates deepsearch artifacts into top-level fields so graph execution
        can continue from collected context instead of starting from scratch.
        """
        session_state = self.get_session_state(thread_id)
        if not session_state:
            return None

        restored = deepcopy(session_state.state)
        artifacts = session_state.deepsearch_artifacts or {}

        if isinstance(update_state, dict):
            restored.update(update_state)

        if additional_input:
            restored["resume_input"] = additional_input

        if artifacts:
            restored["deepsearch_artifacts"] = artifacts
            if artifacts.get("queries") and not restored.get("research_plan"):
                restored["research_plan"] = list(artifacts.get("queries", []))
            if artifacts.get("research_tree") and not restored.get("research_tree"):
                restored["research_tree"] = artifacts.get("research_tree")
            if artifacts.get("quality_summary") and not restored.get("quality_summary"):
                restored["quality_summary"] = artifacts.get("quality_summary")
            if artifacts.get("query_coverage") and not restored.get("query_coverage"):
                restored["query_coverage"] = artifacts.get("query_coverage")
            if artifacts.get("freshness_summary") and not restored.get("freshness_summary"):
                restored["freshness_summary"] = artifacts.get("freshness_summary")

        restored["resumed_from_checkpoint"] = True
        restored["resumed_at"] = datetime.utcnow().isoformat()
        return restored

    async def abuild_resume_state(
        self,
        thread_id: str,
        additional_input: Optional[str] = None,
        update_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Asynchronously build a restored state payload for session resumption."""
        session_state = await self.aget_session_state(thread_id)
        if not session_state:
            return None

        restored = deepcopy(session_state.state)
        artifacts = session_state.deepsearch_artifacts or {}

        if isinstance(update_state, dict):
            restored.update(update_state)

        if additional_input:
            restored["resume_input"] = additional_input

        if artifacts:
            restored["deepsearch_artifacts"] = artifacts
            if artifacts.get("queries") and not restored.get("research_plan"):
                restored["research_plan"] = list(artifacts.get("queries", []))
            if artifacts.get("research_tree") and not restored.get("research_tree"):
                restored["research_tree"] = artifacts.get("research_tree")
            if artifacts.get("quality_summary") and not restored.get("quality_summary"):
                restored["quality_summary"] = artifacts.get("quality_summary")
            if artifacts.get("query_coverage") and not restored.get("query_coverage"):
                restored["query_coverage"] = artifacts.get("query_coverage")
            if artifacts.get("freshness_summary") and not restored.get("freshness_summary"):
                restored["freshness_summary"] = artifacts.get("freshness_summary")

        restored["resumed_from_checkpoint"] = True
        restored["resumed_at"] = datetime.utcnow().isoformat()
        return restored

    def _list_checkpoints_sync(self) -> List[Any]:
        if hasattr(self.checkpointer, "list"):
            return list(self.checkpointer.list({"configurable": {}}))
        if hasattr(self.checkpointer, "storage"):
            checkpoints = []
            for config, checkpoint in self.checkpointer.storage.items():
                checkpoints.append({"config": config, "checkpoint": checkpoint})
            return checkpoints
        logger.warning("Checkpointer does not support listing")
        return []

    async def _list_checkpoints_async(self) -> List[Any]:
        if hasattr(self.checkpointer, "alist") or hasattr(self.checkpointer, "list"):
            return await alist_checkpoints(self.checkpointer, {"configurable": {}})
        if hasattr(self.checkpointer, "storage"):
            checkpoints = []
            for config, checkpoint in self.checkpointer.storage.items():
                checkpoints.append({"config": config, "checkpoint": checkpoint})
            return checkpoints
        logger.warning("Checkpointer does not support listing")
        return []

    def _build_sessions(
        self,
        checkpoints: List[Any],
        *,
        limit: int,
        status_filter: Optional[str],
        user_id_filter: Optional[str],
    ) -> List[SessionInfo]:
        sessions = []
        seen_threads = set()

        for cp_info in checkpoints[:limit * 2]:
            try:
                if isinstance(cp_info, tuple):
                    config, checkpoint = cp_info
                else:
                    config = cp_info.get("config", {})
                    checkpoint = cp_info.get("checkpoint", cp_info)

                thread_id = None
                if isinstance(config, dict):
                    thread_id = config.get("configurable", {}).get("thread_id")
                elif hasattr(config, "configurable"):
                    thread_id = config.configurable.get("thread_id")

                if not thread_id or thread_id in seen_threads:
                    continue

                seen_threads.add(thread_id)

                state = {}
                if hasattr(checkpoint, "checkpoint"):
                    state = checkpoint.checkpoint.get("channel_values", {})
                elif isinstance(checkpoint, dict):
                    state = checkpoint.get("channel_values", {})

                if user_id_filter:
                    owner = state.get("user_id")
                    if not isinstance(owner, str) or owner.strip() != user_id_filter:
                        continue

                session_info = self._build_session_info(thread_id, state, checkpoint)
                if status_filter and session_info.status != status_filter:
                    continue

                sessions.append(session_info)
                if len(sessions) >= limit:
                    break
            except Exception as e:
                logger.debug(f"Error processing checkpoint: {e}")
                continue

        return sessions

    def _build_session_info(
        self,
        thread_id: str,
        state: Dict[str, Any],
        checkpoint_tuple: Any,
    ) -> SessionInfo:
        """Build SessionInfo from state and checkpoint."""
        status = state.get("status", "unknown")
        if state.get("is_complete"):
            status = "completed"
        elif state.get("is_cancelled"):
            status = "cancelled"

        topic = state.get("input", "")[:100]
        route = state.get("route", "unknown")
        has_report = bool(state.get("final_report"))
        revision_count = int(state.get("revision_count", 0))

        messages = state.get("messages", [])
        message_count = len(messages) if isinstance(messages, list) else 0

        created_at = state.get("started_at", "")
        updated_at = state.get("ended_at", "")

        # Try to get timestamps from checkpoint metadata
        if hasattr(checkpoint_tuple, "metadata"):
            metadata = checkpoint_tuple.metadata or {}
            if not created_at:
                created_at = metadata.get("created_at", "")

        return SessionInfo(
            thread_id=thread_id,
            status=status,
            topic=topic,
            created_at=created_at,
            updated_at=updated_at,
            route=route,
            has_report=has_report,
            revision_count=revision_count,
            message_count=message_count,
        )

    def _extract_deepsearch_artifacts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract canonical deepsearch artifacts from state snapshot."""
        if not isinstance(state, dict):
            return {}

        public_artifacts = build_public_deepsearch_artifacts_from_state(state)
        if public_artifacts:
            return public_artifacts

        artifacts = state.get("deepsearch_artifacts")
        scraped_content = state.get("scraped_content", [])
        final_report = state.get("final_report") or state.get("draft_report") or ""

        def _maybe_extract_sources() -> List[Dict[str, Any]]:
            if not isinstance(scraped_content, list) or not scraped_content:
                return []
            try:
                from agent.contracts.research import extract_message_sources

                return extract_message_sources(scraped_content)
            except Exception:
                return []

        def _maybe_extract_claims() -> List[Dict[str, Any]]:
            if not isinstance(final_report, str) or not final_report.strip():
                return []
            scraped_list = scraped_content if isinstance(scraped_content, list) else []
            passages_list: Optional[List[Dict[str, Any]]] = None
            try:
                from agent.contracts.research import ClaimVerifier

                verifier = ClaimVerifier()
                if isinstance(artifacts, dict):
                    raw_passages = artifacts.get("passages")
                    if isinstance(raw_passages, list) and raw_passages:
                        passages_list = raw_passages

                if not scraped_list and not passages_list:
                    return []

                checks = verifier.verify_report(
                    final_report,
                    scraped_list,
                    passages=passages_list,
                )
                claims: List[Dict[str, Any]] = []
                for check in checks:
                    claims.append(
                        {
                            "claim": check.claim,
                            "status": check.status.value,
                            "evidence_urls": check.evidence_urls,
                            "evidence_passages": check.evidence_passages,
                            "score": check.score,
                            "notes": check.notes,
                        }
                    )
                return claims
            except Exception:
                return []

        if isinstance(artifacts, dict):
            enriched = dict(artifacts)
            enriched.setdefault("fetched_pages", [])
            enriched.setdefault("passages", [])
            if "sources" not in enriched:
                sources = _maybe_extract_sources()
                if sources:
                    enriched["sources"] = sources
            if "claims" not in enriched:
                claims = _maybe_extract_claims()
                if claims:
                    enriched["claims"] = claims
            return enriched

        derived_artifacts = build_public_deepsearch_artifacts_from_state(state)
        if isinstance(derived_artifacts, dict) and derived_artifacts:
            enriched = dict(derived_artifacts)
            if "sources" not in enriched:
                sources = _maybe_extract_sources()
                if sources:
                    enriched["sources"] = sources
            if "claims" not in enriched:
                claims = _maybe_extract_claims()
                if claims:
                    enriched["claims"] = claims
            return enriched

        queries = state.get("research_plan", []) if isinstance(state.get("research_plan", []), list) else []
        research_tree = state.get("research_tree")

        quality_summary: Dict[str, Any] = {}
        raw_quality = state.get("quality_summary")
        if isinstance(raw_quality, dict) and raw_quality:
            quality_summary = raw_quality
        else:
            summary_count = len(state.get("summary_notes", []) or [])
            source_count = len(state.get("scraped_content", []) or [])
            quality_overall_score = state.get("quality_overall_score")
            if summary_count > 0 or source_count > 0 or quality_overall_score is not None:
                quality_summary = {
                    "summary_count": summary_count,
                    "source_count": source_count,
                    "revision_count": int(state.get("revision_count", 0) or 0),
                    "quality_overall_score": quality_overall_score,
                }

        query_coverage = state.get("query_coverage")
        if not isinstance(query_coverage, dict):
            query_coverage = {}
        if not query_coverage and isinstance(quality_summary, dict):
            nested_coverage = quality_summary.get("query_coverage")
            if isinstance(nested_coverage, dict) and nested_coverage:
                query_coverage = nested_coverage
            else:
                query_coverage_score = quality_summary.get("query_coverage_score")
                if query_coverage_score is not None:
                    try:
                        query_coverage = {"score": float(query_coverage_score)}
                    except (TypeError, ValueError):
                        query_coverage = {}
        freshness_summary = state.get("freshness_summary")
        if not isinstance(freshness_summary, dict):
            freshness_summary = {}

        if (
            not queries
            and not research_tree
            and not quality_summary
            and not query_coverage
            and not freshness_summary
        ):
            return {}

        sources = _maybe_extract_sources()
        claims = _maybe_extract_claims()

        return {
            "mode": resolve_deep_runtime_mode(state),
            "queries": queries,
            "research_tree": research_tree,
            "quality_summary": quality_summary,
            "query_coverage": query_coverage,
            "freshness_summary": freshness_summary,
            "fetched_pages": [],
            "passages": [],
            "sources": sources,
            "claims": claims,
        }


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(checkpointer) -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None or _session_manager.checkpointer != checkpointer:
        _session_manager = SessionManager(checkpointer)
    return _session_manager
