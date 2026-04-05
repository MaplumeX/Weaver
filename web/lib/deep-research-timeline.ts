import { ProcessEvent } from '@/types/chat'

export type DeepResearchPhaseKey =
  | 'intake'
  | 'scope'
  | 'planning'
  | 'branch_research'
  | 'verify'
  | 'report'

export interface DeepResearchBranchIterationSummary {
  iteration: number | null
  label: string
  headline: string
  metrics: string[]
}

export interface DeepResearchBranchSummary {
  branchId: string
  label: string
  headline: string
  metrics: string[]
  latestIteration: number | null
  iterations: DeepResearchBranchIterationSummary[]
}

export interface DeepResearchPhaseSummary {
  key: DeepResearchPhaseKey
  title: string
  summary: string
  metrics: string[]
  highlights: DeepResearchPhaseHighlight[]
  branches: DeepResearchBranchSummary[]
}

export interface DeepResearchTimelineProjection {
  headerMetrics: string[]
  phases: DeepResearchPhaseSummary[]
  rawEvents: ProcessEvent[]
  rawEventCount: number
  suppressedEventCount: number
  currentIteration: number | null
}

export interface DeepResearchPhaseHighlight {
  id: string
  headline: string
  detail?: string
}

type CanonicalEventType =
  | 'research_agent_start'
  | 'research_agent_complete'
  | 'research_task_update'
  | 'research_artifact_update'
  | 'research_decision'

interface TaskMeta {
  branchId: string
  label: string
  taskKind: string
}

interface CanonicalEvent {
  event: ProcessEvent
  type: CanonicalEventType
  payload: any
  phase: DeepResearchPhaseKey
  branchId: string | null
  taskId: string | null
  taskKind: string
  iteration: number | null
  headline: string
}

interface BranchIterationAccumulator {
  iteration: number | null
  latestTimestamp: number
  latestHeadline: string
  stageLabels: string[]
  sourceUrls: Set<string>
  sourceIds: Set<string>
  documentIds: Set<string>
  evidenceIds: Set<string>
  synthesisIds: Set<string>
  attempt: number | null
  resumed: boolean
}

interface BranchAccumulator {
  branchId: string
  order: number
  label: string
  latestTimestamp: number
  latestHeadline: string
  latestIteration: number | null
  verificationState: string
  sourceUrls: Set<string>
  sourceIds: Set<string>
  documentIds: Set<string>
  evidenceIds: Set<string>
  synthesisIds: Set<string>
  iterations: Map<string, BranchIterationAccumulator>
}

const PHASE_ORDER: DeepResearchPhaseKey[] = [
  'intake',
  'scope',
  'planning',
  'branch_research',
  'verify',
  'report',
]

const PHASE_TITLES: Record<DeepResearchPhaseKey, string> = {
  intake: 'Intake',
  scope: 'Scope',
  planning: 'Planning',
  branch_research: 'Branch Research',
  verify: 'Verify',
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
  'Claim Check',
  'Coverage Check',
  'Submit',
  'Reported',
]

const BRANCH_ARTIFACT_TYPES = new Set([
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
  'tool_start',
  'tool_result',
  'tool_error',
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
    case 'claim_check':
      return 'Claim Check'
    case 'coverage_check':
      return 'Coverage Check'
    case 'submit':
      return 'Submit'
    case 'reported':
      return 'Reported'
    case 'research_brief':
      return 'Brief'
    case 'outline_gate':
      return 'Outline'
    case 'final_report':
      return 'Report'
    default:
      return stage
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
    }
}

function formatVerificationOutcome(outcome: string, validationStage: string): string {
  if (!outcome) return validationStage ? `${formatStageLabel(validationStage)} updated` : 'Verification updated'
  if (outcome === 'passed') return `${formatStageLabel(validationStage || 'verify')} passed`
  if (outcome === 'failed') return `${formatStageLabel(validationStage || 'verify')} failed`
  if (outcome === 'needs_follow_up') return `${formatStageLabel(validationStage || 'verify')} needs follow-up`
  return outcome
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
    case 'plan':
    case 'replan':
    case 'supervisor_plan':
    case 'supervisor_replan':
      return 'Research branches planned'
    case 'research':
      return 'Branch research dispatched'
    case 'retry_branch':
      return 'Branch retry requested'
    case 'verification_retry_requested':
      return 'Verification requested another pass'
    case 'coverage_gap_detected':
      return 'Coverage gaps detected'
    case 'verification_passed':
      return 'Verification passed'
    case 'report':
      return 'Preparing final report'
    case 'synthesize':
    case 'complete':
      return 'Preparing final report'
    case 'outline_ready':
      return 'Outline ready'
    case 'outline_gap_detected':
      return 'Outline blocked by remaining gaps'
    case 'budget_stop':
      return 'Budget limit reached'
    case 'stop':
      return 'Research stopped'
    default:
      return reason || 'Decision recorded'
  }
}

