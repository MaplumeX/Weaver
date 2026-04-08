import type { ProcessEvent } from '@/types/chat'

type DeepResearchCoreEventType =
  | 'research_agent_start'
  | 'research_agent_complete'
  | 'research_task_update'
  | 'research_artifact_update'
  | 'research_decision'

type UserFacingStage =
  | 'clarify'
  | 'scope'
  | 'planning'
  | 'researching'
  | 'supplementing'
  | 'drafting'
  | 'reviewing'
  | 'answering'

type SectionStatus =
  | 'planned'
  | 'researching'
  | 'supplementing'
  | 'drafting'
  | 'revising'
  | 'reviewing'
  | 'needs_more_research'
  | 'review_passed'
  | 'completed'
  | 'blocked'
  | 'failed'

export interface UserFacingResearchDetailItem {
  id: string
  label: string
  detail?: string
}

export interface UserFacingDeepResearchProgressProjection {
  summaryLabel: string
  metrics: string[]
  details: UserFacingResearchDetailItem[]
}

interface TaskMeta {
  sectionId: string
  title: string
}

interface SectionProgress {
  id: string
  title: string
  order: number
  status: SectionStatus
  updatedAt: number
}

type ResearchPayload = Record<string, unknown>

const CORE_DEEP_RESEARCH_EVENTS = new Set<DeepResearchCoreEventType>([
  'research_agent_start',
  'research_agent_complete',
  'research_task_update',
  'research_artifact_update',
  'research_decision',
])

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function positiveNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function toPayload(value: unknown): ResearchPayload {
  return value && typeof value === 'object' ? (value as ResearchPayload) : {}
}

function formatCount(value: number, noun: string): string {
  return `${value} 个${noun}`
}

function isDeepResearchEvent(event: ProcessEvent): boolean {
  return CORE_DEEP_RESEARCH_EVENTS.has(event.type as DeepResearchCoreEventType)
}

function getSectionTitle(payload: ResearchPayload): string {
  return text(payload?.title || payload?.objective_summary || payload?.query)
}

function getReviewOutcome(payload: ResearchPayload): string {
  return text(payload?.review_verdict || payload?.validation_status || payload?.status)
}

function resolveSectionId(payload: ResearchPayload, taskMetaById: Map<string, TaskMeta>): string | null {
  const directSectionId = text(payload?.section_id || payload?.branch_id)
  if (directSectionId) return directSectionId

  const taskId = text(payload?.task_id)
  if (taskId) {
    return taskMetaById.get(taskId)?.sectionId || taskId
  }

  return null
}

function ensureSection(
  sections: Map<string, SectionProgress>,
  sectionId: string,
  order: number,
  title: string,
): SectionProgress {
  const existing = sections.get(sectionId)
  if (existing) {
    if (title && !existing.title) existing.title = title
    return existing
  }

  const section: SectionProgress = {
    id: sectionId,
    title,
    order,
    status: 'planned',
    updatedAt: 0,
  }
  sections.set(sectionId, section)
  return section
}

function setSectionStatus(
  section: SectionProgress,
  status: SectionStatus,
  timestamp: number,
  title: string,
): void {
  if (title && !section.title) section.title = title
  if (timestamp >= section.updatedAt) {
    section.status = status
    section.updatedAt = timestamp
  }
}

function getSectionStatusLabel(status: SectionStatus): string {
  switch (status) {
    case 'researching':
      return '检索资料中'
    case 'supplementing':
      return '补充研究中'
    case 'drafting':
      return '整理章节中'
    case 'revising':
      return '修订中'
    case 'reviewing':
      return '复核中'
    case 'needs_more_research':
      return '待补充研究'
    case 'review_passed':
      return '复核通过'
    case 'completed':
      return '已完成'
    case 'blocked':
      return '研究受阻'
    case 'failed':
      return '研究失败'
    case 'planned':
    default:
      return '未开始'
  }
}

function getSummaryLabel(stage: UserFacingStage | 'completed', isThinking: boolean): string {
  if (!isThinking || stage === 'completed') return '已完成'

  switch (stage) {
    case 'clarify':
      return '正在明确问题'
    case 'scope':
      return '正在确认范围'
    case 'planning':
      return '正在制定研究计划'
    case 'researching':
      return '正在检索资料'
    case 'supplementing':
      return '正在补充研究'
    case 'drafting':
      return '正在整理章节'
    case 'reviewing':
      return '正在复核结论'
    case 'answering':
      return '正在生成最终答案'
    default:
      return '处理中'
  }
}

