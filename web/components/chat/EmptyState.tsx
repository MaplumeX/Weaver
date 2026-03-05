'use client'

import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from '@/components/ui/icons'
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
    <div className="flex flex-col items-center justify-center h-full w-full max-w-[820px] mx-auto p-6 animate-fade-in">

      {/* Hero Section */}
      <div className="flex flex-col items-center space-y-5 mb-14 text-center">
        <div className="flex size-18 items-center justify-center rounded-2xl bg-background border border-border/40 shadow-sm overflow-hidden">
          <Image
            src="/logo.png"
            alt="Weaver"
            width={56}
            height={56}
            className="h-14 w-14 object-contain"
            priority
          />
        </div>

        <div className="space-y-3 max-w-md">
          <h2 className="text-2xl font-semibold text-foreground text-balance">
            {t('emptyStateTitle')}
          </h2>
          <p className="text-muted-foreground text-base text-pretty leading-relaxed">
            {t('emptyStateSubtitle')} <br className="hidden sm:block" />
            {t('emptyStateDescription')}
          </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-[680px]">
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
                "group flex items-start gap-3.5 p-4 rounded-xl text-left transition-colors duration-200",
                "border border-border/40 bg-background",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-0",
                isActive
                  ? "bg-muted/70 text-foreground border-border/60"
                  : "hover:bg-muted/50 hover:border-border/60"
              )}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className={cn(
                "p-2.5 rounded-lg transition-colors",
                "bg-muted",
                isActive && "bg-background"
              )}>
                <starter.icon className={cn(
                  "h-5 w-5 transition-colors",
                  isActive ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"
                )} />
              </div>
              <div className="flex-1 space-y-1.5 min-w-0">
                <p className="text-sm font-medium leading-snug group-hover:text-foreground transition-colors">
                  {starter.text}
                </p>
                <div className={cn(
                  "flex items-center gap-1 text-xs font-medium text-muted-foreground"
                )}>
                  <span>{t('useMode')} {starter.mode} {t('mode')}</span>
                  <ArrowRight className="h-2.5 w-2.5" />
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
