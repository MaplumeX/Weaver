# Weaver Internal SDK (Python)

Internal-only Python client for Weaver (no PyPI publishing).

## Install (editable)

From repo root:

```bash
pip install -e ./sdk/python
```

## Example

```python
from weaver_sdk import WeaverClient

client = WeaverClient(base_url="http://127.0.0.1:8001")  # or env WEAVER_BASE_URL
events = client.chat_sse({"messages": [{"role": "user", "content": "hi"}]})
for ev in events:
    print(ev["type"], ev.get("data"))
```
