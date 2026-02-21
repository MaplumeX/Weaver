import { apiUrl } from '@/lib/api'
import type { components } from '@/lib/api-types'

export type McpServersConfig = Record<string, unknown>

export type McpConfigResponse = {
  enabled: boolean
  servers: McpServersConfig
  loaded_tools: number
}

function mergeHeaders(headers: HeadersInit | undefined, defaults: Record<string, string>): Headers {
  const merged = new Headers(headers)
  for (const [key, value] of Object.entries(defaults)) {
    if (!merged.has(key)) merged.set(key, value)
  }
  return merged
}

function coerceShortText(input: unknown, maxChars = 400): string {
  const raw = String(input ?? '').trim()
  if (!raw) return ''
  if (raw.length <= maxChars) return raw
  return `${raw.slice(0, Math.max(0, maxChars - 1))}…`
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: mergeHeaders(init.headers, { Accept: 'application/json' }),
  })

  const bodyText = await response.text().catch(() => '')
  if (!response.ok) {
    const headerRequestId =
      response.headers.get('X-Request-ID') || response.headers.get('x-request-id') || ''

    let parsed: unknown = null
    try {
      parsed = bodyText ? (JSON.parse(bodyText) as unknown) : null
    } catch {
      parsed = null
    }

    let requestId = headerRequestId
    let messageDetail = ''

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const record = parsed as Record<string, unknown>
      if (typeof record.request_id === 'string' && record.request_id.trim()) {
        requestId = record.request_id.trim()
      }

      const errText = typeof record.error === 'string' ? record.error.trim() : ''
      const detailText = typeof record.detail === 'string' ? record.detail.trim() : ''
      messageDetail = errText || detailText

      if (errText === 'Validation Error' && Array.isArray(record.detail)) {
        const first = record.detail.find((item) => item && typeof item === 'object' && !Array.isArray(item)) as
          | Record<string, unknown>
          | undefined
        if (first) {
          const field = typeof first.field === 'string' ? first.field.trim() : ''
          const msg = typeof first.message === 'string' ? first.message.trim() : ''
          messageDetail = `${field ? `${field}: ` : ''}${msg}`.trim() || messageDetail
        }
      }
    }

    if (!messageDetail) {
      messageDetail = coerceShortText(bodyText)
    }

    const suffix = messageDetail ? `: ${coerceShortText(messageDetail)}` : ''
    const rid = requestId ? ` (request_id: ${requestId})` : ''
    throw new Error(`API request failed (${response.status})${suffix}${rid}`)
  }

  if (!bodyText) return undefined as T
  try {
    return JSON.parse(bodyText) as T
  } catch {
    return bodyText as unknown as T
  }
}

export async function getMcpConfig(): Promise<McpConfigResponse> {
  return apiFetch<McpConfigResponse>('/api/mcp/config')
}

export async function updateMcpConfig(
  payload: components['schemas']['MCPConfigPayload']
): Promise<McpConfigResponse> {
  return apiFetch<McpConfigResponse>('/api/mcp/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export type ResumeInterruptRequest = components['schemas']['GraphInterruptResumeRequest']
export type ChatResponse = {
  id: string
  content: string
  role?: string
  timestamp: string
}
export type ResumeInterruptResponse =
  | ChatResponse
  | { status: 'interrupted'; interrupts: unknown[] }

export async function resumeInterrupt(payload: ResumeInterruptRequest): Promise<ResumeInterruptResponse> {
  return apiFetch<ResumeInterruptResponse>('/api/interrupt/resume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export type SessionEvidenceResponse = components['schemas']['EvidenceResponse']
export type RunMetricsResponse = components['schemas']['RunMetricsResponse']

export async function getSessionEvidence(threadId: string): Promise<SessionEvidenceResponse> {
  const safeId = encodeURIComponent(String(threadId))
  return apiFetch<SessionEvidenceResponse>(`/api/sessions/${safeId}/evidence`)
}

export async function getRunMetrics(threadId: string): Promise<RunMetricsResponse> {
  const safeId = encodeURIComponent(String(threadId))
  return apiFetch<RunMetricsResponse>(`/api/runs/${safeId}`)
}

export type SearchProviderCircuit = components['schemas']['ProviderCircuitSnapshot']
export type SearchProviderSnapshot = components['schemas']['SearchProviderSnapshot']
export type SearchProvidersResponse = components['schemas']['SearchProvidersResponse']

export async function getSearchProviders(): Promise<SearchProvidersResponse> {
  return apiFetch<SearchProvidersResponse>('/api/search/providers')
}
