import { ProcessEvent } from '@/types/chat'

export type DeepResearchPhaseKey =
  | 'intake'
  | 'scope'
  | 'outline'
  | 'section_research'
  | 'section_review'
  | 'report'

export interface DeepResearchSectionIterationSummary {
  iteration: number | null
  label: string
  headline: string
  metrics: string[]
}

export interface DeepResearchSectionSummary {
  sectionId: string
  label: string
  headline: string
  metrics: string[]
  latestIteration: number | null
  iterations: DeepResearchSectionIterationSummary[]
}

export interface DeepResearchPhaseHighlight {
  id: string
  headline: string
  detail?: string
}

export interface DeepResearchPhaseSummary {
  key: DeepResearchPhaseKey
  title: string
  summary: string
  metrics: string[]
  highlights: DeepResearchPhaseHighlight[]
  sections: DeepResearchSectionSummary[]
}

export interface DeepResearchTimelineProjection {
  headerMetrics: string[]
  phases: DeepResearchPhaseSummary[]
  rawEvents: ProcessEvent[]
  rawEventCount: number
  suppressedEventCount: number
  currentIteration: number | null
}

type CanonicalEventType =
  | 'research_agent_start'
  | 'research_agent_complete'
  | 'research_task_update'
  | 'research_artifact_update'
  | 'research_decision'

interface TaskMeta {
  sectionId: string
  label: string
  taskKind: string
}

interface CanonicalEvent {
  event: ProcessEvent
  type: CanonicalEventType
  payload: any
  phase: DeepResearchPhaseKey
  sectionId: string | null
  taskId: string | null
  taskKind: string
  iteration: number | null
  headline: string
}

interface SectionIterationAccumulator {
  iteration: number | null
  latestTimestamp: number
  latestHeadline: string
  stageLabels: string[]
  sourceUrls: Set<string>
  sourceIds: Set<string>
  documentIds: Set<string>
  evidenceIds: Set<string>
  synthesisIds: Set<string>
  reviewIds: Set<string>
  certificationIds: Set<string>
  attempt: number | null
  resumed: boolean
}

interface SectionAccumulator {
  sectionId: string
  order: number
  label: string
  latestTimestamp: number
  latestHeadline: string
  latestIteration: number | null
  reviewState: string
  certified: boolean
  sourceUrls: Set<string>
  sourceIds: Set<string>
  documentIds: Set<string>
  evidenceIds: Set<string>
  synthesisIds: Set<string>
  reviewIds: Set<string>
  certificationIds: Set<string>
  phaseActivity: Set<DeepResearchPhaseKey>
  iterations: Map<string, SectionIterationAccumulator>
}

interface ComputedSectionSummary extends DeepResearchSectionSummary {
  phaseKeys: Set<DeepResearchPhaseKey>
}

const PHASE_ORDER: DeepResearchPhaseKey[] = [
  'intake',
  'scope',
  'outline',
  'section_research',
  'section_review',
  'report',
]

const PHASE_TITLES: Record<DeepResearchPhaseKey, string> = {
  intake: 'Intake',
  scope: 'Scope',
  outline: 'Outline',
  section_research: 'Section Research',
  section_review: 'Section Review',
  report: 'Report',
}

const CANONICAL_EVENT_TYPES = new Set<CanonicalEventType>([
  'research_agent_start',
  'research_agent_complete',
  'research_task_update',
  'research_artifact_update',
  'research_decision',
])

const STAGE_ORDER = [
  'Planned',
  'Queued',
  'Search',
  'Read',
  'Extract',
  'Synthesize',
  'Review',
  'Revision',
  'Certified',
  'Report',
  'Reported',
]

const SECTION_ARTIFACT_TYPES = new Set([
  'evidence_bundle',
  'section_draft',
  'section_review',
  'section_certification',
  'branch_result',
  'validation_summary',
])

const SUPPRESSED_DEFAULT_VIEW_TYPES = new Set([
  'task_update',
  'status',
  'thinking',
  'search',
  'deep_research_topology_update',
  'research_node_start',
  'research_node_complete',
  'quality_update',
  'tool',
  'tool_progress',
  'screenshot',
])

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function positiveNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => text(item)).filter(Boolean)
}

