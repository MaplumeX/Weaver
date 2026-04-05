import { useState, useRef, useCallback } from 'react'
import { Message, Artifact, ToolInvocation, ImageAttachment, RunMetrics, MessageSource } from '@/types/chat'
import { getApiBaseUrl } from '@/lib/api'
import { ChatMode, createSearchModePayload } from '@/lib/chat-mode'
import { createLegacyChatStreamState, consumeLegacyChatStreamChunk } from '@/lib/chatStreamProtocol'
import { appendProcessEvent, createStreamingAssistantMessage } from '@/lib/chat-stream-state'
import {
  buildInterruptResumePayload,
  getInterruptConversationMessage,
  normalizeInterruptReview,
} from '@/lib/interrupt-review'

interface UseChatStreamProps {
  selectedModel: string
  searchMode: ChatMode
}

type ToolLifecycleEventType = 'tool' | 'tool_start' | 'tool_result' | 'tool_error'

export function getDeepResearchAutoStatus(eventType: string, payload: any): string | null {
  const role = String(payload?.role || '').trim()
  const agentId = String(payload?.agent_id || payload?.agentId || '').trim()
  const taskTitle = String(
    payload?.title || payload?.objective_summary || payload?.query || payload?.task_id || '',
  ).trim()
  const decisionType = String(payload?.decision_type || '').trim()
  const artifactType = String(payload?.artifact_type || '').trim()
  const status = String(payload?.status || '').trim()
  const stage = String(payload?.stage || '').trim()
  const validationStage = String(payload?.validation_stage || '').trim()
  const attempt = typeof payload?.attempt === 'number' ? payload.attempt : undefined
  const resumed = Boolean(payload?.resumed_from_checkpoint)

  const researcherStageLabel =
    stage === 'search'
      ? '搜索来源'
      : stage === 'read'
        ? '读取文档'
        : stage === 'extract'
          ? '抽取证据'
          : stage === 'synthesize'
            ? '综合分支结论'
            : '执行分支任务'

  if (eventType === 'research_agent_start') {
    if (role === 'clarify') return '多 Agent 调研：正在澄清研究目标与约束…'
    if (role === 'scope') {
      return resumed ? '多 Agent 调研：正在根据反馈重写研究范围草案…' : '多 Agent 调研：正在生成研究范围草案…'
    }
    if (role === 'supervisor') {
      return resumed
        ? '多 Agent 调研：已确认范围，正在继续评估并派发研究分支…'
        : '多 Agent 调研：正在评估范围并派发研究分支…'
    }
    if (role === 'researcher') {
      const target = taskTitle || agentId || 'researcher'
      if (attempt && attempt > 1) return `多 Agent 调研：重试 branch · ${target} · ${researcherStageLabel}`
      if (resumed) return `多 Agent 调研：恢复 branch · ${target} · ${researcherStageLabel}`
      return `多 Agent 调研：开始 branch · ${target} · ${researcherStageLabel}`
    }
    if (role === 'reviewer') {
      return resumed ? '多 Agent 调研：已恢复执行，正在审查章节草稿…' : '多 Agent 调研：正在审查章节草稿…'
    }
    if (role === 'revisor') {
      return resumed ? '多 Agent 调研：已恢复执行，正在修订章节草稿…' : '多 Agent 调研：正在修订章节草稿…'
    }
    if (role === 'verifier') {
      if (validationStage === 'claim_check' || stage === 'final_claim_gate') {
        return resumed ? '多 Agent 调研：已恢复执行，正在核对 claim 与 citation…' : '多 Agent 调研：正在核对 claim 与 citation…'
      }
      if (validationStage === 'coverage_check') {
        return resumed ? '多 Agent 调研：已恢复执行，正在检查 coverage 与 gap…' : '多 Agent 调研：正在检查 coverage 与 gap…'
      }
      return resumed ? '多 Agent 调研：已恢复执行，正在验证分支结论…' : '多 Agent 调研：正在验证分支结论…'
    }
    if (role === 'reporter') return resumed ? '多 Agent 调研：已恢复执行，正在生成最终报告…' : '多 Agent 调研：正在生成最终报告…'
  }

  if (eventType === 'research_agent_complete') {
    if (role === 'clarify' && status === 'completed') return '多 Agent 调研：需求澄清完成'
    if (role === 'scope' && status === 'completed') return '多 Agent 调研：范围草案已生成'
    if (role === 'reporter' && status === 'completed') return '多 Agent 调研：最终报告已生成'
    if (role === 'reviewer' && status === 'completed') return '多 Agent 调研：章节审查完成'
    if (role === 'revisor' && status === 'completed') return '多 Agent 调研：章节修订完成'
    if (role === 'verifier' && status === 'completed') {
      if (validationStage === 'claim_check') return '多 Agent 调研：claim/citation 检查完成'
      if (validationStage === 'coverage_check') return '多 Agent 调研：coverage/gap 检查完成'
      return '多 Agent 调研：分支验证完成'
    }
    if (role === 'researcher' && status === 'completed') {
      return `多 Agent 调研：branch 完成 · ${taskTitle || agentId || 'researcher'}`
    }
  }

  if (eventType === 'research_task_update') {
    if (status === 'ready') return `多 Agent 调研：branch 已入队 · ${taskTitle || '未命名 branch'}`
    if (status === 'in_progress') {
      if (attempt && attempt > 1) return `多 Agent 调研：重试 branch · ${taskTitle || '未命名 branch'} · ${researcherStageLabel}`
      return `多 Agent 调研：执行 branch · ${taskTitle || '未命名 branch'} · ${researcherStageLabel}`
    }
    if (status === 'completed') return `多 Agent 调研：branch 完成 · ${taskTitle || '未命名 branch'}`
    if (status === 'failed' || status === 'blocked') return `多 Agent 调研：branch${status === 'failed' ? '失败' : '阻塞'} · ${taskTitle || '未命名 branch'}`
  }

  if (eventType === 'research_artifact_update') {
    if (artifactType === 'scope_draft') {
      if (status === 'approved') return '多 Agent 调研：研究范围已批准，准备开始规划'
      if (status === 'revision_requested') return '多 Agent 调研：已收到范围修改意见，正在重写草案'
      return '多 Agent 调研：新的研究范围草案已生成'
    }
    if (artifactType === 'scope') return '多 Agent 调研：研究范围已固化，准备拆分研究分支'
    if (artifactType === 'plan') return '多 Agent 调研：已生成章节研究计划'
    if (artifactType === 'outline') return '多 Agent 调研：已生成研究大纲与必需章节'
    if (artifactType === 'evidence_bundle') {
      const sourceCount = typeof payload?.source_count === 'number' ? payload.source_count : 0
      return sourceCount > 0
        ? `多 Agent 调研：已记录分支证据包 · ${sourceCount} 个来源`
        : '多 Agent 调研：已记录分支证据包'
    }
    if (artifactType === 'section_draft' || artifactType === 'branch_result') return '多 Agent 调研：已生成章节草稿'
    if (artifactType === 'section_review') return '多 Agent 调研：章节审查结果已更新'
    if (artifactType === 'section_certification') return '多 Agent 调研：章节已认证，可进入汇总'
    if (artifactType === 'validation_summary') {
      const validationStatus = String(payload?.validation_status || '').trim()
      if (validationStatus === 'passed') return '多 Agent 调研：分支验证通过'
      if (validationStatus === 'retry') return '多 Agent 调研：分支验证要求补充研究'
      if (validationStatus === 'failed') return '多 Agent 调研：分支验证未通过'
      return '多 Agent 调研：分支验证摘要已更新'
    }
    if (artifactType === 'final_report') return '多 Agent 调研：已落盘最终报告产物'
  }

  if (eventType === 'research_decision') {
    if (decisionType === 'clarify_required') return '多 Agent 调研：需要补充研究背景与约束'
    if (decisionType === 'scope_ready') return '多 Agent 调研：研究范围已准备好进入审阅'
    if (decisionType === 'scope_revision_requested') return '多 Agent 调研：根据反馈重写研究范围'
    if (decisionType === 'scope_approved') return '多 Agent 调研：研究范围已确认，开始正式规划'
    if (decisionType === 'research_brief_ready') return '多 Agent 调研：研究范围已固化，准备生成研究计划'
    if (decisionType === 'outline_plan') return '多 Agent 调研：已生成研究大纲与章节计划'
    if (decisionType === 'retry_branch' || decisionType === 'verification_retry_requested') return '多 Agent 调研：验证要求重试当前 branch'
    if (decisionType === 'review_updated') return '多 Agent 调研：章节审查已更新，正在决定下一步'
    if (decisionType === 'review_passed') return '多 Agent 调研：章节审查已收敛，准备汇总'
    if (decisionType === 'coverage_gap_detected') return '多 Agent 调研：验证发现 coverage gap，准备补充规划'
    if (decisionType === 'verification_passed') return '多 Agent 调研：分支验证通过，准备汇总'
    if (decisionType === 'plan' || decisionType === 'replan' || decisionType === 'supervisor_plan') {
      return '多 Agent 调研：supervisor 已生成研究分支计划'
    }
    if (decisionType === 'research') return '多 Agent 调研：supervisor 决定继续研究'
    if (decisionType === 'report' || decisionType === 'outline_ready') return '多 Agent 调研：验证通过，准备生成最终报告'
    if (decisionType === 'final_claim_gate_passed') return '多 Agent 调研：最终 claim gate 已通过'
    if (decisionType === 'final_claim_gate_blocked') return '多 Agent 调研：最终 claim gate 检出冲突，流程已阻塞'
    if (decisionType === 'synthesize' || decisionType === 'complete') return '多 Agent 调研：supervisor 决定进入汇总阶段'
    if (decisionType === 'budget_stop') return '多 Agent 调研：触发预算停止条件'
    if (decisionType === 'stop') return '多 Agent 调研：调研流程已停止'
  }

  return null
}