function getStageOnlyDetail(summaryLabel: string): UserFacingResearchDetailItem[] {
  if (summaryLabel === '已完成') {
    return [{ id: 'answer', label: '最终答案', detail: '已生成' }]
  }

  return [{ id: 'stage', label: '当前阶段', detail: summaryLabel }]
}

function resolveSectionStatusFromTaskUpdate(payload: ResearchPayload): SectionStatus | null {
  const status = text(payload?.status)
  const stage = text(payload?.stage)
  const taskKind = text(payload?.task_kind)
  const attempt = positiveNumber(payload?.attempt)

  if (status === 'ready') {
    if (attempt !== null && attempt > 1) return 'needs_more_research'
    if (taskKind === 'section_revision' || stage === 'revision') return 'revising'
    return 'planned'
  }

  if (status === 'in_progress') {
    if (taskKind === 'section_revision' || stage === 'revision') return 'revising'
    if (stage === 'synthesize') return 'drafting'
    if (attempt !== null && attempt > 1) return 'supplementing'
    return 'researching'
  }

  if (status === 'completed') {
    if (taskKind === 'section_revision' || stage === 'revision') return 'reviewing'
    return 'reviewing'
  }

  if (status === 'blocked') return 'blocked'
  if (status === 'failed') return 'failed'

  return null
}

function resolveSectionStatusFromArtifact(payload: ResearchPayload): SectionStatus | null {
  const artifactType = text(payload?.artifact_type)
  const reviewOutcome = getReviewOutcome(payload)

  if (artifactType === 'evidence_bundle') return 'researching'
  if (artifactType === 'section_draft' || artifactType === 'branch_result') return 'drafting'

  if (artifactType === 'section_review' || artifactType === 'validation_summary') {
    if (reviewOutcome === 'request_research' || reviewOutcome === 'retry') return 'needs_more_research'
    if (reviewOutcome === 'revise_section') return 'revising'
    if (reviewOutcome === 'accept_section' || reviewOutcome === 'passed') return 'review_passed'
    if (reviewOutcome === 'block_section') return 'blocked'
    if (reviewOutcome === 'failed') return 'failed'
    return 'reviewing'
  }

  if (artifactType === 'section_certification') return 'completed'

  return null
}

function resolveStageFromTaskUpdate(payload: ResearchPayload): UserFacingStage | null {
  const status = text(payload?.status)
  const stage = text(payload?.stage)
  const taskKind = text(payload?.task_kind)
  const attempt = positiveNumber(payload?.attempt)

  if (status === 'ready') return 'planning'
  if (status !== 'in_progress') return null

  if (taskKind === 'section_revision' || stage === 'revision') return 'drafting'
  if (stage === 'synthesize') return 'drafting'
  if (attempt !== null && attempt > 1) return 'supplementing'
  return 'researching'
}

function resolveStageFromArtifact(payload: ResearchPayload): UserFacingStage | null {
  const artifactType = text(payload?.artifact_type)
  const reviewOutcome = getReviewOutcome(payload)

  if (artifactType === 'scope_draft' || artifactType === 'scope') return 'scope'
  if (artifactType === 'outline' || artifactType === 'plan') return 'planning'
  if (artifactType === 'evidence_bundle') return 'researching'
  if (artifactType === 'section_draft' || artifactType === 'branch_result') return 'drafting'

  if (artifactType === 'section_review' || artifactType === 'validation_summary') {
    if (reviewOutcome === 'request_research' || reviewOutcome === 'retry') return 'reviewing'
    if (reviewOutcome === 'revise_section') return 'drafting'
    return 'reviewing'
  }

  if (artifactType === 'section_certification') return 'reviewing'
  if (artifactType === 'final_report') return 'answering'

  return null
}

