from __future__ import annotations

from tools.browser.browser_session import browser_sessions
from tools.sandbox import sandbox_browser_sessions


def build_browser_context_hint(thread_id: str = "default") -> str | None:
    """
    Best-effort browser context summary for prompt augmentation.

    Prefers lightweight browser_session state; falls back to sandbox browser if present.
    """
    session = browser_sessions.get(thread_id)
    page = getattr(session, "current", None)
    if not page or not page.url:
        sb = sandbox_browser_sessions.get(thread_id)
        page = getattr(sb, "current", None) if sb else None
    if not page or not getattr(page, "url", None):
        return None

    links = page.links[:5] if getattr(page, "links", None) else []
    links_text = "\n".join(
        f"- {link.get('text') or link.get('url')}" for link in links if isinstance(link, dict)
    )

    hint = [
        "Browser context (for next step reasoning):",
        f"URL: {getattr(page, 'url', 'N/A')}",
        f"Title: {getattr(page, 'title', 'N/A')}",
    ]
    if links_text:
        hint.append("Top links:")
        hint.append(links_text)
    if getattr(page, "text", ""):
        snippet = (page.text or "")[:400]
        hint.append(f"Page excerpt: {snippet}")
    return "\n".join(hint)
