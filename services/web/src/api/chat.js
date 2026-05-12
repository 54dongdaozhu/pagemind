import { apiFetch, postJson } from './client'

export function sendChatMessage(message, docId, history = []) {
  if (!docId) return postJson('/api/test-llm', { message })
  return postJson('/api/agent/chat', {
    doc_id: docId,
    message,
    history,
  })
}

export function sendChatMessageStream(message, docId, history = [], signal) {
  return apiFetch('/api/agent/chat-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_id: docId || null, message, history }),
    signal,
  })
}
