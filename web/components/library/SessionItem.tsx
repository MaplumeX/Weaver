'use client'

import { ChatSession } from '@/types/chat'
import { MessageSquare, MoreVertical, PencilLine, Trash2, Star, StarOff, Clock } from '@/components/ui/icons'
import { formatRelativeTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

interface SessionItemProps {
  session: ChatSession
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string) => void
  onTogglePin: (id: string) => void
}

export function SessionItem({
  session,
  onSelect,
  onDelete,
  onRename,
  onTogglePin
}: SessionItemProps) {
  return (
    <div
      className={cn(
        "group relative p-4 rounded-xl border bg-card cursor-pointer transition-all duration-200 hover:shadow-sm hover:translate-y-[-1px]",
        session.isPinned
          ? "border-l-2 border-l-primary border-t-border/30 border-r-border/30 border-b-border/30"
          : "border-border/30 hover:border-border/50",
      )}
      onClick={() => onSelect(session.id)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <MessageSquare className="h-4 w-4 text-primary/70 shrink-0" />
            <h3 className="font-semibold text-sm truncate group-hover:text-primary transition-colors">
              {session.title}
            </h3>
            {session.isPinned && <Star className="h-3 w-3 text-primary fill-primary" />}
          </div>

          <p className="text-[13px] text-muted-foreground/80 line-clamp-1 mb-3 pl-6">
            {session.summary || "No summary available"}
          </p>

          <div className="flex flex-wrap items-center gap-2 pl-6">
            <div className="flex items-center gap-1 text-xs text-muted-foreground/50 mr-2">
              <Clock className="h-3 w-3" />
              {formatRelativeTime(session.updatedAt)}
            </div>
            {session.tags?.map(tag => (
              <Badge key={tag} variant="secondary" className="px-1.5 py-0 text-[10px] font-medium bg-muted/40 border-border/30">
                {tag}
              </Badge>
            ))}
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100 rounded-lg"
                aria-label="Session actions"
                title="Session actions"
              >
                <MoreVertical className="h-3.5 w-3.5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-40 p-1 bg-popover/90 backdrop-blur-xl border-border/30" align="end">
              <Button type="button" variant="ghost" className="w-full justify-start text-xs h-8 gap-2" onClick={() => onTogglePin(session.id)}>
                {session.isPinned ? <StarOff className="h-3.5 w-3.5" /> : <Star className="h-3.5 w-3.5" />}
                {session.isPinned ? 'Unpin' : 'Pin'}
              </Button>
              <Button type="button" variant="ghost" className="w-full justify-start text-xs h-8 gap-2" onClick={() => onRename(session.id)}>
                <PencilLine className="h-3.5 w-3.5" /> Rename
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full justify-start text-xs h-8 gap-2 text-destructive hover:text-destructive"
                onClick={() => onDelete(session.id)}
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  )
}
