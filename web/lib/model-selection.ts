import { DEFAULT_MODEL } from '@/lib/constants'
import type { PublicConfigModels } from '@/lib/publicConfig'

export type ModelProviderId = 'openai' | 'anthropic' | 'deepseek' | 'qwen' | 'zhipu' | 'custom'

export interface ConfiguredModelEntry {
  id: string
  name: string
  providerId: ModelProviderId
}

const KNOWN_MODEL_ENTRIES: Record<string, Omit<ConfiguredModelEntry, 'id'>> = {
  'gpt-5': { name: 'GPT-5', providerId: 'openai' },
  'gpt-4.1': { name: 'GPT-4.1', providerId: 'openai' },
  'gpt-4o': { name: 'GPT-4o', providerId: 'openai' },
  'o1-mini': { name: 'o1-mini', providerId: 'openai' },
  'claude-sonnet-4-5-20250514': { name: 'Claude Sonnet 4.5', providerId: 'anthropic' },
  'claude-opus-4-20250514': { name: 'Claude Opus 4', providerId: 'anthropic' },
  'claude-sonnet-4-20250514': { name: 'Claude Sonnet 4', providerId: 'anthropic' },
  'deepseek-chat': { name: 'deepseek-chat', providerId: 'deepseek' },
  'deepseek-reasoner': { name: 'deepseek-reasoner', providerId: 'deepseek' },
  'qwen-plus': { name: 'qwen-plus', providerId: 'qwen' },
  'qwen3-vl-flash': { name: 'qwen3-vl-flash 🖼️', providerId: 'qwen' },
  'glm-4.6': { name: 'GLM-4.6', providerId: 'zhipu' },
  'glm-4.6v': { name: 'glm-4.6v 🖼️', providerId: 'zhipu' },
}

function normalizeModelId(value: string | null | undefined): string {
  return String(value || '').trim()
}

export function getPublicModelOptions(publicModels: PublicConfigModels | null | undefined): string[] {
  const seen = new Set<string>()
  const options: string[] = []

  for (const raw of publicModels?.options || []) {
    const model = normalizeModelId(raw)
    if (!model || seen.has(model)) continue
    seen.add(model)
    options.push(model)
  }

  return options
}

function inferProviderId(modelId: string): ModelProviderId {
  const lowered = modelId.toLowerCase()

  if (lowered.includes('claude')) return 'anthropic'
  if (lowered.includes('deepseek')) return 'deepseek'
  if (lowered.includes('qwen')) return 'qwen'
  if (lowered.startsWith('glm') || lowered.includes('glm')) return 'zhipu'
  if (lowered.includes('gpt') || lowered.startsWith('o1') || lowered.startsWith('o3')) return 'openai'

  return 'custom'
}

export function getConfiguredModelEntries(
  publicModels: PublicConfigModels | null | undefined,
  fallbackModels: Array<string | null | undefined> = [],
): ConfiguredModelEntry[] {
  const configuredOptions = getPublicModelOptions(publicModels)
  const source = configuredOptions.length > 0
    ? configuredOptions
    : fallbackModels.map((value) => normalizeModelId(value)).filter(Boolean)

  const seen = new Set<string>()
  const entries: ConfiguredModelEntry[] = []

  for (const modelId of source) {
    if (!modelId || seen.has(modelId)) continue
    seen.add(modelId)

    const known = KNOWN_MODEL_ENTRIES[modelId]
    if (known) {
      entries.push({ id: modelId, ...known })
      continue
    }

    entries.push({
      id: modelId,
      name: modelId,
      providerId: inferProviderId(modelId),
    })
  }

  return entries
}

export function getModelAllowlist(publicModels: PublicConfigModels | null | undefined): Set<string> | null {
  const options = getPublicModelOptions(publicModels)
  return options.length > 0 ? new Set(options) : null
}

export function resolveModelSelection(
  preferredModel: string | null | undefined,
  publicModels: PublicConfigModels | null | undefined,
  fallbackModel: string = DEFAULT_MODEL,
): string {
  const preferred = normalizeModelId(preferredModel)
  const fallback = normalizeModelId(fallbackModel) || DEFAULT_MODEL
  const options = getPublicModelOptions(publicModels)

  if (options.length === 0) {
    return preferred || fallback
  }

  const allowlist = new Set(options)
  if (preferred && allowlist.has(preferred)) {
    return preferred
  }

  const backendDefault = normalizeModelId(publicModels?.default)
  if (backendDefault && allowlist.has(backendDefault)) {
    return backendDefault
  }

  return options[0] || fallback
}
