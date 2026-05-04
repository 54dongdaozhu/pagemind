import { postJson } from './client'

export function sendChatMessage(message, docId) {
  if (!docId) return postJson('/api/test-llm', { message })
  return postJson('/api/agent/chat', {
    doc_id: docId,
    message,
  })
}
