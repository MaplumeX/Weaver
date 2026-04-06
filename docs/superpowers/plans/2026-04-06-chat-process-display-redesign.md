# Chat Process Display Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一普通问答、tool-calling、deep research 的过程展示，只保留用户摘要层和过程层，移除普通用户可见的原始事件流与重复状态展示。

**Architecture:** 前端新增单一事件投影模块 `web/lib/process-display.ts`，把原始 `processEvents` 和 `toolInvocations` 投影成统一的“摘要 + 语义阶段”模型，`ThinkingProcess` 只负责渲染这个投影结果。后端 `main.py` 继续发原始流事件，但收敛 `agent` 节点的一人称 thinking 文案，并对重复的 generic progress 事件做去重，减少前端噪音和存储冗余。

**Tech Stack:** Next.js 14、React 18、TypeScript、node:test、tsx、FastAPI、pytest、LangGraph

---

## File Structure

**Create**

- `web/lib/process-display.ts`
- `web/tests/process-display.test.ts`
- `web/tests/thinking-process.test.ts`
- `tests/test_chat_sse_process_progress.py`

**Modify**

- `web/components/chat/Chat.tsx`
- `web/components/chat/message/ThinkingProcess.tsx`
- `web/hooks/useChatStream.ts`
- `web/lib/chat-stream-state.ts`
- `web/tests/deep-research-events.test.ts`
- `main.py`

**Responsibility Map**

- `web/lib/process-display.ts`：统一原始事件到用户展示模型的投影逻辑，输出摘要状态、指标和语义化过程项。
- `web/components/chat/message/ThinkingProcess.tsx`：只消费投影结果，不直接渲染原始事件，也不再暴露 `Original Stream Events`。
- `web/components/chat/Chat.tsx`：移除普通用户可见的底部 `currentStatus` 状态条。
- `web/hooks/useChatStream.ts`：保留原始事件接收与消息写入，不再把普通 `status` 事件当作主用户状态源。
- `web/lib/chat-stream-state.ts`：增强语义去重，避免相同 `step` 的状态事件无意义累积。
- `main.py`：收敛 `agent` 节点 thinking/status 噪音，并对重复 generic progress 做后端去重。
- `tests/test_chat_sse_process_progress.py`：锁定后端“无一人称旁白 + 无重复 agent generic progress”的流式契约。

**Repository Constraint**

- 根据仓库 `AGENTS.md`，本计划不包含任何 `git commit` 步骤。

### Task 1: 锁定前端事件投影契约

**Files:**

- Create: `web/tests/process-display.test.ts`
- Create: `web/lib/process-display.ts`

- [ ] **Step 1: 先写失败测试，锁定“技术事件 -> 用户摘要/过程层”的投影结果**

```ts
import { test } from 'node:test'
import * as assert from 'node:assert/strict'

import { buildProcessHeaderText, projectProcessDisplay } from '../lib/process-display'
import type { ProcessEvent, ToolInvocation } from '../types/chat'

function event(
  id: string,
  type: string,
  timestamp: number,
  data: Record<string, unknown>,
): ProcessEvent {
  return { id, type, timestamp, data }
}

test('collapses generic tool-calling chatter into one user-facing summary', () => {
  const tools: ToolInvocation[] = [
    {
      toolCallId: 'tool-1',
      toolName: 'browser_search',
      state: 'running',
      args: { query: 'agent observability' },
    },
  ]

  const projection = projectProcessDisplay({
    isThinking: true,
    tools,
    events: [
      event('init', 'status', 10, { text: 'Initializing research agent...', step: 'init' }),
      event('agent-thinking', 'thinking', 20, {
        text: '我会调用工具完成任务步骤，并记录关键过程。',
        node: 'agent',
      }),
      event('agent-status', 'status', 30, {
        text: 'Running agent (tool-calling)',
        step: 'agent',
      }),
      event('tool', 'tool', 40, { name: 'browser_search', status: 'running' }),
    ],
  })

  assert.equal(projection.summary.label, '正在调用工具')
  assert.deepEqual(
    projection.details.map((item) => item.label),
    ['分析问题', '调用工具'],
  )
  assert.equal(
    buildProcessHeaderText({ projection, durationLabel: '8s' }),
    '正在调用工具 · 8s · 1 个工具',
  )
})

test('projects deep research events into the same two-level display model', () => {
  const projection = projectProcessDisplay({
    isThinking: true,
    tools: [],
    events: [
      event('scope-approved', 'research_decision', 10, { decision_type: 'scope_approved' }),
      event('task-search', 'research_task_update', 20, {
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        status: 'in_progress',
        stage: 'search',
        iteration: 1,
      }),
      event('section-draft', 'research_artifact_update', 30, {
        artifact_id: 'section-draft-1',
        artifact_type: 'section_draft',
        status: 'created',
        task_id: 'task-1',
        section_id: 'section-1',
        task_kind: 'section_research',
        title: 'Supply chain resilience',
        iteration: 1,
      }),
    ],
  })

  assert.equal(projection.summary.label, '正在检索资料')
  assert.ok(projection.summary.metrics.includes('1 section'))
  assert.deepEqual(
    projection.details.map((item) => item.label),
    ['研究范围', '检索资料', '汇总信息'],
  )
})
```

