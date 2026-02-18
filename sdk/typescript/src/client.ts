import type { StreamEvent } from './types.js'
import { readSseEvents } from './sse.js'

export class WeaverApiError extends Error {
  status: number
  path: string
  bodyText: string

  constructor(opts: { status: number; path: string; bodyText: string }) {
    const suffix = opts.bodyText ? `: ${opts.bodyText}` : ''
    super(`Weaver API request failed (${opts.status}) ${opts.path}${suffix}`)
    this.status = opts.status
    this.path = opts.path
    this.bodyText = opts.bodyText
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

function normalizeBaseUrl(raw: string): string {
  const text = String(raw || '').trim()
  if (!text) return 'http://127.0.0.1:8001'
  return text.replace(/\/+$/, '')
}

function mergeHeaders(
  headers: HeadersInit | undefined,
  defaults: Record<string, string>
): Headers {
  const merged = new Headers(headers)
  for (const [key, value] of Object.entries(defaults)) {
    if (!merged.has(key)) merged.set(key, value)
  }
  return merged
}

export class WeaverClient {
  private baseUrl: string
  private headers: Record<string, string>
  private fetchImpl: FetchLike

  constructor(opts: { baseUrl?: string; headers?: Record<string, string>; fetch?: FetchLike } = {}) {
    this.baseUrl = normalizeBaseUrl(opts.baseUrl || 'http://127.0.0.1:8001')
    this.headers = opts.headers || {}
    this.fetchImpl = opts.fetch || fetch
  }

  private url(path: string): string {
    const p = path.startsWith('/') ? path : `/${path}`
    return `${this.baseUrl}${p}`
  }

  async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(this.url(path), {
      ...init,
      headers: mergeHeaders({ ...this.headers, ...(init.headers || {}) }, {
        Accept: 'application/json',
      }),
    })

    const bodyText = await response.text().catch(() => '')
    if (!response.ok) {
      throw new WeaverApiError({ status: response.status, path, bodyText })
    }

    if (!bodyText) return undefined as T
    try {
      return JSON.parse(bodyText) as T
    } catch {
      return bodyText as unknown as T
    }
  }

  async *chatSse(payload: unknown, opts: { signal?: AbortSignal } = {}): AsyncGenerator<StreamEvent> {
    const response = await this.fetchImpl(this.url('/api/chat/sse'), {
      method: 'POST',
      headers: mergeHeaders({ ...this.headers }, {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
      signal: opts.signal,
    })

    if (!response.ok) {
      const bodyText = await response.text().catch(() => '')
      throw new WeaverApiError({ status: response.status, path: '/api/chat/sse', bodyText })
    }

    for await (const event of readSseEvents(response)) {
      const data = event.data

      if (data && typeof data === 'object' && 'type' in data && 'data' in data) {
        yield data as StreamEvent
        continue
      }

      if (event.event) {
        yield { type: event.event, data }
      }
    }
  }
}

