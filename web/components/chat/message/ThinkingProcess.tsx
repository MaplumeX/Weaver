'use client'

import { useMemo, useState } from 'react'
import { ChevronDown, Loader2, Globe, Code, Monitor, Wrench, CheckCircle2, XCircle, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ToolInvocation } from '@/types/chat'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { showError, showSuccess } from '@/lib/toast-utils'

interface ThinkingProcessProps {
  tools: ToolInvocation[]
  isThinking: boolean
}

export function ThinkingProcess({ tools, isThinking }: ThinkingProcessProps) {
  const [isOpen, setIsOpen] = useState(false)

  const stats = useMemo(() => {
    const toolList = tools || []
    const total = toolList.length
    const running = toolList.filter(t => t.state === 'running').length
    const completed = toolList.filter(t => t.state === 'completed').length
    const failed = toolList.filter(t => t.state === 'failed').length

    const byCategory = {
      search: 0,
      code: 0,
      browser: 0,
      other: 0,
    }

    const categorize = (name: string) => {
      const lowered = (name || '').toLowerCase()
      if (lowered.includes('search')) return 'search'
      if (lowered.includes('python') || lowered.includes('code') || lowered.includes('execute')) return 'code'
      if (lowered.includes('browser') || lowered.includes('crawl') || lowered.startsWith('sb_browser_')) return 'browser'
      return 'other'
    }

    for (const tool of toolList) {
      byCategory[categorize(tool.toolName) as keyof typeof byCategory]++
    }

    return { total, running, completed, failed, byCategory }
  }, [tools])

  if (!tools || tools.length === 0) return null

  const statusLabel =
    stats.running > 0 || isThinking
      ? `${stats.running} running · ${stats.completed} done`
      : stats.failed > 0
        ? `${stats.completed} done · ${stats.failed} failed`
        : `${stats.completed} done`

  return (
    <Card className="w-full my-3 overflow-hidden border-border/60">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
         <div className="flex items-center gap-3">
            <div className={cn(
                "flex items-center justify-center size-8 rounded-full ring-1 ring-border shadow-sm transition-colors duration-200",
                (stats.running > 0 || isThinking) ? "bg-primary/10 text-primary ring-primary/20" : "bg-muted text-muted-foreground"
            )}>
                {stats.failed > 0 && !(stats.running > 0 || isThinking) ? (
                  <XCircle className="w-4 h-4" />
                ) : (stats.running > 0 || isThinking) ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
            </div>
            <div className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold text-foreground/90">
                    Tool activity
                </span>
                <span className="text-[10px] font-medium text-muted-foreground uppercase">
                    {statusLabel}
                </span>
            </div>
         </div>
         <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground rounded-full"
            aria-label={isOpen ? "Collapse thinking steps" : "Expand thinking steps"}
            title={isOpen ? "Collapse" : "Expand"}
         >
            <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", isOpen && "rotate-180")} />
         </Button>
      </div>

      {/* Summary */}
      <div className="px-4 pb-3 pt-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-[11px] tabular-nums">
            total {stats.total}
          </Badge>
          <Badge
            variant={stats.running > 0 || isThinking ? 'default' : 'secondary'}
            className="text-[11px] tabular-nums"
          >
            running {stats.running}
          </Badge>
          {stats.failed > 0 ? (
            <Badge variant="destructive" className="text-[11px] tabular-nums">
              failed {stats.failed}
            </Badge>
          ) : null}

          <span className="mx-1 h-4 w-px bg-border/60" aria-hidden="true" />

          <Badge variant="outline" className="text-[11px] tabular-nums">
            <Globe className="mr-1 h-3 w-3" />
            search {stats.byCategory.search}
          </Badge>
          <Badge variant="outline" className="text-[11px] tabular-nums">
            <Code className="mr-1 h-3 w-3" />
            code {stats.byCategory.code}
          </Badge>
          <Badge variant="outline" className="text-[11px] tabular-nums">
            <Monitor className="mr-1 h-3 w-3" />
            browser {stats.byCategory.browser}
          </Badge>
          <Badge variant="outline" className="text-[11px] tabular-nums">
            <Wrench className="mr-1 h-3 w-3" />
            other {stats.byCategory.other}
          </Badge>
        </div>
      </div>

      {/* Logs (Collapsible) */}
      {isOpen && (
        <div className="border-t border-border/60 bg-muted/10">
            <ScrollArea className="h-60">
                <div className="p-3 space-y-2">
                    {tools.map((tool) => (
                        <LogItem key={tool.toolCallId} tool={tool} />
                    ))}
                </div>
            </ScrollArea>
        </div>
      )}
    </Card>
  )
}

function LogItem({ tool }: { tool: ToolInvocation }) {
  const isRunning = tool.state === 'running'
  const query = typeof tool.args?.query === 'string' ? tool.args.query : null
  const url = typeof tool.args?.url === 'string' ? tool.args.url : null
  const path = typeof tool.args?.path === 'string' ? tool.args.path : null
  const command = typeof tool.args?.command === 'string' ? tool.args.command : null
  const code = typeof tool.args?.code === 'string' ? tool.args.code : null

  const copyPayload = (() => {
    if (command) return command
    if (code) return code
    if (url) return url
    if (query) return query
    if (path) return path
    try {
      return JSON.stringify(tool.args || {}, null, 2)
    } catch {
      return String(tool.args || '')
    }
  })()

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(copyPayload)
      showSuccess('Copied', 'tool-activity-copy')
    } catch {
      showError('Copy failed', 'tool-activity-copy-failed')
    }
  }

  const preview = (() => {
    if (query) return `Query: "${query}"`
    if (url) return `URL: ${url}`
    if (path) return `Path: ${path}`
    if (command) return `Command: ${command}`
    if (code) return code.slice(0, 220) + (code.length > 220 ? '…' : '')

    const args = tool.args || {}
    const keys = Object.keys(args)
    if (keys.length === 0) return null
    try {
      const text = JSON.stringify(args)
      return text.length > 260 ? text.slice(0, 260) + '…' : text
    } catch {
      return null
    }
  })()

  return (
    <div className="group flex gap-3 p-2.5 rounded-lg hover:bg-muted/40 border border-transparent hover:border-border/40 transition-colors duration-200">
       <div className="flex flex-col items-center gap-1">
           <div className={cn(
               "w-1.5 h-1.5 rounded-full mt-1.5",
               isRunning ? "bg-primary" : "bg-border/60"
           )} />
           <div className="w-[1px] h-full bg-border/40 group-last:hidden" />
       </div>

       <div className="flex-1 min-w-0">
           <div className="flex items-center justify-between mb-0.5">
               <div className="flex items-center gap-2">
                   <Badge
                     variant="outline"
                     className="text-[10px] h-5 px-1.5 font-mono bg-muted/20 border-border/60 text-muted-foreground"
                   >
                       {tool.toolName.replace(/_/g, ' ')}
                   </Badge>
               </div>
               <div className="flex items-center gap-1">
                 <span className={cn(
                     "text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                     isRunning ? "bg-primary/10 text-primary" : "bg-muted/30 text-muted-foreground"
                 )}>
                     {tool.state}
                 </span>
                 <Button
                   type="button"
                   variant="ghost"
                   size="icon-sm"
                   className="size-7 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/60"
                   onClick={handleCopy}
                   aria-label="Copy tool details"
                   title="Copy"
                 >
                   <Copy className="h-3.5 w-3.5" />
                 </Button>
               </div>
           </div>

           {preview ? (
             <div className="mt-1.5 p-2 rounded bg-muted/40 border border-border/40 font-mono text-[10px] text-muted-foreground overflow-x-auto whitespace-pre-wrap break-words">
               {preview}
             </div>
           ) : null}
       </div>
    </div>
  )
}
