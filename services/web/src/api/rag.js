import { postJson } from './client'


export function indexRagDocument(docId, text, title, chunks = null, images = null) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 15000)
  return postJson(
    '/api/rag/index',
    {
      doc_id: docId,
      text,
      title,
      chunks,
      images: images?.length ? images : null,
    },
    { signal: controller.signal }
  ).finally(() => clearTimeout(timeoutId))
}
