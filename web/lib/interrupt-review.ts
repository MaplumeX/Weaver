export type InterruptReviewKind = 'tool_approval' | 'scope_review' | 'clarify_question' | 'generic'

export interface InterruptReview {
  kind: InterruptReviewKind
  checkpoint: string
  title: string
  description: string
  content: string
  availableActions: string[]
  messageId?: string
  prompt: any
  raw: any
}

function getFirstPrompt(raw: any): any {
  if (raw?.prompts?.[0]) return raw.prompts[0]
  if (raw?.interrupts?.[0]) return raw.interrupts[0]
  if (raw?.prompt) return raw.prompt
  if (raw && typeof raw === 'object') return raw
  return null
}

export function normalizeInterruptReview(raw: any): InterruptReview | null {
  const prompt = getFirstPrompt(raw)
  if (!prompt || typeof prompt !== 'object') return null

  const checkpoint = String(prompt?.checkpoint || '').trim()
  const content = String(prompt?.content || '').trim()
  const message = String(prompt?.message || '').trim()
  const instruction = String(prompt?.instruction || '').trim()

  if (prompt?.action_requests && prompt?.review_configs) {
    return {
      kind: 'tool_approval',
      checkpoint: checkpoint || 'tool_approval',
      title: 'Tool approval required',
      description: message || instruction || 'Approve tool execution to continue.',
      content,
      availableActions: ['approve', 'reject'],
      prompt,
      raw,
    }
  }

  if (checkpoint === 'deepsearch_scope_review') {
    return {
      kind: 'scope_review',
      checkpoint,
      title: 'Review research scope',
      description:
        instruction || message || 'Approve the scope draft or provide feedback for a rewrite.',
      content,
      availableActions: ['approve_scope', 'revise_scope'],
      prompt,
      raw,
    }
  }

  if (checkpoint === 'deepsearch_clarify') {
    return {
      kind: 'clarify_question',
      checkpoint,
      title: 'Clarify research intake',
      description: message || instruction || 'Answer the clarification question to continue.',
      content,
      availableActions: ['answer_clarification'],
      prompt,
      raw,
    }
  }

  const availableActions = Array.isArray(prompt?.available_actions)
    ? prompt.available_actions
        .map((item: any) => String(item || '').trim())
        .filter(Boolean)
    : ['approve', 'edit']

  return {
    kind: 'generic',
    checkpoint,
    title: 'Review required',
    description: instruction || message || 'Review the current checkpoint before continuing.',
    content,
    availableActions,
    prompt,
    raw,
  }
}

export function getInterruptConversationMessage(review: InterruptReview | null, raw: any): string {
  const fallbackMessage = String(raw?.message || raw?.prompts?.[0]?.message || '').trim()
  if (!review) return fallbackMessage

  if (review.kind === 'clarify_question') {
    return review.description || fallbackMessage || review.title
  }

  if (review.kind === 'scope_review') {
    return review.content || review.description || review.title
  }

  return review.content || review.description || fallbackMessage || review.title
}

export function getInterruptInputPlaceholder(
  review: InterruptReview | null,
  options: { revisionMode?: boolean } = {},
): string {
  if (!review) return ''
  const revisionMode = Boolean(options.revisionMode)

  if (review.kind === 'clarify_question') {
    return '继续补充你的研究目标、范围或约束'
  }

  if (review.kind === 'scope_review' && revisionMode) {
    return '继续告诉我你希望如何修改研究范围'
  }

  if (review.kind === 'generic') {
    return '输入补充内容后继续'
  }

  return ''
}

export function buildInterruptResumePayload(
  review: InterruptReview,
  action: string,
  input: string = '',
): any {
  const normalizedAction = String(action || '').trim().toLowerCase()
  const text = String(input || '').trim()

  if (review.kind === 'tool_approval') {
    const toolCalls = review.prompt?.tool_calls || []
    if (normalizedAction === 'reject') {
      return {
        tool_approved: false,
        tool_calls: toolCalls,
        message: text || 'User rejected tool execution.',
      }
    }
    return {
      tool_approved: true,
      tool_calls: toolCalls,
    }
  }

  if (review.kind === 'scope_review') {
    if (normalizedAction === 'approve' || normalizedAction === 'approve_scope') {
      return { action: 'approve_scope' }
    }
    return {
      action: 'revise_scope',
      scope_feedback: text,
    }
  }

  if (review.kind === 'clarify_question') {
    return { clarify_answer: text }
  }

  if (text) {
    return { content: text }
  }
  return { continue: true }
}
