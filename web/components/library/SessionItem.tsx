'use client'

import { ChatSession } from '@/types/chat'
import { MessageSquare, MoreVertical, Pencil, Trash2, Pin, PinOff, Clock } from 'lucide-react'
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
        "group relative p-4 rounded-xl border border-border/60 bg-card cursor-pointer border-l-4 transition-colors hover:bg-accent",
        session.isPinned ? "border-l-primary" : "border-l-transparent",
      )}
      onClick={() => onSelect(session.id)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <MessageSquare className="h-4 w-4 text-primary shrink-0" />
            <h3 className="font-semibold text-base truncate group-hover:text-primary transition-colors">
              {session.title}
            </h3>
            {session.isPinned && <Pin className="h-3 w-3 text-primary fill-primary" />}
          </div>

          <p className="text-sm text-muted-foreground line-clamp-1 mb-3">
            {session.summary || "No summary available"}
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground mr-2">
              <Clock className="h-3 w-3" />
              {formatRelativeTime(session.updatedAt)}
            </div>
            {session.tags?.map(tag => (
              <Badge key={tag} variant="secondary" className="px-1.5 py-0 text-[10px]">
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
                className="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
                aria-label="Session actions"
                title="Session actions"
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-40 p-1" align="end">
              <Button type="button" variant="ghost" className="w-full justify-start text-sm h-9" onClick={() => onTogglePin(session.id)}>
                {session.isPinned ? <PinOff className="mr-2 h-4 w-4" /> : <Pin className="mr-2 h-4 w-4" />}
                {session.isPinned ? 'Unpin' : 'Pin'}
              </Button>
              <Button type="button" variant="ghost" className="w-full justify-start text-sm h-9" onClick={() => onRename(session.id)}>
                <Pencil className="mr-2 h-4 w-4" /> Rename
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full justify-start text-sm h-9 text-destructive hover:text-destructive"
                onClick={() => onDelete(session.id)}
              >
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  )
}
