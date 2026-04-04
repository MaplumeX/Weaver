from common.session_manager import SessionManager


def test_session_manager_drops_legacy_claims_but_preserves_passages():
    manager = SessionManager(checkpointer=object())

    state = {
        "deep_research_artifacts": {
            "claims": [
                {
                    "claim": "Revenue increased in 2024.",
                    "status": "verified",
                    "evidence_urls": ["https://example.com/earnings"],
                    "evidence_passages": [
                        {
                            "url": "https://example.com/earnings",
                            "snippet_hash": "passage_123",
                            "quote": "In 2024, the company's revenue increased by 5% year over year.",
                            "heading_path": ["Results"],
                        }
                    ],
                }
            ],
            "passages": [
                {
                    "url": "https://example.com/earnings",
                    "text": "In 2024, the company's revenue increased by 5% year over year.",
                    "snippet_hash": "passage_123",
                    "quote": "In 2024, the company's revenue increased by 5% year over year.",
                    "heading_path": ["Results"],
                }
            ]
        },
    }

    artifacts = manager._extract_deep_research_artifacts(state)
    assert "claims" not in artifacts
    passages = artifacts.get("passages")
    assert isinstance(passages, list)
    assert passages, "expected passages to be preserved"

    passage = (passages or [None])[0] or {}
    assert passage.get("snippet_hash") == "passage_123"
    assert passage.get("heading_path") == ["Results"]
    assert passage.get("url") == "https://example.com/earnings"
