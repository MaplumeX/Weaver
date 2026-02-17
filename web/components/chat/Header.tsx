'use client'

import { useMemo, memo } from 'react'
import { Button } from '@/components/ui/button'
import { PanelLeft, Sun, Moon, LayoutPanelLeft, Settings } from 'lucide-react'
import { useTheme } from '@/components/theme-provider'
import { useI18n } from '@/lib/i18n/i18n-context'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface HeaderProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  selectedModel: string
  onModelChange: (model: string) => void
  onOpenSettings: () => void
  onToggleInspector?: () => void
  hasInspector?: boolean
  currentView: 'dashboard' | 'discover' | 'library'
  sessionTitle?: string | null
}

export const Header = memo(function Header({
  sidebarOpen,
  onToggleSidebar,
  selectedModel,
  onModelChange,
  onOpenSettings,
  onToggleInspector,
  hasInspector,
  currentView,
  sessionTitle
}: HeaderProps) {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const { t } = useI18n()

  const toggleTheme = () => {
    const currentTheme = resolvedTheme || theme
    setTheme(currentTheme === 'dark' ? 'light' : 'dark')
  }

  const models = useMemo(
    () => [
      { id: 'gpt-5', name: 'GPT-5', provider: 'OpenAI' },
      { id: 'gpt-4.1', name: 'GPT-4.1', provider: 'OpenAI' },
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
      { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5', provider: 'Anthropic' },
      { id: 'claude-opus-4-20250514', name: 'Claude Opus 4', provider: 'Anthropic' },
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', provider: 'Anthropic' },
      { id: 'deepseek-chat', name: 'deepseek-chat', provider: t('deepseek') },
      { id: 'deepseek-reasoner', name: 'deepseek-reasoner', provider: t('deepseek') },
      { id: 'qwen-plus', name: 'qwen-plus', provider: t('qwen') },
      { id: 'qwen3-vl-flash', name: 'qwen3-vl-flash 🖼️', provider: t('qwen') },
      { id: 'glm-4.6', name: 'GLM-4.6', provider: t('zhipu') },
      { id: 'glm-4.6v', name: 'glm-4.6v 🖼️', provider: t('zhipu') },
    ],
    [t],
  )

  const currentModelName = useMemo(
    () => models.find((m) => m.id === selectedModel)?.name || selectedModel,
    [models, selectedModel],
  )

  const viewLabel = useMemo(() => {
    return t(currentView)
  }, [currentView, t])

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/60 bg-background px-4 transition-colors duration-200">
      <div className="flex items-center gap-3 min-w-0">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          className="rounded-full hover:bg-accent md:hidden"
          aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          aria-expanded={sidebarOpen}
        >
          <PanelLeft className="h-5 w-5 text-muted-foreground" />
        </Button>

        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground truncate text-balance">
            {viewLabel}
          </div>
          {currentView === 'dashboard' ? (
            <div className="text-xs text-muted-foreground truncate text-pretty">
              {sessionTitle || t('newInvestigation')}
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Inspector Toggle (Mobile/Tablet) */}
        {hasInspector && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleInspector}
            className="rounded-full text-primary hover:bg-accent xl:hidden"
            aria-label="Toggle inspector"
          >
            <LayoutPanelLeft className="h-5 w-5" />
          </Button>
        )}

        <Select value={selectedModel} onValueChange={onModelChange}>
          <SelectTrigger
            aria-label="Select model"
            className="h-9 w-auto rounded-lg border border-border/60 bg-background px-3 py-1.5 text-sm font-medium shadow-sm transition-colors duration-200 hover:bg-accent focus:ring-offset-0"
          >
            <SelectValue placeholder={currentModelName} />
          </SelectTrigger>
          <SelectContent className="w-64 max-h-80 rounded-xl">
            {models.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                {model.name} ({model.provider})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Desktop theme/settings moved to Rail; keep on mobile */}
        <div className="flex items-center gap-2 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            className="rounded-full hover:bg-accent"
            aria-label={t('toggleTheme')}
          >
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenSettings}
            className="rounded-full hover:bg-accent"
            aria-label={t('settings')}
          >
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  )
})