- [ ] **Step 2: 运行测试，确认新模块尚不存在且契约未实现**

Run: `pnpm -C web exec node --import tsx --test tests/process-display.test.ts`

Expected: FAIL  
Expected failure shape:

- `Cannot find module '../lib/process-display'`
- 或导出的 `projectProcessDisplay` / `buildProcessHeaderText` 未定义

- [ ] **Step 3: 写最小实现，新增统一过程投影模块**

```ts
import { projectDeepResearchTimeline } from '@/lib/deep-research-timeline'
import type { ProcessEvent, ToolInvocation } from '@/types/chat'

export type ProcessSummaryTone = 'running' | 'completed' | 'error' | 'interrupted'

export interface ProcessDisplayItem {
  id: string
  label: string
  detail?: string
  tone?: ProcessSummaryTone
}

export interface ProcessDisplayProjection {
  summary: {
    label: string
    tone: ProcessSummaryTone
    metrics: string[]
  }
  details: ProcessDisplayItem[]
}

const TECHNICAL_STATUS_PATTERNS = [
  /^Initializing research agent/i,
  /^Running agent \(tool-calling\)$/i,
]

function countTools(tools: ToolInvocation[]): number {
  return tools.filter((tool) => tool.state === 'running' || tool.state === 'completed').length
}

function hasEvent(events: ProcessEvent[], ...types: string[]): boolean {
  return events.some((event) => types.includes(event.type))
}

function summarizeDeepResearch(events: ProcessEvent[], isThinking: boolean): ProcessDisplayProjection | null {
  const timeline = projectDeepResearchTimeline(events)
  if (!timeline) return null

  const latestTask = [...events]
    .reverse()
    .find((event) => event.type === 'research_task_update' && event.data?.status === 'in_progress')
  const latestArtifact = [...events]
    .reverse()
    .find((event) => event.type === 'research_artifact_update')

  let label = isThinking ? '处理中' : '已完成'
  if (latestTask?.data?.stage === 'search') label = '正在检索资料'
  else if (latestTask?.data?.stage === 'synthesize' || latestArtifact?.data?.artifact_type === 'section_draft') {
    label = '正在整理答案'
  } else if (isThinking) {
    label = '处理中'
  }

  const details: ProcessDisplayItem[] = []
  if (events.some((event) => event.type === 'research_decision' && event.data?.decision_type === 'scope_approved')) {
    details.push({ id: 'scope', label: '研究范围', detail: '已确认范围并进入正式研究' })
  }
  if (latestTask?.data?.stage === 'search') {
    details.push({ id: 'search', label: '检索资料', detail: String(latestTask.data?.title || '当前章节') })
  }
  if (latestArtifact?.data?.artifact_type === 'section_draft') {
    details.push({ id: 'synthesize', label: '汇总信息', detail: String(latestArtifact.data?.title || '生成章节草稿') })
  }

  return {
    summary: {
      label,
      tone: isThinking ? 'running' : 'completed',
      metrics: timeline.headerMetrics,
    },
    details,
  }
}

function summarizeGeneric(
  events: ProcessEvent[],
  tools: ToolInvocation[],
  isThinking: boolean,
): ProcessDisplayProjection {
  const runningTools = tools.filter((tool) => tool.state === 'running').length
  const hasToolActivity = runningTools > 0 || hasEvent(events, 'tool', 'tool_start', 'tool_result', 'tool_error')
  const hasSearchActivity = hasEvent(events, 'search', 'research_node_start', 'research_node_complete')
  const hasError = hasEvent(events, 'error')
  const hasInterrupt = hasEvent(events, 'interrupt', 'cancelled')
  const hasCompletion = hasEvent(events, 'completion', 'done')

  let label = '处理中'
  let tone: ProcessSummaryTone = 'running'

  if (hasError) {
    label = '处理失败'
    tone = 'error'
  } else if (hasInterrupt) {
    label = '已中断'
    tone = 'interrupted'
  } else if (hasToolActivity) {
    label = '正在调用工具'
  } else if (hasSearchActivity) {
    label = '正在检索资料'
  } else if (!isThinking && hasCompletion) {
    label = '已完成'
    tone = 'completed'
  } else if (!isThinking) {
    label = '已完成'
    tone = 'completed'
  }

  const details: ProcessDisplayItem[] = []
  if (events.some((event) => event.type === 'thinking' || TECHNICAL_STATUS_PATTERNS.some((pattern) => pattern.test(String(event.data?.text || ''))))) {
    details.push({ id: 'analyze', label: '分析问题' })
  }
  if (hasSearchActivity) {
    details.push({ id: 'search', label: '检索资料' })
  }
  if (hasToolActivity) {
    const detail = runningTools > 0 ? `${runningTools} 个工具仍在运行` : `${countTools(tools)} 个工具已调用`
    details.push({ id: 'tools', label: '调用工具', detail })
  }
  if (!isThinking && hasCompletion) {
    details.push({ id: 'answer', label: '生成回答' })
  }

  const metrics = countTools(tools) > 0 ? [`${countTools(tools)} 个工具`] : []

  return {
    summary: { label, tone, metrics },
    details,
  }
}

export function projectProcessDisplay({
  events,
  tools,
  isThinking,
}: {
  events: ProcessEvent[]
  tools?: ToolInvocation[]
  isThinking: boolean
}): ProcessDisplayProjection {
  const nextTools = tools || []
  return summarizeDeepResearch(events, isThinking) || summarizeGeneric(events, nextTools, isThinking)
}

export function buildProcessHeaderText({
  projection,
  durationLabel,
}: {
  projection: ProcessDisplayProjection
  durationLabel?: string
}): string {
  return [projection.summary.label, durationLabel, ...projection.summary.metrics].filter(Boolean).join(' · ')
}
```

