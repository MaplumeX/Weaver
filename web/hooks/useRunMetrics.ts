'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { getRunMetrics, type RunMetricsResponse } from '@/lib/api-client'

type RunMetricsState = {
  metrics: RunMetricsResponse | null
  isLoading: boolean
  error: string | null
}

export function useRunMetrics(threadId: string | null) {
  const [state, setState] = useState<RunMetricsState>({
    metrics: null,
    isLoading: false,
    error: null,
  })

  const requestIdRef = useRef(0)

  const refresh = useCallback(async () => {
    if (!threadId) {
      setState({ metrics: null, isLoading: false, error: null })
      return
    }

    const requestId = ++requestIdRef.current
    setState(prev => ({ ...prev, isLoading: true, error: null }))

    try {
      const data = await getRunMetrics(threadId)
      if (requestId !== requestIdRef.current) return
      setState({ metrics: data, isLoading: false, error: null })
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to load run metrics',
      }))
    }
  }, [threadId])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    metrics: state.metrics,
    isLoading: state.isLoading,
    error: state.error,
    refresh,
  }
}

