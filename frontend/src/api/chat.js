import { postJson } from './client'

export function sendChatMessage(message, docId) {
  if (!docId) return postJson('/api/test-llm', { message })
  return postJson('/api/rag/query', {
    doc_id: docId,
    question: message,
    top_k: 4,
  })
}