function addUnique(list: string[], value: string): void {
  if (value && !list.includes(value)) {
    list.push(value)
  }
}

function formatCount(value: number, singular: string, plural: string): string {
  return `${value} ${value === 1 ? singular : plural}`
}

function isDeepResearchEvent(event: ProcessEvent): boolean {
  return (
    CANONICAL_EVENT_TYPES.has(event.type as CanonicalEventType) ||
    event.type === 'deep_research_topology_update' ||
    event.type === 'research_node_start' ||
    event.type === 'research_node_complete'
  )
}

function formatStageLabel(stage: string): string {
  switch (stage) {
    case 'planned':
      return 'Planned'
    case 'dispatch':
      return 'Queued'
    case 'search':
      return 'Search'
    case 'read':
      return 'Read'
    case 'extract':
      return 'Extract'
    case 'synthesize':
      return 'Synthesize'
    case 'review':
    case 'reviewer':
      return 'Review'
    case 'revision':
    case 'revisor':
      return 'Revision'
    case 'outline_gate':
      return 'Outline'
    case 'reported':
      return 'Reported'
    default:
      return stage
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
    }
}

function formatReviewOutcome(status: string): string {
  switch (status) {
    case 'accept_section':
    case 'passed':
      return 'Section review passed'
    case 'request_research':
    case 'retry':
      return 'Section review requested more evidence'
    case 'revise_section':
      return 'Section review requested revision'
    case 'block_section':
    case 'failed':
      return 'Section review failed'
    default:
      return 'Section review updated'
  }
}

function isPreExecutionTaskUpdate(payload: any): boolean {
  const status = text(payload?.status)
  const stage = text(payload?.stage)
  return (
    (status === 'ready' || status === 'in_progress') &&
    (!stage || stage === 'planned' || stage === 'dispatch')
  )
}

function describeDecision(decisionType: string, reason: string): string {
  switch (decisionType) {
    case 'clarify_required':
      return 'Clarification required'
    case 'scope_ready':
      return 'Scope ready for review'
    case 'scope_revision_requested':
      return 'Scope revision requested'
    case 'scope_approved':
      return 'Scope approved'
    case 'research_brief_ready':
      return 'Research brief ready'
    case 'outline_plan':
      return 'Outline planned'
    case 'plan':
    case 'replan':
    case 'supervisor_plan':
    case 'supervisor_replan':
      return 'Outline planning updated'
    case 'research':
      return 'Section research dispatched'
    case 'retry_branch':
    case 'verification_retry_requested':
      return 'Section review requested another pass'
    case 'review_updated':
      return 'Section review updated'
    case 'review_passed':
      return 'Section review passed'
    case 'coverage_gap_detected':
      return 'Coverage gaps detected'
    case 'verification_passed':
      return 'Legacy verification passed'
    case 'report':
      return 'Preparing final report'
    case 'outline_ready':
      return 'Outline gate passed'
    case 'report_partial':
      return 'Preparing partial report'
    case 'outline_partial':
      return 'Outline gate advisory only'
    case 'budget_stop':
      return 'Budget limit reached'
    case 'stop':
      return 'Research stopped'
    case 'synthesize':
    case 'complete':
      return 'Preparing final report'
    default:
      return reason || 'Decision recorded'
  }
}

function describeArtifact(payload: any): string {
  const artifactType = text(payload?.artifact_type)
  const status = text(payload?.status)
  const reviewVerdict = text(payload?.review_verdict || payload?.validation_status || payload?.status)

  switch (artifactType) {
    case 'scope_draft':
      if (status === 'approved') return 'Scope approved'
      if (status === 'revision_requested') return 'Scope revision requested'
      return 'Scope draft updated'
    case 'scope':
      return 'Scope locked'
    case 'plan':
      return 'Section plan ready'
    case 'outline':
      return 'Outline ready'
    case 'evidence_bundle': {
      const sourceCount = positiveNumber(payload?.source_count)
      return sourceCount !== null ? `Evidence bundle recorded (${sourceCount} sources)` : 'Evidence bundle recorded'
    }
    case 'section_draft':
    case 'branch_result':
      return 'Section draft ready'
    case 'section_review':
      return formatReviewOutcome(reviewVerdict)
    case 'section_certification':
      return 'Section certified'
    case 'validation_summary':
      return formatReviewOutcome(reviewVerdict)
    case 'final_report':
      return 'Final report generated'
    default:
      return status ? `${artifactType || 'Artifact'} ${status}` : artifactType || 'Artifact updated'
  }
}

