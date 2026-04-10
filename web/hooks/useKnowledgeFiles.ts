'use client'

import { useCallback, useEffect, useState } from 'react'

import { getApiBaseUrl } from '@/lib/api'
import { KnowledgeFile } from '@/types/knowledge'

interface KnowledgeFilesPayload {
  files?: KnowledgeFile[]
}

function normalizeFiles(payload: KnowledgeFilesPayload | null | undefined): KnowledgeFile[] {
  const files = Array.isArray(payload?.files) ? payload?.files : []
  return [...files].sort((a, b) => {
    const left = Date.parse(String(a.updated_at || a.created_at || '')) || 0
    const right = Date.parse(String(b.updated_at || b.created_at || '')) || 0
    return right - left
  })
}

export function useKnowledgeFiles() {
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)

  const refresh = useCallback(async () => {
    const response = await fetch(`${getApiBaseUrl()}/api/knowledge/files`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(String(data?.detail || 'Failed to load knowledge files'))
    }
    setFiles(normalizeFiles(data))
  }, [])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const response = await fetch(`${getApiBaseUrl()}/api/knowledge/files`)
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(String(data?.detail || 'Failed to load knowledge files'))
        }
        if (!cancelled) {
          setFiles(normalizeFiles(data))
        }
      } catch {
        if (!cancelled) {
          setFiles([])
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [])

  const uploadFiles = useCallback(
    async (input: File[] | FileList) => {
      const selected = Array.isArray(input) ? input : Array.from(input)
      if (selected.length === 0) return []

      setIsUploading(true)
      try {
        const formData = new FormData()
        selected.forEach((file) => formData.append('files', file))
        const response = await fetch(`${getApiBaseUrl()}/api/knowledge/files`, {
          method: 'POST',
          body: formData,
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(String(data?.detail || 'Failed to upload knowledge files'))
        }
        const uploaded = normalizeFiles(data)
        await refresh()
        return uploaded
      } finally {
        setIsUploading(false)
      }
    },
    [refresh],
  )

  return {
    files,
    isLoading,
    isUploading,
    refresh,
    uploadFiles,
  }
}