function resolveStageFromDecision(payload: ResearchPayload): UserFacingStage | null {
  const decisionType = text(payload?.decision_type)

  if (decisionType === 'clarify_required') return 'clarify'
  if (decisionType.startsWith('scope_') || decisionType === 'research_brief_ready') return 'scope'

  if (
    decisionType === 'outline_plan' ||
    decisionType === 'plan' ||
    decisionType === 'replan' ||
    decisionType === 'supervisor_plan' ||
    decisionType === 'supervisor_replan' ||
    decisionType === 'research'
  ) {
    return 'planning'
  }

  if (
    decisionType === 'retry_branch' ||
    decisionType === 'verification_retry_requested' ||
    decisionType === 'review_updated' ||
    decisionType === 'review_passed' ||
    decisionType === 'coverage_gap_detected' ||
    decisionType === 'verification_passed' ||
    decisionType === 'final_claim_gate_passed' ||
    decisionType === 'final_claim_gate_review_needed' ||
    decisionType === 'final_claim_gate_blocked'
  ) {
    return 'reviewing'
  }

  if (
    decisionType === 'report' ||
    decisionType === 'report_partial' ||
    decisionType === 'outline_ready' ||
    decisionType === 'outline_partial' ||
    decisionType === 'synthesize' ||
    decisionType === 'complete'
  ) {
    return 'answering'
  }

  return null
}

function resolveStageFromAgentLifecycle(payload: ResearchPayload): UserFacingStage | null {
  const role = text(payload?.role)
  const stage = text(payload?.stage)
  const validationStage = text(payload?.validation_stage)
  const attempt = positiveNumber(payload?.attempt)

  if (role === 'clarify') return 'clarify'
  if (role === 'scope') return 'scope'
  if (role === 'supervisor') return 'planning'
  if (role === 'reporter') return 'answering'
  if (role === 'reviewer' || role === 'verifier') return 'reviewing'
  if (role === 'revisor') return 'drafting'
  if (role === 'researcher') {
    if (stage === 'synthesize') return 'drafting'
    if (validationStage === 'claim_check' || validationStage === 'coverage_check') return 'reviewing'
    if (attempt !== null && attempt > 1) return 'supplementing'
    return 'researching'
  }

  return null
}

function resolveUserFacingStage(eventType: string, payload: ResearchPayload): UserFacingStage | null {
  if (eventType === 'research_task_update') return resolveStageFromTaskUpdate(payload)
  if (eventType === 'research_artifact_update') return resolveStageFromArtifact(payload)
  if (eventType === 'research_decision') return resolveStageFromDecision(payload)
  if (eventType === 'research_agent_start' || eventType === 'research_agent_complete') {
    return resolveStageFromAgentLifecycle(payload)
  }
  return null
}

function buildSectionDetails(sections: SectionProgress[]): UserFacingResearchDetailItem[] {
  const pendingCount = sections.filter((section) => section.status === 'planned').length
  const activeSections = sections.filter((section) => section.status !== 'planned')

  const details = activeSections.map((section, index) => ({
    id: section.id,
    label: section.title || `章节 ${index + 1}`,
    detail: getSectionStatusLabel(section.status),
  }))

  if (pendingCount > 0) {
    details.push({
      id: 'pending-sections',
      label: '待开始章节',
      detail: `还有 ${pendingCount} 个章节尚未开始`,
    })
  }

  return details
}