function describeAgentLifecycle(eventType: CanonicalEventType, payload: any): string {
  const role = text(payload?.role)
  const phase = text(payload?.phase)
  const stage = text(payload?.validation_stage || payload?.stage)
  const status = text(payload?.status)

  if (role === 'clarify') {
    return eventType === 'research_agent_complete' && status === 'completed'
      ? 'Clarification complete'
      : 'Clarifying research goal'
  }
  if (role === 'scope') {
    return eventType === 'research_agent_complete' && status === 'completed'
      ? 'Scope drafted'
      : 'Drafting scope'
  }
  if (role === 'supervisor') {
    if (phase === 'outline_plan') return 'Planning outline'
    if (phase === 'supervisor_decide') return 'Reviewing section state'
    return 'Coordinating deep research'
  }
  if (role === 'researcher') {
    if (eventType === 'research_agent_complete' && status === 'completed') return 'Section research complete'
    return stage ? `${formatStageLabel(stage)} in progress` : 'Section research running'
  }
  if (role === 'reviewer') {
    return eventType === 'research_agent_complete' && status === 'completed'
      ? 'Section review complete'
      : 'Reviewing section draft'
  }
  if (role === 'revisor') {
    return eventType === 'research_agent_complete' && status === 'completed'
      ? 'Section revision complete'
      : 'Revising section draft'
  }
  if (role === 'reporter') {
    return eventType === 'research_agent_complete' && status === 'completed'
      ? 'Final report complete'
      : 'Writing final report'
  }
  return 'Agent lifecycle updated'
}

function describeTaskUpdate(payload: any): string {
  const status = text(payload?.status)
  const stage = text(payload?.stage)
  const taskKind = text(payload?.task_kind)
  const stageLabel = stage ? formatStageLabel(stage) : taskKind === 'section_revision' ? 'Revision' : 'Section'

  if (status === 'ready') return taskKind === 'section_revision' ? 'Section revision queued' : 'Section queued'
  if (status === 'in_progress') return `${stageLabel} in progress`
  if (status === 'completed') return `${stageLabel} complete`
  if (status === 'failed') return `${stageLabel} failed`
  if (status === 'blocked') return `${stageLabel} blocked`
  return stageLabel
}

function describeCanonicalEvent(eventType: CanonicalEventType, payload: any): string {
  if (eventType === 'research_decision') return describeDecision(text(payload?.decision_type), text(payload?.reason))
  if (eventType === 'research_artifact_update') return describeArtifact(payload)
  if (eventType === 'research_task_update') return describeTaskUpdate(payload)
  return describeAgentLifecycle(eventType, payload)
}

function trimDetail(detail: string, maxLength: number = 220): string {
  if (detail.length <= maxLength) return detail
  return `${detail.slice(0, maxLength - 1).trimEnd()}…`
}

function describeCanonicalDetail(eventType: CanonicalEventType, payload: any): string {
  if (eventType === 'research_decision') return trimDetail(text(payload?.reason))
  if (eventType === 'research_artifact_update') return trimDetail(text(payload?.summary || payload?.objective_summary))
  if (eventType === 'research_task_update') return trimDetail(text(payload?.title || payload?.objective_summary || payload?.query))
  if (eventType === 'research_agent_complete') return trimDetail(text(payload?.summary || payload?.objective_summary))
  return ''
}

