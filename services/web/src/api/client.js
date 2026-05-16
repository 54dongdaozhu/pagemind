export const API_BASE = import.meta.env.VITE_API_BASE || ''
const TOKEN_KEY = 'ai-study-token'


export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY)
}


export function setAuthToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}


export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY)
}


export async function apiFetch(path, options = {}) {
  const { timeout = 30000, signal: externalSignal, ...fetchOptions } = options
  const token = getAuthToken()
  const headers = { ...(fetchOptions.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`

  let controller, timer, signal = externalSignal
  if (timeout !== null && !externalSignal) {
    controller = new AbortController()
    timer = setTimeout(() => controller.abort(), timeout)
    signal = controller.signal
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers, signal })
    if (response.status === 401) {
      clearAuthToken()
      window.dispatchEvent(new CustomEvent('auth:expired'))
    }
    return response
  } finally {
    clearTimeout(timer)
  }
}


export async function postJson(path, body, options = {}) {
  const response = await apiFetch(path, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    let message = `请求失败: ${response.status}`
    try {
      const data = await response.json()
      if (data?.detail) message = data.detail
    } catch {
      // ignore non-JSON error responses
    }
    const error = new Error(message)
    error.status = response.status
    throw error
  }

  return response.json()
}
