'use client'

import React from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface CitationBadgeProps {
  num: string
  href?: string
}

export function CitationBadge({ num, href }: CitationBadgeProps) {
  const badge = (
    <sup className="ml-0.5 align-super text-[10px] font-bold leading-none text-primary">
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="rounded-sm bg-primary/10 px-1 hover:underline decoration-dotted"
        >
          [{num}]
        </a>
      ) : (
        <span className="rounded-sm bg-primary/10 px-1">[{num}]</span>
      )}
    </sup>
  )

  return (
    <TooltipProvider>
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          {badge}
        </TooltipTrigger>
        <TooltipContent className="max-w-[300px] break-words">
          <div className="space-y-1">
            <p className="font-semibold text-xs">Source [{num}]</p>
            <p className="text-xs text-muted-foreground break-all">
              {href || 'Reference details would appear here.'}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