function resolvePhase(eventType: CanonicalEventType, payload: any): DeepResearchPhaseKey | null {
  const role = text(payload?.role)
  const decisionType = text(payload?.decision_type)
  const artifactType = text(payload?.artifact_type)
  const status = text(payload?.status)
  const stage = text(payload?.stage)
  const taskKind = text(payload?.task_kind)
  const phase = text(payload?.phase)
  const reason = text(payload?.reason)

  if (eventType === 'research_agent_start' || eventType === 'research_agent_complete') {
    if (role === 'clarify') return 'intake'
    if (role === 'scope') return 'scope'
    if (role === 'researcher') return 'section_research'
    if (role === 'reviewer' || role === 'revisor') return 'section_review'
    if (role === 'reporter') return 'report'
    if (role === 'supervisor') {
      if (phase === 'outline_plan' || phase === 'research_brief') return 'outline'
      if (phase === 'supervisor_decide') return 'section_review'
      return 'outline'
    }
  }

  if (eventType === 'research_task_update') {
    if (taskKind === 'section_revision' || stage === 'revision') return 'section_review'
    if (isPreExecutionTaskUpdate(payload)) {
      if (reason === 'review_research_retry') return 'section_review'
      if (status === 'in_progress' && reason === 'checkpoint_resume') return 'section_research'
      return 'outline'
    }
    return 'section_research'
  }

  if (eventType === 'research_artifact_update') {
    if (artifactType === 'scope_draft' || artifactType === 'scope') return 'scope'
    if (artifactType === 'outline' || artifactType === 'plan') return 'outline'
    if (artifactType === 'evidence_bundle' || artifactType === 'section_draft' || artifactType === 'branch_result') {
      return 'section_research'
    }
    if (artifactType === 'section_review' || artifactType === 'section_certification' || artifactType === 'validation_summary') {
      return 'section_review'
    }
    if (artifactType === 'final_report') return 'report'
  }

  if (eventType === 'research_decision') {
    if (decisionType === 'clarify_required') return 'intake'
    if (decisionType.startsWith('scope_')) return 'scope'
    if (
      decisionType === 'research_brief_ready' ||
      decisionType === 'outline_plan' ||
      decisionType === 'plan' ||
      decisionType === 'replan' ||
      decisionType === 'supervisor_plan'
    ) {
      return 'outline'
    }
    if (decisionType === 'research') return 'section_research'
    if (
      decisionType === 'review_updated' ||
      decisionType === 'review_passed' ||
      decisionType === 'retry_branch' ||
      decisionType === 'verification_retry_requested' ||
      decisionType === 'verification_passed' ||
      decisionType === 'coverage_gap_detected'
    ) {
      return 'section_review'
    }
    if (
      decisionType === 'report' ||
      decisionType === 'report_partial' ||
      decisionType === 'outline_ready' ||
      decisionType === 'outline_partial' ||
      decisionType === 'budget_stop' ||
      decisionType === 'stop'
    ) {
      return 'report'
    }
    if (decisionType === 'synthesize' || decisionType === 'complete') return 'report'
    return 'outline'
  }

  return null
}

function sectionLabelHint(payload: any): string {
  return text(payload?.title || payload?.objective_summary || payload?.query)
}

function resolveSectionId(payload: any, taskMetaById: Map<string, TaskMeta>): string | null {
  const directSectionId = text(payload?.section_id || payload?.branch_id)
  if (directSectionId) return directSectionId
  const taskId = text(payload?.task_id)
  if (taskId && taskMetaById.has(taskId)) {
    return taskMetaById.get(taskId)?.sectionId || null
  }
  return null
}

function resolveIteration(
  payload: any,
  sectionId: string | null,
  taskId: string | null,
  taskIterationById: Map<string, number>,
  sectionIterationById: Map<string, number>,
  latestIteration: number | null,
): number | null {
  const directIteration = positiveNumber(payload?.iteration)
  if (directIteration !== null) return directIteration
  if (taskId && taskIterationById.has(taskId)) return taskIterationById.get(taskId) || null
  if (sectionId && sectionIterationById.has(sectionId)) return sectionIterationById.get(sectionId) || null
  return latestIteration
}

