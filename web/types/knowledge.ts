export interface KnowledgeFile {
  id: string
  filename: string
  content_type?: string
  extension?: string
  size_bytes?: number
  bucket?: string
  object_key?: string
  download_path?: string
  collection_name?: string
  status: string
  parser_name?: string
  chunk_count?: number
  indexed_at?: string | null
  error?: string
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}
