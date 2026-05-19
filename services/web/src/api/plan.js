import { apiFetch } from './client'

export function streamPlanChat(message, history = [], signal) {
  return apiFetch('/api/plan/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  })
}
