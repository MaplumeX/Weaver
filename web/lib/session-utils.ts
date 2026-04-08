import { normalizeInterruptReview } from '@/lib/interrupt-review'
import { ChatMode, normalizeChatMode } from '@/lib/chat-mode'
import { Artifact, ChatSession, Message } from '@/types/chat'
import type { RemoteSessionInfo, RemoteSessionSnapshot } from '@/lib/session-api'

interface RequestedSessionRestoreOptions {
  activeSessionId: string | null
  requestedSessionId: string | null
  isHistoryLoading: boolean
  clearingSessionId: string | null
}

interface RequestedSessionRestoreDecision {
  shouldOpen: boolean
  nextClearingSessionId: string | null
}

function toTextContent(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'text' in item) {
          return String((item as { text?: unknown }).text || '')
        }
        return ''
      })
      .filter(Boolean)
      .join('\n')
  }
  if (value == null) return ''
  return String(value)
}

function toTimestamp(value: unknown, fallback: number): number {
  const parsed = Date.parse(String(value || ''))
  return Number.isFinite(parsed) ? parsed : fallback
}

export function sortChatSessions(history: ChatSession[]): ChatSession[] {
  return [...history].sort((a, b) => {
    if (a.isPinned && !b.isPinned) return -1
    if (!a.isPinned && b.isPinned) return 1
    return b.updatedAt - a.updatedAt
  })
}

export function replaceSessionPreservingOrder(
  history: ChatSession[],
  nextSession: ChatSession,
): ChatSession[] {
  const index = history.findIndex((session) => session.id === nextSession.id)
  if (index === -1) {
    return [...history, nextSession]
  }

  return history.map((session, currentIndex) =>
    currentIndex === index ? nextSession : session,
  )
}

export function buildChatSessionFromRemoteInfo(
  remote: Pick<
    RemoteSessionInfo,
    'thread_id' | 'status' | 'route' | 'created_at' | 'updated_at'
  > & {
    topic?: string
    title?: string
    summary?: string
    is_pinned?: boolean
    tags?: string[]
  },
): ChatSession {
  const now = Date.now()
  const createdAt = toTimestamp(remote.created_at, now)
  const updatedAt = toTimestamp(remote.updated_at, createdAt)
  const title = String(remote.title || remote.topic || 'New Conversation')
  const summary = String(remote.summary || remote.topic || '')
  const mode = normalizeChatMode(remote.route)

  return {
    id: remote.thread_id,
    title,
    date: new Date(updatedAt).toLocaleDateString(),
    createdAt,
    updatedAt,
    isPinned: Boolean(remote.is_pinned),
    tags: Array.isArray(remote.tags) ? remote.tags : [],
    summary,
    threadId: remote.thread_id,
    status: String(remote.status || ''),
    route: mode,
    searchMode: mode,
    canResume: false,
    source: 'remote',
  }
}

export function buildChatSnapshotFromRemote(
  snapshot: RemoteSessionSnapshot,
  sessionId: string,
) {
  const createdAt = toTimestamp(snapshot.session.created_at, Date.now())
  const updatedAt = toTimestamp(snapshot.session.updated_at, createdAt)
  const route = normalizeChatMode(snapshot.session.route)
  const messages: Message[] = (Array.isArray(snapshot.messages) ? snapshot.messages : []).map((message) => ({
    id: String(message.id || `${sessionId}-${Math.random().toString(36).slice(2, 8)}`),
    role: message.role,
    content: String(message.content || ''),
    attachments: Array.isArray(message.attachments)
      ? (message.attachments as Message['attachments'])
      : [],
    sources: Array.isArray(message.sources)
      ? message.sources.map((source) => ({
          title: String(source.title || ''),
          url: String(source.url || ''),
        }))
      : [],
    toolInvocations: Array.isArray(message.tool_invocations)
      ? message.tool_invocations.map((tool, index) => ({
          toolId: String(tool.toolId || tool.tool_id || tool.toolName || tool.name || `tool_${index}`),
          toolName: String(tool.toolName || tool.name || `tool_${index}`),
          toolCallId: String(tool.toolCallId || tool.tool_call_id || `tool_call_${index}`),
          state:
            tool.state === 'completed' || tool.state === 'failed' || tool.state === 'running'
              ? tool.state
              : 'completed',
          phase: typeof tool.phase === 'string' ? tool.phase : undefined,
          args: tool.args,
          result: tool.result,
          payload: tool.payload,
        }))
      : [],
    processEvents: Array.isArray(message.process_events)
      ? message.process_events.map((event, index) => ({
          id: String(event.id || `${sessionId}-event-${index}`),
          type: String(event.type || 'event'),
          timestamp:
            typeof event.timestamp === 'number'
              ? event.timestamp
              : toTimestamp(event.timestamp, updatedAt),
          data: event.data,
        }))
      : [],
    metrics: message.metrics as Message['metrics'],
    createdAt: message.created_at ? toTimestamp(message.created_at, createdAt) : undefined,
    completedAt: message.completed_at ? toTimestamp(message.completed_at, updatedAt) : undefined,
  }))

  return {
    sessionId,
    threadId: snapshot.session.thread_id,
    messages,
    artifacts: [] as Artifact[],
    pendingInterrupt: (snapshot.pending_interrupt as any) || null,
    currentStatus: String(snapshot.session.status || ''),
    route,
    searchMode: route,
    status: String(snapshot.session.status || ''),
    canResume: Boolean(snapshot.can_resume),
    updatedAt,
    createdAt,
  }
}

