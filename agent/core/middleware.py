from langchain_core.messages import BaseMessage, ToolMessage

from common.config import settings


def maybe_strip_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Optionally remove ToolMessage from history to save tokens.
    """
    if not settings.strip_tool_messages:
        return messages
    return [m for m in messages if not isinstance(m, ToolMessage)]
