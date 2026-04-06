'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, ChevronDown, Loader2 } from 'lucide-react'

import { buildProcessHeaderText, projectProcessDisplay } from '@/lib/process-display'
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
  const [userToggled, setUserToggled] = useState(false)
  const [now, setNow] = useState(() => Date.now())

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

  const projection = useMemo(() => {
    return projectProcessDisplay({ events, tools, isThinking })
  }, [events, tools, isThinking])

  const hasDetails = projection.details.length > 0
  const headerText = buildProcessHeaderText({ projection, durationLabel })

  useEffect(() => {
    if (userToggled) return
    if (isThinking) setOpen(true)
    else setOpen(false)
  }, [isThinking, userToggled])

  const toggle = () => {
    if (!hasDetails) return
    setUserToggled(true)
    setOpen((value) => !value)
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
          !hasDetails && 'cursor-default hover:bg-transparent',
        )}
        aria-expanded={open}
      >
        <span
          className={cn(
            'flex h-4 w-4 items-center justify-center',
            isThinking ? 'text-primary' : 'text-muted-foreground',
          )}
        >
          {isThinking ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
        </span>
        <span className="font-medium">{headerText}</span>
        {hasDetails ? (
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-200 ease-out',
              open ? 'rotate-180' : 'rotate-0',
            )}
          />
        ) : null}
      </button>

      {hasDetails ? (
        <div
          className="grid transition-[grid-template-rows] duration-200 ease-out"
          style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="mt-2 ml-2 border-l border-border/60 pl-4 text-sm text-muted-foreground">
              <div className="space-y-2 py-1">
                {projection.details.map((item) => (
                  <div key={item.id} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                    <div className="min-w-0">
                      <div className="truncate text-foreground/85">{item.label}</div>
                      {item.detail ? (
                        <div className="text-xs text-muted-foreground">{item.detail}</div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
