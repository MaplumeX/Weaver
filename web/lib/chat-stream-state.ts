import { Message, ProcessEvent } from '@/types/chat'

const MAX_PROCESS_EVENTS = 200
const RETAIN_THINKING_EVENTS = 3
const RETAIN_TAIL_EVENTS = 60

const KEY_AGENT_ROLES = new Set([
  'clarify',
  'scope',
  'supervisor',
  'reviewer',
  'revisor',
  'verifier',
  'reporter',
])

const KEY_DECISIONS = new Set([
  'clarify_required',
  'scope_ready',
  'scope_revision_requested',
  'scope_approved',
  'research_brief_ready',
  'outline_plan',
  'retry_branch',
  'verification_retry_requested',
  'review_updated',
  'review_passed',
  'coverage_gap_detected',
  'verification_passed',
  'plan',
  'replan',
  'supervisor_plan',
  'research',
  'report',
  'outline_ready',
  'final_claim_gate_passed',
  'final_claim_gate_blocked',
  'synthesize',
  'complete',
  'budget_stop',
  'stop',
])

export function createStreamingAssistantMessage(overrides: Partial<Message> = {}): Message {
  const createdAt = typeof overrides.createdAt === 'number' ? overrides.createdAt : Date.now()

  return {
    id: overrides.id || `assistant-${createdAt}-${Math.random().toString(16).slice(2)}`,
    role: 'assistant',
    content: '',
    toolInvocations: [],
    processEvents: [],
    createdAt,
    isStreaming: true,
    ...overrides,
  }
}

export function appendProcessEvent(
  message: Message,
  type: string,
  payload: any,
  timestamp: number = Date.now(),
): Message {
  const next: ProcessEvent = {
    id: `evt-${timestamp}-${Math.random().toString(16).slice(2)}`,
    type,
    timestamp,
    data: payload,
  }

  const prevEvents = message.processEvents || []
  const last = prevEvents[prevEvents.length - 1]

  const replaceLastEvent = (events: ProcessEvent[], event: ProcessEvent): ProcessEvent[] => {
    return [...events.slice(0, -1), event]
  }

  if (last?.type === type) {
    if (type === 'status') {
      const lastStep = String(last.data?.step || '').trim()
      const nextStep = String(payload?.step || '').trim()
      if (lastStep && nextStep && lastStep === nextStep) {
        return {
          ...message,
          processEvents: replaceLastEvent(prevEvents, next),
        }
      }
      if (last.data?.text && last.data?.text === payload?.text) return message
    }
    if (type === 'search' && last.data?.query && last.data?.query === payload?.query) return message
    if (type === 'tool') {
      const lastName = String(last.data?.name || last.data?.tool || '').trim()
      const nextName = String(payload?.name || payload?.tool || '').trim()
      const lastStatus = String(last.data?.status || '').trim()
      const nextStatus = String(payload?.status || '').trim()
      const lastQuery = String(last.data?.query || last.data?.args?.query || '').trim()
      const nextQuery = String(payload?.query || payload?.args?.query || '').trim()
      if (lastName && lastName === nextName && lastStatus === nextStatus && lastQuery === nextQuery) {
        return message
      }
    }
  }

  return {
    ...message,
    processEvents: [...prevEvents, next].slice(-MAX_PROCESS_EVENTS),
  }
}

function isKeyDeepResearchEvent(ev: ProcessEvent): boolean {
  if (ev.type === 'interrupt') return true

  if (ev.type === 'status') {
    const step = String(ev.data?.step || '').trim().toLowerCase()
    return ['clarifying', 'planning', 'deep_research', 'resume'].includes(step)
  }

  if (ev.type === 'research_artifact_update') {
    return [
      'scope_draft',
      'plan',
      'outline',
      'evidence_bundle',
      'section_draft',
      'section_review',
      'section_certification',
      'branch_result',
      'validation_summary',
      'final_report',
    ].includes(String(ev.data?.artifact_type || '').trim())
  }

  if (ev.type === 'research_decision') {
    return KEY_DECISIONS.has(String(ev.data?.decision_type || '').trim())
  }

  if (ev.type === 'research_agent_start' || ev.type === 'research_agent_complete') {
    const role = String(ev.data?.role || '').trim()
    return KEY_AGENT_ROLES.has(role) || Boolean(ev.data?.resumed_from_checkpoint)
  }

  return false
}

export function getRetainedProcessEvents(events: ProcessEvent[]): ProcessEvent[] {
  const anchors = events.filter((ev) => ev.type !== 'done' && isKeyDeepResearchEvent(ev))
  const thoughts = events.filter((ev) => ev.type === 'thinking').slice(-RETAIN_THINKING_EVENTS)
  const tail = events
    .filter((ev) => ev.type !== 'done' && ev.type !== 'thinking')
    .slice(-RETAIN_TAIL_EVENTS)

  const unique = new Map<string, ProcessEvent>()
  for (const ev of [...anchors, ...thoughts, ...tail]) {
    unique.set(ev.id, ev)
  }

  return [...unique.values()].sort((a, b) => a.timestamp - b.timestamp)
}
