import { projectUserFacingDeepResearchProgress } from '@/lib/deep-research-progress'
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
  const progress = projectUserFacingDeepResearchProgress(events, isThinking)
  if (!progress) return null

  const hasError = hasEvent(events, 'error')
  const hasInterrupt = hasEvent(events, 'interrupt', 'cancelled')
  const tone: ProcessSummaryTone = hasError
    ? 'error'
    : hasInterrupt
      ? 'interrupted'
      : isThinking
        ? 'running'
        : 'completed'

  return {
    summary: {
      label: hasError ? '处理失败' : hasInterrupt ? '已中断' : progress.summaryLabel,
      tone,
      metrics: progress.metrics,
    },
    details: progress.details as ProcessDisplayItem[],
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
