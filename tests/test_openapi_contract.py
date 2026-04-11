from main import app


def _resolve_schema_ref(spec: dict, schema: dict) -> dict:
    ref = (schema or {}).get("$ref")
    if not ref or not isinstance(ref, str):
        return schema or {}

    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        return schema or {}

    name = ref[len(prefix) :]
    components = spec.get("components", {}) or {}
    schemas = components.get("schemas", {}) or {}
    return schemas.get(name, {}) or {}


def test_openapi_has_key_paths_and_distinct_resume_schemas():
    spec = app.openapi()
    assert isinstance(spec, dict)

    paths = spec.get("paths", {}) or {}
    assert "/api/interrupt/resume" in paths
    assert "/api/sessions/{thread_id}/resume" in paths
    assert "/api/agents" in paths
    assert "/api/sessions" in paths
    assert "/api/sessions/{thread_id}/comments" in paths
    assert "/api/sessions/{thread_id}/versions" in paths
    assert "/api/sessions/{thread_id}/evidence" in paths
    assert "/api/knowledge/files" in paths
    assert "/api/knowledge/files/{file_id}" in paths
    assert "/api/knowledge/files/{file_id}/reindex" in paths
    assert "/api/knowledge/files/{file_id}/download" in paths
    assert "/api/chat/sse" in paths
    assert "/api/runs/{thread_id}" in paths

    schemas = (spec.get("components", {}) or {}).get("schemas", {}) or {}
    assert "GraphInterruptResumeRequest" in schemas
    assert "SessionResumeRequest" in schemas

    agents_get = (paths.get("/api/agents", {}) or {}).get("get", {}) or {}
    agents_schema = (
        (agents_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert agents_schema, "/api/agents 200 schema should not be empty (response_model missing?)"
    agents_resolved = _resolve_schema_ref(spec, agents_schema)
    agents_props = agents_resolved.get("properties", {}) or {}
    assert "agents" in agents_props
    assert agents_props["agents"].get("type") == "array"

    sessions_get = (paths.get("/api/sessions", {}) or {}).get("get", {}) or {}
    sessions_schema = (
        (sessions_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert sessions_schema, "/api/sessions 200 schema should not be empty (response_model missing?)"
    sessions_resolved = _resolve_schema_ref(spec, sessions_schema)
    sessions_props = sessions_resolved.get("properties", {}) or {}
    assert sessions_props.get("count", {}).get("type") == "integer"
    assert sessions_props.get("sessions", {}).get("type") == "array"

    comments_get = (paths.get("/api/sessions/{thread_id}/comments", {}) or {}).get("get", {}) or {}
    comments_schema = (
        (comments_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert (
        comments_schema
    ), "/api/sessions/{thread_id}/comments 200 schema should not be empty (response_model missing?)"
    comments_resolved = _resolve_schema_ref(spec, comments_schema)
    comments_props = comments_resolved.get("properties", {}) or {}
    assert comments_props.get("count", {}).get("type") == "integer"
    assert comments_props.get("comments", {}).get("type") == "array"

    versions_get = (paths.get("/api/sessions/{thread_id}/versions", {}) or {}).get("get", {}) or {}
    versions_schema = (
        (versions_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert (
        versions_schema
    ), "/api/sessions/{thread_id}/versions 200 schema should not be empty (response_model missing?)"
    versions_resolved = _resolve_schema_ref(spec, versions_schema)
    versions_props = versions_resolved.get("properties", {}) or {}
    assert versions_props.get("count", {}).get("type") == "integer"
    assert versions_props.get("versions", {}).get("type") == "array"

    evidence_get = (
        (paths.get("/api/sessions/{thread_id}/evidence", {}) or {}).get("get", {}) or {}
    )
    evidence_schema = (
        (evidence_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert (
        evidence_schema
    ), "/api/sessions/{thread_id}/evidence 200 schema should not be empty (response_model missing?)"
    evidence_resolved = _resolve_schema_ref(spec, evidence_schema)
    evidence_props = evidence_resolved.get("properties", {}) or {}
    assert evidence_props.get("sources", {}).get("type") == "array"
    assert "claims" not in evidence_props
    assert evidence_props.get("fetched_pages", {}).get("type") == "array"
    assert evidence_props.get("passages", {}).get("type") == "array"

    passage_item = schemas.get("EvidencePassageItem", {}) or {}
    passage_item_props = passage_item.get("properties", {}) or {}
    assert "heading" in passage_item_props
    assert "heading_path" in passage_item_props
    assert "page_title" in passage_item_props
    assert "retrieved_at" in passage_item_props
    assert "method" in passage_item_props
    assert "quote" in passage_item_props
    assert "snippet_hash" in passage_item_props

    runs_get = (paths.get("/api/runs/{thread_id}", {}) or {}).get("get", {}) or {}
    runs_schema = (
        (runs_get.get("responses", {}) or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        or {}
    )
    assert runs_schema, "/api/runs/{thread_id} 200 schema should not be empty (response_model missing?)"
    runs_resolved = _resolve_schema_ref(spec, runs_schema)
    runs_props = runs_resolved.get("properties", {}) or {}
    assert "evidence_summary" in runs_props
    evidence_summary_schema = runs_props.get("evidence_summary", {}) or {}
    evidence_summary_resolved = _resolve_schema_ref(spec, evidence_summary_schema)
    evidence_summary_props = evidence_summary_resolved.get("properties", {}) or {}
    assert evidence_summary_props.get("sources_count", {}).get("type") == "integer"
    assert evidence_summary_props.get("unsupported_claims_count", {}).get("type") == "integer"
