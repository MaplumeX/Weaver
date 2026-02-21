'use client'

import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'
import { deriveUiModeId, searchModeFromId, type CoreModeId, type SearchMode } from '@/lib/chat-mode'

interface EmptyStateProps {
  selectedMode: SearchMode
  mcpMode: boolean
  onModeSelect: (mode: SearchMode) => void
  onStarterClick?: (text: string, mode: CoreModeId) => void
}

export function EmptyState({ selectedMode, mcpMode, onModeSelect, onStarterClick }: EmptyStateProps) {
  const { t } = useI18n()

  const activeMode = deriveUiModeId(selectedMode, mcpMode)

  const starters = [
    {
      icon: TrendingUp,
      text: t('starterAnalyze'),
      mode: "ultra" as CoreModeId
    },
    {
      icon: Code2,
      text: t('starterWrite'),
      mode: "agent" as CoreModeId
    },
    {
      icon: BookOpen,
      text: t('starterSummarize'),
      mode: "web" as CoreModeId
    },
    {
      icon: Sparkles,
      text: t('starterPlan'),
      mode: "direct" as CoreModeId
    }
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full w-full max-w-[820px] mx-auto p-6">

      {/* Hero Section */}
      <div className="flex flex-col items-center space-y-6 mb-12 text-center">
        <div className="flex size-24 items-center justify-center rounded-3xl border border-border/60 bg-card shadow-sm overflow-hidden">
          <Image
            src="/logo.png"
            alt="Weaver"
            width={80}
            height={80}
            className="h-20 w-20 object-contain"
            priority
          />
        </div>

        <div className="space-y-2 max-w-lg">
          <h2 className="text-3xl font-semibold text-balance">
            {t('emptyStateTitle')}
          </h2>
          <p className="text-muted-foreground text-lg text-pretty">
            {t('emptyStateSubtitle')} <br className="hidden sm:block" />
            {t('emptyStateDescription')}
          </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-[820px]">
        {starters.map((starter, i) => {
          const isActive = activeMode === starter.mode
          return (
            <button
              key={i}
              onClick={() => {
                onModeSelect(searchModeFromId(starter.mode))
                onStarterClick?.(starter.text, starter.mode)
              }}
              className={cn(
                "group flex items-start gap-4 p-4 rounded-xl border border-border/60 bg-card text-left transition-colors duration-200",
                isActive
                  ? "border-primary/30"
                  : "hover:bg-accent"
              )}
            >
            <div className="p-2 rounded-lg bg-muted group-hover:bg-primary/10 group-hover:text-primary transition-colors">
              <starter.icon className="h-5 w-5" />
            </div>
            <div className="flex-1 space-y-1">
              <p className="text-sm font-medium leading-snug group-hover:text-primary transition-colors">
                {starter.text}
              </p>
              <div className={cn("mt-1 flex items-center gap-1 text-xs text-muted-foreground", isActive && "text-primary")}>
                <span>{t('useMode')} {starter.mode} {t('mode')}</span>
                <ArrowRight className="h-3 w-3" />
              </div>
            </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
