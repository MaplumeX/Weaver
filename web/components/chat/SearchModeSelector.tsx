'use client'

import React from 'react'
import { Bot, Rocket } from 'lucide-react'
import { ChatMode } from '@/lib/chat-mode'
import { cn } from '@/lib/utils'

interface SearchModeSelectorProps {
  mode: ChatMode
  onChange: (mode: ChatMode) => void
}

export function SearchModeSelector({ mode, onChange }: SearchModeSelectorProps) {
  const options = [
    {
      id: 'agent' as ChatMode,
      label: 'Agent',
      description: '默认对话模式，支持工具与搜索',
      icon: Bot,
      activeClassName: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700',
      iconClassName: 'text-emerald-600',
    },
    {
      id: 'deep' as ChatMode,
      label: 'Deep Research',
      description: '显式进入深度研究流程',
      icon: Rocket,
      activeClassName: 'border-amber-500/30 bg-amber-500/10 text-amber-700',
      iconClassName: 'text-amber-600',
    },
  ]

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isActive = mode === option.id
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            className={cn(
              'flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors',
              isActive ? option.activeClassName : 'border-border bg-background text-muted-foreground hover:bg-muted/50',
            )}
          >
            <option.icon className={cn('h-3.5 w-3.5', isActive ? option.iconClassName : 'text-muted-foreground')} />
            <span>{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
