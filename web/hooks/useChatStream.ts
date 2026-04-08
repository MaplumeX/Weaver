import { useState, useRef, useCallback } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, RunMetrics, MessageSource } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'
import { ChatMode, createSearchModePayload } from '@/lib/chat-mode'
import { buildChatRequestPayload } from '@/lib/chat-request'
import { createLegacyChatStreamState, consumeLegacyChatStreamChunk } from '@/lib/chatStreamProtocol'
import { appendProcessEvent, createStreamingAssistantMessage } from '@/lib/chat-stream-state'
import { getDeepResearchAutoStatusText } from '@/lib/deep-research-progress'
import {
  buildInterruptResumePayload,
  getInterruptConversationMessage,
  InterruptReview,
  normalizeInterruptReview,
} from '@/lib/interrupt-review'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: ChatMode
}

type ToolLifecycleEventType = 'tool'

export function getDeepResearchAutoStatus(eventType: string, payload: unknown): string | null {
  return getDeepResearchAutoStatusText(eventType, payload)
}

function getInterruptStatusText(review: InterruptReview | null, message: string): string {
  if (review?.kind === 'clarify_question') return '继续补充你的研究目标与约束'
  if (review?.kind === 'scope_review') return '请确认研究范围，或继续修改'
  return review?.title || message || 'Review required before continuing'
}

