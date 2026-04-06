'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { ArrowDown, X, Monitor } from 'lucide-react'

import { ArtifactsPanel } from './ArtifactsPanel'
import { BrowserViewer } from './BrowserViewer'
import { ChatInput } from './ChatInput'
import { EmptyState } from './EmptyState'
import { Header } from './Header'
import { MessageItem } from './MessageItem'
import { Sidebar } from './Sidebar'
import { Button } from '@/components/ui/button'
import { Discover } from '@/components/views/Discover'
import { Library } from '@/components/views/Library'
import { useChatHistory } from '@/hooks/useChatHistory'
import { usePublicModels } from '@/hooks/usePublicModels'
import { useChatStream } from '@/hooks/useChatStream'
import { ChatMode, DEFAULT_CHAT_MODE } from '@/lib/chat-mode'
import { DEFAULT_MODEL, STORAGE_KEYS } from '@/lib/constants'
import { filesToImageAttachments } from '@/lib/file-utils'
import { getInterruptInputPlaceholder } from '@/lib/interrupt-review'
import { resolveModelSelection } from '@/lib/model-selection'
import { resolveRequestedSessionRestore } from '@/lib/session-utils'
import { cn } from '@/lib/utils'
import { Message } from '@/types/chat'

export function Chat() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const requestedSessionId = searchParams.get('session')

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL)
  const [searchMode, setSearchMode] = useState<ChatMode>(DEFAULT_CHAT_MODE)
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [showMobileArtifacts, setShowMobileArtifacts] = useState(false)
  const [isArtifactsOpen, setIsArtifactsOpen] = useState(true)
  const [showBrowserViewer, setShowBrowserViewer] = useState(true)
  const [scopeRevisionMode, setScopeRevisionMode] = useState(false)
  const [currentView, setCurrentView] = useState('dashboard')
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [hasHydratedModel, setHasHydratedModel] = useState(false)

  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const lastAtBottom = useRef<boolean | null>(null)
  const openingSessionId = useRef<string | null>(null)
  const clearingSessionIdRef = useRef<string | null>(null)
  const suppressAutosaveRef = useRef(false)
  const { models: publicModels } = usePublicModels()

  const {
    history,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory,
    togglePin,
    renameSession,
  } = useChatHistory()

  const {
    messages,
    setMessages,
    isLoading,
    currentStatus,
    setCurrentStatus,
    artifacts,
    setArtifacts,
    pendingInterrupt,
    setPendingInterrupt,
    threadId,
    setThreadId,
    processChat,
    handleStop,
    handleApproveInterrupt,
    resumeInterrupt,
  } = useChatStream({ selectedModel, searchMode })

  const updateSessionUrl = useCallback(
    (sessionId: string | null) => {
      const params = new URLSearchParams(searchParams.toString())
      if (sessionId) {
        params.set('session', sessionId)
      } else {
        params.delete('session')
      }

      const query = params.toString()
      router.replace(query ? `/?${query}` : '/', { scroll: false })
    },
    [router, searchParams],
  )

  useEffect(() => {
    setScopeRevisionMode(false)
  }, [pendingInterrupt?.checkpoint, pendingInterrupt?.content, pendingInterrupt?.messageId])

  useEffect(() => {
    const savedModel = localStorage.getItem(STORAGE_KEYS.MODEL)
    if (savedModel) {
      setSelectedModel(savedModel)
    }
    setHasHydratedModel(true)
  }, [])

  useEffect(() => {
    if (!hasHydratedModel) return
    localStorage.setItem(STORAGE_KEYS.MODEL, selectedModel)
  }, [hasHydratedModel, selectedModel])

  useEffect(() => {
    const nextModel = resolveModelSelection(selectedModel, publicModels)
    if (nextModel === selectedModel) return
    setSelectedModel(nextModel)
  }, [publicModels, selectedModel])

  useEffect(() => {
    const sessionId = activeSessionId || threadId
    if (!sessionId) return
    if (messages.length === 0 && artifacts.length === 0 && !pendingInterrupt && !threadId) return
    if (suppressAutosaveRef.current) {
      suppressAutosaveRef.current = false
      return
    }

    saveToHistory(messages, sessionId, {
      artifacts,
      pendingInterrupt,
      threadId: threadId || sessionId,
      currentStatus,
      route: searchMode,
      searchMode,
      status: pendingInterrupt ? 'interrupted' : undefined,
      canResume: Boolean(pendingInterrupt),
    })
  }, [
    activeSessionId,
    artifacts,
    currentStatus,
    messages,
    pendingInterrupt,
    saveToHistory,
    searchMode,
    threadId,
  ])

  useEffect(() => {
    if (!threadId) return
    if (activeSessionId === threadId) return

    setActiveSessionId(threadId)
    updateSessionUrl(threadId)
  }, [activeSessionId, threadId, updateSessionUrl])

  const resetComposerState = useCallback(() => {
    setInput('')
    setAttachments([])
    setPendingInterrupt(null)
    setCurrentStatus('')
    setArtifacts([])
    setMessages([])
    setThreadId(null)
    setScopeRevisionMode(false)
    setSearchMode(DEFAULT_CHAT_MODE)
  }, [
    setArtifacts,
    setCurrentStatus,
    setMessages,
    setPendingInterrupt,
    setThreadId,
  ])

  const openSessionById = useCallback(
    async (sessionId: string) => {
      if (!sessionId || openingSessionId.current === sessionId) return
      openingSessionId.current = sessionId

      try {
        if (isLoading) {
          await handleStop()
        }

        const snapshot = await loadSession(sessionId)
        if (!snapshot) {
          if (requestedSessionId === sessionId) {
            updateSessionUrl(null)
          }
          return
        }

        suppressAutosaveRef.current = true
        setMessages(snapshot.messages)
        setArtifacts(snapshot.artifacts)
        setPendingInterrupt(snapshot.pendingInterrupt || null)
        setCurrentStatus(snapshot.currentStatus || '')
        setThreadId(snapshot.threadId || null)
        setSearchMode(snapshot.searchMode || DEFAULT_CHAT_MODE)
        setInput('')
        setAttachments([])
        setScopeRevisionMode(false)
        setCurrentView('dashboard')
        setActiveSessionId(sessionId)
      } finally {
        openingSessionId.current = null
      }
    },
    [
      handleStop,
      isLoading,
      loadSession,
      requestedSessionId,
      setArtifacts,
      setCurrentStatus,
      setMessages,
      setPendingInterrupt,
      setThreadId,
      updateSessionUrl,
    ],
  )

  useEffect(() => {
    const restoreDecision = resolveRequestedSessionRestore({
      activeSessionId,
      requestedSessionId,
      isHistoryLoading,
      clearingSessionId: clearingSessionIdRef.current,
    })
    clearingSessionIdRef.current = restoreDecision.nextClearingSessionId

    if (!restoreDecision.shouldOpen || !requestedSessionId) return
    void openSessionById(requestedSessionId)
  }, [activeSessionId, isHistoryLoading, openSessionById, requestedSessionId])

  const handleNewChat = useCallback(async () => {
    if (isLoading) {
      await handleStop()
    }

    const sessionId = activeSessionId || threadId
    if (messages.length > 0 && sessionId) {
      saveToHistory(messages, sessionId, {
        artifacts,
        pendingInterrupt,
        threadId: threadId || sessionId,
        currentStatus,
        route: searchMode,
        searchMode,
        status: pendingInterrupt ? 'interrupted' : undefined,
        canResume: Boolean(pendingInterrupt),
      })
    }

    clearingSessionIdRef.current = requestedSessionId || sessionId || null
    setCurrentView('dashboard')
    setActiveSessionId(null)
    updateSessionUrl(null)
    resetComposerState()
  }, [
    activeSessionId,
    artifacts,
    currentStatus,
    handleStop,
    isLoading,
    messages,
    pendingInterrupt,
    resetComposerState,
    requestedSessionId,
    saveToHistory,
    searchMode,
    threadId,
    updateSessionUrl,
  ])

  const handleDeleteChat = useCallback(
    async (id: string) => {
      await deleteSession(id)
      if (activeSessionId === id) {
        void handleNewChat()
      }
    },
    [activeSessionId, deleteSession, handleNewChat],
  )

  const handleClearHistory = useCallback(async () => {
    await clearHistory()
    await handleNewChat()
  }, [clearHistory, handleNewChat])

  const handleChatSelect = useCallback(
    (id: string) => {
      updateSessionUrl(id)
      void openSessionById(id)
    },
    [openSessionById, updateSessionUrl],
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if ((!input.trim() && attachments.length === 0) || isLoading) return

    const imagePayloads = await filesToImageAttachments(attachments)
    const trimmedInput = input.trim()
    const effectiveModel = resolveModelSelection(selectedModel, publicModels)
    const isInterruptReply =
      pendingInterrupt?.kind === 'clarify_question' || pendingInterrupt?.kind === 'scope_review'

    if (isInterruptReply && !trimmedInput) {
      return
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmedInput,
      attachments: imagePayloads,
    }

    const newHistory = [...messages, userMessage]
    setMessages(newHistory)
    setInput('')
    setAttachments([])
    if (effectiveModel !== selectedModel) {
      setSelectedModel(effectiveModel)
    }

    const sessionId = activeSessionId || threadId
    if (sessionId) {
      saveToHistory(newHistory, sessionId, {
        artifacts,
        pendingInterrupt,
        threadId: threadId || sessionId,
        currentStatus,
        route: searchMode,
        searchMode,
        status: pendingInterrupt ? 'interrupted' : undefined,
        canResume: Boolean(pendingInterrupt),
      })
    }

    if (pendingInterrupt?.kind === 'clarify_question') {
      await resumeInterrupt('answer_clarification', trimmedInput, effectiveModel)
      return
    }

    if (pendingInterrupt?.kind === 'scope_review') {
      setScopeRevisionMode(false)
      await resumeInterrupt('revise_scope', trimmedInput, effectiveModel)
      return
    }

    await processChat(newHistory, imagePayloads, effectiveModel)
  }

  const handleEditMessage = async (id: string, newContent: string) => {
    const index = messages.findIndex((message) => message.id === id)
    if (index === -1) return
    const effectiveModel = resolveModelSelection(selectedModel, publicModels)

    const previousMessages = messages.slice(0, index)
    const updatedMessage: Message = {
      ...messages[index],
      content: newContent,
    }

    const newHistory = [...previousMessages, updatedMessage]
    setMessages(newHistory)

    const sessionId = activeSessionId || threadId
    if (sessionId) {
      saveToHistory(newHistory, sessionId, {
        artifacts,
        pendingInterrupt,
        threadId: threadId || sessionId,
        currentStatus,
        route: searchMode,
        searchMode,
        status: pendingInterrupt ? 'interrupted' : undefined,
        canResume: Boolean(pendingInterrupt),
      })
    }

    if (updatedMessage.role === 'user') {
      if (effectiveModel !== selectedModel) {
        setSelectedModel(effectiveModel)
      }
      await processChat(newHistory, updatedMessage.attachments, effectiveModel)
    }
  }

  const handleStarterClick = (text: string, mode: ChatMode) => {
    setInput(text)
    setSearchMode(mode)
  }

  const handleAtBottomChange = (atBottom: boolean) => {
    if (lastAtBottom.current === atBottom) return
    lastAtBottom.current = atBottom
    setShowScrollButton(!atBottom)
  }

  const scrollToBottom = () => {
    const idx = messages.length - 1
    if (idx >= 0) {
      virtuosoRef.current?.scrollToIndex({
        index: idx,
        align: 'end',
        behavior: 'smooth',
      })
    }
  }

  const inputPlaceholder = getInterruptInputPlaceholder(pendingInterrupt, {
    revisionMode: scopeRevisionMode,
  })

  const renderContent = () => {
    if (currentView === 'discover') return <Discover />
    if (currentView === 'library') {
      return (
        <Library
          history={history}
          isHistoryLoading={isHistoryLoading}
          onNewChat={() => void handleNewChat()}
          onSelectSession={handleChatSelect}
          onDeleteSession={(id) => {
            void handleDeleteChat(id)
          }}
          onRenameSession={renameSession}
          onTogglePin={togglePin}
        />
      )
    }

    return (
      <div className="flex-1 flex flex-col min-h-0">
        {messages.length === 0 ? (
          <div className="h-full w-full p-4 overflow-y-auto">
            <EmptyState
              selectedMode={searchMode}
              onModeSelect={setSearchMode}
              onStarterClick={handleStarterClick}
            />
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={messages}
            followOutput="auto"
            atBottomStateChange={handleAtBottomChange}
            className="scrollbar-thin scrollbar-thumb-muted/20"
            itemContent={(index, message) => (
              <div className="max-w-5xl mx-auto px-4 sm:px-0">
                <MessageItem
                  key={message.id}
                  message={message}
                  onEdit={handleEditMessage}
                  footer={
                    pendingInterrupt?.kind === 'scope_review' &&
                    pendingInterrupt?.messageId === message.id ? (
                      <div className="flex flex-col gap-3">
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            onClick={() => {
                              setScopeRevisionMode(false)
                              void resumeInterrupt('approve_scope')
                            }}
                            disabled={isLoading}
                          >
                            确认开始研究
                          </Button>
                          <Button
                            size="sm"
                            variant={scopeRevisionMode ? 'default' : 'secondary'}
                            onClick={() => {
                              setScopeRevisionMode(true)
                              setCurrentStatus('继续在下方输入框里说明你希望如何修改研究范围')
                            }}
                            disabled={isLoading}
                          >
                            继续修改
                          </Button>
                        </div>
                        {scopeRevisionMode ? (
                          <div className="text-xs text-muted-foreground">
                            在下方输入框继续补充修改意见，发送后会基于你的反馈重写草案。
                          </div>
                        ) : null}
                      </div>
                    ) : undefined
                  }
                />
              </div>
            )}
            components={{
              Footer: () => (
                <div className="max-w-5xl mx-auto px-4 sm:px-0 pb-4">
                  <div className="h-4" />
                </div>
              ),
            }}
          />
        )}
      </div>
    )
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground font-sans selection:bg-primary/20">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={() => void handleNewChat()}
        onSelectChat={handleChatSelect}
        onDeleteChat={(id) => {
          void handleDeleteChat(id)
        }}
        onTogglePin={togglePin}
        onClearHistory={() => {
          void handleClearHistory()
        }}
        activeView={currentView}
        onViewChange={setCurrentView}
        history={history}
        activeSessionId={activeSessionId}
        isLoading={isHistoryLoading}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        <Header
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onToggleArtifacts={() => setShowMobileArtifacts(!showMobileArtifacts)}
          hasArtifacts={artifacts.length > 0}
        />

        {renderContent()}
        {currentView === 'dashboard' && (
          <>
            <div
              className={cn(
                'absolute bottom-24 right-6 z-30 transition-all duration-500',
                showScrollButton
                  ? 'translate-y-0 opacity-100'
                  : 'translate-y-10 opacity-0 pointer-events-none',
              )}
            >
              <Button
                variant="outline"
                size="icon"
                className="rounded-full shadow-lg bg-background/80 backdrop-blur border-primary/20 hover:bg-background"
                onClick={scrollToBottom}
              >
                <ArrowDown className="h-4 w-4" />
              </Button>
            </div>

            {pendingInterrupt && pendingInterrupt.kind === 'tool_approval' && (
              <div className="mx-4 mb-3 p-3 border rounded-xl bg-amber-50 text-amber-900 shadow-sm flex flex-col gap-2">
                <div className="text-sm font-semibold">{pendingInterrupt.title || 'Review required'}</div>
                <div className="text-xs text-amber-800">
                  {pendingInterrupt.description || 'Review the current checkpoint before continuing.'}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleApproveInterrupt} disabled={isLoading}>
                    Approve & Continue
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setPendingInterrupt(null)}
                    disabled={isLoading}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {currentView === 'dashboard' && (
          <ChatInput
            input={input}
            setInput={setInput}
            attachments={attachments}
            setAttachments={setAttachments}
            placeholder={inputPlaceholder || undefined}
            onSubmit={handleSubmit}
            isLoading={isLoading}
            onStop={handleStop}
            searchMode={searchMode}
            setSearchMode={setSearchMode}
          />
        )}
      </div>

      {artifacts.length > 0 && (
        <div
          className={cn(
            'border-l hidden xl:flex flex-col bg-card animate-in slide-in-from-right duration-500 shadow-2xl z-20 transition-all',
            isArtifactsOpen ? 'w-[400px]' : 'w-[50px]',
          )}
        >
          <ArtifactsPanel
            artifacts={artifacts}
            isOpen={isArtifactsOpen}
            onToggle={() => setIsArtifactsOpen(!isArtifactsOpen)}
          />
        </div>
      )}

      {currentView === 'dashboard' && threadId && (
        <>
          <Button
            variant="outline"
            size="icon"
            className="fixed bottom-32 right-6 z-50 rounded-full shadow-lg bg-background"
            onClick={() => setShowBrowserViewer(!showBrowserViewer)}
            title={showBrowserViewer ? 'Hide Browser' : 'Show Browser'}
          >
            <Monitor className={cn('h-4 w-4', showBrowserViewer && 'text-primary')} />
          </Button>

          {showBrowserViewer && (
            <div className="fixed bottom-48 right-6 z-40">
              <BrowserViewer
                threadId={threadId}
                className="shadow-2xl"
                defaultExpanded={true}
                alwaysShow={true}
                mode="stream"
                onClose={() => setShowBrowserViewer(false)}
              />
            </div>
          )}
        </>
      )}

      {showMobileArtifacts && (
        <div className="fixed inset-0 z-50 bg-background xl:hidden flex flex-col animate-in slide-in-from-right duration-300">
          <div className="flex items-center justify-between p-4 border-b">
            <h2 className="font-semibold">Artifacts</h2>
            <Button variant="ghost" size="icon" onClick={() => setShowMobileArtifacts(false)}>
              <X className="h-5 w-5" />
            </Button>
          </div>
          <div className="flex-1 overflow-hidden">
            <ArtifactsPanel artifacts={artifacts} />
          </div>
        </div>
      )}
    </div>
  )
}
