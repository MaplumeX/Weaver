import { describe, expect, it } from 'vitest'

import type { components } from '../api-types'
import { getClaimStatusCounts, normalizeClaimStatus } from './normalizeClaims'

type EvidenceClaim = components['schemas']['EvidenceClaim']

describe('normalizeClaimStatus', () => {
  it('maps known statuses to a stable union', () => {
    expect(normalizeClaimStatus('verified')).toBe('verified')
    expect(normalizeClaimStatus('unsupported')).toBe('unsupported')
    expect(normalizeClaimStatus('contradicted')).toBe('contradicted')
  })

  it('treats unknown values as unknown', () => {
    expect(normalizeClaimStatus('weird')).toBe('unknown')
    expect(normalizeClaimStatus(null)).toBe('unknown')
    expect(normalizeClaimStatus(undefined)).toBe('unknown')
  })
})

describe('getClaimStatusCounts', () => {
  it('counts claim statuses consistently', () => {
    const claims: EvidenceClaim[] = [
      {
        claim: 'A',
        status: 'verified',
        evidence_urls: [],
        evidence_passages: [],
        score: 1,
        notes: '',
      },
      {
        claim: 'B',
        status: 'unsupported',
        evidence_urls: [],
        evidence_passages: [],
        score: 0,
        notes: '',
      },
      {
        claim: 'C',
        status: 'contradicted',
        evidence_urls: [],
        evidence_passages: [],
        score: 0,
        notes: '',
      },
      // Unknown / unexpected backend payloads should not break the UI.
      {
        claim: 'D',
        status: 'maybe',
        evidence_urls: [],
        evidence_passages: [],
        score: 0,
        notes: '',
      } as unknown as EvidenceClaim,
    ]

    const counts = getClaimStatusCounts(claims)
    expect(counts.total).toBe(4)
    expect(counts.verified).toBe(1)
    expect(counts.unsupported).toBe(1)
    expect(counts.contradicted).toBe(1)
    expect(counts.unknown).toBe(1)
  })
})