export function resolveLoadedSessionSnapshot({
  remoteSnapshot,
  fallbackSnapshot,
  sessionId,
}: {
  remoteSnapshot: RemoteSessionSnapshot | null
  fallbackSnapshot: any
  sessionId: string
}) {
  if (remoteSnapshot) {
    return buildChatSnapshotFromRemote(remoteSnapshot, sessionId)
  }
  if (fallbackSnapshot) {
    return fallbackSnapshot
  }
  return null
}

export function mergeRemoteAndCachedHistory(
  remoteHistory: ChatSession[],
  cachedHistory: ChatSession[],
): ChatSession[] {
  const remoteIds = new Set(remoteHistory.map((session) => session.id))
  const merged = [
    ...remoteHistory,
    ...cachedHistory.filter((session) => !remoteIds.has(session.id)),
  ]
  return sortChatSessions(merged)
}

export function createConversationId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function deriveSearchModeFromRoute(route?: string | null): ChatMode {
  return normalizeChatMode(route)
}

export function resolveRequestedSessionRestore({
  activeSessionId,
  requestedSessionId,
  isHistoryLoading,
  clearingSessionId,
}: RequestedSessionRestoreOptions): RequestedSessionRestoreDecision {
  const isWaitingForClearedUrl = Boolean(
    clearingSessionId && requestedSessionId === clearingSessionId,
  )

  if (isWaitingForClearedUrl) {
    return {
      shouldOpen: false,
      nextClearingSessionId: clearingSessionId,
    }
  }

  if (isHistoryLoading || !requestedSessionId || requestedSessionId === activeSessionId) {
    return {
      shouldOpen: false,
      nextClearingSessionId: null,
    }
  }

  return {
    shouldOpen: true,
    nextClearingSessionId: null,
  }
}

export function getDefaultSessionTitle(messages: Message[]): string {
  const firstUserMessage = messages.find((message) => message.role === 'user')
  const content = String(firstUserMessage?.content || '').trim()
  return content ? content.slice(0, 40) : 'New Conversation'
}

export function getSessionSummary(messages: Message[]): string {
  const assistantMessage = [...messages].reverse().find((message) => message.role === 'assistant')
  if (assistantMessage?.content?.trim()) {
    return assistantMessage.content.trim().slice(0, 140)
  }

  const userMessage = [...messages].reverse().find((message) => message.role === 'user')
  if (userMessage?.content?.trim()) {
    return userMessage.content.trim().slice(0, 140)
  }

  return ''
}

export function mapStoredMessageTypeToRole(type: unknown): Message['role'] {
  const normalized = String(type || '').trim().toLowerCase()
  if (normalized === 'human' || normalized === 'humanmessage' || normalized === 'user') {
    return 'user'
  }
  if (normalized === 'ai' || normalized === 'aimessage' || normalized === 'assistant') {
    return 'assistant'
  }
  return 'system'
}

export function buildMessagesFromSessionState(
  state: Record<string, unknown>,
  sessionId: string,
): Message[] {
  const rawMessages = Array.isArray(state.messages) ? state.messages : []

  return rawMessages
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null
      const typed = item as { type?: unknown; content?: unknown }
      const content = toTextContent(typed.content).trim()
      if (!content) return null

      return {
        id: `${sessionId}-restored-${index}`,
        role: mapStoredMessageTypeToRole(typed.type),
        content,
      } satisfies Message
    })
    .filter((item): item is Message => Boolean(item))
}

export function buildArtifactsFromSessionState(
  state: Record<string, unknown>,
  sessionId: string,
): Artifact[] {
  const finalReport = toTextContent(state.final_report).trim()
  if (!finalReport) return []

  const now = Date.now()
  return [
    {
      id: `${sessionId}-artifact-report`,
      sessionId,
      type: 'report',
      title: 'Final Report',
      content: finalReport,
      createdAt: now,
      updatedAt: now,
    },
  ]
}

export function buildPendingInterrupt(
  prompts: unknown,
  messages: Message[],
) {
  const promptList = Array.isArray(prompts) ? prompts : []
  if (promptList.length === 0) return null

  const review = normalizeInterruptReview({ prompts: promptList })
  if (!review) return null

  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === 'assistant')
  return {
    ...review,
    messageId: review.messageId || lastAssistantMessage?.id,
  }
}
