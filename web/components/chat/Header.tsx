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
  onToggleArtifacts?: () => void
  hasArtifacts?: boolean
}

export const Header = memo(function Header({
  sidebarOpen,
  onToggleSidebar,
  selectedModel,
  onModelChange,
  onOpenSettings,
  onToggleArtifacts,
  hasArtifacts
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

  return (
    <header className="flex h-16 items-center justify-between border-b px-4 bg-background/80 backdrop-blur-md sticky top-0 z-30 transition-colors duration-200">
      <div className="flex items-center gap-3">
        {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              className="hidden md:flex hover:bg-muted/50 rounded-full"
              aria-label="Open sidebar"
            >
              <PanelLeft className="h-5 w-5 text-muted-foreground" />
            </Button>
        )}
      </div>

      <div className="flex items-center gap-2">
         {/* Artifacts Toggle (Mobile/Tablet) */}
         {hasArtifacts && (
             <Button
                variant="ghost"
                size="icon"
                onClick={onToggleArtifacts}
                className="xl:hidden hover:bg-muted/50 rounded-full text-orange-500"
                aria-label="Toggle artifacts"
             >
                <LayoutPanelLeft className="h-5 w-5" />
             </Button>
         )}

        <Select value={selectedModel} onValueChange={onModelChange}>
          <SelectTrigger
            aria-label="Select model"
            className="h-9 w-auto rounded-full border border-border/60 bg-muted/20 px-3 py-1.5 text-sm font-medium shadow-sm hover:bg-muted/50 transition-colors duration-200 focus:ring-offset-0"
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

                  <Button
                    variant="ghost"           size="icon"
           onClick={toggleTheme}
           className="rounded-full hover:bg-muted/50"
         >
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
            <span className="sr-only">Toggle theme</span>
         </Button>

         <Button
           variant="ghost"
           size="icon"
           onClick={onOpenSettings}
           className="rounded-full hover:bg-muted/50"
         >
            <Settings className="h-5 w-5" />
            <span className="sr-only">Settings</span>
         </Button>
      </div>
    </header>
  )
})
