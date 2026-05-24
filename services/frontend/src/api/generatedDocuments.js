import { apiFetch } from './client'


export async function fetchGeneratedDocuments() {
  const response = await apiFetch('/api/generated-documents')
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  return response.json()
}


export async function fetchGeneratedDocument(generatedDocId) {
  const response = await apiFetch(`/api/generated-documents/${encodeURIComponent(generatedDocId)}`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const data = await response.json()
  return {
    id: data.generated_doc_id,
    name: data.title || data.topic || '生成文档',
    topic: data.topic || '',
    requirements: data.requirements || '',
    html: data.html_snapshot || '',
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  }
}


export async function saveGeneratedDocumentSnapshot({ sourceTaskId, title, topic, requirements, html }) {
  const response = await apiFetch('/api/generated-documents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_task_id: sourceTaskId || null,
      title: title || topic || '生成文档',
      topic: topic || title || '生成文档',
      requirements: requirements || '',
      html_snapshot: html,
    }),
  })
  if (!response.ok) throw new Error(`保存失败: ${response.status}`)
  return response.json()
}
