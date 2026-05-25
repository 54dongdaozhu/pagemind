import { apiFetch, clearAuthToken, getAuthToken, postJson, setAuthToken } from './client'


function storeSession(data) {
  if (data?.access_token) setAuthToken(data.access_token)
  return data
}


export async function registerUser({ username, email, password }) {
  return storeSession(await postJson('/api/auth/register', { username, email, password }))
}


export async function loginUser({ account, password }) {
  return storeSession(await postJson('/api/auth/login', { account, password }))
}


export async function fetchCurrentUser() {
  if (!getAuthToken()) return null
  const response = await apiFetch('/api/auth/me', { timeout: 5000 })
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  return response.json()
}


export function logoutUser() {
  clearAuthToken()
}
