from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier


def test_claim_without_matching_evidence_is_unsupported():
    verifier = ClaimVerifier()
    report = "2024年该公司营收增长了20%，并在海外市场创下历史新高。"
    scraped_content = [
        {
            "query": "company update",
            "results": [
                {
                    "url": "https://example.com/product",
                    "summary": "The company launched a new product line for developers.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.UNSUPPORTED


def test_claim_with_conflicting_evidence_is_contradicted():
    verifier = ClaimVerifier()
    report = "The company's revenue increased in 2024 according to the annual report."
    scraped_content = [
        {
            "query": "revenue trend",
            "results": [
                {
                    "url": "https://example.com/earnings?utm_source=test",
                    "summary": "The company's revenue did not increase in 2024 and decreased by 5%.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED
    assert checks[0].evidence_urls == ["https://example.com/earnings"]


def test_claim_with_matching_passage_attaches_passage_level_evidence():
    verifier = ClaimVerifier()
    report = "The company's revenue increased in 2024 according to the annual report."
    scraped_content = []
    passages = [
        {
            "url": "https://example.com/earnings?utm_source=test",
            "text": "In 2024, the company's revenue increased by 5% year over year.",
            "snippet_hash": "passage_123",
            "quote": "In 2024, the company's revenue increased by 5% year over year.",
            "heading_path": ["Results"],
        }
    ]

    checks = verifier.verify_report(report, scraped_content, passages=passages)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.VERIFIED
    assert checks[0].evidence_urls == ["https://example.com/earnings"]
    assert checks[0].evidence_passages
    assert checks[0].evidence_passages[0]["snippet_hash"] == "passage_123"


def test_claim_without_explicit_signal_markers_still_gets_checked():
    verifier = ClaimVerifier()
    report = "NVIDIA is not the market leader in AI chips across cloud training workloads."
    scraped_content = [
        {
            "query": "ai chip market leader",
            "results": [
                {
                    "url": "https://example.com/market",
                    "summary": "NVIDIA is the market leader in AI chips across cloud training workloads.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED


def test_negation_detection_ignores_words_that_only_contain_not_as_substring():
    verifier = ClaimVerifier()
    report = "Notably, the company revenue increased in 2024 according to the annual report."
    scraped_content = [
        {
            "query": "annual report",
            "results": [
                {
                    "url": "https://example.com/report",
                    "summary": "The company revenue increased in 2024 according to the annual report.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.VERIFIED
