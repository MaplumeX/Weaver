'use client'

import React, { useState, useMemo, useCallback, memo } from 'react'
import { Check, Copy, ChevronDown, ChevronRight, WrapText, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { showSuccess } from '@/lib/toast-utils'
import dynamic from 'next/dynamic'
import { Virtuoso, type ScrollerProps } from 'react-virtuoso'
import { cn } from '@/lib/utils'

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
  wrap
}: {
  line: string
  lineNumber: number
  wrap: boolean
}) {
  return (
    <div className="flex font-mono text-sm leading-6">
      <span className="select-none text-white/30 w-12 pr-4 text-right shrink-0 tabular-nums">
        {lineNumber}
      </span>
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
  const [copied, setCopied] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)
  const [wrapLines, setWrapLines] = useState(false)

  // Memoize line splitting
  const lines = useMemo(() => value.split('\n'), [value])
  const useVirtualization = lines.length > VIRTUAL_SCROLL_THRESHOLD

  // Memoized item renderer for Virtuoso
  const itemContent = useCallback((index: number) => (
    <CodeLine
      key={index}
      line={lines[index] ?? ''}
      lineNumber={index + 1}
      wrap={wrapLines}
    />
  ), [lines, wrapLines])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(value)
    setCopied(true)
    showSuccess('Code copied', 'code-copy')
    setTimeout(() => setCopied(false), 2000)
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
                style={{ height: '400px' }}
                totalCount={lines.length}
                itemContent={itemContent}
                components={virtualizationComponents}
              />
            </div>
          ) : (
            // Standard rendering for smaller code blocks
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
              showLineNumbers={false}
              wrapLongLines={wrapLines}
              PreTag="div"
            >
              {value}
            </SyntaxHighlighter>
          )}
        </div>
      )}
    </div>
  )
}
