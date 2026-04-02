from common.session_manager import SessionManager


def test_session_manager_preserves_claims_with_passage_level_evidence():
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
    claims = artifacts.get("claims")
    assert isinstance(claims, list)
    assert claims, "expected canonical claims to be preserved"
    claim = (claims or [None])[0] or {}
    assert isinstance(claim.get("evidence_urls"), list)
    assert isinstance(claim.get("evidence_passages"), list)
    assert claim.get("evidence_passages"), "expected evidence_passages to be preserved"

    passage = (claim.get("evidence_passages") or [None])[0] or {}
    assert passage.get("snippet_hash") == "passage_123"
    assert passage.get("heading_path") == ["Results"]
    assert passage.get("url") == "https://example.com/earnings"