function updateSourceStats(
  payload: any,
  artifactType: string,
  sourceUrls: Set<string>,
  sourceIds: Set<string>,
  documentIds: Set<string>,
  evidenceIds: Set<string>,
  synthesisIds: Set<string>,
  reviewIds: Set<string>,
  certificationIds: Set<string>,
): void {
  const artifactId = text(payload?.artifact_id)
  const sourceUrl = text(payload?.source_url)
  const sourceUrlsList = stringList(payload?.source_urls)
  const citationUrls = stringList(payload?.citation_urls)

  if (sourceUrl) sourceUrls.add(sourceUrl)
  for (const url of sourceUrlsList) sourceUrls.add(url)
  for (const url of citationUrls) sourceUrls.add(url)
  if (!artifactId) return

  if (artifactType === 'evidence_bundle') {
    evidenceIds.add(artifactId)
    documentIds.add(artifactId)
    return
  }
  if (artifactType === 'section_draft' || artifactType === 'branch_result') {
    synthesisIds.add(artifactId)
    return
  }
  if (artifactType === 'section_review' || artifactType === 'validation_summary') {
    reviewIds.add(artifactId)
    return
  }
  if (artifactType === 'section_certification') {
    certificationIds.add(artifactId)
  }
}

function shouldTrackSectionHistory(
  phase: DeepResearchPhaseKey,
  payload: any,
  sectionId: string | null,
): boolean {
  if (!sectionId) return false
  if (phase === 'section_research' || phase === 'section_review') return true
  return SECTION_ARTIFACT_TYPES.has(text(payload?.artifact_type))
}

function createSectionAccumulator(sectionId: string, order: number, label: string): SectionAccumulator {
  return {
    sectionId,
    order,
    label,
    latestTimestamp: 0,
    latestHeadline: 'Section updated',
    latestIteration: null,
    reviewState: '',
    certified: false,
    sourceUrls: new Set<string>(),
    sourceIds: new Set<string>(),
    documentIds: new Set<string>(),
    evidenceIds: new Set<string>(),
    synthesisIds: new Set<string>(),
    reviewIds: new Set<string>(),
    certificationIds: new Set<string>(),
    phaseActivity: new Set<DeepResearchPhaseKey>(),
    iterations: new Map<string, SectionIterationAccumulator>(),
  }
}

function stageLabelForEvent(phase: DeepResearchPhaseKey, payload: any): string {
  const stage = text(payload?.validation_stage || payload?.stage)
  if (stage) return formatStageLabel(stage)
  if (phase === 'outline') return 'Outline'
  if (phase === 'section_research') return 'Research'
  if (phase === 'section_review') return 'Review'
  if (phase === 'report') return 'Report'
  return ''
}

function compareStageLabels(left: string, right: string): number {
  const leftIndex = STAGE_ORDER.indexOf(left)
  const rightIndex = STAGE_ORDER.indexOf(right)
  const normalizedLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex
  const normalizedRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex
  if (normalizedLeft !== normalizedRight) return normalizedLeft - normalizedRight
  return left.localeCompare(right)
}

