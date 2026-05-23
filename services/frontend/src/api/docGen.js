import { getAuthToken } from './client'

const DOC_GEN_BASE = import.meta.env.VITE_DOC_GEN_API_BASE || ''

async function _docGenFetch(path, options = {}) {
  const token = getAuthToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(`${DOC_GEN_BASE}/api/doc-gen${path}`, { ...options, headers })
}

export async function startDocGen(topic, requirements, userId, userProfile = null) {
  const resp = await _docGenFetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, requirements, user_id: userId, user_profile: userProfile || {} }),
  })
  if (!resp.ok) throw new Error(`启动失败: ${resp.status}`)
  return resp.json()  // { task_id }
}

export function streamDocGen(taskId, { onProgress, onHumanInterrupt, onComplete, onError }) {
  const controller = new AbortController()

  async function _run() {
    try {
      const token = getAuthToken()
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(`${DOC_GEN_BASE}/api/doc-gen/${taskId}/stream`, {
        headers,
        signal: controller.signal,
      })
      if (!resp.ok) throw new Error(`流连接失败: ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed) continue
          try {
            const msg = JSON.parse(trimmed)
            if (msg.type === 'progress' || msg.type === 'section_ready') {
              onProgress?.(msg)
            } else if (msg.type === 'human_interrupt') {
              onHumanInterrupt?.(msg)
            } else if (msg.type === 'complete') {
              onComplete?.(msg)
            } else if (msg.type === 'error') {
              onError?.(new Error(msg.message))
            }
          } catch {
            // ignore malformed lines
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') onError?.(err)
    }
  }

  _run()
  return () => controller.abort()
}

export async function resumeDocGen(taskId, decision, feedback = '') {
  const resp = await _docGenFetch(`/${taskId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, feedback }),
  })
  if (!resp.ok) throw new Error(`Resume 失败: ${resp.status}`)
  return resp.json()
}

export function getWordDownloadUrl(taskId) {
  return `${DOC_GEN_BASE}/api/doc-gen/${taskId}/word`
}

export async function deleteDocGenTask(taskId) {
  await _docGenFetch(`/${taskId}`, { method: 'DELETE' })
}
