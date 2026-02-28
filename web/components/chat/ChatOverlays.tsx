'use client'

import { ArrowDown } from '@/components/ui/icons'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ArtifactsPanel } from './ArtifactsPanel'
import { Artifact, PendingInterrupt } from '@/types/chat'

interface ScrollButtonProps {
  visible: boolean
  onClick: () => void
}

export function ScrollToBottomButton({ visible, onClick }: ScrollButtonProps) {
  return (
    <div className={cn(
      "absolute right-6 z-30 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
      visible
        ? "translate-y-0 opacity-100"
        : "translate-y-8 opacity-0 pointer-events-none"
    )}
    style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom, 0px))' }}
    >
      <Button
        variant="outline"
        size="icon"
        className="rounded-full bg-card/80 backdrop-blur-xl border-border/30 shadow-lg hover:bg-card hover:shadow-xl transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] h-9 w-9"
        onClick={onClick}
        aria-label="Scroll to bottom"
      >
        <ArrowDown className="h-4 w-4" />
      </Button>
    </div>
  )
}

interface InterruptBannerProps {
  pendingInterrupt: PendingInterrupt | null
  isLoading: boolean
  onApprove: () => void
  onDismiss: () => void
}

export function InterruptBanner({ pendingInterrupt, isLoading, onApprove, onDismiss }: InterruptBannerProps) {
  if (!pendingInterrupt) return null

  return (
    <div
      className={cn(
        "mx-4 mb-3 p-3.5 rounded-xl border shadow-sm flex flex-col gap-2 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
        "bg-amber-50/40 text-amber-950 border-border/30",
        "dark:bg-amber-950/10 dark:text-amber-50 dark:border-border/30"
      )}
      role="alert"
    >
      <div className="text-[13px] font-medium">Tool approval required</div>
      <div className="text-xs text-amber-900/60 dark:text-amber-100/60 text-pretty">
        {pendingInterrupt.message || pendingInterrupt?.prompts?.[0]?.message || 'Approve tool execution to continue.'}
      </div>
      <div className="flex gap-2 mt-0.5">
        <Button size="sm" className="h-8 text-xs" onClick={onApprove} disabled={isLoading}>
          Approve & Continue
        </Button>
        <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={onDismiss} disabled={isLoading}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}

interface MobileArtifactsOverlayProps {
  show: boolean
  artifacts: Artifact[]
  threadId: string | null
  onClose: () => void
}

export function MobileArtifactsOverlay({ show, artifacts, threadId, onClose }: MobileArtifactsOverlayProps) {
  if (!show) return null

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-xl xl:hidden flex flex-col transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <ArtifactsPanel
        artifacts={artifacts}
        threadId={threadId}
        isOpen={true}
        onToggle={onClose}
        toggleLabel="Close inspector"
        toggleTitle="Close inspector"
        allowFullscreen={false}
      />
    </div>
  )
}
