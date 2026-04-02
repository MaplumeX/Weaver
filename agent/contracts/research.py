"""
Stable research-related contracts for external consumers.
"""

from agent.contracts.claim_verifier import ClaimStatus, ClaimVerifier
from agent.contracts.evidence_extractor import extract_message_sources
from agent.contracts.result_aggregator import ResultAggregator

__all__ = [
    "ClaimStatus",
    "ClaimVerifier",
    "ResultAggregator",
    "extract_message_sources",
]
