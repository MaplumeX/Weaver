from agent.contracts.source_registry import SourceRegistry


def test_source_registry_canonicalizes_tracking_params_and_fragments():
    registry = SourceRegistry()

    url_a = "HTTPS://Example.com/path/?utm_source=newsletter&a=1#section"
    url_b = "https://example.com/path?a=1"

    canonical_a = registry.canonicalize_url(url_a)
    canonical_b = registry.canonicalize_url(url_b)

    assert canonical_a == canonical_b
    assert canonical_a == "https://example.com/path?a=1"


def test_source_registry_generates_stable_source_id_for_equivalent_urls():
    registry = SourceRegistry()

    source_a = registry.register("https://example.com/a/?utm_medium=email")
    source_b = registry.register("https://example.com/a")

    assert source_a is not None
    assert source_b is not None
    assert source_a.source_id == source_b.source_id
    assert source_a.canonical_url == source_b.canonical_url
