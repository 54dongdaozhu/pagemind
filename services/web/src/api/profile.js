import { apiFetch, postJson } from './client'

export async function analyzeProfile(backgroundText) {
  return postJson('/api/profile/analyze', { background_text: backgroundText })
}

export async function fetchMyProfile() {
  const res = await apiFetch('/api/profile/me')
  if (res.status === 404) return null
  if (!res.ok) return null
  return res.json()
}