export function projectUserFacingDeepResearchProgress(
  events: ProcessEvent[],
  isThinking: boolean,
): UserFacingDeepResearchProgressProjection | null {
  const relevantEvents = events.filter((event) => event.type !== 'done' && isDeepResearchEvent(event))
  if (relevantEvents.length === 0) return null

  const taskMetaById = new Map<string, TaskMeta>()
  const sectionOrderById = new Map<string, number>()
  const sectionTitleById = new Map<string, string>()

  relevantEvents.forEach((event, index) => {
    const payload = toPayload(event.data)
    const taskId = text(payload?.task_id)
    const sectionId = text(payload?.section_id || payload?.branch_id)
    const title = getSectionTitle(payload)

    if (taskId && sectionId) {
      taskMetaById.set(taskId, { sectionId, title })
    } else if (taskId && title && taskMetaById.has(taskId)) {
      const existing = taskMetaById.get(taskId)
      if (existing && !existing.title) {
        taskMetaById.set(taskId, { ...existing, title })
      }
    }

    if (sectionId) {
      if (!sectionOrderById.has(sectionId)) sectionOrderById.set(sectionId, index)
      if (title && !sectionTitleById.has(sectionId)) sectionTitleById.set(sectionId, title)
    }
  })

  const sections = new Map<string, SectionProgress>()
  let sawClarify = false
  let sawScope = false
  let sawPlanning = false
  let sawReviewing = false
  let sawAnswering = false

  for (const event of relevantEvents) {
    const payload = toPayload(event.data)
    const stage = resolveUserFacingStage(event.type, payload)

    if (stage === 'clarify') sawClarify = true
    if (stage === 'scope') sawScope = true
    if (stage === 'planning') sawPlanning = true
    if (stage === 'reviewing') sawReviewing = true
    if (stage === 'answering') sawAnswering = true

    const sectionId = resolveSectionId(payload, taskMetaById)
    if (!sectionId) continue

    const order = sectionOrderById.get(sectionId) ?? sections.size
    const title = getSectionTitle(payload) || sectionTitleById.get(sectionId) || taskMetaById.get(text(payload?.task_id))?.title || ''
    const section = ensureSection(sections, sectionId, order, title)

    let nextStatus: SectionStatus | null = null
    if (event.type === 'research_task_update') {
      nextStatus = resolveSectionStatusFromTaskUpdate(payload)
    } else if (event.type === 'research_artifact_update') {
      nextStatus = resolveSectionStatusFromArtifact(payload)
    }

    if (nextStatus) {
      setSectionStatus(section, nextStatus, event.timestamp, title)
    }
  }

  const orderedSections = [...sections.values()].sort(
    (left, right) => left.order - right.order || left.updatedAt - right.updatedAt,
  )

  const hasSectionWork = orderedSections.some((section) => section.status !== 'planned')
  const hasSupplementing = orderedSections.some((section) => section.status === 'supplementing')
  const hasResearching = orderedSections.some((section) => section.status === 'researching')
  const hasDrafting = orderedSections.some(
    (section) => section.status === 'drafting' || section.status === 'revising',
  )
  const hasReviewingSections = orderedSections.some((section) =>
    ['reviewing', 'needs_more_research', 'review_passed'].includes(section.status),
  )
  const completedCount = orderedSections.filter((section) => section.status === 'completed').length
  const totalCount = orderedSections.length

  let summaryStage: UserFacingStage | 'completed' = 'clarify'
  if (!isThinking) {
    summaryStage = 'completed'
  } else if (hasSupplementing) {
    summaryStage = 'supplementing'
  } else if (hasResearching) {
    summaryStage = 'researching'
  } else if (hasDrafting) {
    summaryStage = 'drafting'
  } else if (sawAnswering) {
    summaryStage = 'answering'
  } else if (hasReviewingSections || sawReviewing) {
    summaryStage = 'reviewing'
  } else if (totalCount > 0 || sawPlanning) {
    summaryStage = 'planning'
  } else if (sawScope) {
    summaryStage = 'scope'
  } else if (sawClarify) {
    summaryStage = 'clarify'
  }

  const metrics: string[] = []
  if (totalCount > 0) {
    if (hasSectionWork || !isThinking) {
      metrics.push(`${completedCount}/${totalCount} 章节完成`)
    } else {
      metrics.push(`已规划 ${formatCount(totalCount, '章节')}`)
    }
  }

  const details = buildSectionDetails(orderedSections)

  return {
    summaryLabel: getSummaryLabel(summaryStage, isThinking),
    metrics,
    details: details.length > 0 ? details : getStageOnlyDetail(getSummaryLabel(summaryStage, isThinking)),
  }
}

