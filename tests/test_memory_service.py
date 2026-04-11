from common.memory_service import MemoryExtractionResult, MemoryService, ModelBackedMemoryExtractor


class FakeMemoryStore:
    def __init__(self, entries=None):
        self.entries = list(entries or [])
        self.events = []
        self.touched_ids = []

    def upsert_entry(self, **kwargs):
        entry = {
            "id": f"mem_{len(self.entries) + 1}",
            "user_id": kwargs["user_id"],
            "memory_type": kwargs["memory_type"],
            "content": kwargs["content"],
            "normalized_key": kwargs["normalized_key"],
            "source_kind": kwargs["source_kind"],
            "source_thread_id": kwargs.get("source_thread_id", ""),
            "source_message": kwargs.get("source_message", ""),
            "importance": kwargs.get("importance", 50),
            "status": "active",
            "retrieval_count": 0,
            "last_retrieved_at": None,
            "invalidated_at": None,
            "invalidation_reason": "",
            "metadata": kwargs.get("metadata", {}),
            "created_at": "2026-04-07T00:00:00Z",
            "updated_at": "2026-04-07T00:00:00Z",
        }
        self.entries.append(entry)
        return entry

    def record_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs

    def list_entries(self, *, user_id: str, limit: int = 50, status=None, memory_type=None):
        items = [entry for entry in self.entries if entry["user_id"] == user_id]
        if status:
            items = [entry for entry in items if entry["status"] == status]
        if memory_type:
            items = [entry for entry in items if entry["memory_type"] == memory_type]
        return items[:limit]

    def touch_entries(self, *, entry_ids):
        self.touched_ids = list(entry_ids)


