'use client'

import React, { useEffect, useMemo, useState } from 'react'
import {
  Bot,
  ChevronDown,
  Loader2,
  CheckCircle2,
  Search,
  Wrench,
  FileText,
  Image as ImageIcon,
  Sparkles,
  ListTodo,
  TreePine,
  ShieldCheck,
} from 'lucide-react'
import { getRetainedProcessEvents } from '@/lib/chat-stream-state'
import {
  DeepResearchPhaseSummary,
  DeepResearchTimelineProjection,
  projectDeepResearchTimeline,
} from '@/lib/deep-research-timeline'
import { cn } from '@/lib/utils'
import { ProcessEvent, RunMetrics, ToolInvocation } from '@/types/chat'

interface ThinkingProcessProps {
  tools?: ToolInvocation[]
  events?: ProcessEvent[]
  metrics?: RunMetrics
  isThinking: boolean
  startedAt?: number
  completedAt?: number
}

export function ThinkingProcess({
  tools = [],
  events = [],
  metrics,
  isThinking,
  startedAt,
  completedAt,
}: ThinkingProcessProps) {
  const [open, setOpen] = useState(false)
  const [rawOpen, setRawOpen] = useState(false)
  const [userToggled, setUserToggled] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const hasDetails = tools.length > 0 || events.length > 0

  useEffect(() => {
    if (!isThinking) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [isThinking])

  const durationMs = useMemo(() => {
    const metricDuration = typeof metrics?.duration_ms === 'number' ? metrics.duration_ms : undefined
    if (metricDuration && metricDuration > 0) return metricDuration
    if (!startedAt) return undefined

    const end = isThinking ? now : completedAt
    if (typeof end === 'number' && end >= startedAt) return end - startedAt
    return undefined
  }, [metrics?.duration_ms, startedAt, completedAt, isThinking, now])

  const durationLabel = useMemo(() => {
    if (!durationMs || durationMs <= 0) return ''
    const seconds = Math.max(1, Math.round(durationMs / 1000))
    return `${seconds}s`
  }, [durationMs])

  const deepResearchTimeline = useMemo(() => {
    return projectDeepResearchTimeline(events)
  }, [events])

  const stepCount = useMemo(() => {
    if (tools.length > 0) return tools.length
    const stepTypes = new Set([
      'search',
      'tool',
      'tool_start',
      'tool_result',
      'tool_error',
      'screenshot',
      'research_node_start',
      'research_node_complete',
      'research_agent_start',
      'research_agent_complete',
      'research_task_update',
      'research_artifact_update',
      'research_decision',
    ])
    return events.filter((e) => stepTypes.has(e.type)).length
  }, [tools.length, events])

  const displayEvents = useMemo(() => {
    return getRetainedProcessEvents(events)
  }, [events])

  useEffect(() => {
    if (userToggled) return
    if (isThinking) setOpen(true)
    else setOpen(false)
  }, [isThinking, userToggled])

  useEffect(() => {
    if (!deepResearchTimeline) setRawOpen(false)
  }, [deepResearchTimeline])

  if (!hasDetails && !isThinking) return null

  const progressLabel = deepResearchTimeline
    ? deepResearchTimeline.headerMetrics.join(' · ')
    : stepCount
      ? `${stepCount} steps`
      : ''

  const headerText = isThinking
    ? `Thinking…${durationLabel ? ` · ${durationLabel}` : ''}${progressLabel ? ` · ${progressLabel}` : ''}`
    : `Thought${durationLabel ? ` for ${durationLabel}` : ''}${progressLabel ? ` · ${progressLabel}` : ''}`

  const toggle = () => {
    if (!hasDetails) return
    setUserToggled(true)
    setOpen((v) => !v)
  }

  return (
    <div className="w-full my-2">
      <button
        type="button"
        onClick={toggle}
        className={cn(
          'group inline-flex items-center gap-2 rounded-full px-3 py-1.5',
          'text-sm text-muted-foreground hover:text-foreground',
          'hover:bg-muted/40 transition-colors duration-150',
          !hasDetails && 'cursor-default hover:bg-transparent'
        )}
        aria-expanded={open}
      >
        <span
          className={cn(
            'flex h-4 w-4 items-center justify-center',
            isThinking ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {isThinking ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
        </span>
        <span className="font-medium">{headerText}</span>
        {hasDetails && (
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-200 ease-out',
              open ? 'rotate-180' : 'rotate-0'
            )}
          />
        )}
      </button>

      {hasDetails && (
        <div
          className="grid transition-[grid-template-rows] duration-200 ease-out"
            style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="mt-2 pl-4 ml-2 border-l border-border/60 text-sm text-muted-foreground">
              <div className="space-y-2 py-1">
                {deepResearchTimeline ? (
                  <DeepResearchTimelineView
                    timeline={deepResearchTimeline}
                    rawOpen={rawOpen}
                    onToggleRaw={() => setRawOpen((value) => !value)}
                  />
                ) : displayEvents.length > 0 ? (
                  displayEvents.map((ev) => <EventRow key={ev.id} ev={ev} />)
                ) : (
                  <FallbackTools tools={tools} />
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DeepResearchTimelineView({
  timeline,
  rawOpen,
  onToggleRaw,
}: {
  timeline: DeepResearchTimelineProjection
  rawOpen: boolean
  onToggleRaw: () => void
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-border/70 bg-muted/20 px-3 py-2">
        <div className="text-[13px] leading-6 text-foreground/80">
          {timeline.headerMetrics.join(' · ')}
        </div>
        {timeline.suppressedEventCount > 0 ? (
          <div className="text-xs text-muted-foreground">
            Default view collapses {timeline.suppressedEventCount} low-level events into phase and section summaries.
          </div>
        ) : null}
      </div>

      {timeline.phases.map((phase) => (
        <DeepResearchPhaseCard key={phase.key} phase={phase} />
      ))}

      <div className="rounded-2xl border border-border/70 bg-background/70">
        <button
          type="button"
          onClick={onToggleRaw}
          className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
          aria-expanded={rawOpen}
        >
          <div>
            <div className="font-medium text-foreground/80">Original Stream Events</div>
            <div className="text-xs text-muted-foreground">
              {timeline.rawEventCount} full-fidelity events remain available for drilldown.
            </div>
          </div>
          <ChevronDown
            className={cn(
              'h-4 w-4 shrink-0 transition-transform duration-200 ease-out',
              rawOpen ? 'rotate-180' : 'rotate-0'
            )}
          />
        </button>

        {rawOpen ? (
          <div className="space-y-2 border-t border-border/60 px-3 py-3">
            {timeline.rawEvents.map((event) => (
              <EventRow key={event.id} ev={event} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function DeepResearchPhaseCard({ phase }: { phase: DeepResearchPhaseSummary }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium text-foreground/90">{phase.title}</div>
          <div className="mt-1 text-[13px] leading-6 text-muted-foreground">{phase.summary}</div>
        </div>
      </div>

      {phase.metrics.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {phase.metrics.map((metric) => (
            <span
              key={metric}
              className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground"
            >
              {metric}
            </span>
          ))}
        </div>
      ) : null}

      {phase.highlights.length > 0 ? (
        <div className="mt-3 space-y-2">
          {phase.highlights.map((highlight) => (
            <div key={highlight.id} className="rounded-lg bg-muted/20 px-3 py-2">
              <div className="text-[13px] font-medium leading-6 text-foreground/85">{highlight.headline}</div>
              {highlight.detail ? (
                <div className="mt-1 text-[13px] leading-6 text-muted-foreground">{highlight.detail}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {phase.sections.length > 0 ? (
        <div className="mt-3 space-y-3">
          {phase.sections.map((section) => (
            <div key={section.sectionId} className="rounded-xl border border-border/60 bg-muted/20 px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-foreground/90">{section.label}</div>
                  <div className="mt-1 text-[13px] leading-6 text-muted-foreground">{section.headline}</div>
                </div>
                {section.latestIteration !== null ? (
                  <span className="rounded-full bg-background px-2 py-1 text-[11px] font-medium text-muted-foreground">
                    Iteration {section.latestIteration}
                  </span>
                ) : null}
              </div>

              {section.metrics.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {section.metrics.map((metric) => (
                    <span
                      key={metric}
                      className="rounded-full bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground"
                    >
                      {metric}
                    </span>
                  ))}
                </div>
              ) : null}

              <div className="mt-3 space-y-2">
                {section.iterations.map((iteration) => (
                  <div key={`${section.sectionId}-${iteration.label}`} className="rounded-lg bg-background/80 px-3 py-2">
                    <div className="font-medium text-foreground/80">{iteration.label}</div>
                    <div className="mt-1 text-[13px] leading-6 text-muted-foreground">{iteration.headline}</div>
                    {iteration.metrics.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {iteration.metrics.map((metric) => (
                          <span
                            key={metric}
                            className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                          >
                            {metric}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function EventRow({ ev }: { ev: ProcessEvent }) {
  const kind = ev.type

  if (kind === 'status') {
    return (
      <div className="flex items-start gap-2">
        <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
        <div className="min-w-0">
          <div className="truncate">{String(ev.data?.text || 'Working…')}</div>
        </div>
      </div>
    )
  }

  if (kind === 'thinking') {
    const text = String(ev.data?.text || '').trim()
    if (!text) return null
    return (
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="whitespace-pre-wrap break-words text-[13px] leading-6 text-foreground/80">
            {text}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'task_update') {
    const title = String(ev.data?.title || '').trim()
    const status = String(ev.data?.status || '').trim()
    const progress = ev.data?.progress
    const label = title || String(ev.data?.id || 'task')

    return (
      <div className="flex items-start gap-2">
        <ListTodo className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Task</span>
            <span className="ml-2">{label}</span>
            {status ? (
              <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
          {typeof progress === 'number' ? (
            <div className="text-xs text-muted-foreground">{Math.round(progress)}%</div>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_agent_start' || kind === 'research_agent_complete') {
    const role = String(ev.data?.role || '').trim() || 'agent'
    const agentId = String(ev.data?.agent_id || ev.data?.agentId || '').trim()
    const phase = String(ev.data?.phase || '').trim()
    const stage = String(ev.data?.stage || '').trim()
    const validationStage = String(ev.data?.validation_stage || '').trim()
    const taskKind = String(ev.data?.task_kind || '').trim()
    const taskId = String(ev.data?.task_id || '').trim()
    const nodeId = String(ev.data?.node_id || '').trim()
    const sectionId = String(ev.data?.section_id || ev.data?.branch_id || '').trim()
    const attempt = typeof ev.data?.attempt === 'number' ? ev.data.attempt : undefined
    const status = kind === 'research_agent_complete' ? String(ev.data?.status || '').trim() : 'running'
    const summary = String(ev.data?.summary || '').trim()

    return (
      <div className="flex items-start gap-2">
        <Bot className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">{role}</span>
            {agentId ? <span className="ml-2 font-mono text-[12px]">{agentId}</span> : null}
            <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {status}
            </span>
          </div>
	          {(phase || taskId) ? (
	            <div className="truncate text-xs text-muted-foreground">
	              {[
	                phase || null,
	                stage ? `stage ${stage}` : null,
                validationStage ? `validation ${validationStage}` : null,
                taskKind ? `kind ${taskKind}` : null,
                taskId ? `task ${taskId}` : null,
	                sectionId ? `section ${sectionId}` : null,
	                nodeId ? `node ${nodeId}` : null,
	                attempt && attempt > 1 ? `attempt ${attempt}` : null,
	              ]
	                .filter(Boolean)
	                .join(' · ')}
	            </div>
	          ) : null}
          {summary ? <div className="line-clamp-2 text-xs text-muted-foreground">{summary}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_task_update') {
    const taskId = String(ev.data?.task_id || '').trim()
    const title = String(ev.data?.title || ev.data?.objective_summary || ev.data?.query || taskId || 'task').trim()
    const status = String(ev.data?.status || '').trim()
    const query = String(ev.data?.query || '').trim()
    const taskKind = String(ev.data?.task_kind || '').trim()
    const stage = String(ev.data?.stage || '').trim()
    const priority = ev.data?.priority
    const sectionId = String(ev.data?.section_id || ev.data?.branch_id || '').trim()
    const attempt = typeof ev.data?.attempt === 'number' ? ev.data.attempt : undefined

    return (
      <div className="flex items-start gap-2">
        <ListTodo className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Section task</span>
            <span className="ml-2">{title}</span>
            {status ? (
              <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
	          <div className="truncate text-xs text-muted-foreground">
	            {[
	              query || null,
	              taskKind ? `kind ${taskKind}` : null,
	              stage ? `stage ${stage}` : null,
	              typeof priority === 'number' ? `p${priority}` : null,
	              sectionId ? `section ${sectionId}` : null,
	              attempt && attempt > 1 ? `attempt ${attempt}` : null,
	            ]
	              .filter(Boolean)
	              .join(' · ')}
	          </div>
        </div>
      </div>
    )
  }

  if (kind === 'research_artifact_update') {
    const artifactType = String(ev.data?.artifact_type || '').trim() || 'artifact'
    const status = String(ev.data?.status || '').trim()
    const summary = String(ev.data?.summary || '').trim()
    const sourceUrl = String(ev.data?.source_url || '').trim()
    const sectionId = String(ev.data?.section_id || ev.data?.branch_id || '').trim()
    const taskId = String(ev.data?.task_id || '').trim()
    const taskKind = String(ev.data?.task_kind || '').trim()
    const stage = String(ev.data?.stage || '').trim()
    const validationStage = String(ev.data?.validation_stage || '').trim()
    const scopeVersion = typeof ev.data?.scope_version === 'number' ? ev.data.scope_version : undefined

    return (
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Artifact</span>
            <span className="ml-2">{artifactType}</span>
            {typeof scopeVersion === 'number' ? (
              <span className="ml-2 text-xs text-muted-foreground">v{scopeVersion}</span>
            ) : null}
            {status ? (
              <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
	          {(taskId || sectionId) ? (
	            <div className="truncate text-xs text-muted-foreground">
	              {[
	                taskId ? `task ${taskId}` : null,
	                sectionId ? `section ${sectionId}` : null,
	                taskKind ? `kind ${taskKind}` : null,
	                stage ? `stage ${stage}` : null,
	                validationStage ? `validation ${validationStage}` : null,
	              ]
	                .filter(Boolean)
	                .join(' · ')}
	            </div>
	          ) : null}
          {summary ? <div className="line-clamp-2 text-xs text-muted-foreground">{summary}</div> : null}
          {sourceUrl ? <div className="truncate font-mono text-xs text-muted-foreground">{sourceUrl}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_decision') {
    const decision = String(ev.data?.decision_type || '').trim()
    const reason = String(ev.data?.reason || '').trim()
    const coverage = typeof ev.data?.coverage === 'number' ? `${Math.round(ev.data.coverage * 100)}%` : ''
    const gapCount = typeof ev.data?.gap_count === 'number' ? `${ev.data.gap_count} gaps` : ''
    const nodeId = String(ev.data?.node_id || '').trim()
    const validationStage = String(ev.data?.validation_stage || '').trim()
    const attempt = typeof ev.data?.attempt === 'number' ? ev.data.attempt : undefined
    const scopeVersion = typeof ev.data?.scope_version === 'number' ? ev.data.scope_version : undefined
    const actorLabel =
      decision.startsWith('scope_') || decision.startsWith('clarify_')
        ? 'Intake'
        : decision.startsWith('final_claim_gate')
          ? 'Final Claim Gate'
          : validationStage
          ? 'Verifier'
          : decision.startsWith('review_')
            ? 'Reviewer'
            : decision === 'outline_plan'
              ? 'Outline'
              : 'Coordinator'

    return (
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">{actorLabel}</span>
            {decision ? <span className="ml-2 font-mono text-[12px]">{decision}</span> : null}
            {typeof scopeVersion === 'number' ? (
              <span className="ml-2 text-xs text-muted-foreground">v{scopeVersion}</span>
            ) : null}
            {[coverage || null, gapCount || null].filter(Boolean).map((item) => (
              <span key={item} className="ml-2 text-xs text-muted-foreground">{item}</span>
            ))}
          </div>
	          {(nodeId || (attempt && attempt > 1)) ? (
	            <div className="truncate text-xs text-muted-foreground">
	              {[
	                nodeId ? `node ${nodeId}` : null,
	                validationStage ? `validation ${validationStage}` : null,
	                attempt && attempt > 1 ? `attempt ${attempt}` : null,
	              ]
	                .filter(Boolean)
	                .join(' · ')}
	            </div>
	          ) : null}
          {reason ? <div className="line-clamp-2 text-xs text-muted-foreground">{reason}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_node_start') {
    const nodeId = String(ev.data?.node_id || ev.data?.nodeId || '').trim()
    const topic = String(ev.data?.topic || '').trim()
    const epoch = ev.data?.epoch
    const depth = ev.data?.depth

    const subtitle = [
      typeof epoch === 'number' ? `epoch ${epoch}` : null,
      typeof depth === 'number' ? `depth ${depth}` : null,
    ]
      .filter(Boolean)
      .join(' · ')

    return (
      <div className="flex items-start gap-2">
        <TreePine className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research start</span>
            {nodeId ? <span className="ml-2 font-mono text-[12px]">{nodeId}</span> : null}
          </div>
          {subtitle ? <div className="text-xs text-muted-foreground">{subtitle}</div> : null}
          {topic ? <div className="truncate text-xs text-muted-foreground">{topic}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'research_node_complete') {
    const nodeId = String(ev.data?.node_id || ev.data?.nodeId || '').trim()
    const epoch = ev.data?.epoch
    const summary = String(ev.data?.summary || '').trim()

    const subtitle = typeof epoch === 'number' ? `epoch ${epoch}` : ''

    return (
      <div className="flex items-start gap-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research done</span>
            {nodeId ? <span className="ml-2 font-mono text-[12px]">{nodeId}</span> : null}
            {subtitle ? <span className="ml-2 text-xs text-muted-foreground">{subtitle}</span> : null}
          </div>
          {summary ? (
            <div className="line-clamp-2 text-xs text-muted-foreground">{summary}</div>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'quality_update') {
    const stage = String(ev.data?.stage || '').trim()
    const epoch = ev.data?.epoch
    const score =
      typeof ev.data?.query_coverage_score === 'number'
        ? ev.data.query_coverage_score
        : typeof ev.data?.citation_coverage_score === 'number'
          ? ev.data.citation_coverage_score
          : typeof ev.data?.citation_coverage === 'number'
            ? ev.data.citation_coverage
            : undefined
    const scorePct = typeof score === 'number' ? `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%` : ''

    return (
      <div className="flex items-start gap-2">
        <ShieldCheck className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Quality</span>
            {typeof epoch === 'number' ? <span className="ml-2 text-xs">epoch {epoch}</span> : null}
            {stage ? <span className="ml-2 text-xs text-muted-foreground">{stage}</span> : null}
            {scorePct ? <span className="ml-2 font-mono text-[12px]">{scorePct}</span> : null}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'deep_research_topology_update') {
    return (
      <div className="flex items-start gap-2">
        <TreePine className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Research tree updated</span>
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'search') {
    const query = String(ev.data?.query || '').trim()
    const provider = String(ev.data?.provider || '').trim()
    const count = ev.data?.count
    return (
      <div className="flex items-start gap-2">
        <Search className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Search</span>
            {query ? <span className="ml-2 font-mono text-[12px]">{query}</span> : null}
          </div>
          <div className="text-xs text-muted-foreground">
            {[provider || null, typeof count === 'number' ? `${count} results` : null]
              .filter(Boolean)
              .join(' · ')}
          </div>
        </div>
      </div>
    )
  }

  if (kind === 'screenshot') {
    const pageUrl = String(ev.data?.page_url || ev.data?.pageUrl || '').trim()
    const action = String(ev.data?.action || '').trim()
    return (
      <div className="flex items-start gap-2">
        <ImageIcon className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="truncate">
            <span className="font-medium text-foreground/80">Screenshot</span>
            {action ? <span className="ml-2">{action}</span> : null}
          </div>
          {pageUrl ? <div className="truncate font-mono text-xs">{pageUrl}</div> : null}
        </div>
      </div>
    )
  }

  if (kind === 'tool_progress') {
    const toolName = String(ev.data?.name || ev.data?.tool || '').trim() || 'tool'
    const action = String(ev.data?.action || '').trim()
    const info = String(ev.data?.info || ev.data?.message || '').trim()

    return (
      <div className="flex items-start gap-2">
        <Wrench className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground/80 truncate">{toolName}</span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              running
            </span>
          </div>
          {action || info ? (
            <div className="truncate text-xs text-muted-foreground">
              {[action || null, info || null].filter(Boolean).join(' · ')}
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'tool' || kind === 'tool_start' || kind === 'tool_result' || kind === 'tool_error') {
    const toolName = String(ev.data?.name || ev.data?.tool || '').trim() || 'tool'
    const status = String(ev.data?.status || '').trim()
    const args = ev.data?.args
    const query = String(ev.data?.query || args?.query || '').trim()
    const url = String(args?.url || ev.data?.url || ev.data?.page_url || '').trim()

    const hint = query || url

    return (
      <div className="flex items-start gap-2">
        <Wrench className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground/80 truncate">{toolName}</span>
            {status ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {status}
              </span>
            ) : null}
          </div>
          {hint ? <div className="truncate font-mono text-xs">{hint}</div> : null}
        </div>
      </div>
    )
  }

  // Fallback: show type name only (keeps UI stable as backend adds new event kinds)
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
      <div className="min-w-0">
        <div className="truncate font-mono text-xs">{kind}</div>
      </div>
    </div>
  )
}

function FallbackTools({ tools }: { tools: ToolInvocation[] }) {
  if (!tools.length) {
    return <div className="text-xs text-muted-foreground">No process details.</div>
  }
  return (
    <div className="space-y-2">
      {tools.slice(-20).map((tool) => (
        <div key={tool.toolCallId} className="flex items-start gap-2">
          <Wrench className="mt-0.5 h-4 w-4 text-muted-foreground/60" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate font-medium text-foreground/80">{tool.toolName}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {tool.state}
              </span>
            </div>
            {tool.args?.query ? (
              <div className="truncate font-mono text-xs">{String(tool.args.query)}</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}
