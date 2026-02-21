'use client'

import React, { useRef, useState, useMemo, useCallback, memo } from 'react'
import { Check, Copy, ChevronDown, ChevronRight, WrapText, Download, MoreHorizontal, ArrowUp, ArrowDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { showSuccess } from '@/lib/toast-utils'
import dynamic from 'next/dynamic'
import { Virtuoso, type ScrollerProps, type VirtuosoHandle } from 'react-virtuoso'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'

// Lazy-load SyntaxHighlighter to reduce initial bundle (~200KB savings)
const SyntaxHighlighter = dynamic(
  () => import('react-syntax-highlighter/dist/esm/prism').then(mod => mod.default || mod),
  { ssr: false }
)

// Static import for the theme (small JSON file, ok to keep static)
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface CodeBlockProps {
  language: string
  value: string
  defaultCollapsed?: boolean
}

// Threshold for enabling virtual scrolling
const VIRTUAL_SCROLL_THRESHOLD = 100

function extensionForLanguage(language: string): string {
  const lang = String(language || '').trim().toLowerCase()
  if (!lang || lang === 'text' || lang === 'plain') return 'txt'

  if (lang === 'ts' || lang === 'typescript') return 'ts'
  if (lang === 'tsx') return 'tsx'
  if (lang === 'js' || lang === 'javascript') return 'js'
  if (lang === 'jsx') return 'jsx'
  if (lang === 'py' || lang === 'python') return 'py'
  if (lang === 'sh' || lang === 'bash' || lang === 'shell') return 'sh'
  if (lang === 'json') return 'json'
  if (lang === 'yaml' || lang === 'yml') return 'yml'
  if (lang === 'md' || lang === 'markdown') return 'md'
  if (lang === 'html') return 'html'
  if (lang === 'css') return 'css'
  if (lang === 'sql') return 'sql'
  if (lang === 'go' || lang === 'golang') return 'go'
  if (lang === 'rs' || lang === 'rust') return 'rs'

  return 'txt'
}

// Memoized line component for virtual scrolling
const CodeLine = memo(function CodeLine({
  line,
  lineNumber,
  wrap,
  showLineNumbers,
  isMatch,
  isActiveMatch,
}: {
  line: string
  lineNumber: number
  wrap: boolean
  showLineNumbers: boolean
  isMatch: boolean
  isActiveMatch: boolean
}) {
  return (
    <div
      className={cn(
        "flex font-mono text-sm leading-6 rounded-sm px-2",
        isMatch && "bg-white/5",
        isActiveMatch && "bg-primary/20 ring-1 ring-primary/30"
      )}
      data-code-line={lineNumber}
    >
      {showLineNumbers ? (
        <span className="select-none text-white/30 w-12 pr-4 text-right shrink-0 tabular-nums">
          {lineNumber}
        </span>
      ) : null}
      <code
        className={cn(
          'flex-1 min-w-0 text-white/90',
          wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre',
        )}
      >
        {line || ' '}
      </code>
    </div>
  )
})

export function CodeBlock({ language, value, defaultCollapsed = false }: CodeBlockProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const codeContainerRef = useRef<HTMLDivElement | null>(null)

  const [copied, setCopied] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)
  const [wrapLines, setWrapLines] = useState(false)
  const [showLineNumbers, setShowLineNumbers] = useState(false)
  const [findQuery, setFindQuery] = useState('')
  const [activeMatchCursor, setActiveMatchCursor] = useState(0)

  // Memoize line splitting
  const lines = useMemo(() => value.split('\n'), [value])
  const useVirtualization = lines.length > VIRTUAL_SCROLL_THRESHOLD
  const normalizedFindQuery = findQuery.trim()

  const matchLineIndexes = useMemo(() => {
    if (!normalizedFindQuery) return []
    const q = normalizedFindQuery.toLowerCase()
    const out: number[] = []
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (typeof line === 'string' && line.toLowerCase().includes(q)) {
        out.push(i)
      }
    }
    return out
  }, [lines, normalizedFindQuery])

  const matchLineSet = useMemo(() => new Set(matchLineIndexes), [matchLineIndexes])

  const matchCount = matchLineIndexes.length
  const safeActiveCursor = matchCount > 0 ? Math.min(activeMatchCursor, matchCount - 1) : 0
  const activeMatchLineIndex = matchCount > 0 ? matchLineIndexes[safeActiveCursor] ?? null : null

  // Memoized item renderer for Virtuoso
  const itemContent = useCallback((index: number) => (
    <CodeLine
      key={index}
      line={lines[index] ?? ''}
      lineNumber={index + 1}
      wrap={wrapLines}
      showLineNumbers={showLineNumbers}
      isMatch={matchLineSet.has(index)}
      isActiveMatch={activeMatchLineIndex === index}
    />
  ), [lines, wrapLines, showLineNumbers, matchLineSet, activeMatchLineIndex])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(value)
    setCopied(true)
    showSuccess('Code copied', 'code-copy')
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCopyFenced = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const normalizedLang = String(language || '').trim().toLowerCase()
    const lang = normalizedLang && normalizedLang !== 'text' ? normalizedLang : ''
    const content = String(value || '').replace(/\n$/, '')
    const fenced = lang ? `\`\`\`${lang}\n${content}\n\`\`\`` : `\`\`\`\n${content}\n\`\`\``
    try {
      await navigator.clipboard.writeText(fenced)
      showSuccess('Copied as fenced block', 'code-copy-fenced')
    } catch {
      // Keep silent; clipboard may be blocked in some contexts.
    }
  }

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    const ext = extensionForLanguage(language)
    const filename = `snippet.${ext}`
    const blob = new Blob([value], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)

    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()

    URL.revokeObjectURL(url)
    showSuccess('Download started', 'code-download')
  }

  const toggleCollapse = () => {
    setIsCollapsed(!isCollapsed)
  }

  const toggleWrap = (e: React.MouseEvent) => {
    e.stopPropagation()
    setWrapLines(v => !v)
  }

  const handleFindChange = (value: string) => {
    setFindQuery(value)
    setActiveMatchCursor(0)
  }

  const scrollToLineIndex = useCallback((lineIndex: number) => {
    if (lineIndex < 0) return
    if (useVirtualization) {
      virtuosoRef.current?.scrollToIndex({ index: lineIndex, align: 'center', behavior: 'smooth' })
      return
    }

    const el = codeContainerRef.current?.querySelector(
      `[data-code-line="${lineIndex + 1}"]`
    ) as HTMLElement | null
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [useVirtualization])

  const goToMatchCursor = useCallback((cursor: number) => {
    if (matchCount === 0) return
    const nextCursor = ((cursor % matchCount) + matchCount) % matchCount
    setActiveMatchCursor(nextCursor)
    const lineIndex = matchLineIndexes[nextCursor]
    if (typeof lineIndex === 'number') {
      scrollToLineIndex(lineIndex)
    }
  }, [matchCount, matchLineIndexes, scrollToLineIndex])

  const goToNextMatch = useCallback(() => {
    goToMatchCursor(safeActiveCursor + 1)
  }, [goToMatchCursor, safeActiveCursor])

  const goToPrevMatch = useCallback(() => {
    goToMatchCursor(safeActiveCursor - 1)
  }, [goToMatchCursor, safeActiveCursor])

  const virtualizationComponents = useMemo(() => {
    const Scroller = React.forwardRef<HTMLDivElement, ScrollerProps>(function ScrollerBase(
      { style, children, ...props },
      ref
    ) {
      return (
        <div
          ref={ref}
          {...props}
          style={{
            ...style,
            overflowX: wrapLines ? 'hidden' : 'auto',
          }}
          className="scrollbar-thin scrollbar-thumb-white/20"
        >
          {children}
        </div>
      )
    })

    return { Scroller }
  }, [wrapLines])

  const codeWrapStyle = useMemo(() => {
    return {
      whiteSpace: wrapLines ? 'pre-wrap' : 'pre',
      wordBreak: wrapLines ? 'break-word' : 'normal',
      overflowWrap: wrapLines ? 'anywhere' : 'normal',
    } as const
  }, [wrapLines])

  return (
    <div className="relative w-full my-4 rounded-xl overflow-hidden border border-border/40 bg-[#282c34] shadow-sm group transition-shadow duration-200 hover:shadow-md">
      <div
        className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/10 select-none cursor-pointer hover:bg-white/10 transition-colors duration-200"
        onClick={toggleCollapse}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-white/70 font-mono flex items-center gap-2">
            {language || 'text'}
            {isCollapsed && <span className="text-xs text-white/40">collapsed</span>}
            {wrapLines && !isCollapsed && <span className="text-xs text-white/40">wrap</span>}
            {showLineNumbers && !isCollapsed && <span className="text-xs text-white/40">lines</span>}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={handleCopy}
            aria-label="Copy code"
            title="Copy code"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={handleDownload}
            aria-label="Download code"
            title="Download"
          >
            <Download className="h-4 w-4" />
          </Button>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
                onClick={(e) => e.stopPropagation()}
                aria-label="Code block actions"
                title="Actions"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              align="end"
              className="w-80 p-3"
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-muted-foreground uppercase">Code tools</div>
                  <div className="text-[10px] text-muted-foreground tabular-nums">
                    {lines.length} lines
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={handleCopyFenced}
                  >
                    Copy fenced
                  </Button>
                  <div className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2">
                    <span className="text-sm font-medium">Line numbers</span>
                    <Switch
                      checked={showLineNumbers}
                      onCheckedChange={setShowLineNumbers}
                      aria-label="Toggle line numbers"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-semibold text-muted-foreground uppercase">Find</div>
                    <div className="text-[10px] text-muted-foreground tabular-nums">
                      {matchCount > 0 ? `${safeActiveCursor + 1}/${matchCount}` : '0'}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Input
                      value={findQuery}
                      onChange={(e) => handleFindChange(e.target.value)}
                      placeholder="Find in code..."
                      className="h-9"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          if (e.shiftKey) goToPrevMatch()
                          else goToNextMatch()
                        } else if (e.key === 'Escape') {
                          e.preventDefault()
                          handleFindChange('')
                        }
                      }}
                      aria-label="Find in code"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      className="h-9 w-9"
                      onClick={(e) => {
                        e.stopPropagation()
                        goToPrevMatch()
                      }}
                      disabled={matchCount === 0}
                      aria-label="Previous match"
                      title="Previous"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      className="h-9 w-9"
                      onClick={(e) => {
                        e.stopPropagation()
                        goToNextMatch()
                      }}
                      disabled={matchCount === 0}
                      aria-label="Next match"
                      title="Next"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </PopoverContent>
          </Popover>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className={cn(
              "h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200",
              wrapLines && "text-white bg-white/10"
            )}
            onClick={toggleWrap}
            aria-label={wrapLines ? "Disable line wrap" : "Enable line wrap"}
            title={wrapLines ? "Disable wrap" : "Wrap lines"}
          >
            <WrapText className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="h-8 w-8 text-white/60 hover:text-white hover:bg-white/10 transition-colors duration-200"
            onClick={(e) => {
              e.stopPropagation()
              toggleCollapse()
            }}
            aria-label={isCollapsed ? "Expand code block" : "Collapse code block"}
            title={isCollapsed ? "Expand" : "Collapse"}
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Code Content */}
      {!isCollapsed && (
        <div className={cn("overflow-x-auto", wrapLines ? "overflow-x-hidden" : "overflow-x-auto")}>
          {useVirtualization ? (
            // Virtual scrolling for large code blocks (>100 lines)
            <div className="px-4 py-4">
              <Virtuoso
                ref={virtuosoRef}
                style={{ height: '400px' }}
                totalCount={lines.length}
                itemContent={itemContent}
                components={virtualizationComponents}
              />
            </div>
          ) : (
            // Standard rendering for smaller code blocks
            <div ref={codeContainerRef}>
              <SyntaxHighlighter
                language={language?.toLowerCase() || 'text'}
                style={oneDark}
                customStyle={{
                  margin: 0,
                  padding: '1.5rem',
                  background: 'transparent',
                  fontSize: '14px',
                  lineHeight: '1.6',
                  fontFamily: 'var(--font-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  whiteSpace: codeWrapStyle.whiteSpace,
                  wordBreak: codeWrapStyle.wordBreak,
                  overflowWrap: codeWrapStyle.overflowWrap,
                }}
                codeTagProps={{
                  style: {
                    whiteSpace: codeWrapStyle.whiteSpace,
                    wordBreak: codeWrapStyle.wordBreak,
                    overflowWrap: codeWrapStyle.overflowWrap,
                  }
                }}
                showLineNumbers={showLineNumbers}
                wrapLongLines={wrapLines}
                wrapLines={Boolean(normalizedFindQuery)}
                lineProps={(lineNumber: number) => {
                  const idx = lineNumber - 1
                  const isMatch = matchLineSet.has(idx)
                  const isActive = activeMatchLineIndex === idx
                  return {
                    'data-code-line': lineNumber,
                    className: cn(
                      'block rounded-sm px-2',
                      isMatch && 'bg-white/5',
                      isActive && 'bg-primary/20 ring-1 ring-primary/30'
                    )
                  }
                }}
                PreTag="div"
              >
                {value}
              </SyntaxHighlighter>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
