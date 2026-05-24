import { apiFetch, postJson } from './client'

export async function getSkillTree(signal) {
  const res = await apiFetch('/api/skill-tree', signal ? { signal } : {})
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`获取技能树失败: ${res.status}`)
  return res.json()
}

export async function generateSkillTree(force = false) {
  return postJson('/api/skill-tree/generate', { force })
}

export async function getSkillTreeStatus(snapshotId) {
  const res = await apiFetch(`/api/skill-tree/status/${snapshotId}`)
  if (!res.ok) throw new Error(`获取状态失败: ${res.status}`)
  return res.json()
}