- [ ] **Step 4: 运行测试，确认事件投影契约通过**

Run: `pnpm -C web exec node --import tsx --test tests/process-display.test.ts`

Expected: PASS  
Expected output shape:

- `ok 1 - collapses generic tool-calling chatter into one user-facing summary`
- `ok 2 - projects deep research events into the same two-level display model`

### Task 2: 改写消息内过程展示并移除普通用户底部状态条

**Files:**

- Modify: `web/components/chat/message/ThinkingProcess.tsx`
- Modify: `web/components/chat/Chat.tsx`
- Create: `web/tests/thinking-process.test.ts`

- [ ] **Step 1: 先写失败测试，锁定 `ThinkingProcess` 头部只显示用户摘要，不再暴露 `Thinking…/Thought`**

```ts
import { test } from 'node:test'
import * as assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { ThinkingProcess } from '../components/chat/message/ThinkingProcess'

test('renders user-facing process header copy instead of legacy Thinking text', () => {
  const html = renderToStaticMarkup(
    React.createElement(ThinkingProcess, {
      isThinking: true,
      startedAt: Date.now() - 3000,
      tools: [
        {
          toolCallId: 'tool-1',
          toolName: 'browser_search',
          state: 'running',
          args: { query: 'agent observability' },
        },
      ],
      events: [
        {
          id: 'status-agent',
          type: 'status',
          timestamp: 10,
          data: { text: 'Running agent (tool-calling)', step: 'agent' },
        },
      ],
    }),
  )

  assert.match(html, /正在调用工具/)
  assert.doesNotMatch(html, /Thinking…/)
  assert.doesNotMatch(html, /Thought/)
})
```

- [ ] **Step 2: 运行组件测试，确认当前 UI 仍输出 legacy 头部文案**