function getInterruptStatusText(review: any, message: string): string {
  if (review?.kind === 'clarify_question') return '继续补充你的研究目标与约束'
  if (review?.kind === 'scope_review') return '请确认研究范围，或继续修改'
  return review?.title || message || 'Review required before continuing'
}

function normalizeToolEvent(
  eventType: ToolLifecycleEventType,
  payload: any,
) {
  const toolName = String(payload?.name || payload?.tool || '').trim() || 'unknown'
  const args =
    payload?.args && typeof payload.args === 'object'
      ? payload.args
      : payload?.input && typeof payload.input === 'object'
        ? payload.input
        : payload?.query
          ? { query: payload.query }
          : {}

  const status =
    eventType === 'tool'
      ? String(payload?.status || '').trim() || (payload?.success === false ? 'failed' : 'running')
      : eventType === 'tool_result'
        ? payload?.success === false
          ? 'failed'
          : 'completed'
        : eventType === 'tool_error'
          ? 'failed'
          : 'running'

  const toolCallId = String(payload?.toolCallId || payload?.tool_call_id || '').trim()

  return {
    toolName,
    args,
    status,
    toolCallId: toolCallId || undefined,
    payload: {
      ...payload,
      name: toolName,
      tool: toolName,
      status,
      ...(Object.keys(args).length > 0 ? { args } : {}),
    },
  }
}

