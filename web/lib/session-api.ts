import { getApiBaseUrl } from '@/lib/api'

export interface RemoteSessionInfo {
  thread_id: string
  status: string
  topic: string
  created_at: string
  updated_at: string
  route: string
  has_report: boolean
  revision_count: number
  message_count: number
  title?: string
  summary?: string
  is_pinned?: boolean
  tags?: string[]
}

export interface RemoteSessionMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments?: Array<Record<string, unknown>>
  sources?: Array<Record<string, unknown>>
  tool_invocations?: Array<Record<string, unknown>>
  process_events?: Array<Record<string, unknown>>
  metrics?: Record<string, unknown>
  created_at?: string | null
  completed_at?: string | null
}

export interface RemoteSessionSnapshot {
  session: {
    thread_id: string
    title: string
    status: string
    route: string
    created_at: string
    updated_at: string
    summary?: string
    is_pinned?: boolean
    tags?: string[]
  }
  messages: RemoteSessionMessage[]
  pending_interrupt?: Record<string, unknown> | null
  can_resume: boolean
  checkpoint_cleanup_pending?: boolean
}

async function fetchJson(path: string, init?: RequestInit) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: 'no-store',
    ...init,
  })
  if (response.status === 404) return null
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json()
}

export async function fetchSessions(limit: number = 100): Promise<RemoteSessionInfo[]> {
  const payload = await fetchJson(`/api/sessions?limit=${limit}`)
  return Array.isArray(payload?.sessions) ? payload.sessions : []
}

export async function fetchSessionInfo(threadId: string) {
  return fetchJson(`/api/sessions/${threadId}`)
}

export async function fetchSessionSnapshot(threadId: string): Promise<RemoteSessionSnapshot | null> {
  return fetchJson(`/api/sessions/${threadId}/snapshot`)
}

export async function fetchSessionState(threadId: string) {
  return fetchJson(`/api/sessions/${threadId}/state`)
}

export async function fetchInterruptStatus(threadId: string) {
  return fetchJson(`/api/interrupt/${threadId}/status`)
}

export async function patchSession(threadId: string, payload: Record<string, unknown>) {
  return fetchJson(`/api/sessions/${threadId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}

export async function deleteRemoteSession(threadId: string): Promise<boolean> {
  const response = await fetch(`${getApiBaseUrl()}/api/sessions/${threadId}`, {
    method: 'DELETE',
  })

  if (response.status === 404) return false
  if (!response.ok) {
    throw new Error(`Delete session failed: ${response.status}`)
  }
  return true
}
