import { postJson } from './client'

export function sendChatMessage(message) {
  return postJson('/api/test-llm', { message })
}
