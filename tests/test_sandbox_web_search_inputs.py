from pydantic import ValidationError

from tools.sandbox.sandbox_web_search_tool import (
    SandboxSearchAndClickInput,
    SandboxWebSearchInput,
)


def test_sandbox_web_search_input_rejects_non_browser_engine():
    try:
        SandboxWebSearchInput(query="OpenAI", engine="tavily")
    except ValidationError:
        return
    raise AssertionError("expected tavily to be rejected as a browser engine")


def test_sandbox_search_and_click_input_rejects_non_browser_engine():
    try:
        SandboxSearchAndClickInput(query="OpenAI", result_index=1, engine="tavily")
    except ValidationError:
        return
    raise AssertionError("expected tavily to be rejected as a browser engine")
