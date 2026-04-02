'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

import {
  deleteRemoteSession,
  fetchInterruptStatus,
  fetchSessionInfo,
  fetchSessions,
  fetchSessionState,
  RemoteSessionInfo,
} from '@/lib/session-api'
import {
  buildArtifactsFromSessionState,
  buildMessagesFromSessionState,
  buildPendingInterrupt,
  createConversationId,
  deriveSearchModeFromRoute,
  getDefaultSessionTitle,
  getSessionSummary,
  replaceSessionPreservingOrder,
  sortChatSessions,
} from '@/lib/session-utils'
import { StorageService } from '@/lib/storage-service'
import { Artifact, ChatSession, Message, SessionSnapshot } from '@/types/chat'

const REMOTE_SESSION_LIMIT = 100

interface SaveToHistoryOptions {
  artifacts?: Artifact[]
  pendingInterrupt?: SessionSnapshot['pendingInterrupt']
  threadId?: string | null
  currentStatus?: string
  route?: string
  searchMode?: string
  status?: string
  canResume?: boolean
  title?: string
  summary?: string
  preserveOrder?: boolean
}

function toTimestamp(value: unknown, fallback: number): number {
  const parsed = Date.parse(String(value || ''))
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeSession(session: Partial<ChatSession>): ChatSession {
  const now = Date.now()
  const createdAt = Number(session.createdAt || now)
  const updatedAt = Number(session.updatedAt || createdAt)
  const rawId = String(session.id || '')
  const rawThreadId = typeof session.threadId === 'string' ? session.threadId.trim() : ''
  const inferredSource =
    session.source === 'legacy-local'
      ? 'legacy-local'
      : session.source === 'cache'
        ? 'cache'
        : rawThreadId || rawId.startsWith('thread_')
          ? 'remote'
          : 'legacy-local'

  return {
    id: rawId || rawThreadId || createConversationId(),
    title: String(session.title || 'New Conversation'),
    date: String(session.date || new Date(updatedAt).toLocaleDateString()),
    createdAt,
    updatedAt,
    isPinned: Boolean(session.isPinned),
    tags: Array.isArray(session.tags) ? session.tags : [],
    summary: typeof session.summary === 'string' ? session.summary : '',
    threadId: rawThreadId || (rawId.startsWith('thread_') ? rawId : null),
    status: typeof session.status === 'string' ? session.status : '',
    route: typeof session.route === 'string' ? session.route : '',
    searchMode:
      typeof session.searchMode === 'string'
        ? session.searchMode
        : deriveSearchModeFromRoute(typeof session.route === 'string' ? session.route : ''),
    canResume: Boolean(session.canResume),
    source: inferredSource,
  }
}

function isRemoteBackedSession(session: ChatSession): boolean {
  return Boolean(session.threadId || session.id.startsWith('thread_'))
}

function getThreadIdFromSession(session?: Partial<ChatSession> | null): string | null {
  const threadId = typeof session?.threadId === 'string' ? session.threadId.trim() : ''
  if (threadId) return threadId
  const id = typeof session?.id === 'string' ? session.id.trim() : ''
  return id.startsWith('thread_') ? id : null
}

function readCachedHistory(): ChatSession[] {
  return sortChatSessions(
    StorageService.getHistory<ChatSession>()
      .map((session) => normalizeSession(session))
      .filter(isRemoteBackedSession),
  )
}

function readSnapshot(sessionId: string, fallback?: Partial<ChatSession>): SessionSnapshot | null {
  const stored = StorageService.getSessionSnapshot<SessionSnapshot>(sessionId)
  if (stored) {
    return {
      ...stored,
      sessionId,
      threadId:
        typeof stored.threadId === 'string' && stored.threadId.trim()
          ? stored.threadId
          : getThreadIdFromSession(fallback),
      messages: Array.isArray(stored.messages) ? stored.messages : [],
      artifacts: Array.isArray(stored.artifacts) ? stored.artifacts : [],
      pendingInterrupt: stored.pendingInterrupt || null,
      currentStatus: String(stored.currentStatus || ''),
      route: String(stored.route || fallback?.route || ''),
      searchMode:
        typeof stored.searchMode === 'string'
          ? stored.searchMode
          : deriveSearchModeFromRoute(String(stored.route || fallback?.route || '')),
      status: String(stored.status || fallback?.status || ''),
      canResume:
        typeof stored.canResume === 'boolean'
          ? stored.canResume
          : Boolean(stored.pendingInterrupt || fallback?.canResume),
      updatedAt: Number(stored.updatedAt || fallback?.updatedAt || Date.now()),
      createdAt: Number(stored.createdAt || fallback?.createdAt || Date.now()),
    }
  }

  const messages = StorageService.getSessionMessages<Message>(sessionId)
  if (messages.length === 0 && !fallback) return null

  const now = Date.now()
  return {
    sessionId,
    threadId: getThreadIdFromSession(fallback),
    messages,
    artifacts: [],
    pendingInterrupt: null,
    currentStatus: '',
    route: String(fallback?.route || ''),
    searchMode: deriveSearchModeFromRoute(String(fallback?.route || '')),
    status: String(fallback?.status || ''),
    canResume: Boolean(fallback?.canResume),
    updatedAt: Number(fallback?.updatedAt || now),
    createdAt: Number(fallback?.createdAt || now),
  }
}

function writeSnapshot(sessionId: string, snapshot: SessionSnapshot) {
  StorageService.saveSessionSnapshot(sessionId, snapshot)
  StorageService.saveSessionMessages(sessionId, snapshot.messages)
}

function buildSessionFromRemote(remote: RemoteSessionInfo, cached?: ChatSession | null): ChatSession {
  const snapshot = readSnapshot(remote.thread_id, cached || undefined)
  const now = Date.now()
  const snapshotTitle = snapshot?.messages?.length
    ? getDefaultSessionTitle(snapshot.messages)
    : ''
  const snapshotSummary = snapshot?.messages?.length
    ? getSessionSummary(snapshot.messages)
    : ''

  return normalizeSession({
    ...cached,
    id: remote.thread_id,
    threadId: remote.thread_id,
    title: cached?.title || String(remote.topic || snapshotTitle || 'New Conversation'),
    summary: cached?.summary || snapshotSummary || String(remote.topic || ''),
    status: String(remote.status || ''),
    route: String(remote.route || ''),
    searchMode: cached?.searchMode || deriveSearchModeFromRoute(remote.route),
    canResume:
      typeof cached?.canResume === 'boolean'
        ? cached.canResume
        : Boolean(snapshot?.pendingInterrupt),
    createdAt: toTimestamp(remote.created_at, cached?.createdAt || snapshot?.createdAt || now),
    updatedAt: toTimestamp(remote.updated_at, cached?.updatedAt || snapshot?.updatedAt || now),
    source: 'remote',
  })
}

export function useChatHistory() {
  const [history, setHistory] = useState<ChatSession[]>([])
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)
  const historyRef = useRef<ChatSession[]>([])

  const commitHistory = useCallback(
    (
      nextHistory: ChatSession[],
      options: {
        preserveOrder?: boolean
      } = {},
    ) => {
      const committedHistory = options.preserveOrder ? [...nextHistory] : sortChatSessions(nextHistory)
      historyRef.current = committedHistory
      setHistory(committedHistory)
      StorageService.saveHistory(committedHistory)
    },
    [],
  )

  const refreshHistory = useCallback(async () => {
    const cachedHistory = readCachedHistory()

    try {
      const remoteHistory = await fetchSessions(REMOTE_SESSION_LIMIT)
      const merged = remoteHistory.map((remoteSession) => {
        const cached = cachedHistory.find((session) => session.id === remoteSession.thread_id) || null
        return buildSessionFromRemote(remoteSession, cached)
      })

      commitHistory(merged)
      return merged
    } catch (error) {
      console.error('Failed to refresh history from backend', error)
      if (historyRef.current.length === 0 && cachedHistory.length > 0) {
        commitHistory(cachedHistory)
      }
      return historyRef.current
    } finally {
      setIsHistoryLoading(false)
    }
  }, [commitHistory])

  useEffect(() => {
    const cachedHistory = readCachedHistory()
    if (cachedHistory.length > 0) {
      commitHistory(cachedHistory)
      setIsHistoryLoading(false)
    }

    void refreshHistory()
  }, [commitHistory, refreshHistory])

  const saveToHistory = useCallback(
    (messages: Message[], currentSessionId?: string, options: SaveToHistoryOptions = {}) => {
      const sessionId = currentSessionId || options.threadId || null
      if (!sessionId) return null

      const timestamp = Date.now()
      const existing = historyRef.current.find((session) => session.id === sessionId)
      const title = existing?.title || options.title || getDefaultSessionTitle(messages)
      const summary = options.summary || getSessionSummary(messages) || existing?.summary || title
      const nextSession = normalizeSession({
        ...existing,
        id: sessionId,
        threadId: options.threadId || existing?.threadId || sessionId,
        title,
        summary,
        status: options.status ?? existing?.status ?? '',
        route: options.route ?? existing?.route ?? '',
        searchMode:
          options.searchMode ??
          existing?.searchMode ??
          deriveSearchModeFromRoute(options.route ?? existing?.route),
        canResume:
          typeof options.canResume === 'boolean'
            ? options.canResume
            : Boolean(options.pendingInterrupt || existing?.canResume),
        updatedAt: timestamp,
        createdAt: existing?.createdAt || timestamp,
        source: 'cache',
      })

      const previousSnapshot = readSnapshot(sessionId, nextSession)
      const snapshot: SessionSnapshot = {
        sessionId,
        threadId: options.threadId || previousSnapshot?.threadId || nextSession.threadId || sessionId,
        messages,
        artifacts: options.artifacts ?? previousSnapshot?.artifacts ?? [],
        pendingInterrupt:
          typeof options.pendingInterrupt === 'undefined'
            ? previousSnapshot?.pendingInterrupt || null
            : options.pendingInterrupt,
        currentStatus:
          typeof options.currentStatus === 'undefined'
            ? previousSnapshot?.currentStatus || ''
            : options.currentStatus,
        route: options.route ?? previousSnapshot?.route ?? nextSession.route ?? '',
        searchMode:
          options.searchMode ??
          previousSnapshot?.searchMode ??
          nextSession.searchMode ??
          deriveSearchModeFromRoute(options.route ?? nextSession.route),
        status: options.status ?? previousSnapshot?.status ?? nextSession.status ?? '',
        canResume:
          typeof options.canResume === 'boolean'
            ? options.canResume
            : Boolean(options.pendingInterrupt || previousSnapshot?.canResume || nextSession.canResume),
        updatedAt: timestamp,
        createdAt: previousSnapshot?.createdAt || nextSession.createdAt || timestamp,
      }

      writeSnapshot(sessionId, snapshot)
      const nextHistory = options.preserveOrder
        ? replaceSessionPreservingOrder(historyRef.current, nextSession)
        : [nextSession, ...historyRef.current.filter((session) => session.id !== sessionId)]

      commitHistory(nextHistory, { preserveOrder: options.preserveOrder })
      return sessionId
    },
    [commitHistory],
  )

  const loadSession = useCallback(
    async (id: string): Promise<SessionSnapshot | null> => {
      const baseSession = historyRef.current.find((session) => session.id === id) || null
      const sessionId = id
      let snapshot = readSnapshot(sessionId, baseSession || { id: sessionId, threadId: sessionId })

      try {
        const [info, statePayload, interruptStatus] = await Promise.all([
          fetchSessionInfo(sessionId).catch(() => null),
          fetchSessionState(sessionId).catch(() => null),
          fetchInterruptStatus(sessionId).catch(() => null),
        ])

        if (!info && !statePayload && !snapshot) {
          return null
        }

        if (!snapshot) {
          snapshot = {
            sessionId,
            threadId: sessionId,
            messages: [],
            artifacts: [],
            pendingInterrupt: null,
            currentStatus: '',
            route: '',
            searchMode: '',
            status: '',
            canResume: false,
            updatedAt: Date.now(),
            createdAt: Date.now(),
          }
        }

        snapshot.threadId = sessionId

        if (statePayload?.state && typeof statePayload.state === 'object') {
          if (snapshot.messages.length === 0) {
            snapshot.messages = buildMessagesFromSessionState(statePayload.state, sessionId)
          }
          if (snapshot.artifacts.length === 0) {
            snapshot.artifacts = buildArtifactsFromSessionState(statePayload.state, sessionId)
          }

          const route = String(statePayload.state.route || info?.route || snapshot.route || '').trim()
          if (route) {
            snapshot.route = route
            snapshot.searchMode = deriveSearchModeFromRoute(route)
          }
        }

        if (interruptStatus?.is_interrupted) {
          const review = buildPendingInterrupt(interruptStatus.prompts, snapshot.messages)
          if (review) {
            snapshot.pendingInterrupt = review
            snapshot.canResume = true
            snapshot.currentStatus = review.description || review.title
          }
        } else if (interruptStatus?.is_interrupted === false) {
          snapshot.pendingInterrupt = null
          snapshot.canResume = false
          snapshot.currentStatus = ''
        }

        if (info) {
          snapshot.status = String(info.status || snapshot.status || '')
          if (!snapshot.route) {
            snapshot.route = String(info.route || '').trim()
          }
          if (!snapshot.searchMode) {
            snapshot.searchMode = deriveSearchModeFromRoute(snapshot.route)
          }
          snapshot.createdAt = toTimestamp(info.created_at, snapshot.createdAt)
          snapshot.updatedAt = toTimestamp(info.updated_at, snapshot.updatedAt)
        }

        writeSnapshot(sessionId, snapshot)

        const nextSession = info
          ? buildSessionFromRemote(info as RemoteSessionInfo, historyRef.current.find((session) => session.id === sessionId) || null)
          : normalizeSession({
              ...(baseSession || {}),
              id: sessionId,
              threadId: sessionId,
              title: baseSession?.title || getDefaultSessionTitle(snapshot.messages),
              summary: baseSession?.summary || getSessionSummary(snapshot.messages),
              route: snapshot.route,
              searchMode: snapshot.searchMode,
              status: snapshot.status,
              canResume: snapshot.canResume,
              createdAt: snapshot.createdAt,
              updatedAt: snapshot.updatedAt,
              source: 'cache',
            })

        commitHistory(replaceSessionPreservingOrder(historyRef.current, nextSession), {
          preserveOrder: true,
        })

        return snapshot
      } catch (error) {
        console.error('Failed to hydrate session', error)
        return snapshot
      }
    },
    [commitHistory],
  )

  const deleteSession = useCallback(
    async (id: string) => {
      const threadId = id
      const previousHistory = historyRef.current
      commitHistory(previousHistory.filter((session) => session.id !== id))
      StorageService.removeSessionMessages(id)
      StorageService.removeSessionSnapshot(id)

      try {
        await deleteRemoteSession(threadId)
        return true
      } catch (error) {
        console.error('Failed to delete remote session', error)
        await refreshHistory()
        return false
      }
    },
    [commitHistory, refreshHistory],
  )

  const clearHistory = useCallback(async () => {
    const remoteIds = Array.from(
      new Set(
        historyRef.current
          .map((session) => getThreadIdFromSession(session))
          .filter((value): value is string => Boolean(value)),
      ),
    )

    StorageService.clearAll()
    commitHistory([])

    const results = await Promise.allSettled(remoteIds.map((threadId) => deleteRemoteSession(threadId)))
    const hasFailures = results.some((result) => result.status === 'rejected')
    if (hasFailures) {
      console.error('Failed to delete one or more remote sessions while clearing history')
    }

    await refreshHistory()
  }, [commitHistory, refreshHistory])

  const togglePin = useCallback(
    (id: string) => {
      commitHistory(
        historyRef.current.map((session) =>
          session.id === id ? { ...session, isPinned: !session.isPinned, source: 'cache' } : session,
        ),
      )
    },
    [commitHistory],
  )

  const renameSession = useCallback(
    (id: string, newTitle: string) => {
      commitHistory(
        historyRef.current.map((session) =>
          session.id === id ? { ...session, title: newTitle, source: 'cache' } : session,
        ),
        { preserveOrder: true },
      )
    },
    [commitHistory],
  )

  const updateTags = useCallback(
    (id: string, tags: string[]) => {
      commitHistory(
        historyRef.current.map((session) =>
          session.id === id ? { ...session, tags, source: 'cache' } : session,
        ),
        { preserveOrder: true },
      )
    },
    [commitHistory],
  )

  return {
    history,
    isHistoryLoading,
    saveToHistory,
    loadSession,
    deleteSession,
    clearHistory,
    togglePin,
    renameSession,
    updateTags,
    refreshHistory,
  }
}