function describeArtifact(payload: any): string {
  const artifactType = text(payload?.artifact_type)
  const status = text(payload?.status)
  const validationStage = text(payload?.validation_stage)
  const outcome = text(payload?.outcome)

  switch (artifactType) {
    case 'scope_draft':
      if (status === 'approved') return 'Scope approved'
      if (status === 'revision_requested') return 'Scope revision requested'
      return 'Scope draft updated'
    case 'scope':
      return 'Scope locked'
    case 'plan':
      return 'Research branches planned'
    case 'outline':
      return 'Outline ready'
    case 'evidence_bundle': {
      const sourceCount = positiveNumber(payload?.source_count)
      return sourceCount !== null ? `Evidence bundle recorded (${sourceCount} sources)` : 'Evidence bundle recorded'
    }
    case 'branch_result':
    case 'section_draft':
      return 'Branch result ready'
    case 'validation_summary':
    case 'section_review': {
      const validationStatus = text(payload?.validation_status || payload?.review_verdict || payload?.status)
      if (validationStatus === 'passed' || validationStatus === 'accept_section') return 'Verification passed'
      if (validationStatus === 'retry' || validationStatus === 'request_research') return 'Verification requested another pass'
      if (validationStatus === 'failed' || validationStatus === 'block_section') return 'Verification failed'
      return formatVerificationOutcome(outcome, validationStage)
    }
    case 'section_certification':
      return 'Section certified'
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
    if (phase === 'loop_decision') return 'Reviewing verification results'
    if (phase === 'research_brief_handoff') return 'Preparing research brief'
    return 'Planning research branches'
  }
  if (role === 'researcher') {
    if (eventType === 'research_agent_complete' && status === 'completed') return 'Branch research complete'
    return stage ? `${formatStageLabel(stage)} in progress` : 'Branch research running'
  }
  if (role === 'verifier') {
    if (eventType === 'research_agent_complete' && status === 'completed') {
      return stage ? `${formatStageLabel(stage)} complete` : 'Verification complete'
    }
    return stage ? `${formatStageLabel(stage)} in progress` : 'Verification running'
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
  const stage = text(payload?.validation_stage || payload?.stage)
  const stageLabel = stage ? formatStageLabel(stage) : 'Branch'

  if (status === 'ready') return 'Branch queued'
  if (status === 'in_progress') return `${stageLabel} in progress`
  if (status === 'completed') return `${stageLabel} complete`
  if (status === 'failed') return `${stageLabel} failed`
  if (status === 'blocked') return `${stageLabel} blocked`
  return stageLabel
}

function describeCanonicalEvent(eventType: CanonicalEventType, payload: any): string {
  if (eventType === 'research_decision') {
    return describeDecision(text(payload?.decision_type), text(payload?.reason))
  }
  if (eventType === 'research_artifact_update') {
    return describeArtifact(payload)
  }
  if (eventType === 'research_task_update') {
    return describeTaskUpdate(payload)
  }
  return describeAgentLifecycle(eventType, payload)
}

function trimDetail(detail: string, maxLength: number = 220): string {
  if (detail.length <= maxLength) return detail
  return `${detail.slice(0, maxLength - 1).trimEnd()}…`
}

function describeCanonicalDetail(eventType: CanonicalEventType, payload: any): string {
  if (eventType === 'research_decision') {
    return trimDetail(text(payload?.reason))
  }

  if (eventType === 'research_artifact_update') {
    const detail = text(payload?.summary || payload?.objective_summary)
    return trimDetail(detail)
  }

  if (eventType === 'research_task_update') {
    const detail = text(payload?.title || payload?.objective_summary || payload?.query)
    return trimDetail(detail)
  }

  if (eventType === 'research_agent_complete') {
    const detail = text(payload?.summary || payload?.objective_summary)
    return trimDetail(detail)
  }

  return ''
}

function resolvePhase(eventType: CanonicalEventType, payload: any): DeepResearchPhaseKey | null {
  const role = text(payload?.role)
  const decisionType = text(payload?.decision_type)
  const artifactType = text(payload?.artifact_type)
  const status = text(payload?.status)
  const phase = text(payload?.phase)
  const stage = text(payload?.stage)
  const validationStage = text(payload?.validation_stage)

  if (eventType === 'research_agent_start' || eventType === 'research_agent_complete') {
    if (role === 'clarify') return 'intake'
    if (role === 'scope') return 'scope'
    if (role === 'researcher') return 'branch_research'
    if (role === 'verifier') return 'verify'
    if (role === 'reporter') return 'report'
    if (role === 'supervisor') return phase === 'loop_decision' ? 'verify' : 'planning'
  }

  if (eventType === 'research_task_update') {
    if (validationStage || stage === 'claim_check' || stage === 'coverage_check') return 'verify'
    if (status === 'ready' && (stage === 'planned' || stage === 'dispatch')) return 'planning'
    return 'branch_research'
  }

  if (eventType === 'research_artifact_update') {
    if (artifactType === 'scope_draft' || artifactType === 'scope') return 'scope'
    if (artifactType === 'plan' || artifactType === 'outline') return 'planning'
    if (artifactType === 'validation_summary' || artifactType === 'section_review' || artifactType === 'section_certification') return 'verify'
    if (artifactType === 'final_report') return 'report'
    if (artifactType === 'evidence_bundle' || artifactType === 'branch_result' || artifactType === 'section_draft') return 'branch_research'
    if (validationStage || stage === 'claim_check' || stage === 'coverage_check') return 'verify'
    return 'branch_research'
  }

  if (eventType === 'research_decision') {
    if (decisionType === 'clarify_required') return 'intake'
    if (decisionType.startsWith('scope_')) return 'scope'
    if (
      decisionType === 'research_brief_ready' ||
      decisionType === 'outline_plan' ||
      decisionType === 'plan' ||
      decisionType === 'replan' ||
      decisionType === 'supervisor_plan' ||
      decisionType === 'supervisor_replan'
    ) {
      return 'planning'
    }
    if (
      decisionType === 'retry_branch' ||
      decisionType === 'verification_retry_requested' ||
      decisionType === 'review_updated' ||
      decisionType === 'review_passed' ||
      decisionType === 'coverage_gap_detected' ||
      decisionType === 'verification_passed'
    ) {
      return 'verify'
    }
    if (
      decisionType === 'report' ||
      decisionType === 'synthesize' ||
      decisionType === 'complete' ||
      decisionType === 'outline_ready' ||
      decisionType === 'final_claim_gate_passed' ||
      decisionType === 'final_claim_gate_blocked' ||
      decisionType === 'outline_gap_detected' ||
      decisionType === 'budget_stop' ||
      decisionType === 'stop'
    ) {
      return 'report'
    }
    if (decisionType === 'research') return 'branch_research'
    return 'planning'
  }

  return null
}

function branchLabelHint(payload: any): string {
  return text(payload?.title || payload?.objective_summary || payload?.query)
}

function resolveBranchId(payload: any, taskMetaById: Map<string, TaskMeta>): string | null {
  const directBranchId = text(payload?.section_id || payload?.branch_id)
  if (directBranchId) return directBranchId
  const taskId = text(payload?.task_id)
  if (taskId && taskMetaById.has(taskId)) {
    return taskMetaById.get(taskId)?.branchId || null
  }
  return null
}

function resolveIteration(
  payload: any,
  branchId: string | null,
  taskId: string | null,
  taskIterationById: Map<string, number>,
  branchIterationById: Map<string, number>,
  latestIteration: number | null,
): number | null {
  const directIteration = positiveNumber(payload?.iteration)
  if (directIteration !== null) return directIteration
  if (taskId && taskIterationById.has(taskId)) {
    return taskIterationById.get(taskId) || null
  }
  if (branchId && branchIterationById.has(branchId)) {
    return branchIterationById.get(branchId) || null
  }
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
): void {
  const artifactId = text(payload?.artifact_id)
  const sourceUrl = text(payload?.source_url)
  const sourceUrlsList = stringList(payload?.source_urls)
  const citationUrls = stringList(payload?.citation_urls)

  if (sourceUrl) sourceUrls.add(sourceUrl)
  for (const url of sourceUrlsList) {
    sourceUrls.add(url)
  }
  for (const url of citationUrls) {
    sourceUrls.add(url)
  }

  if (!artifactId) return

  if (artifactType === 'evidence_bundle') {
    evidenceIds.add(artifactId)
    documentIds.add(artifactId)
    return
  }
  if (artifactType === 'branch_result' || artifactType === 'section_draft') {
    synthesisIds.add(artifactId)
    return
  }
}

function shouldTrackBranchHistory(
  phase: DeepResearchPhaseKey,
  payload: any,
  branchId: string | null,
  taskId: string | null,
  taskKind: string,
): boolean {
  if (!branchId) return false
  if (taskKind === 'branch_research') return true
  if (taskId) return true
  const artifactType = text(payload?.artifact_type)
  if (BRANCH_ARTIFACT_TYPES.has(artifactType)) return true
  return phase === 'branch_research'
}

function createBranchAccumulator(branchId: string, order: number, label: string): BranchAccumulator {
  return {
    branchId,
    order,
    label,
    latestTimestamp: 0,
    latestHeadline: 'Branch updated',
    latestIteration: null,
    verificationState: '',
    sourceUrls: new Set<string>(),
    sourceIds: new Set<string>(),
    documentIds: new Set<string>(),
    evidenceIds: new Set<string>(),
    synthesisIds: new Set<string>(),
    iterations: new Map<string, BranchIterationAccumulator>(),
  }
}

function stageLabelForEvent(phase: DeepResearchPhaseKey, payload: any): string {
  const validationStage = text(payload?.validation_stage)
  if (validationStage) return formatStageLabel(validationStage)
  const stage = text(payload?.stage)
  if (stage) return formatStageLabel(stage)
  if (phase === 'verify') return 'Verify'
  if (phase === 'planning') return 'Planned'
  if (phase === 'branch_research') return 'Research'
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

function formatCount(value: number, singular: string, plural: string): string {
  return `${value} ${value === 1 ? singular : plural}`
}

function buildPhaseSummary(
  key: DeepResearchPhaseKey,
  events: CanonicalEvent[],
  branches: DeepResearchBranchSummary[],
  sourceCount: number,
  currentIteration: number | null,
): DeepResearchPhaseSummary | null {
  if (key === 'branch_research') {
    if (branches.length === 0) return null
    const uniqueIterations = new Set(
      branches.flatMap((branch) => branch.iterations.map((iteration) => iteration.iteration).filter(Boolean)),
    )
    const metrics = [
      formatCount(branches.length, 'branch', 'branches'),
      uniqueIterations.size > 0 ? formatCount(uniqueIterations.size, 'iteration', 'iterations') : '',
      sourceCount > 0 ? formatCount(sourceCount, 'source', 'sources') : '',
    ].filter(Boolean)
    return {
      key,
      title: PHASE_TITLES[key],
      summary: 'Continuous branch histories combine planning, research, retries, and verification updates.',
      metrics,
      highlights: [],
      branches,
    }
  }

  if (events.length === 0) return null

  const latestHeadline = events[events.length - 1]?.headline || 'Updated'
  const metrics: string[] = []

  if (key === 'planning') {
    const branchIds = new Set(events.map((event) => event.branchId).filter(Boolean))
    if (branchIds.size > 0) metrics.push(formatCount(branchIds.size, 'branch', 'branches'))
    if (currentIteration !== null) metrics.push(`Iteration ${currentIteration}`)
  }

  if (key === 'verify') {
    let passed = 0
    let retry = 0
    let failed = 0
    for (const event of events) {
      if (event.type !== 'research_artifact_update') continue
      const artifactType = text(event.payload?.artifact_type)
      if (artifactType !== 'validation_summary' && artifactType !== 'section_review' && artifactType !== 'section_certification') continue
      const validationStatus = text(
        event.payload?.validation_status || event.payload?.review_verdict || event.payload?.status || (artifactType === 'section_certification' ? 'passed' : ''),
      )
      if (validationStatus === 'passed') passed += 1
      else if (validationStatus === 'failed') failed += 1
      else if (validationStatus === 'retry') retry += 1
    }
    if (passed > 0) metrics.push(formatCount(passed, 'verified branch', 'verified branches'))
    if (retry > 0) metrics.push(formatCount(retry, 'retry', 'retries'))
    if (failed > 0) metrics.push(formatCount(failed, 'failed branch', 'failed branches'))
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
    branches: [],
  }
}

export function projectDeepResearchTimeline(events: ProcessEvent[]): DeepResearchTimelineProjection | null {
  const rawEvents = events.filter((event) => event.type !== 'done')
  const relevantEvents = rawEvents.filter(isDeepResearchEvent)
  const canonicalEvents = relevantEvents.filter((event) =>
    CANONICAL_EVENT_TYPES.has(event.type as CanonicalEventType),
  )

  if (canonicalEvents.length === 0) return null

  const taskMetaById = new Map<string, TaskMeta>()
  const taskIterationById = new Map<string, number>()
  const branchIterationById = new Map<string, number>()
  const branchOrderById = new Map<string, number>()
  const branchLabelById = new Map<string, string>()
  let latestIteration: number | null = null

  canonicalEvents.forEach((event, index) => {
    const payload = event.data || {}
    const taskId = text(payload?.task_id)
    const branchId = text(payload?.section_id || payload?.branch_id)
    const taskKind = text(payload?.task_kind)
    const labelHint = branchLabelHint(payload)
    const iteration = positiveNumber(payload?.iteration)

    if (taskId && branchId) {
      taskMetaById.set(taskId, {
        branchId,
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

    if (branchId) {
      if (!branchOrderById.has(branchId)) branchOrderById.set(branchId, index)
      if (labelHint && !branchLabelById.has(branchId)) branchLabelById.set(branchId, labelHint)
    }

    if (iteration !== null) {
      latestIteration = Math.max(latestIteration ?? 0, iteration)
      if (taskId) taskIterationById.set(taskId, iteration)
      if (branchId) branchIterationById.set(branchId, iteration)
    }
  })

  const phaseBuckets = new Map<DeepResearchPhaseKey, CanonicalEvent[]>()
  PHASE_ORDER.forEach((phase) => phaseBuckets.set(phase, []))

  const branchBuckets = new Map<string, BranchAccumulator>()
  const globalSourceUrls = new Set<string>()
  const globalSourceIds = new Set<string>()
  let suppressedEventCount = 0

  for (const event of rawEvents) {
    if (SUPPRESSED_DEFAULT_VIEW_TYPES.has(event.type)) {
      suppressedEventCount += 1
    }
  }

  for (const event of canonicalEvents) {
    const payload = event.data || {}
    const type = event.type as CanonicalEventType
    const taskId = text(payload?.task_id) || null
    const taskMeta = taskId ? taskMetaById.get(taskId) : undefined
    const branchId = resolveBranchId(payload, taskMetaById)
    const taskKind = text(payload?.task_kind) || taskMeta?.taskKind || ''
    const phase = resolvePhase(type, payload)

    if (!phase) continue

    const iteration = resolveIteration(
      payload,
      branchId,
      taskId,
      taskIterationById,
      branchIterationById,
      latestIteration,
    )

    if (iteration !== null) {
      latestIteration = Math.max(latestIteration ?? 0, iteration)
      if (taskId) taskIterationById.set(taskId, iteration)
      if (branchId) branchIterationById.set(branchId, iteration)
    }

    const canonicalEvent: CanonicalEvent = {
      event,
      type,
      payload,
      phase,
      branchId,
      taskId,
      taskKind,
      iteration,
      headline: describeCanonicalEvent(type, payload),
    }

    phaseBuckets.get(phase)?.push(canonicalEvent)

    const artifactType = text(payload?.artifact_type)
    updateSourceStats(
      payload,
      artifactType,
      globalSourceUrls,
      globalSourceIds,
      new Set<string>(),
      new Set<string>(),
      new Set<string>(),
    )

    if (!shouldTrackBranchHistory(phase, payload, branchId, taskId, taskKind)) {
      continue
    }

    if (!branchId) {
      continue
    }

    const branchOrder = branchOrderById.get(branchId) ?? branchBuckets.size
    const label = branchLabelById.get(branchId) || taskMeta?.label || ''
    const bucket = branchBuckets.get(branchId) || createBranchAccumulator(branchId, branchOrder, label)
    if (!branchBuckets.has(branchId)) {
      branchBuckets.set(branchId, bucket)
    }

    if (label && !bucket.label) {
      bucket.label = label
    }

    if (event.timestamp >= bucket.latestTimestamp) {
      bucket.latestTimestamp = event.timestamp
      bucket.latestHeadline = canonicalEvent.headline
      bucket.latestIteration = canonicalEvent.iteration
    }

    updateSourceStats(
      payload,
      artifactType,
      bucket.sourceUrls,
      bucket.sourceIds,
      bucket.documentIds,
      bucket.evidenceIds,
      bucket.synthesisIds,
    )

    if (artifactType === 'validation_summary' || artifactType === 'section_review' || artifactType === 'section_certification') {
      bucket.verificationState = describeArtifact(payload)
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
        attempt: positiveNumber(payload?.attempt),
        resumed: Boolean(payload?.resumed_from_checkpoint),
      }

    if (!bucket.iterations.has(iterationKey)) {
      bucket.iterations.set(iterationKey, iterationBucket)
    }

    const stageLabel = stageLabelForEvent(phase, payload)
    if (stageLabel) addUnique(iterationBucket.stageLabels, stageLabel)

    if (event.timestamp >= iterationBucket.latestTimestamp) {
      iterationBucket.latestTimestamp = event.timestamp
      iterationBucket.latestHeadline = canonicalEvent.headline
      iterationBucket.iteration = canonicalEvent.iteration
    }

    const attempt = positiveNumber(payload?.attempt)
    if (attempt !== null) {
      iterationBucket.attempt = Math.max(iterationBucket.attempt ?? 0, attempt)
    }
    iterationBucket.resumed = iterationBucket.resumed || Boolean(payload?.resumed_from_checkpoint)

    updateSourceStats(
      payload,
      artifactType,
      iterationBucket.sourceUrls,
      iterationBucket.sourceIds,
      iterationBucket.documentIds,
      iterationBucket.evidenceIds,
      iterationBucket.synthesisIds,
    )
  }

  const branchSummaries = [...branchBuckets.values()]
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
          const metrics = [
            iterationBucket.stageLabels.sort(compareStageLabels).join(' -> '),
            iterationBucket.sourceUrls.size > 0
              ? formatCount(iterationBucket.sourceUrls.size, 'source', 'sources')
              : iterationBucket.sourceIds.size > 0
                ? formatCount(iterationBucket.sourceIds.size, 'source', 'sources')
                : '',
            iterationBucket.documentIds.size > 0
              ? formatCount(iterationBucket.documentIds.size, 'document', 'documents')
              : '',
            iterationBucket.evidenceIds.size > 0
              ? formatCount(iterationBucket.evidenceIds.size, 'evidence item', 'evidence items')
              : '',
            iterationBucket.synthesisIds.size > 0
              ? formatCount(iterationBucket.synthesisIds.size, 'synthesis', 'syntheses')
              : '',
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
        bucket.evidenceIds.size > 0 ? formatCount(bucket.evidenceIds.size, 'evidence item', 'evidence items') : '',
        bucket.synthesisIds.size > 0 ? formatCount(bucket.synthesisIds.size, 'synthesis', 'syntheses') : '',
        bucket.verificationState,
      ].filter(Boolean)

      return {
        branchId: bucket.branchId,
        label: bucket.label || `Branch ${index + 1}`,
        headline: bucket.latestHeadline,
        metrics,
        latestIteration: bucket.latestIteration,
        iterations,
      }
    })

  const sourceCount = globalSourceUrls.size > 0 ? globalSourceUrls.size : globalSourceIds.size
  const phaseSummaries = PHASE_ORDER.map((phase) =>
    buildPhaseSummary(
      phase,
      phaseBuckets.get(phase) || [],
      branchSummaries,
      sourceCount,
      latestIteration,
    ),
  ).filter((phase): phase is DeepResearchPhaseSummary => phase !== null)

  const headerMetrics = [
    formatCount(phaseSummaries.length, 'phase', 'phases'),
    branchSummaries.length > 0 ? formatCount(branchSummaries.length, 'branch', 'branches') : '',
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
