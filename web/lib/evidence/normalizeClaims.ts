import type { components } from '../api-types'

export type EvidenceClaim = components['schemas']['EvidenceClaim']

export type NormalizedClaimStatus = 'verified' | 'unsupported' | 'contradicted' | 'unknown'

export function normalizeClaimStatus(raw: unknown): NormalizedClaimStatus {
  const value = String(raw ?? '').trim().toLowerCase()
  if (value === 'verified') return 'verified'
  if (value === 'unsupported') return 'unsupported'
  if (value === 'contradicted') return 'contradicted'
  return 'unknown'
}

export function getClaimStatusCounts(claims: EvidenceClaim[]): {
  total: number
  verified: number
  unsupported: number
  contradicted: number
  unknown: number
} {
  const counts = {
    total: 0,
    verified: 0,
    unsupported: 0,
    contradicted: 0,
    unknown: 0,
  }

  if (!Array.isArray(claims) || claims.length === 0) {
    return counts
  }

  for (const claim of claims) {
    counts.total += 1
    const status = normalizeClaimStatus((claim as any)?.status)
    if (status === 'verified') counts.verified += 1
    else if (status === 'unsupported') counts.unsupported += 1
    else if (status === 'contradicted') counts.contradicted += 1
    else counts.unknown += 1
  }

  return counts
}

