'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { getSessionEvidence, type SessionEvidenceResponse } from '@/lib/api-client'

type EvidenceState = {
  evidence: SessionEvidenceResponse | null
  isLoading: boolean
  error: string | null
}

export function useSessionEvidence(threadId: string | null) {
  const [state, setState] = useState<EvidenceState>({
    evidence: null,
    isLoading: false,
    error: null,
  })

  const requestIdRef = useRef(0)

  const refresh = useCallback(async () => {
    if (!threadId) {
      setState({ evidence: null, isLoading: false, error: null })
      return
    }

    const requestId = ++requestIdRef.current
    setState(prev => ({ ...prev, isLoading: true, error: null }))

    try {
      const data = await getSessionEvidence(threadId)
      if (requestId !== requestIdRef.current) return
      setState({ evidence: data, isLoading: false, error: null })
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to load evidence',
      }))
    }
  }, [threadId])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    evidence: state.evidence,
    isLoading: state.isLoading,
    error: state.error,
    refresh,
  }
}

