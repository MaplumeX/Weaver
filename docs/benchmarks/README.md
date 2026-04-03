# Deep Research Benchmarks

## Files

- `eval/benchmarks/sample_tasks.jsonl`: sample benchmark inputs
- `eval/golden_queries.json`: lightweight golden baseline cases
- `scripts/benchmark_deep_research.py`: regression smoke runner

## Run Smoke Benchmark

```bash
python scripts/benchmark_deep_research.py \
  --max-cases 3 \
  --mode auto \
  --min-query-coverage 0.6 \
  --min-freshness-ratio 0.4 \
  --output /tmp/bench.json
```

## Run Execute Benchmark (Real Deep Research)

This mode **actually runs** deep research for each case via `POST /api/research/sse` and records
evidence metrics (citation coverage, freshness ratio, query coverage, claim verifier counts).

Prereqs:
- Configure `.env` with real API keys (LLM + at least one search provider).
- For in-process runs (default `--base-url asgi`), you do **not** need to start the backend server.

```bash
.venv/bin/python scripts/benchmark_deep_research.py \
  --max-cases 3 \
  --mode auto \
  --execute \
  --timeout-s 240 \
  --output /tmp/bench-exec.json
```

Optional: call a running backend instead of in-process ASGI:

```bash
.venv/bin/python scripts/benchmark_deep_research.py \
  --max-cases 3 \
  --mode auto \
  --execute \
  --base-url http://127.0.0.1:8001 \
  --output /tmp/bench-exec-remote.json
```

## CLI Options

- `--max-cases`: number of benchmark cases to include
- `--mode`: `auto|tree|linear`
- `--min-query-coverage`: base query-coverage target (0-1) used for case policy
- `--min-freshness-ratio`: base freshness ratio target (0-1) used for case policy
- `--output`: output JSON report path
- `--bench-file`: custom JSONL benchmark file path
- `--execute`: run real deep research and collect metrics
- `--base-url`: `asgi` (default) or `http://...` backend base URL
- `--model`: override backend model for execution mode (defaults to `PRIMARY_MODEL`)
- `--timeout-s`: per-case wall-clock timeout for execution mode

## JSONL Schema

Each line must be one JSON object:

```json
{
  "id": "case_001",
  "query": "Latest AI chip market share in 2025",
  "constraints": {"freshness_days": 30},
  "expected_fields": ["market_share", "top_vendors"],
  "metadata": {"domain": "financial"}
}
```

Required fields:
- `query` (string)
- `constraints` (object)
- `expected_fields` (non-empty string array)

## Report Output

The runner writes a JSON report containing:
- run metadata (`mode`, `max_cases`, timestamp)
- selected cases (`quality_targets` per case)
- summary metrics:
  - `time_sensitive_cases`
  - average query coverage/freshness targets
  - default quality gate values used in this run

Use this as a reproducible smoke signal in CI/nightly workflows.

## Verification Revision Loop Metrics

When `--execute` is enabled, the benchmark report also aggregates the latest `quality_update`
payload emitted by Deep Research and exposes these revision-loop metrics:

- `avg_verification_precision`: average `grounded_claims / total_checked_claims`
- `avg_unresolved_issue_count`: average count of open or accepted revision issues
- `avg_revision_convergence`: average `resolved_issues / total_revision_issues`

These metrics are complementary to `avg_citation_coverage`, `avg_query_coverage_score` and
`unsupported_claims_total`. A run should be treated as healthy only when evidence quality is
acceptable and revision-loop metrics show that verification is converging instead of accumulating
open issues.
