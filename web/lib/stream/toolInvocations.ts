import type { ToolInvocation } from '@/types/chat'

export type ToolStreamPayload = {
  toolCallId?: string
  name?: string
  status?: string
  query?: string
  args?: Record<string, unknown>
}

function normalizeStatus(status: unknown): ToolInvocation['state'] {
  const raw = String(status || '').toLowerCase()
  if (raw === 'completed' || raw === 'complete' || raw === 'done') return 'completed'
  if (raw === 'failed' || raw === 'error') return 'failed'
  return 'running'
}

function stableFallbackMatchKey(payload: ToolStreamPayload): string {
  const name = String(payload.name || '').trim()
  const query = String(payload.query || '').trim()
  return query ? `${name}::${query}` : name
}

export function applyToolStreamEvent(
  existing: ToolInvocation[],
  payload: ToolStreamPayload,
): ToolInvocation[] {
  const toolName = String(payload?.name || '').trim()
  if (!toolName) return existing

  const state = normalizeStatus(payload.status)

  const args: Record<string, unknown> = {
    ...(payload.args && typeof payload.args === 'object' ? payload.args : {}),
  }

  if (payload.query && typeof args.query !== 'string') {
    args.query = payload.query
  }

  const toolCallId = typeof payload.toolCallId === 'string' && payload.toolCallId.trim()
    ? payload.toolCallId.trim()
    : null

  const matchIndex = (() => {
    if (toolCallId) {
      return existing.findIndex(t => t.toolCallId === toolCallId)
    }

    const key = stableFallbackMatchKey(payload)
    if (!key) return -1

    // Prefer updating an in-flight invocation when the backend doesn't provide ids.
    return existing.findIndex(t => {
      if (t.state !== 'running') return false
      const tQuery = typeof t.args?.query === 'string' ? String(t.args.query).trim() : ''
      return `${t.toolName}::${tQuery}` === key || t.toolName === toolName
    })
  })()

  if (matchIndex >= 0) {
    const prev = existing[matchIndex]!
    const next: ToolInvocation = {
      ...prev,
      toolName,
      state,
      args: { ...(prev.args || {}), ...args },
      toolCallId: toolCallId || prev.toolCallId,
    }

    const copy = existing.slice()
    copy[matchIndex] = next
    return copy
  }

  const newInvocation: ToolInvocation = {
    toolCallId: toolCallId || `tool-${Date.now()}-${Math.random()}`,
    toolName,
    state,
    args,
  }

  return [...existing, newInvocation]
}
