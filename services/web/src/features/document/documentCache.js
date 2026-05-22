const DB_NAME = 'ai-study-documents'
const DB_VERSION = 1
const STORE_NAME = 'renderSnapshots'

function openDocumentCache() {
  if (!('indexedDB' in window)) return Promise.resolve(null)

  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => resolve(null)
    request.onblocked = () => resolve(null)
  })
}

async function withStore(mode, callback) {
  const db = await openDocumentCache()
  if (!db) return null

  return new Promise((resolve) => {
    const tx = db.transaction(STORE_NAME, mode)
    const store = tx.objectStore(STORE_NAME)
    let value = null
    tx.oncomplete = () => {
      db.close()
      resolve(value)
    }
    tx.onerror = () => {
      db.close()
      resolve(null)
    }
    value = callback(store)
  })
}

export async function saveDocumentSnapshot(snapshot) {
  if (!snapshot?.id || !snapshot.html) return
  await withStore('readwrite', store => {
    store.put({
      ...snapshot,
      cachedAt: new Date().toISOString(),
    })
  })
}

export async function getDocumentSnapshot(docId) {
  if (!docId) return null
  return withStore('readonly', store => new Promise((resolve) => {
    const request = store.get(docId)
    request.onsuccess = () => resolve(request.result || null)
    request.onerror = () => resolve(null)
  }))
}
