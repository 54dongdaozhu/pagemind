import { apiFetch, postJson } from './client'


export function startKnowledgeExtraction(docId, chunks, title) {
  return postJson('/api/extract-knowledge/start', {
    doc_id: docId,
    chunks,
    title,
    source: 'frontend_chunks',
  })
}


export function extractKnowledge(text, chunkId, docId, chunkIndex, runId = null) {
  return postJson('/api/extract-knowledge', {
    text,
    chunk_id: chunkId,
    doc_id: docId,
    chunk_index: chunkIndex,
    run_id: runId,
  })
}


export function extractKnowledgeBatch(chunks, runId = null) {
  return postJson('/api/extract-knowledge-batch', { chunks, run_id: runId })
}


export function finalizeKnowledgeExtraction(runId, docId, chunks) {
  return postJson('/api/extract-knowledge/finalize', {
    run_id: runId,
    doc_id: docId,
    chunks,
  })
}


export function fetchKnowledgeExtractionStatus(runId) {
  return apiFetch(`/api/extract-knowledge/status?run_id=${encodeURIComponent(runId)}`)
    .then(response => {
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      return response.json()
    })
}


export function extractDocumentKnowledge(docId, text, title) {
  return postJson('/api/extract-knowledge-document', {
    doc_id: docId,
    text,
    title,
  })
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
