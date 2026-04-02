import { DEFAULT_MODEL } from '@/lib/constants'
import type { PublicConfigModels } from '@/lib/publicConfig'

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
