# Deep Research Rollout Guide

## Scope

This guide covers rollout of Deep Research VNext capabilities:
- multi-search orchestration
- freshness ranking
- domain-aware provider profiles
- citation gate and quality loop
- multi-agent runtime orchestration
- budget guards and session cache
- benchmark smoke/regression

## Engine Switch

Deep Research now exposes two runtime engines behind the same `deepsearch_node` entry:

- `DEEPSEARCH_ENGINE=legacy`
  - Keeps the existing tree/linear runner path.
  - Recommended as the safe default during initial rollout.
- `DEEPSEARCH_ENGINE=multi_agent`
  - Enables coordinator/planner/researcher/verifier/reporter orchestration.
  - Emits additional task/agent/artifact/decision progress events.

Request-level overrides can be injected through `configurable.deepsearch_engine` when calling the graph directly.

## Rollout Stages

### Stage 1: Local Validation

1. Run backend checks:
   - `make lint`
   - `make test`
   - `uv run pytest tests/test_deepsearch_mode_selection.py tests/test_deepsearch_multi_agent_runtime.py tests/test_chat_sse_multi_agent_events.py -q`
2. Run frontend checks:
   - `pnpm -C web lint`
   - `pnpm -C web build`
   - `npm --prefix web test -- --test-reporter=spec`
3. Verify API contract drift guard:
   - `bash scripts/check_openapi_ts_types.sh`
4. Run benchmark smoke:
   - `python scripts/benchmark_deep_research.py --max-cases 3 --mode auto --output /tmp/bench.json`

Exit criteria:
- checks pass
- benchmark report generated
 - OpenAPI contract drift guard clean (no diff in `web/lib/api-types.ts`)

### Stage 2: Pre-Prod

1. Start with conservative settings:
   - `DEEPSEARCH_ENGINE=legacy`
   - `DEEPSEARCH_MODE=linear`
   - `SEARCH_STRATEGY=fallback`
   - `CITATION_GATE_MIN_COVERAGE=0.5`
2. Observe:
   - multi-agent failure count
   - citation gate revise rate
   - average deepsearch latency
   - cache hit rate trends
3. Increase confidence:
   - enable `DEEPSEARCH_ENGINE=multi_agent` for canary traffic
   - enable `DEEPSEARCH_MODE=auto`
   - keep fallback search strategy unless provider health is stable

Exit criteria:
- no sustained error-rate regression
- acceptable latency and revise-loop behavior

### Stage 3: Production

1. Enable desired defaults:
   - `DEEPSEARCH_ENGINE=multi_agent` only after canary stability is confirmed
   - `DEEPSEARCH_MODE=auto`
   - `SEARCH_ENABLE_FRESHNESS_RANKING=true`
2. Keep rollback toggles prepared (below).
3. Schedule nightly benchmark workflow.

## Rollback Switches

- Deep mode rollback:
  - `DEEPSEARCH_ENGINE=legacy`
  - `DEEPSEARCH_MODE=linear`
  - `TREE_EXPLORATION_ENABLED=false`
- Search reliability rollback:
  - `SEARCH_STRATEGY=fallback`
- Citation gate rollback:
  - lower `CITATION_GATE_MIN_COVERAGE`
- Cache rollback:
  - reduce `SEARCH_CACHE_TTL_SECONDS`
  - reduce `SEARCH_CACHE_MAX_SIZE`
- Chat streaming rollback (frontend):
  - `NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=legacy` (see `docs/chat-streaming.md`)

## Troubleshooting

### Symptom: repeated revise loop

- Check `citation_coverage` in eval dimensions.
- Verify report output includes explicit citations.
- Temporarily relax `CITATION_GATE_MIN_COVERAGE`.

### Symptom: deepsearch too slow

- Keep `DEEPSEARCH_ENGINE=legacy` while investigating multi-agent overhead.
- Set `DEEPSEARCH_MAX_SECONDS` and `DEEPSEARCH_MAX_TOKENS`.
- Reduce `DEEPSEARCH_QUERY_NUM` and `DEEPSEARCH_RESULTS_PER_QUERY`.
- Disable tree default in early rollout.

### Symptom: multi-agent runtime fails explicitly

- Inspect backend logs for `multi-agent runtime failed`.
- Watch for `research_decision` and `research_agent_*` events in `/api/events/{thread_id}`.
- Re-run with `DEEPSEARCH_ENGINE=multi_agent` and `LOG_LEVEL=DEBUG` to capture the failing phase.

### Symptom: stale or repetitive sources

- Enable freshness ranking.
- Reduce cache TTL.
- Verify provider profile mapping for the domain.

## Operational Checklist

- [ ] CI green (backend + frontend)
- [ ] benchmark smoke report generated
- [ ] rollback env vars documented in deployment config
- [ ] citation gate threshold reviewed by product/ops
- [ ] nightly benchmark workflow enabled
- [ ] multi-agent failure reasons sampled from canary logs


### Stage 4: Quality Diagnostics (New)

DeepSearch now emits additional diagnostics in `quality_summary` and `deepsearch_artifacts`:
- `query_coverage_score` + `query_dimensions_covered/missing`
- `freshness_summary` (7d/30d/180d buckets + known/unknown date counts)
- `freshness_warning` for time-sensitive prompts when fresh-source ratio is too low
- `task_queue` / `artifact_store` / `runtime_state` snapshots when `DEEPSEARCH_ENGINE=multi_agent`
- configurable thresholds:
  - `DEEPSEARCH_FRESHNESS_WARNING_MIN_KNOWN` (default: `3`)
  - `DEEPSEARCH_FRESHNESS_WARNING_MIN_RATIO` (default: `0.4`)
  - `DEEPSEARCH_EVENT_RESULTS_LIMIT` (default: `5`, range: `1-20`)

Operational use:
- Track low query coverage as an early signal of shallow planning.
- For time-sensitive asks (latest/recent/current), treat `freshness_warning` as a retry trigger.
- Prefer adding official docs + recent updates queries before increasing `deepsearch_max_epochs`.
- For multi-agent debugging, inspect `deepsearch_agent_runs`, `deepsearch_task_queue`, and `deepsearch_artifact_store`.

Reference directions (latest deep-research patterns):
- OpenAI: [Introducing deep research](https://openai.com/index/introducing-deep-research/)
- Google Gemini API changelog (Deep Research + thought summaries): [Developer changelog](https://ai.google.dev/changelog)
- Anthropic: [Think tool](https://www.anthropic.com/engineering/claude-think-tool)
- Open deep-research implementation reference: [HKUDS/DeepResearchAgent](https://github.com/HKUDS/DeepResearchAgent)