Run: `pnpm -C web exec node --import tsx --test tests/thinking-process.test.ts`

Expected: FAIL  
Expected failure shape:

- `The input did not match the regular expression /正在调用工具/`
- 或 HTML 中仍包含 `Thinking…`

- [ ] **Step 3: 重写 `ThinkingProcess` 为纯投影渲染器，并移除普通用户可见的底部全局状态条**

```tsx
// web/components/chat/message/ThinkingProcess.tsx
import { buildProcessHeaderText, projectProcessDisplay } from '@/lib/process-display'

const projection = useMemo(() => {
  return projectProcessDisplay({ events, tools, isThinking })
}, [events, tools, isThinking])

const headerText = buildProcessHeaderText({
  projection,
  durationLabel,
})

return (
  <div className="w-full my-2">
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'group inline-flex items-center gap-2 rounded-full px-3 py-1.5',
        'text-sm text-muted-foreground hover:text-foreground',
        'hover:bg-muted/40 transition-colors duration-150',
        projection.details.length === 0 && 'cursor-default hover:bg-transparent',
      )}
      aria-expanded={open}
    >
      <span className={cn('flex h-4 w-4 items-center justify-center', isThinking ? 'text-primary' : 'text-muted-foreground')}>
        {isThinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
      </span>
      <span className="font-medium">{headerText}</span>
      {projection.details.length > 0 ? (
        <ChevronDown className={cn('h-4 w-4 transition-transform duration-200 ease-out', open ? 'rotate-180' : 'rotate-0')} />
      ) : null}
    </button>

    {projection.details.length > 0 ? (
      <div className="grid transition-[grid-template-rows] duration-200 ease-out" style={{ gridTemplateRows: open ? '1fr' : '0fr' }}>
        <div className="overflow-hidden">
          <div className="mt-2 pl-4 ml-2 border-l border-border/60 text-sm text-muted-foreground">
            <div className="space-y-2 py-1">
              {projection.details.map((item) => (
                <div key={item.id} className="flex items-start gap-2">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                  <div className="min-w-0">
                    <div className="truncate text-foreground/85">{item.label}</div>
                    {item.detail ? <div className="text-xs text-muted-foreground">{item.detail}</div> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    ) : null}
  </div>
)
```

```tsx
// web/components/chat/Chat.tsx
components={{
  Footer: () => (
    <div className="max-w-5xl mx-auto px-4 sm:px-0 pb-4">
      <div className="h-4" />
    </div>
  ),
}}
```

实现要求：

- 删除 `rawOpen` 与 `Original Stream Events` 展示块。
- 删除 `Thinking…` / `Thought` 头部文案路径。
- `Chat.tsx` 不再渲染普通用户底部 `currentStatus` 状态条。

- [ ] **Step 4: 运行前端测试和 lint，确认 UI 重构未破坏静态契约**

Run: `pnpm -C web exec node --import tsx --test tests/process-display.test.ts tests/thinking-process.test.ts`

Expected: PASS

Run: `pnpm -C web lint`

Expected: PASS  
Expected output shape:

- `✔ No ESLint warnings or errors`

### Task 3: 收敛流式状态写入与前端事件去重

**Files:**

- Modify: `web/hooks/useChatStream.ts`
- Modify: `web/lib/chat-stream-state.ts`
- Modify: `web/tests/deep-research-events.test.ts`

- [ ] **Step 1: 先写失败测试，锁定相同 `step` 的状态事件会被语义去重，而不是无限累积**

```ts
test('appendProcessEvent replaces repeated status events for the same semantic step', () => {
  let message = createStreamingAssistantMessage({ id: 'assistant-status' })

  message = appendProcessEvent(
    message,
    'status',
    { text: 'Preparing tools', step: 'agent' },
    100,
  )
  message = appendProcessEvent(
    message,
    'status',
    { text: 'Running agent (tool-calling)', step: 'agent' },
    110,
  )

  assert.equal(message.processEvents?.length, 1)
  assert.equal(message.processEvents?.[0]?.data?.step, 'agent')
  assert.equal(message.processEvents?.[0]?.data?.text, 'Running agent (tool-calling)')
})
```

- [ ] **Step 2: 运行前端测试，确认当前去重逻辑只处理“完全相同文本”**

