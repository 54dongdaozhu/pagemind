import { API_BASE, postJson } from './client'


function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer)
  const chunkSize = 0x8000
  let binary = ''
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

function resolveAssetUrl(url) {
  if (!API_BASE || !url.startsWith('/')) return url
  return new URL(url, API_BASE).toString()
}

export async function uploadImageAsset(file, relativePath = '') {
  const result = await postJson('/api/assets/images', {
    filename: file.name,
    content_type: file.type || '',
    relative_path: relativePath,
    data_base64: arrayBufferToBase64(await file.arrayBuffer()),
  })

  return {
    ...result,
    url: resolveAssetUrl(result.url),
  }
}