function normalizeToolEvent(
  _eventType: ToolLifecycleEventType,
  payload: Record<string, unknown> | undefined,
) {
  const toolName = String(payload?.name || payload?.tool || payload?.tool_id || '').trim() || 'unknown'
  const args =
    payload?.args && typeof payload.args === 'object'
      ? payload.args
      : payload?.input && typeof payload.input === 'object'
        ? payload.input
        : payload?.query
          ? { query: payload.query }
          : {}

  const status =
    String(payload?.status || '').trim() || (payload?.success === false ? 'failed' : 'running')

  const toolCallId = String(payload?.toolCallId || payload?.tool_call_id || '').trim()

  return {
    toolName,
    args,
    status,
    toolCallId: toolCallId || undefined,
    payload: {
      ...payload,
      tool_id: payload?.tool_id || toolName,
      name: toolName,
      tool: toolName,
      status,
      phase: payload?.phase || (status === 'completed' ? 'result' : status === 'failed' ? 'error' : 'start'),
      ...(Object.keys(args).length > 0 ? { args } : {}),
    },
  }
}

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<InterruptReview | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  
  const abortControllerRef = useRef<AbortController | null>(null)

  const handleStop = useCallback(async () => {
    // 优先通知后端取消当前线程
    if (threadId) {
      try {
        await fetch(
          `${getApiBaseUrl()}/api/chat/cancel/${threadId}`,
          { method: 'POST' }
        )
        setCurrentStatus('已发送取消请求...')
      } catch (err) {
        console.error('取消请求失败', err)
      }
    }
    // 同时中断前端的 SSE
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
    setCurrentStatus('已取消')
    setTimeout(() => setCurrentStatus(''), 3000)
  }, [threadId])

  const consumeStreamingResponse = useCallback(
    async (
      response: Response,
      initialMessage: Message,
      readerOverride?: ReadableStreamDefaultReader<Uint8Array>,
    ) => {
      const threadHeader = response.headers.get('X-Thread-ID') || response.headers.get('x-thread-id')
      if (threadHeader) {
        setThreadId(threadHeader)
      }

      const reader = readerOverride || response.body?.getReader()
      if (!reader) {
        throw new Error('No reader available')
      }

      let assistantMessage = initialMessage
      const decoder = new TextDecoder()
      const streamState = createLegacyChatStreamState()
      let interrupted = false
      let searchCount = 0
      let lastAutoStatus = ''
      let lastAutoStatusAt = 0

      const syncAssistantMessage = () => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMessage.id ? { ...assistantMessage } : msg))
        )
      }

      const pushProcessEvent = (type: string, payload: unknown) => {
        assistantMessage = appendProcessEvent(assistantMessage, type, payload)
      }

      const setAutoStatus = (text: string) => {
        const next = String(text || '').trim()
        if (!next) return
        const now = Date.now()
        if (next === lastAutoStatus) return
        if (now - lastAutoStatusAt < 250) return
        lastAutoStatus = next
        lastAutoStatusAt = now
        setCurrentStatus(next)
      }

      while (true) {
        const { done, value } = await reader.read()
        const chunk = done ? decoder.decode() : decoder.decode(value, { stream: true })
        const events = consumeLegacyChatStreamChunk(streamState, chunk, { flush: done })

        for (const data of events) {
          if (data.type === 'status') {
            pushProcessEvent('status', data.data)
            syncAssistantMessage()
          } else if (data.type === 'text') {
            assistantMessage.content += data.data.content
            syncAssistantMessage()
          } else if (data.type === 'message') {
            assistantMessage.content = data.data.content
            syncAssistantMessage()
          } else if (data.type === 'interrupt') {
            interrupted = true
            const reviewBase = normalizeInterruptReview(data.data)
            const review = reviewBase ? { ...reviewBase, messageId: assistantMessage.id } : null
            setPendingInterrupt(review)
            const msg = getInterruptConversationMessage(reviewBase, data.data)
            setCurrentStatus(getInterruptStatusText(review, msg))
            assistantMessage.content =
              assistantMessage.content || msg || review?.title || 'Review required before continuing.'
            assistantMessage.isStreaming = false
            assistantMessage.completedAt = Date.now()
            pushProcessEvent('interrupt', data.data)
            syncAssistantMessage()
            break
          } else if (data.type === 'tool') {
            const normalized = normalizeToolEvent('tool', data.data)
            const toolCallId = normalized.toolCallId || `tool-${Date.now()}-${Math.random()}`

            const state: ToolInvocation['state'] =
              normalized.status === 'completed'
                ? 'completed'
                : normalized.status === 'failed'
                  ? 'failed'
                  : 'running'

            const toolInvocation: ToolInvocation = {
              toolCallId,
              toolName: normalized.toolName,
              state,
              args: normalized.args,
            }

            const prevTools = assistantMessage.toolInvocations || []
            const existingIndex = prevTools.findIndex((t) =>
              normalized.toolCallId
                ? t.toolCallId === toolCallId
                : t.toolName === normalized.toolName && t.state === 'running'
            )
            assistantMessage = {
              ...assistantMessage,
              toolInvocations:
                existingIndex >= 0
                  ? prevTools.map((tool, index) =>
                      index === existingIndex ? { ...tool, ...toolInvocation } : tool,
                    )
                  : [...prevTools, toolInvocation],
            }

            pushProcessEvent('tool', normalized.payload)
            syncAssistantMessage()
          } else if (data.type === 'search') {
            searchCount += 1
            const query = String(data.data?.query || '').trim()
            const mode = String(data.data?.mode || '').trim().toLowerCase()
            const epoch = data.data?.epoch

            if (query) {
              if (mode === 'tree') {
                setAutoStatus(`深度调研（树）：第 ${searchCount} 次检索 · ${query}`)
              } else if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：第 ${epoch} 轮检索（${searchCount}）· ${query}`)
              } else {
                setAutoStatus(`检索中（${searchCount}）· ${query}`)
              }
            }

            pushProcessEvent('search', data.data)
            syncAssistantMessage()
          } else if (data.type === 'research_node_start') {
            const nodeId = String(data.data?.node_id || data.data?.nodeId || '').trim()
            const epoch = data.data?.epoch
            if (nodeId.includes('deep_research')) {
              if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：开始第 ${epoch} 轮…`)
              } else {
                setAutoStatus('深度调研：开始调研…')
              }
            } else if (nodeId) {
              setAutoStatus(`研究节点开始：${nodeId}`)
            }
            pushProcessEvent('research_node_start', data.data)
            syncAssistantMessage()
          } else if (data.type === 'research_node_complete') {
            const nodeId = String(data.data?.node_id || data.data?.nodeId || '').trim()
            const epoch = data.data?.epoch
            if (nodeId.includes('deep_research')) {
              if (typeof epoch === 'number') {
                setAutoStatus(`深度调研：完成第 ${epoch} 轮，继续…`)
              } else {
                setAutoStatus('深度调研：本轮完成，继续…')
              }
            }
            pushProcessEvent('research_node_complete', data.data)
            syncAssistantMessage()
          } else if (data.type === 'quality_update') {
            const score =
              typeof data.data?.query_coverage_score === 'number'
                ? data.data.query_coverage_score
                : typeof data.data?.citation_coverage_score === 'number'
                  ? data.data.citation_coverage_score
                  : undefined
            if (typeof score === 'number' && score >= 0) {
              const pct = Math.max(0, Math.min(1, score)) * 100
              setAutoStatus(`质量评估：覆盖度 ${pct.toFixed(0)}%`)
            }
            pushProcessEvent('quality_update', data.data)
            syncAssistantMessage()
          } else if (data.type === 'deep_research_topology_update') {
            pushProcessEvent('deep_research_topology_update', data.data)
            syncAssistantMessage()
          } else if (
            [
              'research_agent_start',
              'research_agent_complete',
              'research_task_update',
              'research_artifact_update',
              'research_decision',
            ].includes(data.type)
          ) {
            const autoStatus = getDeepResearchAutoStatus(data.type, data.data)
            if (autoStatus) setAutoStatus(autoStatus)
            pushProcessEvent(data.type, data.data)
            syncAssistantMessage()
          } else if (['thinking', 'screenshot', 'task_update'].includes(data.type)) {
            pushProcessEvent(data.type, data.data)
            syncAssistantMessage()
          } else if (data.type === 'tool_progress') {
            const normalized = normalizeToolEvent('tool', data.data)
            pushProcessEvent('tool_progress', {
              ...data.data,
              name: normalized.toolName,
              tool: normalized.toolName,
              tool_id: data.data?.tool_id || normalized.toolName,
              phase: data.data?.phase || 'progress',
            })
            syncAssistantMessage()
          } else if (data.type === 'sources') {
            const items = (data.data?.items || []) as MessageSource[]
            assistantMessage = { ...assistantMessage, sources: items }
            syncAssistantMessage()
          } else if (data.type === 'completion') {
            assistantMessage = {
              ...assistantMessage,
              content: data.data.content,
              isStreaming: false,
              completedAt: Date.now(),
            }
            syncAssistantMessage()
          } else if (data.type === 'done') {
            const metrics = (data.data?.metrics || {}) as RunMetrics
            assistantMessage = {
              ...assistantMessage,
              metrics,
              isStreaming: false,
              completedAt: assistantMessage.completedAt || Date.now(),
            }
            pushProcessEvent('done', data.data)
            syncAssistantMessage()
          } else if (data.type === 'cancelled') {
            const msg = data.data?.message || 'Task was cancelled'
            assistantMessage = {
              ...assistantMessage,
              content: assistantMessage.content || msg,
              isStreaming: false,
              completedAt: Date.now(),
            }
            pushProcessEvent('cancelled', data.data)
            syncAssistantMessage()
          } else if (data.type === 'error') {
            const msg = data.data?.message || 'An error occurred'
            assistantMessage = {
              ...assistantMessage,
              content: assistantMessage.content || msg,
              isStreaming: false,
              completedAt: Date.now(),
            }
            pushProcessEvent('error', data.data)
            syncAssistantMessage()
          } else if (data.type === 'artifact') {
            const newArtifact = data.data as Artifact
            setArtifacts((prev) => {
              if (prev.some((a) => a.id === newArtifact.id)) return prev
              if (
                newArtifact.type === 'report' &&
                prev.some(
                  (a) =>
                    a.type === 'report' &&
                    a.title === newArtifact.title &&
                    a.content === newArtifact.content,
                )
              ) {
                return prev
              }
              return [...prev, newArtifact]
            })
          }
        }

        if (done || interrupted) break
      }

      if (assistantMessage.isStreaming) {
        assistantMessage = {
          ...assistantMessage,
          isStreaming: false,
          completedAt: assistantMessage.completedAt || Date.now(),
        }
        syncAssistantMessage()
      }

      if (!interrupted) {
        setCurrentStatus('')
      }
    },
    [],
  )

  const processChat = useCallback(async (
    messageHistory: Message[],
    images?: ImageAttachment[],
    modelOverride?: string,
  ) => {
    setIsLoading(true)
    abortControllerRef.current = new AbortController()

    try {
      const requestModel = String(modelOverride || selectedModel || '').trim()
      const response = await fetch(
        `${getApiBaseUrl()}/api/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(
            buildChatRequestPayload({
              messageHistory: messageHistory.map(m => ({ role: m.role, content: m.content })),
              model: requestModel,
              searchMode: createSearchModePayload(searchMode),
              images: images || [],
              threadId,
            }),
          ),
          signal: abortControllerRef.current.signal
        }
      )

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const assistantMessage = createStreamingAssistantMessage()
      setMessages((prev) => [...prev, assistantMessage])
      await consumeStreamingResponse(response, assistantMessage)
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Ignore aborts triggered by the user.
      } else {
        console.error('Error:', error)
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: 'Sorry, an error occurred. Please try again.',
          },
        ])
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [selectedModel, searchMode, consumeStreamingResponse, threadId])

  const resumeInterrupt = useCallback(async (
    action: string,
    input: string = '',
    modelOverride?: string,
  ) => {
    if (!pendingInterrupt || !threadId) return
    setIsLoading(true)
    setCurrentStatus('继续执行调研流程…')
    abortControllerRef.current = new AbortController()
    try {
      const requestModel = String(modelOverride || selectedModel || '').trim()
      const resumePayload = buildInterruptResumePayload(pendingInterrupt, action, input)
      const res = await fetch(
        `${getApiBaseUrl()}/api/interrupt/resume`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            thread_id: threadId,
            payload: resumePayload,
            stream: true,
            model: requestModel,
            search_mode: createSearchModePayload(searchMode),
          }),
          signal: abortControllerRef.current.signal,
        }
      )
      if (!res.ok) {
        let detail = 'Failed to resume'
        try {
          const err = await res.json()
          detail = String(err?.detail || detail)
        } catch {}
        throw new Error(detail)
      }

      const reader = res.body?.getReader()
      if (!reader) {
        throw new Error('No reader available')
      }

      const assistantMessage = createStreamingAssistantMessage()
      setPendingInterrupt(null)
      setMessages((prev) => [...prev, assistantMessage])
      await consumeStreamingResponse(res, assistantMessage, reader)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        // Ignore aborts triggered by the user.
      } else {
        console.error('Failed to resume interrupt', err)
        setMessages(prev => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: err instanceof Error ? err.message : 'Resume failed. Please retry.',
          }
        ])
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [pendingInterrupt, threadId, selectedModel, searchMode, consumeStreamingResponse])

  const handleApproveInterrupt = useCallback(async () => {
    await resumeInterrupt('approve')
  }, [resumeInterrupt])

  return {
    messages,
    setMessages,
    isLoading,
    setIsLoading,
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
  }
}
