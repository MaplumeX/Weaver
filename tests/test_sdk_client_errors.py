from __future__ import annotations

import sys
from pathlib import Path

import httpx

SDK_PYTHON_ROOT = Path(__file__).resolve().parent.parent / "sdk" / "python"
sys.path.insert(0, str(SDK_PYTHON_ROOT))

from weaver_sdk.client import WeaverApiError, WeaverClient  # noqa: E402


def test_sdk_request_json_raises_with_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://test")
    client = WeaverClient(base_url="http://test", http=http)

    try:
        client.request_json("/api/health")
        assert False, "expected WeaverApiError"
    except WeaverApiError as e:
        assert e.status == 500
        assert e.body_text == "boom"

