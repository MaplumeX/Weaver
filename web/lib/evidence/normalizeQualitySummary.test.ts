import { describe, expect, it } from 'vitest'

import { normalizeQualitySummary } from './normalizeQualitySummary'

describe('normalizeQualitySummary', () => {
  it('extracts key deepsearch diagnostics from a loose dict payload', () => {
    const normalized = normalizeQualitySummary({
      query_coverage_score: 0.75,
      freshness_summary: { fresh_30_ratio: 0.5 },
      time_sensitive_query: true,
      freshness_warning: 'low_freshness_for_time_sensitive_query',
      tokens_used: 123,
      elapsed_seconds: 4.2,
      budget_stop_reason: 'max_tokens',
    })

    expect(normalized.queryCoverageScore).toBeCloseTo(0.75)
    expect(normalized.freshnessRatio30d).toBeCloseTo(0.5)
    expect(normalized.timeSensitive).toBe(true)
    expect(normalized.freshnessWarning).toBe('low_freshness_for_time_sensitive_query')
    expect(normalized.tokensUsed).toBe(123)
    expect(normalized.elapsedSeconds).toBeCloseTo(4.2)
    expect(normalized.budgetStopReason).toBe('max_tokens')
  })

  it('parses numeric strings and ignores invalid fields', () => {
    const normalized = normalizeQualitySummary({
      query_coverage_score: '0.66',
      freshness_summary: { fresh_30_ratio: 'nope' },
      elapsed_seconds: '5',
      tokens_used: '42',
    })

    expect(normalized.queryCoverageScore).toBeCloseTo(0.66)
    expect(normalized.freshnessRatio30d).toBeUndefined()
    expect(normalized.elapsedSeconds).toBe(5)
    expect(normalized.tokensUsed).toBe(42)
  })

  it('returns empty object for non-object inputs', () => {
    expect(normalizeQualitySummary(null)).toEqual({})
    expect(normalizeQualitySummary('nope')).toEqual({})
  })
})