function buildPhaseSummary(
  key: DeepResearchPhaseKey,
  events: CanonicalEvent[],
  sections: ComputedSectionSummary[],
  sourceCount: number,
  currentIteration: number | null,
): DeepResearchPhaseSummary | null {
  const phaseSections = sections
    .filter((section) => section.phaseKeys.has(key))
    .map(({ phaseKeys: _phaseKeys, ...rest }) => rest)

  if ((key === 'section_research' || key === 'section_review') && phaseSections.length > 0) {
    const uniqueIterations = new Set(
      phaseSections.flatMap((section) => section.iterations.map((iteration) => iteration.iteration).filter((value) => value !== null)),
    )
    const certifiedCount = phaseSections.filter((section) => section.metrics.some((metric) => metric === 'Certified')).length
    const metrics = [
      formatCount(phaseSections.length, 'section', 'sections'),
      uniqueIterations.size > 0 ? formatCount(uniqueIterations.size, 'iteration', 'iterations') : '',
      key === 'section_review' && certifiedCount > 0 ? formatCount(certifiedCount, 'certified', 'certified') : '',
      sourceCount > 0 ? formatCount(sourceCount, 'source', 'sources') : '',
    ].filter(Boolean)
    const latestHeadline = events[events.length - 1]?.headline || (key === 'section_review' ? 'Section review updated' : 'Section research updated')
    return {
      key,
      title: PHASE_TITLES[key],
      summary: latestHeadline,
      metrics,
      highlights: [],
      sections: phaseSections,
    }
  }

  if (events.length === 0) return null

  const latestHeadline = events[events.length - 1]?.headline || 'Updated'
  const metrics: string[] = []

  if (key === 'outline') {
    if (sections.length > 0) metrics.push(formatCount(sections.length, 'section', 'sections'))
    if (currentIteration !== null) metrics.push(`Iteration ${currentIteration}`)
  }

  if (key === 'report' && sourceCount > 0) {
    metrics.push(formatCount(sourceCount, 'source', 'sources'))
  }

  const highlights = events
    .map((event) => ({
      id: event.event.id,
      headline: event.headline,
      detail: describeCanonicalDetail(event.type, event.payload) || undefined,
    }))
    .filter((highlight, index, list) => {
      const previous = list[index - 1]
      if (!previous) return true
      return previous.headline !== highlight.headline || previous.detail !== highlight.detail
    })
    .slice(-4)

  return {
    key,
    title: PHASE_TITLES[key],
    summary: latestHeadline,
    metrics,
    highlights,
    sections: [],
  }
}

