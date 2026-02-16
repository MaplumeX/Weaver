def test_settings_exposes_reader_and_fetcher_fields_with_defaults(monkeypatch):
    # Avoid relying on a local `.env` file or a developer's shell environment.
    for key in (
        "READER_FALLBACK_MODE",
        "READER_PUBLIC_BASE",
        "READER_SELF_HOSTED_BASE",
        "RESEARCH_FETCH_TIMEOUT_S",
        "RESEARCH_FETCH_MAX_BYTES",
        "RESEARCH_FETCH_CONCURRENCY",
        "RESEARCH_FETCH_CONCURRENCY_PER_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)

    from common.config import Settings

    s = Settings(_env_file=None)

    assert s.reader_fallback_mode == "both"
    assert s.reader_public_base == "https://r.jina.ai"
    assert s.reader_self_hosted_base == ""
    assert s.research_fetch_timeout_s == 25.0
    assert s.research_fetch_max_bytes == 2_000_000
    assert s.research_fetch_concurrency == 6
    assert s.research_fetch_concurrency_per_domain == 2
