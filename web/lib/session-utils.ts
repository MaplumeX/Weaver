import { normalizeInterruptReview } from '@/lib/interrupt-review'
import { Artifact, ChatSession, Message } from '@/types/chat'

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

export function createConversationId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function deriveSearchModeFromRoute(route?: string | null): string {
  const normalized = String(route || '').trim().toLowerCase()
  if (normalized === 'deep') return 'deep'
  if (normalized === 'agent') return 'agent'
  if (normalized === 'web') return 'web'
  return ''
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
