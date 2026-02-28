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
        <div className="flex size-16 items-center justify-center rounded-2xl bg-card border border-border/20 shadow-sm overflow-hidden">
          <Image
            src="/logo.png"
            alt="Weaver"
            width={48}
            height={48}
            className="h-12 w-12 object-contain"
            priority
          />
        </div>

        <div className="space-y-2 max-w-md">
          <h2 className="text-xl font-semibold text-foreground/90 text-balance tracking-tight">
            {t('emptyStateTitle')}
          </h2>
          <p className="text-muted-foreground/50 text-sm text-pretty leading-relaxed">
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
                "group flex items-start gap-3 p-3.5 rounded-xl border text-left transition-all duration-200",
                isActive
                  ? "border-primary/20 bg-primary/[0.04] shadow-sm shadow-primary/5"
                  : "border-border/20 bg-card/40 hover:bg-card/80 hover:border-border/40 hover:shadow-sm"
              )}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className={cn(
                "p-2 rounded-lg transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "bg-muted/30 text-muted-foreground/50 group-hover:bg-primary/8 group-hover:text-primary"
              )}>
                <starter.icon className="h-4 w-4" />
              </div>
              <div className="flex-1 space-y-1 min-w-0">
                <p className="text-[13px] font-medium leading-snug group-hover:text-foreground transition-colors">
                  {starter.text}
                </p>
                <div className={cn(
                  "flex items-center gap-1 text-xs",
                  isActive ? "text-primary/60" : "text-muted-foreground/35"
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
