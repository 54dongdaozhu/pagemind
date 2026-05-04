import { postJson } from './client'


export function indexRagDocument(docId, text, title) {
  return postJson('/api/rag/index', {
    doc_id: docId,
    text,
    title,
  })
}
