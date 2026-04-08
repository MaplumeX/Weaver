import { projectDeepResearchTimeline } from '@/lib/deep-research-timeline'
import type { ProcessEvent, ToolInvocation } from '@/types/chat'

export type ProcessSummaryTone = 'running' | 'completed' | 'error' | 'interrupted'

export interface ProcessDisplayItem {
  id: string
  label: string
  detail?: string
  tone?: ProcessSummaryTone
}

export interface ProcessDisplayProjection {
  summary: {
    label: string
    tone: ProcessSummaryTone
    metrics: string[]
  }
  details: ProcessDisplayItem[]
}

const TECHNICAL_STATUS_PATTERNS = [
  /^Initializing research agent/i,
  /^Running agent \(tool-calling\)$/i,
]

function countTools(tools: ToolInvocation[]): number {
  return tools.filter((tool) => tool.state === 'running' || tool.state === 'completed').length
}

function hasEvent(events: ProcessEvent[], ...types: string[]): boolean {
  return events.some((event) => types.includes(event.type))
}

function summarizeDeepResearch(
  events: ProcessEvent[],
  isThinking: boolean,
): ProcessDisplayProjection | null {
  const timeline = projectDeepResearchTimeline(events)
  if (!timeline) return null

  const latestTask = [...events]
    .reverse()
    .find((event) => event.type === 'research_task_update' && event.data?.status === 'in_progress')
  const latestArtifact = [...events]
    .reverse()
    .find((event) => event.type === 'research_artifact_update')

  let label = isThinking ? '处理中' : '已完成'
  if (latestTask?.data?.stage === 'search') {
    label = '正在检索资料'
  } else if (
    latestTask?.data?.stage === 'synthesize' ||
    latestArtifact?.data?.artifact_type === 'section_draft'
  ) {
    label = '正在整理答案'
  } else if (isThinking) {
    label = '处理中'
  }

  const details: ProcessDisplayItem[] = []
  if (
    events.some(
      (event) =>
        event.type === 'research_decision' && event.data?.decision_type === 'scope_approved',
    )
  ) {
    details.push({ id: 'scope', label: '研究范围', detail: '已确认范围并进入正式研究' })
  }
  if (latestTask?.data?.stage === 'search') {
    details.push({
      id: 'search',
      label: '检索资料',
      detail: String(latestTask.data?.title || '当前章节'),
    })
  }
  if (latestArtifact?.data?.artifact_type === 'section_draft') {
    details.push({
      id: 'synthesize',
      label: '汇总信息',
      detail: String(latestArtifact.data?.title || '生成章节草稿'),
    })
  }

  return {
    summary: {
      label,
      tone: isThinking ? 'running' : 'completed',
      metrics: timeline.headerMetrics,
    },
    details,
  }
}

function summarizeGeneric(
  events: ProcessEvent[],
  tools: ToolInvocation[],
  isThinking: boolean,
): ProcessDisplayProjection {
  const runningTools = tools.filter((tool) => tool.state === 'running').length
  const toolCount = countTools(tools)
  const hasToolActivity =
    runningTools > 0 || hasEvent(events, 'tool')
  const hasSearchActivity = hasEvent(events, 'search', 'research_node_start', 'research_node_complete')
  const hasError = hasEvent(events, 'error')
  const hasInterrupt = hasEvent(events, 'interrupt', 'cancelled')
  const hasCompletion = hasEvent(events, 'completion', 'done')

  let label = '处理中'
  let tone: ProcessSummaryTone = 'running'

  if (hasError) {
    label = '处理失败'
    tone = 'error'
  } else if (hasInterrupt) {
    label = '已中断'
    tone = 'interrupted'
  } else if (hasToolActivity) {
    label = '正在调用工具'
  } else if (hasSearchActivity) {
    label = '正在检索资料'
  } else if (!isThinking && hasCompletion) {
    label = '已完成'
    tone = 'completed'
  } else if (!isThinking) {
    label = '已完成'
    tone = 'completed'
  }

  const details: ProcessDisplayItem[] = []
  if (
    events.some(
      (event) =>
        event.type === 'thinking' ||
        TECHNICAL_STATUS_PATTERNS.some((pattern) => pattern.test(String(event.data?.text || ''))),
    )
  ) {
    details.push({ id: 'analyze', label: '分析问题' })
  }
  if (hasSearchActivity) {
    details.push({ id: 'search', label: '检索资料' })
  }
  if (hasToolActivity) {
    const detail = runningTools > 0 ? `${runningTools} 个工具仍在运行` : `${toolCount} 个工具已调用`
    details.push({ id: 'tools', label: '调用工具', detail })
  }
  if (!isThinking && hasCompletion) {
    details.push({ id: 'answer', label: '生成回答' })
  }

  return {
    summary: {
      label,
      tone,
      metrics: toolCount > 0 ? [`${toolCount} 个工具`] : [],
    },
    details,
  }
}

export function projectProcessDisplay({
  events,
  tools,
  isThinking,
}: {
  events: ProcessEvent[]
  tools?: ToolInvocation[]
  isThinking: boolean
}): ProcessDisplayProjection {
  const nextTools = tools || []
  return summarizeDeepResearch(events, isThinking) || summarizeGeneric(events, nextTools, isThinking)
}

export function buildProcessHeaderText({
  projection,
  durationLabel,
}: {
  projection: ProcessDisplayProjection
  durationLabel?: string
}): string {
  return [projection.summary.label, durationLabel, ...projection.summary.metrics]
    .filter(Boolean)
    .join(' · ')
}
