export type NormalizedQualitySummary = {
  queryCoverageScore?: number
  freshnessRatio30d?: number
  timeSensitive?: boolean
  freshnessWarning?: string
  budgetStopReason?: string
  tokensUsed?: number
  elapsedSeconds?: number
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') {
    const lowered = value.trim().toLowerCase()
    if (lowered === 'true') return true
    if (lowered === 'false') return false
  }
  return undefined
}

function asString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

export function normalizeQualitySummary(raw: unknown): NormalizedQualitySummary {
  if (!raw || typeof raw !== 'object') return {}

  const obj = raw as Record<string, unknown>
  const freshnessSummary = obj.freshness_summary
  const freshnessRatio30d =
    freshnessSummary && typeof freshnessSummary === 'object'
      ? asNumber((freshnessSummary as any).fresh_30_ratio)
      : undefined

  const queryCoverageScore = asNumber(obj.query_coverage_score ?? (obj as any).queryCoverageScore)

  return {
    queryCoverageScore,
    freshnessRatio30d,
    timeSensitive: asBoolean(obj.time_sensitive_query),
    freshnessWarning: asString(obj.freshness_warning),
    budgetStopReason: asString(obj.budget_stop_reason),
    tokensUsed: asNumber(obj.tokens_used),
    elapsedSeconds: asNumber(obj.elapsed_seconds),
  }
}

