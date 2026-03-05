'use client'

import React, { useState, useCallback } from 'react'
import { Globe, Bot, Rocket, Plug, ChevronDown, Check } from '@/components/ui/icons'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { deriveUiModeId, searchModeFromId, type SearchMode } from '@/lib/chat-mode'
import type { McpProviderId } from '@/hooks/useChatState'

interface ModeSelectorProps {
  searchMode: SearchMode
  onSearchModeChange: (mode: SearchMode) => void
  mcpMode: boolean
  onMcpModeChange: (enabled: boolean) => void
  mcpProvider: McpProviderId
  onMcpProviderChange: (provider: McpProviderId) => void
}

interface ModeOption {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
}

interface McpOption {
  id: McpProviderId
  label: string
}

const MODE_CONTAINER =
  "inline-flex items-center gap-1 rounded-xl border border-border/40 bg-muted p-1"

export function ModeSelector({
  searchMode,
  onSearchModeChange,
  mcpMode,
  onMcpModeChange,
  mcpProvider,
  onMcpProviderChange,
}: ModeSelectorProps) {
  const { t } = useI18n()
  const [isMcpOpen, setIsMcpOpen] = useState(false)

  const activeMode = deriveUiModeId(searchMode, mcpMode)

  const modes: ModeOption[] = [
    { id: 'web', label: t('web'), icon: Globe },
    { id: 'agent', label: t('agent'), icon: Bot },
    { id: 'ultra', label: t('ultra'), icon: Rocket },
  ]

  const mcpOptions: McpOption[] = [
    { id: 'filesystem', label: t('filesystem') },
    { id: 'memory', label: t('memory') },
  ]

  const handleModeClick = useCallback((modeId: string) => {
    if (activeMode === modeId) onSearchModeChange(searchModeFromId('direct'))
    else if (modeId === 'web') onSearchModeChange(searchModeFromId('web'))
    else if (modeId === 'agent') onSearchModeChange(searchModeFromId('agent'))
    else if (modeId === 'ultra') onSearchModeChange(searchModeFromId('ultra'))
    onMcpModeChange(false)
    setIsMcpOpen(false)
  }, [activeMode, onMcpModeChange, onSearchModeChange])

  const handleMcpToggle = useCallback(() => {
    if (mcpMode) {
      onMcpModeChange(false)
      onSearchModeChange(searchModeFromId('direct'))
      setIsMcpOpen(false)
    } else {
      onMcpModeChange(true)
      onSearchModeChange(searchModeFromId('agent'))
      setIsMcpOpen((prev) => !prev)
    }
  }, [mcpMode, onMcpModeChange, onSearchModeChange])

  const handleMcpSelect = useCallback((next: McpProviderId) => {
    onMcpProviderChange(next)
    onMcpModeChange(true)
    onSearchModeChange(searchModeFromId('agent'))
    setIsMcpOpen(false)
  }, [onMcpModeChange, onMcpProviderChange, onSearchModeChange])

  return (
    <div
      className={cn(
        MODE_CONTAINER,
      )}
      role="radiogroup"
      aria-label="Search mode"
    >
      {modes.map((mode) => {
        const Icon = mode.icon
        const isActive = activeMode === mode.id
        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => handleModeClick(mode.id)}
            className={cn(
              "relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-0",
              isActive
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-background"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {mode.label}
          </button>
        )
      })}

      {/* MCP Dropdown */}
      <div className="relative">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isMcpOpen}
          onClick={handleMcpToggle}
          className={cn(
            "relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-0",
            mcpMode
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-background"
          )}
        >
          <Plug className="h-3.5 w-3.5" />
          {mcpMode ? (mcpOptions.find(o => o.id === mcpProvider)?.label || 'MCP') : 'MCP'}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>

        {isMcpOpen && (
          <div
            role="listbox"
            aria-label="MCP providers"
            className={cn(
              "absolute bottom-full left-0 mb-2 w-40 rounded-xl z-50 overflow-hidden animate-scale-in",
              "bg-popover border border-border/40 shadow-md",
            )}
          >
            <div className="p-1">
              {mcpOptions.map(opt => (
                <button
                  key={opt.id}
                  role="option"
                  aria-selected={mcpProvider === opt.id && mcpMode}
                  onClick={() => handleMcpSelect(opt.id)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2 py-2 text-xs transition-colors hover:bg-muted",
                    mcpProvider === opt.id && mcpMode && "bg-muted font-medium text-foreground"
                  )}
                >
                  {opt.label}
                  {mcpProvider === opt.id && mcpMode && <Check className="h-3 w-3 text-primary" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
