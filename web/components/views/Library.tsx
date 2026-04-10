'use client'

import React, { useMemo, useRef, useState } from 'react'
import { FolderOpen, History, Upload } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useArtifacts } from '@/hooks/useArtifacts'
import { useKnowledgeFiles } from '@/hooks/useKnowledgeFiles'
import { SessionItem } from '@/components/library/SessionItem'
import { ArtifactItem } from '@/components/library/ArtifactItem'
import { KnowledgeFileItem } from '@/components/library/KnowledgeFileItem'
import { SearchInput } from '@/components/ui/search-input'
import { FilterGroup } from '@/components/ui/filter-group'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EditDialog } from '@/components/ui/edit-dialog'
import { Button } from '@/components/ui/button'
import { Artifact, ChatSession } from '@/types/chat'
import { toast } from 'sonner'

type LibraryTab = 'all' | 'sessions' | 'artifacts' | 'pinned'
type LibraryItem =
  | (ChatSession & { libType: 'session' })
  | (Artifact & { libType: 'artifact' })

interface LibraryProps {
  history: ChatSession[]
  isHistoryLoading?: boolean
  onNewChat: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onRenameSession: (id: string, title: string) => void
  onTogglePin: (id: string) => void
}

export function Library({
  history,
  isHistoryLoading = false,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onTogglePin,
}: LibraryProps) {
  const { artifacts, deleteArtifact, isLoading: isArtifactsLoading } = useArtifacts()
  const { files: knowledgeFiles, isLoading: isKnowledgeLoading, isUploading, uploadFiles } = useKnowledgeFiles()

  const [activeTab, setActiveTab] = useState<LibraryTab>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const knowledgeInputRef = useRef<HTMLInputElement>(null)
  
  // Dialog States
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [deleteType, setDeleteType] = useState<'session' | 'artifact' | null>(null)
  const [editSession, setEditSession] = useState<{id: string, title: string} | null>(null)

  const filterOptions = [
    { label: 'All Items', value: 'all' },
    { label: 'Chats', value: 'sessions' },
    { label: 'Files', value: 'artifacts' },
    { label: 'Pinned', value: 'pinned' },
  ]

  const filteredItems = useMemo(() => {
    let combined: LibraryItem[] = []
    
    if (activeTab === 'all' || activeTab === 'sessions' || activeTab === 'pinned') {
        const h = history.map(s => ({ ...s, libType: 'session' as const }))
        combined = [...combined, ...h]
    }
    
    if (activeTab === 'all' || activeTab === 'artifacts') {
        const a = artifacts.map(art => ({ ...art, libType: 'artifact' as const }))
        combined = [...combined, ...a]
    }

    if (activeTab === 'pinned') {
        combined = combined.filter(item => item.libType === 'session' && item.isPinned)
    }

    return combined
      .filter(item => {
        const titleMatch = item.title?.toLowerCase().includes(searchQuery.toLowerCase())
        const contentMatch = item.libType === 'artifact'
          ? item.content.toLowerCase().includes(searchQuery.toLowerCase())
          : false
        return titleMatch || contentMatch
      })
      .sort((a, b) => (b.updatedAt || b.createdAt) - (a.updatedAt || a.createdAt))
  }, [activeTab, searchQuery, history, artifacts])

  const filteredKnowledgeFiles = useMemo(() => {
    const q = searchQuery.toLowerCase()
    return knowledgeFiles.filter((item) => {
      if (!q) return true
      return (
        item.filename.toLowerCase().includes(q) ||
        item.status.toLowerCase().includes(q) ||
        String(item.parser_name || '').toLowerCase().includes(q)
      )
    })
  }, [knowledgeFiles, searchQuery])

  const handleDelete = () => {
    if (!deleteId || !deleteType) return
    if (deleteType === 'session') onDeleteSession(deleteId)
    else deleteArtifact(deleteId)
    setDeleteId(null)
  }

  const handleRename = (newTitle: string) => {
    if (editSession) {
      onRenameSession(editSession.id, newTitle)
      setEditSession(null)
    }
  }

  const isLoading = isHistoryLoading || isArtifactsLoading

  const handleKnowledgeUpload = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return
    try {
      const uploaded = await uploadFiles(fileList)
      const failed = uploaded.filter((item) => item.status === 'failed').length
      if (failed > 0) {
        toast.error(`Uploaded ${uploaded.length} files, ${failed} failed to index`)
      } else {
        toast.success(`Indexed ${uploaded.length} knowledge files`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to upload knowledge files')
    } finally {
      if (knowledgeInputRef.current) {
        knowledgeInputRef.current.value = ''
      }
    }
  }

  return (
    <div className="flex-1 h-full overflow-hidden flex flex-col bg-background">
      <div className="max-w-6xl mx-auto w-full h-full flex flex-col p-6 md:p-10 gap-8">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <FolderOpen className="h-8 w-8 text-primary" />
              Library
            </h1>
            <p className="text-muted-foreground mt-2 text-lg">
              Manage your saved conversations and artifacts.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={knowledgeInputRef}
              type="file"
              accept=".pdf,.docx,.md,.txt"
              multiple
              className="hidden"
              onChange={(event) => {
                void handleKnowledgeUpload(event.target.files)
              }}
            />
            <Button
              variant="default"
              size="sm"
              onClick={() => knowledgeInputRef.current?.click()}
              disabled={isUploading}
            >
              <Upload className="mr-2 h-4 w-4" />
              {isUploading ? 'Uploading...' : 'Upload Knowledge'}
            </Button>
            <Button variant="outline" size="sm" onClick={onNewChat}>
              New Chat
            </Button>
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-4">
          <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
            <FilterGroup 
              options={filterOptions} 
              value={activeTab} 
              onChange={(v) => setActiveTab(v as LibraryTab)} 
            />
            <SearchInput 
              onSearch={setSearchQuery} 
              placeholder="Search in library..." 
              containerClassName="w-full md:w-80"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0">
          <ScrollArea className="h-full pr-4">
            {(activeTab === 'all' || activeTab === 'artifacts') && (
              <div className="space-y-4 pb-8">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold">Knowledge Base</h2>
                    <p className="text-sm text-muted-foreground">
                      Uploaded files are stored in MinIO and indexed for researcher RAG retrieval.
                    </p>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {knowledgeFiles.length} files
                  </div>
                </div>

                {isKnowledgeLoading ? (
                  <div className="flex items-center justify-center h-24 rounded-2xl border bg-muted/20 text-muted-foreground">
                    Loading knowledge files...
                  </div>
                ) : filteredKnowledgeFiles.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filteredKnowledgeFiles.map((item) => (
                      <KnowledgeFileItem key={item.id} file={item} />
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-40 border-2 border-dashed rounded-3xl bg-muted/30 text-center px-6">
                    <h3 className="text-lg font-semibold">No knowledge files yet</h3>
                    <p className="text-sm text-muted-foreground mt-1 max-w-md">
                      Upload PDF, DOCX, MD, or TXT files here to make them searchable by researcher.
                    </p>
                  </div>
                )}
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground">
                Loading your library...
              </div>
            ) : filteredItems.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-10">
                {filteredItems.map((item) => (
                  item.libType === 'session' ? (
                    <SessionItem 
                      key={item.id} 
                      session={item} 
                      onSelect={onSelectSession}
                      onDelete={(id) => { setDeleteId(id); setDeleteType('session'); }}
                      onRename={(id) => setEditSession({ id, title: item.title })}
                      onTogglePin={onTogglePin}
                    />
                  ) : (
                    <ArtifactItem 
                      key={item.id} 
                      artifact={item}
                      onDelete={(id) => { setDeleteId(id); setDeleteType('artifact'); }}
                    />
                  )
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-80 border-2 border-dashed rounded-3xl bg-muted/30">
                <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-4">
                    <History className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-semibold">No items found</h3>
                <p className="text-muted-foreground mt-1 text-center max-w-xs">
                    {searchQuery ? `We couldn't find anything matching "${searchQuery}"` : "Your library is empty. Start a conversation to see it here."}
                </p>
              </div>
            )}
          </ScrollArea>
        </div>
      </div>

      {/* Dialogs */}
      <ConfirmDialog 
        open={!!deleteId} 
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Item"
        description="Are you sure you want to delete this? This action cannot be undone."
        onConfirm={handleDelete}
        variant="destructive"
      />

      {editSession && (
        <EditDialog 
          open={!!editSession}
          onOpenChange={(open) => !open && setEditSession(null)}
          title="Rename Session"
          label="Session Title"
          initialValue={editSession.title}
          onSave={handleRename}
        />
      )}
    </div>
  )
}