Run: `pnpm -C web exec node --import tsx --test tests/deep-research-events.test.ts`

Expected: FAIL  
Expected failure shape:

- `Expected values to be strictly equal: 2 !== 1`

- [ ] **Step 3: 调整过程事件去重逻辑，并停止把普通 `status` 事件镜像成全局用户状态**

```ts
// web/lib/chat-stream-state.ts
function replaceLastEvent(events: ProcessEvent[], next: ProcessEvent): ProcessEvent[] {
  return [...events.slice(0, -1), next]
}

if (last?.type === type) {
  if (type === 'status') {
    const lastStep = String(last.data?.step || '').trim()
    const nextStep = String(payload?.step || '').trim()
    if (lastStep && nextStep && lastStep === nextStep) {
      return {
        ...message,
        processEvents: replaceLastEvent(prevEvents, next),
      }
    }
    if (last.data?.text && last.data?.text === payload?.text) return message
  }
  if (type === 'search' && last.data?.query && last.data?.query === payload?.query) return message
}
```

```ts
// web/hooks/useChatStream.ts
if (data.type === 'status') {
  pushProcessEvent('status', data.data)
  syncAssistantMessage()
}
```

实现要求：

- `interrupt` / `cancelled` / 手动 stop 的 `currentStatus` 逻辑保留。
- 普通流式 `status` 继续写入 `processEvents`，但不再作为底部全局主状态源。
- 去重优先按 `step` 语义收敛，再回退到已有的文本去重。

- [ ] **Step 4: 运行前端回归测试，确认事件去重与过程保留规则通过**

Run: `pnpm -C web exec node --import tsx --test tests/deep-research-events.test.ts tests/process-display.test.ts`

Expected: PASS  
Expected output shape:

- `ok - appendProcessEvent replaces repeated status events for the same semantic step`
- 现有 `getRetainedProcessEvents` / `getDeepResearchAutoStatus` 测试继续通过

### Task 4: 后端去掉 `agent` 一人称旁白并去重重复 generic progress

**Files:**

- Create: `tests/test_chat_sse_process_progress.py`
- Modify: `main.py`

- [ ] **Step 1: 先写失败测试，锁定 `agent` 节点不再向普通流输出一人称 thinking，且重复 start 事件只发一条 generic progress**

```python
import json

import pytest

import main


async def _noop_async(*args, **kwargs):
    return None


def _common_stream_monkeypatch(monkeypatch):
    monkeypatch.setattr(main, "add_memory_entry", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "store_interaction", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "fetch_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)


@pytest.mark.asyncio
async def test_stream_deduplicates_agent_generic_progress(monkeypatch):
    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            for event_name in ("on_graph_start", "on_node_start", "on_chain_start"):
                yield {
                    "event": event_name,
                    "name": "agent",
                    "run_id": "agent-run-1",
                    "data": {},
                }
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    _common_stream_monkeypatch(monkeypatch)
    monkeypatch.setattr(main, "research_graph", _DummyGraph())

    payloads = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread-agent-progress"):
        if chunk.startswith("0:"):
            payloads.append(json.loads(chunk[2:]))

    agent_statuses = [
        payload
        for payload in payloads
        if payload["type"] == "status" and payload["data"].get("step") == "agent"
    ]

    assert len(agent_statuses) == 1
    assert not any(
        payload["type"] == "thinking" and payload["data"].get("node") == "agent"
        for payload in payloads
    )


def test_agent_node_has_no_first_person_thinking_intro():
    assert main._thinking_intro_for_node("agent", use_zh=True) == ""
```

- [ ] **Step 2: 运行后端测试，确认当前实现仍会发出 `agent` thinking 和重复 generic progress**

Run: `uv run pytest tests/test_chat_sse_process_progress.py -v`

Expected: FAIL  
Expected failure shape:

- `assert 3 == 1` 或 `assert 2 == 1`
- `assert '我会调用工具完成任务步骤，并记录关键过程。' == ''`

- [ ] **Step 3: 修改后端流式映射，移除 `agent` thinking 旁白并按 `run_id + node_name + step` 去重 generic progress**

```python
# main.py
def _thinking_intro_for_node(node_name: str, *, use_zh: bool) -> str:
    name = (node_name or "").strip().lower()
    if not name:
        return ""
    if name == "agent":
        return ""
    ...
```

