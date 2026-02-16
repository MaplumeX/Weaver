import json


def test_build_openapi_spec_contains_openapi_version_and_chat_path():
    from scripts.export_openapi import build_openapi_spec

    spec = build_openapi_spec()
    assert isinstance(spec, dict)
    assert "openapi" in spec
    assert "/api/chat" in (spec.get("paths") or {})
    json.dumps(spec)