export function projectDeepResearchTimeline(events: ProcessEvent[]): DeepResearchTimelineProjection | null {
  const rawEvents = events.filter((event) => event.type !== 'done')
  const relevantEvents = rawEvents.filter(isDeepResearchEvent)
  const canonicalEvents = relevantEvents.filter((event) => CANONICAL_EVENT_TYPES.has(event.type as CanonicalEventType))

  if (canonicalEvents.length === 0) return null

  const taskMetaById = new Map<string, TaskMeta>()
  const taskIterationById = new Map<string, number>()
  const sectionIterationById = new Map<string, number>()
  const sectionOrderById = new Map<string, number>()
  const sectionLabelById = new Map<string, string>()
  let latestIteration: number | null = null

  canonicalEvents.forEach((event, index) => {
    const payload = event.data || {}
    const taskId = text(payload?.task_id)
    const sectionId = text(payload?.section_id || payload?.branch_id)
    const taskKind = text(payload?.task_kind)
    const labelHint = sectionLabelHint(payload)
    if (taskId && sectionId) {
      taskMetaById.set(taskId, {
        sectionId,
        label: labelHint,
        taskKind,
      })
    } else if (taskId && labelHint && taskMetaById.has(taskId)) {
      const existing = taskMetaById.get(taskId)
      if (existing) {
        taskMetaById.set(taskId, {
          ...existing,
          label: existing.label || labelHint,
        })
      }
    }

    if (sectionId) {
      if (!sectionOrderById.has(sectionId)) sectionOrderById.set(sectionId, index)
      if (labelHint && !sectionLabelById.has(sectionId)) sectionLabelById.set(sectionId, labelHint)
    }
  })

  const phaseBuckets = new Map<DeepResearchPhaseKey, CanonicalEvent[]>()
  PHASE_ORDER.forEach((phase) => phaseBuckets.set(phase, []))

  const sectionBuckets = new Map<string, SectionAccumulator>()
  const globalSourceUrls = new Set<string>()
  const globalSourceIds = new Set<string>()
  const suppressedEventCount = rawEvents.filter((event) => SUPPRESSED_DEFAULT_VIEW_TYPES.has(event.type)).length

  for (const event of canonicalEvents) {
    const payload = event.data || {}
    const type = event.type as CanonicalEventType
    const taskId = text(payload?.task_id) || null
    const taskMeta = taskId ? taskMetaById.get(taskId) : undefined
    const sectionId = resolveSectionId(payload, taskMetaById)
    const taskKind = text(payload?.task_kind) || taskMeta?.taskKind || ''
    const phase = resolvePhase(type, payload)

    if (!phase) continue

    const iteration = resolveIteration(
      payload,
      sectionId,
      taskId,
      taskIterationById,
      sectionIterationById,
      latestIteration,
    )

    if (
      iteration !== null &&
      (phase === 'section_research' ||
        phase === 'section_review' ||
        phase === 'report')
    ) {
      latestIteration = Math.max(latestIteration ?? 0, iteration)
      if (taskId) taskIterationById.set(taskId, iteration)
      if (sectionId) sectionIterationById.set(sectionId, iteration)
    }

    const canonicalEvent: CanonicalEvent = {
      event,
      type,
      payload,
      phase,
      sectionId,
      taskId,
      taskKind,
      iteration,
      headline: describeCanonicalEvent(type, payload),
    }

    phaseBuckets.get(phase)?.push(canonicalEvent)

    updateSourceStats(
      payload,
      text(payload?.artifact_type),
      globalSourceUrls,
      globalSourceIds,
      new Set<string>(),
      new Set<string>(),
      new Set<string>(),
      new Set<string>(),
      new Set<string>(),
    )

    if (!shouldTrackSectionHistory(phase, payload, sectionId) || !sectionId) {
      continue
    }

    const sectionOrder = sectionOrderById.get(sectionId) ?? sectionBuckets.size
    const label = sectionLabelById.get(sectionId) || taskMeta?.label || ''
    const bucket = sectionBuckets.get(sectionId) || createSectionAccumulator(sectionId, sectionOrder, label)
    if (!sectionBuckets.has(sectionId)) sectionBuckets.set(sectionId, bucket)

    if (label && !bucket.label) bucket.label = label
    bucket.phaseActivity.add(phase)

    if (event.timestamp >= bucket.latestTimestamp) {
      bucket.latestTimestamp = event.timestamp
      bucket.latestHeadline = canonicalEvent.headline
      bucket.latestIteration = canonicalEvent.iteration
    }

    updateSourceStats(
      payload,
      text(payload?.artifact_type),
      bucket.sourceUrls,
      bucket.sourceIds,
      bucket.documentIds,
      bucket.evidenceIds,
      bucket.synthesisIds,
      bucket.reviewIds,
      bucket.certificationIds,
    )

    const artifactType = text(payload?.artifact_type)
    if (artifactType === 'section_review' || artifactType === 'validation_summary') {
      bucket.reviewState = describeArtifact(payload)
    }
    if (artifactType === 'section_certification') {
      bucket.reviewState = 'Section certified'
      bucket.certified = true
    }

    const iterationKey = canonicalEvent.iteration !== null ? String(canonicalEvent.iteration) : 'legacy'
    const iterationBucket =
      bucket.iterations.get(iterationKey) ||
      {
        iteration: canonicalEvent.iteration,
        latestTimestamp: 0,
        latestHeadline: canonicalEvent.headline,
        stageLabels: [],
        sourceUrls: new Set<string>(),
        sourceIds: new Set<string>(),
        documentIds: new Set<string>(),
        evidenceIds: new Set<string>(),
        synthesisIds: new Set<string>(),
        reviewIds: new Set<string>(),
        certificationIds: new Set<string>(),
        attempt: positiveNumber(payload?.attempt),
        resumed: Boolean(payload?.resumed_from_checkpoint),
      }

    if (!bucket.iterations.has(iterationKey)) bucket.iterations.set(iterationKey, iterationBucket)

    const stageLabel = stageLabelForEvent(phase, payload)
    if (stageLabel) addUnique(iterationBucket.stageLabels, stageLabel)

    if (event.timestamp >= iterationBucket.latestTimestamp) {
      iterationBucket.latestTimestamp = event.timestamp
      iterationBucket.latestHeadline = canonicalEvent.headline
      iterationBucket.iteration = canonicalEvent.iteration
    }

    const attempt = positiveNumber(payload?.attempt)
    if (attempt !== null) iterationBucket.attempt = Math.max(iterationBucket.attempt ?? 0, attempt)
    iterationBucket.resumed = iterationBucket.resumed || Boolean(payload?.resumed_from_checkpoint)

    updateSourceStats(
      payload,
      artifactType,
      iterationBucket.sourceUrls,
      iterationBucket.sourceIds,
      iterationBucket.documentIds,
      iterationBucket.evidenceIds,
      iterationBucket.synthesisIds,
      iterationBucket.reviewIds,
      iterationBucket.certificationIds,
    )
  }

  const computedSectionSummaries: ComputedSectionSummary[] = [...sectionBuckets.values()]
    .sort((left, right) => left.order - right.order || left.latestTimestamp - right.latestTimestamp)
    .map((bucket, index) => {
      const iterations = [...bucket.iterations.values()]
        .sort((left, right) => {
          if (left.iteration === null && right.iteration === null) return left.latestTimestamp - right.latestTimestamp
          if (left.iteration === null) return 1
          if (right.iteration === null) return -1
          return left.iteration - right.iteration
        })
        .map((iterationBucket) => {
          const sourceCount = iterationBucket.sourceUrls.size > 0 ? iterationBucket.sourceUrls.size : iterationBucket.sourceIds.size
          const metrics = [
            iterationBucket.stageLabels.sort(compareStageLabels).join(' -> '),
            sourceCount > 0 ? formatCount(sourceCount, 'source', 'sources') : '',
            iterationBucket.documentIds.size > 0 ? formatCount(iterationBucket.documentIds.size, 'document', 'documents') : '',
            iterationBucket.reviewIds.size > 0 ? formatCount(iterationBucket.reviewIds.size, 'review', 'reviews') : '',
            iterationBucket.certificationIds.size > 0 ? 'Certified' : '',
            iterationBucket.attempt && iterationBucket.attempt > 1 ? `Attempt ${iterationBucket.attempt}` : '',
            iterationBucket.resumed ? 'Resumed' : '',
          ].filter(Boolean)

          return {
            iteration: iterationBucket.iteration,
            label: iterationBucket.iteration !== null ? `Iteration ${iterationBucket.iteration}` : 'Unscoped',
            headline: iterationBucket.latestHeadline,
            metrics,
          }
        })

      const sourceCount = bucket.sourceUrls.size > 0 ? bucket.sourceUrls.size : bucket.sourceIds.size
      const metrics = [
        formatCount(iterations.length, 'iteration', 'iterations'),
        sourceCount > 0 ? formatCount(sourceCount, 'source', 'sources') : '',
        bucket.documentIds.size > 0 ? formatCount(bucket.documentIds.size, 'document', 'documents') : '',
        bucket.reviewIds.size > 0 ? formatCount(bucket.reviewIds.size, 'review', 'reviews') : '',
        bucket.certified ? 'Certified' : '',
        bucket.reviewState,
      ].filter(Boolean)

      return {
        sectionId: bucket.sectionId,
        label: bucket.label || `Section ${index + 1}`,
        headline: bucket.latestHeadline,
        metrics,
        latestIteration: bucket.latestIteration,
        iterations,
        phaseKeys: bucket.phaseActivity,
      }
    })

  const sourceCount = globalSourceUrls.size > 0 ? globalSourceUrls.size : globalSourceIds.size
  const phaseSummaries = PHASE_ORDER.map((phase) =>
    buildPhaseSummary(
      phase,
      phaseBuckets.get(phase) || [],
      computedSectionSummaries,
      sourceCount,
      latestIteration,
    ),
  ).filter((phase): phase is DeepResearchPhaseSummary => phase !== null)

  const certifiedCount = computedSectionSummaries.filter((section) => section.metrics.includes('Certified')).length
  const headerMetrics = [
    formatCount(phaseSummaries.length, 'phase', 'phases'),
    computedSectionSummaries.length > 0 ? formatCount(computedSectionSummaries.length, 'section', 'sections') : '',
    certifiedCount > 0 ? formatCount(certifiedCount, 'certified', 'certified') : '',
    sourceCount > 0 ? formatCount(sourceCount, 'source', 'sources') : '',
    latestIteration !== null ? `Iteration ${latestIteration}` : '',
  ].filter(Boolean)

  return {
    headerMetrics,
    phases: phaseSummaries,
    rawEvents,
    rawEventCount: rawEvents.length,
    suppressedEventCount,
    currentIteration: latestIteration,
  }
}
