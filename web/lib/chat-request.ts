import type { ImageAttachment } from '@/types/chat'
import type { SearchModePayload } from '@/lib/chat-mode'

export function buildChatRequestPayload({
  messageHistory,
  model,
  searchMode,
  images,
  threadId,
}: {
  messageHistory: Array<{ role: string; content: string }>
  model: string
  searchMode: SearchModePayload
  images: ImageAttachment[]
  threadId?: string | null
}) {
  return {
    messages: messageHistory.map((message) => ({ role: message.role, content: message.content })),
    stream: true,
    model,
    search_mode: searchMode,
    images: images.map((img) => ({
      name: img.name,
      mime: img.mime,
      data: img.data,
    })),
    ...(threadId ? { thread_id: threadId } : {}),
  }
}