export function useChatStream({ selectedModel, searchMode }: UseChatStreamProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentStatus, setCurrentStatus] = useState<string>('')
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [pendingInterrupt, setPendingInterrupt] = useState<any>(null)
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

      const pushProcessEvent = (type: string, payload: any) => {
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
            setCurrentStatus(data.data.text)
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
          } else if (['tool_start', 'tool_result', 'tool_error'].includes(data.type)) {
            const normalized = normalizeToolEvent(data.type as ToolLifecycleEventType, data.data)
            pushProcessEvent('tool', normalized.payload)
            syncAssistantMessage()
          } else if (data.type === 'tool_progress') {
            const normalized = normalizeToolEvent('tool_start', data.data)
            pushProcessEvent('tool_progress', {
              ...data.data,
              name: normalized.toolName,
              tool: normalized.toolName,
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
          body: JSON.stringify({
            messages: messageHistory.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            model: requestModel,
            search_mode: createSearchModePayload(searchMode),
            images: (images || []).map(img => ({
              name: img.name,
              mime: img.mime,
              data: img.data
            }))
          }),
          signal: abortControllerRef.current.signal
        }
      )

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const assistantMessage = createStreamingAssistantMessage()
      setMessages((prev) => [...prev, assistantMessage])
      await consumeStreamingResponse(response, assistantMessage)
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('Request aborted')
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
  }, [selectedModel, searchMode, consumeStreamingResponse])

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
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        console.log('Resume request aborted')
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
