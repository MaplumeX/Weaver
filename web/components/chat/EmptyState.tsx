'use client'

import React from 'react'
import Image from 'next/image'
import { ArrowRight, Sparkles, TrendingUp, Code2, BookOpen } from 'lucide-react'
import { useI18n } from '@/lib/i18n/i18n-context'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  selectedMode: string
  onModeSelect: (mode: string) => void
  onStarterClick?: (text: string, mode: string) => void
}

export function EmptyState({ selectedMode, onModeSelect, onStarterClick }: EmptyStateProps) {
  const { t } = useI18n()

  const starters = [
    {
      icon: TrendingUp,
      text: t('starterAnalyze'),
      mode: "ultra"
    },
    {
      icon: Code2,
      text: t('starterWrite'),
      mode: "agent"
    },
    {
      icon: BookOpen,
      text: t('starterSummarize'),
      mode: "web"
    },
    {
      icon: Sparkles,
      text: t('starterPlan'),
      mode: "direct"
    }
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full w-full max-w-4xl mx-auto p-6 animate-in fade-in zoom-in-95 duration-500">

      {/* Hero Section */}
      <div className="flex flex-col items-center space-y-6 mb-12 text-center">
        <div className="relative group cursor-default">
          <div className="absolute inset-0 bg-primary/20 rounded-3xl blur-xl opacity-40 transition duration-500 group-hover:opacity-60 group-hover:scale-105" />
          <div className="relative h-24 w-24 rounded-3xl flex items-center justify-center shadow-xl shadow-primary/20 ring-1 ring-white/20 overflow-hidden bg-white">
            <Image
              src="/logo.png"
              alt="Weaver"
              width={80}
              height={80}
              className="h-20 w-20 object-contain"
              priority
            />
          </div>
        </div>

        <div className="space-y-2 max-w-lg">
          <h2 className="text-3xl font-bold tracking-tight text-balance bg-clip-text text-transparent bg-gradient-to-b from-foreground to-foreground/70">
            {t('emptyStateTitle')}
          </h2>
          <p className="text-muted-foreground text-lg text-pretty">
            {t('emptyStateSubtitle')} <br className="hidden sm:block" />
            {t('emptyStateDescription')}
          </p>
        </div>
      </div>

      {/* Starter Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
        {starters.map((starter, i) => {
          const isActive = selectedMode === starter.mode
          return (
            <button
              key={i}
              onClick={() => {
                onModeSelect(starter.mode)
                onStarterClick?.(starter.text, starter.mode)
              }}
              className={cn(
                "group flex items-start gap-4 p-4 rounded-xl border text-left transition duration-300",
                isActive
                  ? "bg-card shadow-md border-primary/30"
                  : "bg-card/50 hover:bg-card hover:shadow-md hover:border-primary/20"
              )}
            >
            <div className="p-2 rounded-lg bg-muted group-hover:bg-primary/10 group-hover:text-primary transition-colors">
              <starter.icon className="h-5 w-5" />
            </div>
            <div className="flex-1 space-y-1">
              <p className="text-sm font-medium leading-snug group-hover:text-primary transition-colors">
                {starter.text}
              </p>
              <div className={cn(
                "flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider font-semibold transition-opacity translate-y-2 group-hover:translate-y-0 group-hover:opacity-100",
                isActive ? "opacity-100 translate-y-0" : "opacity-0"
              )}>
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
