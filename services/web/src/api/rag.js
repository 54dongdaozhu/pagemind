import { apiFetch, postJson } from './client'


export function indexRagDocument(docId, text, title, chunks = null, images = null, render = {}) {
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
      render_html: render.html || null,
      render_outline: render.outline?.length
        ? render.outline.map(item => ({
            text: item.text,
            level: item.level,
            page_num: item.pageNum ?? item.page_num ?? null,
          }))
        : null,
    },
    { signal: controller.signal }
  ).finally(() => clearTimeout(timeoutId))
}


export async function fetchRagDocuments() {
  const response = await apiFetch('/api/rag/documents')
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  return response.json()
}


export async function fetchRagDocumentRender(docId) {
  const response = await apiFetch(`/api/rag/documents/${encodeURIComponent(docId)}/render`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const data = await response.json()
  return {
    id: data.doc_id,
    name: data.title || '未命名文档',
    html: data.html,
    plainText: data.plain_text || '',
    outline: (data.outline || []).map(item => ({
      text: item.text,
      level: item.level,
      pageNum: item.page_num ?? item.pageNum ?? null,
    })),
    updatedAt: data.updated_at,
  }
}