export function getDeepResearchAutoStatusText(eventType: string, payload: unknown): string | null {
  const normalizedPayload = toPayload(payload)
  const title = getSectionTitle(normalizedPayload)
  const decisionType = text(normalizedPayload?.decision_type)
  const artifactType = text(normalizedPayload?.artifact_type)
  const status = text(normalizedPayload?.status)
  const reviewOutcome = getReviewOutcome(normalizedPayload)

  if (eventType === 'research_task_update') {
    const sectionStatus = resolveSectionStatusFromTaskUpdate(normalizedPayload)
    if (status === 'ready') return `多 Agent 调研：已规划章节 · ${title || '未命名章节'}`
    if (sectionStatus === 'supplementing') return `多 Agent 调研：正在补充研究 · ${title || '未命名章节'}`
    if (sectionStatus === 'researching') return `多 Agent 调研：正在检索资料 · ${title || '未命名章节'}`
    if (sectionStatus === 'drafting' || sectionStatus === 'revising') {
      return `多 Agent 调研：正在整理章节 · ${title || '未命名章节'}`
    }
    if (sectionStatus === 'completed') return `多 Agent 调研：章节已完成 · ${title || '未命名章节'}`
    if (sectionStatus === 'blocked' || sectionStatus === 'failed') {
      return `多 Agent 调研：章节研究受阻 · ${title || '未命名章节'}`
    }
  }

  if (eventType === 'research_agent_start' || eventType === 'research_agent_complete') {
    const stage = resolveStageFromAgentLifecycle(normalizedPayload)
    if (stage === 'clarify') return '多 Agent 调研：正在明确问题'
    if (stage === 'scope') return '多 Agent 调研：正在确认范围'
    if (stage === 'planning') return '多 Agent 调研：正在制定研究计划'
    if (stage === 'reviewing') return '多 Agent 调研：正在复核结论'
    if (stage === 'answering') return '多 Agent 调研：正在生成最终答案'
    if (stage === 'researching') return `多 Agent 调研：正在检索资料 · ${title || '当前章节'}`
    if (stage === 'supplementing') return `多 Agent 调研：正在补充研究 · ${title || '当前章节'}`
    if (stage === 'drafting') return `多 Agent 调研：正在整理章节 · ${title || '当前章节'}`
  }

  if (eventType === 'research_artifact_update') {
    if (artifactType === 'scope_draft') {
      if (status === 'revision_requested') return '多 Agent 调研：需要调整研究范围'
      if (status === 'approved') return '多 Agent 调研：研究范围已确认'
      return '多 Agent 调研：正在确认范围'
    }
    if (artifactType === 'scope') return '多 Agent 调研：研究范围已确认'
    if (artifactType === 'outline' || artifactType === 'plan') return '多 Agent 调研：已规划研究章节'
    if (artifactType === 'evidence_bundle') {
      return `多 Agent 调研：已收集章节资料 · ${title || '当前章节'}`
    }
    if (artifactType === 'section_draft' || artifactType === 'branch_result') {
      return `多 Agent 调研：正在整理章节 · ${title || '当前章节'}`
    }
    if (artifactType === 'section_review' || artifactType === 'validation_summary') {
      if (reviewOutcome === 'request_research' || reviewOutcome === 'retry') {
        return `多 Agent 调研：需要补充研究 · ${title || '当前章节'}`
      }
      if (reviewOutcome === 'accept_section' || reviewOutcome === 'passed') {
        return `多 Agent 调研：章节已通过复核${title ? ` · ${title}` : ''}`
      }
      return `多 Agent 调研：正在复核结论${title ? ` · ${title}` : ''}`
    }
    if (artifactType === 'section_certification') {
      return `多 Agent 调研：章节已完成${title ? ` · ${title}` : ''}`
    }
    if (artifactType === 'final_report') return '多 Agent 调研：已生成最终答案'
  }

  if (eventType === 'research_decision') {
    if (decisionType === 'clarify_required') return '多 Agent 调研：需要补充研究问题'
    if (
      decisionType === 'scope_ready' ||
      decisionType === 'scope_revision_requested' ||
      decisionType === 'scope_approved' ||
      decisionType === 'research_brief_ready'
    ) {
      return '多 Agent 调研：研究范围已确认'
    }
    if (
      decisionType === 'outline_plan' ||
      decisionType === 'plan' ||
      decisionType === 'replan' ||
      decisionType === 'supervisor_plan' ||
      decisionType === 'supervisor_replan'
    ) {
      return '多 Agent 调研：正在制定研究计划'
    }
    if (
      decisionType === 'retry_branch' ||
      decisionType === 'verification_retry_requested' ||
      decisionType === 'coverage_gap_detected'
    ) {
      return '多 Agent 调研：需要补充研究'
    }
    if (
      decisionType === 'review_updated' ||
      decisionType === 'review_passed' ||
      decisionType === 'verification_passed' ||
      decisionType === 'final_claim_gate_review_needed'
    ) {
      return '多 Agent 调研：正在复核结论'
    }
    if (decisionType === 'final_claim_gate_passed') return '多 Agent 调研：最终结论已复核'
    if (decisionType === 'final_claim_gate_blocked') return '多 Agent 调研：最终结论存在冲突'
    if (
      decisionType === 'report' ||
      decisionType === 'report_partial' ||
      decisionType === 'outline_ready' ||
      decisionType === 'outline_partial' ||
      decisionType === 'synthesize' ||
      decisionType === 'complete'
    ) {
      return '多 Agent 调研：正在生成最终答案'
    }
  }

  return null
}
