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
    checks = verifier.verify_report(
        report,
        scraped_content=[],
        passages=[
            {
                "id": "passage_conflict_1",
                "url": "https://example.com/earnings?utm_source=test",
                "text": "The company's revenue did not increase in 2024 and decreased by 5%.",
                "quote": "The company's revenue did not increase in 2024 and decreased by 5%.",
                "heading_path": ["Results"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED
    assert checks[0].evidence_urls == ["https://example.com/earnings"]


def test_claim_with_matching_passage_attaches_passage_level_evidence():
    verifier = ClaimVerifier()
    report = "The company's revenue increased in 2024 according to the annual report."
    scraped_content = []
    passages = [
        {
            "id": "passage_123",
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
    checks = verifier.verify_report(
        report,
        scraped_content=[],
        passages=[
            {
                "id": "passage_market_1",
                "url": "https://example.com/market",
                "text": "NVIDIA is the market leader in AI chips across cloud training workloads.",
                "quote": "NVIDIA is the market leader in AI chips across cloud training workloads.",
                "heading_path": ["Market share"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED


def test_negation_detection_ignores_words_that_only_contain_not_as_substring():
    verifier = ClaimVerifier()
    report = "Notably, the company revenue increased in 2024 according to the annual report."
    checks = verifier.verify_report(
        report,
        scraped_content=[],
        passages=[
            {
                "id": "passage_report_1",
                "url": "https://example.com/report",
                "text": "The company revenue increased in 2024 according to the annual report.",
                "quote": "The company revenue increased in 2024 according to the annual report.",
                "heading_path": ["Annual report"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.VERIFIED


def test_claim_with_chinese_semantic_rewrite_passage_is_verified():
    verifier = ClaimVerifier()
    report = "公司2024年营收显著增长，主要由云业务带动。"
    checks = verifier.verify_report(
        report,
        scraped_content=[],
        passages=[
            {
                "id": "passage_cn_1",
                "url": "https://example.com/cn-report",
                "text": "2024年该公司云业务带动收入上升，并推动整体营收增长。",
                "quote": "2024年该公司云业务带动收入上升，并推动整体营收增长。",
                "heading_path": ["业绩回顾"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.VERIFIED
    assert checks[0].evidence_urls == ["https://example.com/cn-report"]


def test_snippet_only_scraped_content_is_not_authoritative_evidence():
    verifier = ClaimVerifier()
    report = "The company revenue increased in 2024 according to the annual report."
    checks = verifier.verify_report(
        report,
        scraped_content=[
            {
                "query": "annual report",
                "results": [
                    {
                        "url": "https://example.com/report",
                        "summary": "The company revenue increased in 2024 according to the annual report.",
                    }
                ],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.UNSUPPORTED


def test_claim_with_conflicting_percentage_is_contradicted():
    verifier = ClaimVerifier()
    checks = verifier.verify_report(
        "Revenue increased by 20% in 2024.",
        scraped_content=[],
        passages=[
            {
                "id": "passage_pct_1",
                "url": "https://example.com/pct",
                "text": "Revenue increased by 5% in 2024.",
                "quote": "Revenue increased by 5% in 2024.",
                "heading_path": ["Financials"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED


def test_claim_with_conflicting_date_is_contradicted():
    verifier = ClaimVerifier()
    checks = verifier.verify_report(
        "The product launched in March 2024.",
        scraped_content=[],
        passages=[
            {
                "id": "passage_date_1",
                "url": "https://example.com/date",
                "text": "The product launched in April 2024.",
                "quote": "The product launched in April 2024.",
                "heading_path": ["Timeline"],
            }
        ],
    )

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED
