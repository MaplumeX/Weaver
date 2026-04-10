'use client'

import React from 'react'
import { Clock, Download, FileText, HardDrive, MoreVertical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { getApiBaseUrl } from '@/lib/api'
import { formatBytes, formatRelativeTime } from '@/lib/utils'
import { KnowledgeFile } from '@/types/knowledge'

interface KnowledgeFileItemProps {
  file: KnowledgeFile
}

function statusLabel(status: string): string {
  if (status === 'indexed') return 'Indexed'
  if (status === 'failed') return 'Failed'
  if (status === 'uploaded') return 'Uploaded'
  if (status === 'uploading') return 'Uploading'
  return status || 'Unknown'
}

function statusClassName(status: string): string {
  if (status === 'indexed') return 'bg-emerald-500/10 text-emerald-700'
  if (status === 'failed') return 'bg-destructive/10 text-destructive'
  return 'bg-amber-500/10 text-amber-700'
}

export function KnowledgeFileItem({ file }: KnowledgeFileItemProps) {
  const downloadHref = `${getApiBaseUrl()}${file.download_path || `/api/knowledge/files/${file.id}/download`}`

  return (
    <div className="group relative p-4 rounded-xl border bg-card hover:bg-muted/50 transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
              <HardDrive className="h-4 w-4 text-muted-foreground" />
            </div>
            <h3 className="font-semibold text-sm truncate" title={file.filename}>
              {file.filename}
            </h3>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className={`inline-flex rounded-full px-2 py-0.5 font-medium ${statusClassName(file.status)}`}>
              {statusLabel(file.status)}
            </span>
            <span className="text-muted-foreground uppercase">{file.extension || 'file'}</span>
            <span className="text-muted-foreground">{file.chunk_count || 0} chunks</span>
          </div>

          {file.error ? (
            <p className="mt-2 text-xs text-destructive line-clamp-2">{file.error}</p>
          ) : null}

          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatRelativeTime(Date.parse(String(file.updated_at || file.created_at || '')) || Date.now())}
              </div>
              {file.size_bytes ? <span>{formatBytes(file.size_bytes)}</span> : null}
            </div>
            <div className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground/50 flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" />
              <span>{file.parser_name || 'file'}</span>
            </div>
          </div>
        </div>

        <div onClick={(e) => e.stopPropagation()}>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1" align="end">
              <Button asChild variant="ghost" className="w-full justify-start text-sm h-9">
                <a href={downloadHref} target="_blank" rel="noreferrer">
                  <Download className="mr-2 h-4 w-4" /> Download
                </a>
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  )
}
