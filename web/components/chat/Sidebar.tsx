'use client'

import { useMemo, useState, useCallback, memo } from 'react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useI18n } from '@/lib/i18n/i18n-context'
import { Plus, Compass, LayoutGrid, FolderOpen, MessageSquare, PanelLeft, Trash2, Pin, PinOff } from 'lucide-react'
import { Virtuoso } from 'react-virtuoso'
import { ChatSession } from '@/types/chat'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useTheme } from '@/components/theme-provider'
import { Sun, Moon, Settings } from 'lucide-react'
import { WORKSPACE_PANEL_W, WORKSPACE_RAIL_W } from './workspace-layout'

// Constant group order - defined outside component to avoid recreating on each render
const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 Days', 'Older'] as const

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  onNewChat: () => void
  onSelectChat: (id: string) => void
  onDeleteChat: (id: string) => void
  onTogglePin: (id: string) => void
  onRenameChat: (id: string, title: string) => void
  onClearHistory: () => void
  onOpenSettings: () => void
  activeView: string
  onViewChange: (view: string) => void
  history: ChatSession[]
  isLoading?: boolean
}

export const Sidebar = memo(function Sidebar(props: SidebarProps) {
  const {
    isOpen,
    onToggle,
    onNewChat,
    onSelectChat,
    onDeleteChat,
    onTogglePin,
    onClearHistory,
    onOpenSettings,
    activeView,
    onViewChange,
    history,
    isLoading = false,
  } = props
  const { t } = useI18n()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')

  const toggleTheme = () => {
    const currentTheme = resolvedTheme || theme
    setTheme(currentTheme === 'dark' ? 'light' : 'dark')
  }

  const pinnedItems = useMemo(() => history.filter(s => s.isPinned), [history])
  const unpinnedItems = useMemo(() => history.filter(s => !s.isPinned), [history])

  const normalizedQuery = historyQuery.trim().toLowerCase()
  const hasQuery = normalizedQuery.length > 0

  const filteredPinnedItems = useMemo(() => {
    if (!hasQuery) return pinnedItems
    return pinnedItems.filter((s) => (s.title || '').toLowerCase().includes(normalizedQuery))
  }, [hasQuery, normalizedQuery, pinnedItems])

  const filteredUnpinnedItems = useMemo(() => {
    if (!hasQuery) return unpinnedItems
    return unpinnedItems.filter((s) => (s.title || '').toLowerCase().includes(normalizedQuery))
  }, [hasQuery, normalizedQuery, unpinnedItems])

  const groupedHistory = useMemo(() => {
    const groups: Record<string, typeof history> = {}
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const yesterday = today - 86400000
    const sevenDaysAgo = today - 86400000 * 7

    filteredUnpinnedItems.forEach(item => {
      const time = item.updatedAt || item.createdAt || Date.now()
      let key = 'Older'
      if (time >= today) key = 'Today'
      else if (time >= yesterday) key = 'Yesterday'
      else if (time >= sevenDaysAgo) key = 'Previous 7 Days'

      const group = (groups[key] ??= [])
      group.push(item)
    })
    return groups
  }, [filteredUnpinnedItems])

  // Build a flat list of items with group headers for virtual scrolling
  type FlatEntry =
    | { type: 'header'; kind: 'pinned' | 'group' | 'results' | 'empty'; label: string }
    | { type: 'item'; item: ChatSession }

  const flatItems = useMemo(() => {
    const items: FlatEntry[] = []

    if (hasQuery) {
      const matches = [...filteredPinnedItems, ...filteredUnpinnedItems]
      if (matches.length === 0) {
        items.push({ type: 'header', kind: 'empty', label: '' })
        return items
      }

      items.push({ type: 'header', kind: 'results', label: '' })
      matches.forEach(item => items.push({ type: 'item', item }))
      return items
    }

    if (filteredPinnedItems.length > 0) {
      items.push({ type: 'header', kind: 'pinned', label: '' })
      filteredPinnedItems.forEach(item => items.push({ type: 'item', item }))
    }

    GROUP_ORDER.forEach(dateLabel => {
      const group = groupedHistory[dateLabel]
      if (group && group.length > 0) {
        items.push({ type: 'header', kind: 'group', label: dateLabel })
        group.forEach(item => items.push({ type: 'item', item }))
      }
    })

    return items
  }, [filteredPinnedItems, filteredUnpinnedItems, groupedHistory, hasQuery])

  // Virtuoso item renderer
  const renderFlatItem = useCallback((index: number) => {
    const entry = flatItems[index]!
    if (entry.type === 'header') {
      const text =
        entry.kind === 'pinned'
          ? t('pinned')
          : entry.kind === 'results'
            ? t('results')
            : entry.kind === 'empty'
              ? t('noResults')
              : entry.label

      return (
        <div className={cn(
          "px-3 text-[11px] font-semibold uppercase mb-1 pt-3",
          entry.kind === 'pinned' ? "text-primary flex items-center gap-1" : "text-muted-foreground/70"
        )}>
          {entry.kind === 'pinned' && <Pin className="h-3 w-3 fill-primary" />}
          {text}
        </div>
      )
    }
    return (
      <SidebarChatItem
        item={entry.item}
        onSelect={onSelectChat}
        onDelete={setDeleteId}
        onTogglePin={onTogglePin}
      />
    )
  }, [flatItems, onSelectChat, onTogglePin, t])

  return (
    <>
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Chat"
        description="Are you sure you want to delete this conversation? This action cannot be undone."
        onConfirm={() => deleteId && onDeleteChat(deleteId)}
        confirmText="Delete"
        variant="destructive"
      />

      <ConfirmDialog
        open={showClearConfirm}
        onOpenChange={setShowClearConfirm}
        title="Clear History"
        description="Are you sure you want to delete all chat history? This action cannot be undone."
        onConfirm={onClearHistory}
        confirmText="Clear All"
        variant="destructive"
      />

      {/* Mobile Overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/30 md:hidden transition-opacity duration-200",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onToggle}
      />

      {/* Mobile Drawer */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 md:hidden",
          "w-[320px] max-w-[85vw]",
          "bg-card border-r border-border/60",
          "transition-transform duration-200 ease-out",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
        aria-hidden={!isOpen}
      >
        <div className="flex h-full flex-col p-3 gap-3">
          <div className="flex items-center justify-between px-2 pt-1">
            <div className="flex items-center gap-2 select-none">
              <div className="flex size-7 items-center justify-center rounded-md border border-border/60 bg-background text-xs font-semibold text-foreground">
                W
              </div>
              <span className="text-base font-semibold text-foreground">{t('weaver')}</span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggle}
              aria-label="Close sidebar"
              aria-expanded={isOpen}
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          </div>

          <div>
            <Button
              className="w-full justify-start gap-2 h-10 shadow-sm transition-colors font-medium text-sm"
              variant="default"
              onClick={onNewChat}
            >
              <Plus className="h-4 w-4" />
              <span className="truncate">{t('newInvestigation')}</span>
            </Button>
          </div>

          <div className="space-y-1" role="group" aria-label="Workspace navigation">
            <SidebarItem icon={LayoutGrid} label={t('dashboard')} active={activeView === 'dashboard'} onClick={() => onViewChange('dashboard')} />
            <SidebarItem icon={Compass} label={t('discover')} active={activeView === 'discover'} onClick={() => onViewChange('discover')} />
            <SidebarItem icon={FolderOpen} label={t('library')} active={activeView === 'library'} onClick={() => onViewChange('library')} />
          </div>

          <div className="pt-1">
            <Input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              aria-label="Search chat history"
              className="h-9"
            />
          </div>

          <div className="flex-1 min-h-0 overflow-hidden">
            {isLoading ? (
              <div className="space-y-4 px-2 py-2">
                {[1, 2, 3, 4, 5, 6].map(i => (
                  <div key={i} className="space-y-2 animate-pulse">
                    <div className="h-3 w-20 bg-muted/40 rounded" />
                    <div className="h-8 w-full bg-muted/30 rounded-lg" />
                  </div>
                ))}
              </div>
            ) : history.length === 0 ? (
              <div className="px-3 text-xs text-muted-foreground italic py-2">{t('noRecentChats')}</div>
            ) : (
              <Virtuoso
                style={{ height: '100%' }}
                totalCount={flatItems.length}
                itemContent={renderFlatItem}
                className="scrollbar-thin scrollbar-thumb-muted/50"
              />
            )}
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-2 px-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={toggleTheme}
              aria-label={t('toggleTheme')}
              title={t('toggleTheme')}
              className="text-muted-foreground hover:text-foreground"
            >
              <Sun className="h-4 w-4 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={onOpenSettings}
              aria-label={t('settings')}
              title={t('settings')}
              className="text-muted-foreground hover:text-foreground"
            >
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Desktop Rail + Panel */}
      <aside className="hidden md:flex h-dvh shrink-0">
        <TooltipProvider delayDuration={200}>
          <div
            className="flex h-full flex-col items-center justify-between bg-card border-r border-border/60 py-3"
            style={{ width: WORKSPACE_RAIL_W }}
          >
            <div className="flex flex-col items-center gap-2">
              <div className="flex size-9 items-center justify-center rounded-lg border border-border/60 bg-background text-xs font-semibold text-foreground select-none">
                W
              </div>

              <RailButton
                label={isOpen ? t('collapsePanel') : t('expandPanel')}
                active={false}
                onClick={onToggle}
              >
                <PanelLeft className={cn("h-4 w-4", !isOpen && "rotate-180")} aria-hidden="true" />
              </RailButton>

              <div className="h-3" />

              <RailButton
                label={t('dashboard')}
                active={activeView === 'dashboard'}
                onClick={() => onViewChange('dashboard')}
              >
                <LayoutGrid className="h-4 w-4" aria-hidden="true" />
              </RailButton>
              <RailButton
                label={t('discover')}
                active={activeView === 'discover'}
                onClick={() => onViewChange('discover')}
              >
                <Compass className="h-4 w-4" aria-hidden="true" />
              </RailButton>
              <RailButton
                label={t('library')}
                active={activeView === 'library'}
                onClick={() => onViewChange('library')}
              >
                <FolderOpen className="h-4 w-4" aria-hidden="true" />
              </RailButton>
            </div>

            <div className="flex flex-col items-center gap-2">
              <RailButton label={t('toggleTheme')} active={false} onClick={toggleTheme}>
                <>
                  <Sun className="h-4 w-4 rotate-0 scale-100 transition-transform duration-200 dark:-rotate-90 dark:scale-0" aria-hidden="true" />
                  <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform duration-200 dark:rotate-0 dark:scale-100" aria-hidden="true" />
                </>
              </RailButton>

              <RailButton label={t('settings')} active={false} onClick={onOpenSettings}>
                <Settings className="h-4 w-4" aria-hidden="true" />
              </RailButton>
            </div>
          </div>
        </TooltipProvider>

        <div
          className={cn(
            "h-full bg-card overflow-hidden",
            isOpen && "border-r border-border/60"
          )}
          style={{ width: isOpen ? WORKSPACE_PANEL_W : 0 }}
          aria-hidden={!isOpen}
        >
          {isOpen ? (
            <div className="flex h-full flex-col p-3 gap-3">
              <div>
                <Button
                  className="w-full justify-start gap-2 h-10 shadow-sm transition-colors font-medium text-sm"
                  variant="default"
                  onClick={onNewChat}
                >
                  <Plus className="h-4 w-4" />
                  <span className="truncate">{t('newInvestigation')}</span>
                </Button>
              </div>

              <div className="pt-1">
                <Input
                  value={historyQuery}
                  onChange={(e) => setHistoryQuery(e.target.value)}
                  placeholder={t('searchPlaceholder')}
                  aria-label="Search chat history"
                  className="h-9"
                />
              </div>

              <div className="flex-1 min-h-0 overflow-hidden">
                {isLoading ? (
                  <div className="space-y-4 px-2 py-2">
                    {[1, 2, 3, 4, 5, 6].map(i => (
                      <div key={i} className="space-y-2 animate-pulse">
                        <div className="h-3 w-20 bg-muted/40 rounded" />
                        <div className="h-8 w-full bg-muted/30 rounded-lg" />
                      </div>
                    ))}
                  </div>
                ) : history.length === 0 ? (
                  <div className="px-3 text-xs text-muted-foreground italic py-2">{t('noRecentChats')}</div>
                ) : (
                  <Virtuoso
                    style={{ height: '100%' }}
                    totalCount={flatItems.length}
                    itemContent={renderFlatItem}
                    className="scrollbar-thin scrollbar-thumb-muted/50"
                  />
                )}
              </div>

              <div className="border-t border-border/60 pt-2 px-1 flex items-center justify-between">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowClearConfirm(true)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {t('clearHistory')}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </>
  )
})

function RailButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          aria-label={label}
          aria-current={active ? 'page' : undefined}
          className={cn(
            "relative flex size-10 items-center justify-center rounded-xl border transition-colors duration-200",
            active
              ? "bg-primary/10 border-primary/20 text-primary"
              : "bg-transparent border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/60 hover:border-border/60"
          )}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

function SidebarChatItem({
  item,
  onSelect,
  onDelete,
  onTogglePin
}: {
  item: ChatSession,
  onSelect: (id: string) => void,
  onDelete: (id: string) => void,
  onTogglePin: (id: string) => void
}) {
  return (
    <div className="group relative" role="listitem">
      <button
        onClick={() => onSelect(item.id)}
        aria-label={`Open chat: ${item.title}`}
        className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm transition-colors duration-200 text-muted-foreground hover:bg-muted/60 hover:text-foreground text-left pr-12"
      >
        <MessageSquare className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" aria-hidden="true" />
        <span className="truncate">{item.title}</span>
      </button>
      <div className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 flex items-center transition-opacity duration-200 bg-background/90 pl-2">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onTogglePin(item.id)
          }}
          aria-label={item.isPinned ? `Unpin ${item.title}` : `Pin ${item.title}`}
          aria-pressed={item.isPinned}
          className={cn(
            "p-1 text-muted-foreground hover:text-primary transition-colors",
            item.isPinned && "text-primary"
          )}
        >
          {item.isPinned ? <PinOff className="h-3.5 w-3.5" aria-hidden="true" /> : <Pin className="h-3.5 w-3.5" aria-hidden="true" />}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete(item.id)
          }}
          aria-label={`Delete ${item.title}`}
          className="p-1 text-muted-foreground hover:text-destructive transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}


function SidebarItem({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        "sidebar-item group",
        active && "active"
      )}>
      <Icon className={cn("h-4 w-4 transition-colors", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} aria-hidden="true" />
      <span className="truncate">{label}</span>
    </button>
  )
}