class FakeExtractor:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []
        self.model_name = "gpt-test"
        self.extractor_version = "memory-explicit-v1"

    def extract(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeStructuredModel:
    def __init__(self, *, response=None, error: Exception | None = None):
        self.response = response
        self.error = error

    def invoke(self, messages, config=None):
        if self.error is not None:
            raise self.error
        return self.response


class FakeLLM:
    def __init__(self, responses_by_method):
        self.responses_by_method = dict(responses_by_method)
        self.methods = []

    def with_structured_output(self, schema, method=None):
        self.methods.append(method)
        response = self.responses_by_method.get(method)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise RuntimeError(f"missing response for method={method}")
        return FakeStructuredModel(response=response)


def test_ingest_user_message_requires_explicit_memory_intent_and_extractor_success():
    store = FakeMemoryStore()
    extractor = FakeExtractor(
        response=MemoryExtractionResult(
            should_store=True,
            memory_type="preference",
            fact="回答时保持简洁",
            normalized_key_hint="简洁回答",
            importance=91,
            reasoning="Stable response preference explicitly requested by the user.",
            stability="high",
        )
    )
    service = MemoryService(store=store, extractor=extractor)

    created = service.ingest_user_message(
        user_id="alice",
        text="请记住我喜欢简洁回答",
        source_kind="chat",
        thread_id="thread-1",
    )

    assert len(created) == 1
    assert created[0]["memory_type"] == "preference"
    assert created[0]["content"] == "用户偏好: 回答时保持简洁"
    assert created[0]["source_thread_id"] == "thread-1"
    assert created[0]["metadata"]["ingestion_method"] == "explicit_rule_llm"
    assert created[0]["metadata"]["extractor_model"] == "gpt-test"
    assert created[0]["metadata"]["dedupe_basis"] == "简洁回答"
    assert extractor.calls == [
        {
            "source_message": "请记住我喜欢简洁回答",
            "intent_fact": "我喜欢简洁回答",
            "forced_type": None,
        }
    ]
    assert store.events[-1]["event_type"] == "ingested"

    assert service.ingest_user_message(
        user_id="alice",
        text="我喜欢简洁回答",
        source_kind="chat",
    ) == []


def test_ingest_user_message_rejects_ephemeral_task_state_before_extractor():
    store = FakeMemoryStore()
    extractor = FakeExtractor(
        response=MemoryExtractionResult(
            should_store=True,
            memory_type="user_fact",
            fact="当前任务先改 main.py",
            reasoning="This should never be used because explicit guard should reject it first.",
            stability="high",
        )
    )
    service = MemoryService(store=store, extractor=extractor)

    created = service.ingest_user_message(
        user_id="alice",
        text="记住这次任务先改 main.py",
        source_kind="chat",
    )

    assert created == []
    assert store.entries == []
    assert extractor.calls == []


def test_ingest_user_message_skips_when_extractor_is_not_configured():
    store = FakeMemoryStore()
    service = MemoryService(store=store)

    created = service.ingest_user_message(
        user_id="alice",
        text="请记住我主要用 FastAPI",
        source_kind="chat",
        thread_id="thread-1",
    )

    assert created == []
    assert store.entries == []
    assert store.events[-1]["event_type"] == "ingest_skipped"


def test_ingest_user_message_skips_when_extractor_fails():
    store = FakeMemoryStore()
    extractor = FakeExtractor(error=RuntimeError("gateway timeout"))
    service = MemoryService(store=store, extractor=extractor)

    created = service.ingest_user_message(
        user_id="alice",
        text="请记住我主要用 FastAPI",
        source_kind="chat",
        thread_id="thread-1",
    )

    assert created == []
    assert store.entries == []
    assert store.events[-1]["event_type"] == "extract_failed"


def test_ingest_user_message_rejects_low_stability_extraction():
    store = FakeMemoryStore()
    extractor = FakeExtractor(
        response=MemoryExtractionResult(
            should_store=True,
            memory_type="preference",
            fact="用中文回答",
            reasoning="Maybe stable but not certain.",
            stability="medium",
        )
    )
    service = MemoryService(store=store, extractor=extractor)

    created = service.ingest_user_message(
        user_id="alice",
        text="请记住以后请用中文回答",
        source_kind="chat",
    )

    assert created == []
    assert store.entries == []
    assert store.events[-1]["event_type"] == "extract_rejected"
    assert store.events[-1]["reason"] == "memory extractor stability was medium"


def test_model_backed_memory_extractor_falls_back_to_next_method():
    llm = FakeLLM(
        {
            None: RuntimeError("default structured output failed"),
            "json_schema": {
                "should_store": True,
                "memory_type": "user_fact",
                "fact": "我主要用 FastAPI",
                "normalized_key_hint": "主要用 FastAPI",
                "importance": 82,
                "reasoning": "The user explicitly asked to remember a stable tooling fact.",
                "stability": "high",
            },
        }
    )
    extractor = ModelBackedMemoryExtractor(
        model=llm,
        model_name="gpt-test",
        methods=(None, "json_schema"),
    )

    result = extractor.extract(
        source_message="请记住我主要用 FastAPI",
        intent_fact="我主要用 FastAPI",
        forced_type=None,
    )

    assert isinstance(result, MemoryExtractionResult)
    assert result.should_store is True
    assert result.fact == "我主要用 FastAPI"
    assert llm.methods == [None, "json_schema"]


def test_debug_context_returns_structured_matches_and_touches_entries():
    store = FakeMemoryStore(
        entries=[
            {
                "id": "mem_1",
                "user_id": "alice",
                "memory_type": "preference",
                "content": "用户偏好: 用中文回答",
                "source_kind": "chat",
                "source_thread_id": "thread-1",
                "source_message": "请记住以后请用中文回答",
                "importance": 90,
                "status": "active",
                "retrieval_count": 0,
                "last_retrieved_at": None,
                "invalidated_at": None,
                "invalidation_reason": "",
                "metadata": {},
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            },
            {
                "id": "mem_2",
                "user_id": "alice",
                "memory_type": "user_fact",
                "content": "用户信息: 我主要用 FastAPI",
                "source_kind": "chat",
                "source_thread_id": "thread-2",
                "source_message": "请记住我主要用 FastAPI",
                "importance": 80,
                "status": "active",
                "retrieval_count": 0,
                "last_retrieved_at": None,
                "invalidated_at": None,
                "invalidation_reason": "",
                "metadata": {},
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            },
        ]
    )
    service = MemoryService(store=store)

    context = service.debug_context(user_id="alice", query="用中文回答", limit=2)

    assert context["stored"] == ["用户偏好: 用中文回答", "用户信息: 我主要用 FastAPI"]
    assert context["relevant"][0] == "用户偏好: 用中文回答"
    assert "matched query tokens" in context["relevant_entries"][0]["reason"]
    assert set(store.touched_ids) == {"mem_1", "mem_2"}
