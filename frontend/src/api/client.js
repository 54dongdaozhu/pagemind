const API_HOST = window.location.hostname || 'localhost'

export const API_BASE = `http://${API_HOST}:8000`


export async function postJson(path, body, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...options,
  })

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`)
  }

  return response.json()
}
