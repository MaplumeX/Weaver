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

const MODE_COLORS: Record<string, { icon: string; activeIcon: string; activeBg: string; activeBorder: string; activeShadow: string }> = {
  ultra: {
    icon: 'text-violet-500/50 dark:text-violet-400/50',
    activeIcon: 'text-violet-500 dark:text-violet-400',
    activeBg: 'bg-violet-500/[0.04]',
    activeBorder: 'border-violet-500/20',
    activeShadow: 'shadow-violet-500/5',
  },
  agent: {
    icon: 'text-sky-500/50 dark:text-sky-400/50',
    activeIcon: 'text-sky-500 dark:text-sky-400',
    activeBg: 'bg-sky-500/[0.04]',
    activeBorder: 'border-sky-500/20',
    activeShadow: 'shadow-sky-500/5',
  },
  web: {
    icon: 'text-emerald-500/50 dark:text-emerald-400/50',
    activeIcon: 'text-emerald-500 dark:text-emerald-400',
    activeBg: 'bg-emerald-500/[0.04]',
    activeBorder: 'border-emerald-500/20',
    activeShadow: 'shadow-emerald-500/5',
  },
  direct: {
    icon: 'text-amber-500/50 dark:text-amber-400/50',
    activeIcon: 'text-amber-500 dark:text-amber-400',
    activeBg: 'bg-amber-500/[0.04]',
    activeBorder: 'border-amber-500/20',
    activeShadow: 'shadow-amber-500/5',
  },
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
          const colors = (MODE_COLORS[starter.mode] ?? MODE_COLORS['direct'])!
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
                  ? [colors.activeBorder, colors.activeBg, "shadow-sm", colors.activeShadow]
                  : "border-border/20 bg-card/40 hover:bg-card/80 hover:border-border/40 hover:shadow-sm"
              )}
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className={cn(
                "p-2 rounded-lg transition-colors",
                isActive
                  ? [colors.activeBg, colors.activeIcon]
                  : ["bg-muted/30", colors.icon, "group-hover:bg-muted/50"]
              )}>
                <starter.icon className="h-4 w-4" />
              </div>
              <div className="flex-1 space-y-1 min-w-0">
                <p className="text-[13px] font-medium leading-snug group-hover:text-foreground transition-colors">
                  {starter.text}
                </p>
                <div className={cn(
                  "flex items-center gap-1 text-xs",
                  isActive ? [colors.activeIcon, "opacity-60"] : "text-muted-foreground/35"
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
