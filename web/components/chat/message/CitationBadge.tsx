'use client'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { MessageSource } from '@/types/chat'

interface CitationBadgeProps {
  num: string
  source?: MessageSource
  active?: boolean
  onClick?: (num: string) => void
}

function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'unknown'
  }
}

export function CitationBadge({ num, source, active = false, onClick }: CitationBadgeProps) {
  const href = source?.rawUrl || source?.url || ''
  const title = source?.title || ''
  const domain = source?.domain || (href ? domainFromUrl(href) : '')
  const provider = source?.provider || ''
  const published = source?.publishedDate || ''

  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <sup
            role="button"
            tabIndex={0}
            onClick={() => onClick?.(num)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick?.(num)
              }
            }}
            className={[
              'ml-0.5 cursor-pointer text-[10px] font-bold hover:underline decoration-dotted select-none px-1 rounded-sm',
              active ? 'bg-primary text-primary-foreground' : 'text-primary bg-primary/10',
            ].join(' ')}
            aria-label={title ? `Open source ${num}: ${title}` : `Open source ${num}`}
          >
            [{num}]
          </sup>
        </TooltipTrigger>
        <TooltipContent className="max-w-[300px] break-words">
          <div className="space-y-1">
            <p className="font-semibold text-xs">Source [{num}]</p>
            {title ? (
              <p className="text-xs leading-snug">{title}</p>
            ) : (
              <p className="text-xs text-muted-foreground">No source details available.</p>
            )}
            <div className="flex flex-wrap gap-1 text-[10px] text-muted-foreground">
              {domain ? <span className="rounded bg-muted px-1.5 py-0.5">{domain}</span> : null}
              {provider ? <span className="rounded bg-muted px-1.5 py-0.5">{provider}</span> : null}
              {published ? <span className="rounded bg-muted px-1.5 py-0.5">{published}</span> : null}
            </div>
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="block text-[11px] text-primary hover:underline"
              >
                {href}
              </a>
            ) : null}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
