import { apiFetch, postJson } from './client'


export function extractKnowledge(text, chunkId) {
  return postJson('/api/extract-knowledge', { text, chunk_id: chunkId })
}


export function extractKnowledgeBatch(chunks) {
  return postJson('/api/extract-knowledge-batch', { chunks })
}


export function fetchKnowledgeStatuses(kpTexts) {
  return postJson('/api/knowledge/status-batch', { kp_texts: kpTexts })
}


export function recordKnowledgeClick(kp) {
  return postJson('/api/knowledge/click', { kp_text: kp.text, kp_type: kp.type })
}


export function markKnowledgeKnown(kp) {
  return postJson('/api/knowledge/mark-known', { kp_text: kp.text, kp_type: kp.type })
}


export function unmarkKnowledgeKnown(kp) {
  return postJson('/api/knowledge/unmark-known', { kp_text: kp.text })
}


export function requestDeepExplanation(kp, context, signal) {
  return apiFetch('/api/explain-deep', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword: kp.text, kp_type: kp.type, context }),
    signal,
  })
}
