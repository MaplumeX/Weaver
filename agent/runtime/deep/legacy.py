"""
Legacy deep-research runtime entrypoints.
"""

from agent.runtime.deep.legacy_linear import run_deepsearch_optimized
from agent.runtime.deep.legacy_tree import run_deepsearch_tree

__all__ = ["run_deepsearch_optimized", "run_deepsearch_tree"]
