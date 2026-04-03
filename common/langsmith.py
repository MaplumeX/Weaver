import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def sync_langsmith_env(
    *,
    tracing: bool,
    api_key: str = "",
    project: str = "",
    endpoint: str = "",
    workspace_id: str = "",
) -> None:
    """
    Sync LangSmith settings into process environment variables.

    Pydantic `.env` loading does not populate `os.environ`, but LangSmith's
    auto-tracing reads process environment variables directly.
    """
    os.environ["LANGSMITH_TRACING"] = "true" if tracing else "false"

    env_values = {
        "LANGSMITH_API_KEY": api_key.strip(),
        "LANGSMITH_PROJECT": project.strip(),
        "LANGSMITH_ENDPOINT": endpoint.strip(),
        "LANGSMITH_WORKSPACE_ID": workspace_id.strip(),
    }
    for key, value in env_values.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def is_langsmith_enabled(*, tracing: bool, api_key: str) -> bool:
    return bool(tracing and api_key.strip())


def build_langsmith_run_name(*, surface: str, mode: str) -> str:
    safe_surface = (surface or "chat").strip() or "chat"
    safe_mode = (mode or "agent").strip() or "agent"
    return f"weaver-{safe_surface}-{safe_mode}"


def build_langsmith_tags(
    *,
    surface: str,
    mode: str,
    stream: bool | None = None,
    resumed_from_checkpoint: bool = False,
) -> list[str]:
    tags = [
        "weaver",
        f"surface:{(surface or 'chat').strip() or 'chat'}",
        f"mode:{(mode or 'agent').strip() or 'agent'}",
    ]
    if stream is True:
        tags.append("stream")
    elif stream is False:
        tags.append("sync")
    if resumed_from_checkpoint:
        tags.append("resume")
    return tags


def build_langsmith_metadata(
    *,
    thread_id: str,
    user_id: str,
    model: str,
    surface: str,
    mode: str,
    agent_id: str = "",
    app_env: str = "",
    resumed_from_checkpoint: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "model": model,
        "surface": surface,
        "mode": mode,
        "resumed_from_checkpoint": resumed_from_checkpoint,
    }
    if agent_id:
        metadata["agent_id"] = agent_id
    if app_env:
        metadata["app_env"] = app_env
    if extra:
        metadata.update({k: v for k, v in extra.items() if v is not None})
    return metadata


def with_langsmith_context(
    config: dict[str, Any],
    *,
    run_name: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(config)
    enriched["run_name"] = run_name
    if tags:
        enriched["tags"] = list(tags)
    if metadata:
        enriched["metadata"] = dict(metadata)
    return enriched


def wrap_openai_client(client: Any) -> Any:
    """
    Best-effort wrapper for direct OpenAI SDK clients.

    LangSmith is optional at runtime during tests or partial installations, so
    missing package / wrapper failures should never break the application.
    """
    try:
        from langsmith.wrappers import wrap_openai
    except ImportError:
        return client

    try:
        return wrap_openai(client)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to wrap OpenAI client with LangSmith: %s", exc)
        return client
