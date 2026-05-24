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
