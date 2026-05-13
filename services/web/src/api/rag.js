import { postJson } from './client'


export function indexRagDocument(docId, text, title) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 15000)
  return postJson(
    '/api/rag/index',
    {
      doc_id: docId,
      text,
      title,
    },
    { signal: controller.signal }
  ).finally(() => clearTimeout(timeoutId))
}