```python
# main.py inside _stream_graph_execution()
seen_progress_keys: set[tuple[str, str, str]] = set()

...
event_type = event.get("event")
name = event.get("name", "") or event.get("run_name", "")
run_id = str(event.get("run_id", "") or "")

if event_type in {"on_chain_start", "on_node_start", "on_graph_start"}:
    ...
    if emit_generic_progress:
        progress_step = ""
        if "clarify" in node_name:
            progress_step = "clarifying"
        elif "supervisor" in node_name:
            progress_step = "supervisor"
        elif "deepsearch" in node_name:
            progress_step = "deep_research"
        elif node_name == "agent":
            progress_step = "agent"

        progress_key = (node_name, run_id or event_type, progress_step)
        if progress_step and progress_key in seen_progress_keys:
            continue
        if progress_step:
            seen_progress_keys.add(progress_key)

        ...
```

实现要求：

- 只去重 generic progress，不影响真实 `tool`、`research_*` 事件。
- `multi-agent deep` 模式原有 suppress 逻辑保持不变。
- `_thinking_intro_for_node("agent")` 返回空字符串，避免一人称旁白继续泄漏到普通流。

- [ ] **Step 4: 运行后端回归测试，确认流式事件契约收敛**

Run: `uv run pytest tests/test_chat_sse_process_progress.py tests/test_chat_sse_multi_agent_events.py tests/test_chat_stream_tool_events.py -v`

Expected: PASS  
Expected output shape:

- `test_stream_deduplicates_agent_generic_progress PASSED`
- `test_agent_node_has_no_first_person_thinking_intro PASSED`
- 既有 multi-agent/tool stream 测试继续通过

### Task 5: 做完整验证并记录人工检查点

**Files:**

- Modify: `web/components/chat/Chat.tsx`
- Modify: `web/components/chat/message/ThinkingProcess.tsx`
- Modify: `web/hooks/useChatStream.ts`
- Modify: `web/lib/chat-stream-state.ts`
- Modify: `web/lib/process-display.ts`
- Modify: `main.py`

- [ ] **Step 1: 运行前端完整测试集**

Run: `pnpm -C web test`

Expected: PASS

- [ ] **Step 2: 运行前端 lint 和 build，确认 UI 重构没有类型或打包回归**

Run: `pnpm -C web lint`

Expected: PASS

Run: `pnpm -C web build`

Expected: PASS

- [ ] **Step 3: 运行后端相关 pytest，确认流式契约未回归**

Run: `uv run pytest tests/test_chat_sse_process_progress.py tests/test_chat_sse_multi_agent_events.py tests/test_chat_stream_tool_events.py tests/test_chat_sse_quality_events.py -v`

Expected: PASS

- [ ] **Step 4: 做一次人工 smoke check，确认用户界面只剩两层展示**

Manual checklist:

- 发起一次普通问答，消息头部显示 `处理中` / `已完成`，不再显示 `Thinking…`。
- 发起一次 tool-calling，会话中不再同时出现底部状态条和消息内重复状态。
- 发起一次 deep research，展开后只看到语义化阶段，不再出现 `Original Stream Events`。
- 浏览器里确认看不到 `Initializing research agent...`、`Running agent (tool-calling)`、`我会调用工具完成任务步骤，并记录关键过程。`

## Self-Review

### Spec coverage

- “只保留用户摘要层和过程层”：
  - Task 1 定义统一投影模型
  - Task 2 重写 `ThinkingProcess` 和移除底部状态条
- “原始事件不进入普通用户界面”：
  - Task 2 删除 `Original Stream Events`
- “同一状态只保留一个主展示来源”：
  - Task 2 移除 `Chat.tsx` 底部状态条
  - Task 3 收敛 `status` 写入逻辑
- “后端减少噪音和重复 generic progress”：
  - Task 4 覆盖 `main.py` 旁白移除与去重

### Placeholder scan

- 无 `TODO` / `TBD`
- 每个任务都给出明确文件、测试、命令和实现代码块

### Type consistency

- 前端统一使用 `ProcessDisplayProjection`、`ProcessDisplayItem`
- `ThinkingProcess` 只依赖 `buildProcessHeaderText` / `projectProcessDisplay`
- 后端去重键使用 `node_name + run_id + progress_step`，与测试保持一致
