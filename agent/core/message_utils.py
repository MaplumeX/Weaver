import logging
import textwrap

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.core.llm_factory import create_summary_model
from common.config import settings

logger = logging.getLogger(__name__)

# Use shared factory
_chat_model_summary = create_summary_model


def _messages_to_text(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = m.type if hasattr(m, "type") else m.__class__.__name__
        content = getattr(m, "content", "")
        if isinstance(content, list):
            # for multimodal, keep text parts only
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "\n".join(text_parts)
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _truncate_summary(content: str, *, word_limit: int) -> str:
    text = " ".join(str(content or "").split()).strip()
    if not text:
        return ""
    words = text.split(" ")
    if len(words) <= word_limit:
        return text
    return " ".join(words[:word_limit]).strip()


def summarize_history_slice(
    messages: list[BaseMessage],
    *,
    previous_summary: str = "",
) -> str:
    if not messages:
        return str(previous_summary or "").strip()

    word_limit = int(settings.summary_messages_word_limit or 200)
    llm = _chat_model_summary()
    prompt = textwrap.dedent(
        f"""You are a concise summarizer.
Update the existing rolling summary with any new critical facts, names,
numbers, decisions, constraints, and user intent.
Do NOT add new info. Respond in <= {word_limit} words.

Existing summary:
{{previous_summary}}

Conversation:
{{conversation}}
"""
    )
    convo_text = _messages_to_text(messages)
    fallback_input = "\n".join(
        part for part in [previous_summary.strip(), convo_text] if part
    ).strip()
    if not (settings.openai_api_key or settings.azure_api_key):
        return _truncate_summary(fallback_input, word_limit=word_limit)
    try:
        resp = llm.invoke(
            [
                HumanMessage(
                    content=prompt.format(
                        previous_summary=previous_summary.strip() or "(none)",
                        conversation=convo_text,
                    )
                )
            ]
        )
        content = getattr(resp, "content", "") or fallback_input
    except Exception as e:
        logger.warning(f"Summarization failed, falling back to truncation: {e}")
        content = fallback_input

    return _truncate_summary(str(content).strip(), word_limit=word_limit)


def summarize_messages(messages: list[BaseMessage]) -> SystemMessage:
    """Summarize middle conversation history into a compact system message."""
    if not messages:
        return SystemMessage(content="Conversation summary: (empty)")

    summary = summarize_history_slice(messages)
    return SystemMessage(content=f"Conversation summary:\\n{summary}")
