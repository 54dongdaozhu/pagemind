import { useCallback, useMemo, useRef, useState } from 'react'

import { extractKnowledge } from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


const EXTRACTION_CONCURRENCY = 3


export function useKnowledgeExtraction() {
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extractError, setExtractError] = useState('')
  const [extracting, setExtracting] = useState(false)
  const extractingRef = useRef(false)
  const extractionRunRef = useRef(0)

  const resetExtraction = useCallback(() => {
    extractionRunRef.current += 1
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })
    setExtractError('')
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const restoreExtraction = useCallback((snapshot = {}) => {
    extractionRunRef.current += 1
    setKnowledgePoints(snapshot.knowledgePoints || [])
    setExtractProgress(snapshot.extractProgress || { done: 0, total: 0 })
    setExtractError(snapshot.extractError || '')
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const extractAllChunks = useCallback(async (html, docId = null) => {
    if (extractingRef.current) return
    extractingRef.current = true
    const runId = extractionRunRef.current + 1
    extractionRunRef.current = runId
    setExtracting(true)
    setExtractError('')
    const chunks = splitIntoChunks(html)
    setExtractProgress({ done: 0, total: chunks.length })
    const kpsByChunk = Array.from({ length: chunks.length }, () => [])
    let nextChunkIndex = 0
    let completed = 0

    const updateKnowledgePoints = () => {
      setKnowledgePoints(kpsByChunk.flat())
    }

    const extractNextChunk = async () => {
      while (nextChunkIndex < chunks.length && extractionRunRef.current === runId) {
        const i = nextChunkIndex
        nextChunkIndex += 1
        const text = chunks[i]
        const chunkId = hashString(text)

        try {
          const data = await extractKnowledge(text, chunkId, docId, i)
          kpsByChunk[i] = (data.knowledge_points || []).map(kp => ({
            ...kp,
            chunkIndex: i,
            id: hashString(kp.text + i),
          }))
          if (extractionRunRef.current === runId) {
            updateKnowledgePoints()
          }
        } catch (err) {
          console.error(`块 ${i} 提取出错:`, err)
          if (extractionRunRef.current === runId) {
            if (err?.status === 401) {
              setExtractError('登录状态已失效，请重新登录后再提取知识点。')
            } else {
              setExtractError(err?.message || '知识点接口暂时不可用，请确认后端服务已启动并可访问。')
            }
          }
        } finally {
          completed += 1
          if (extractionRunRef.current === runId) {
            setExtractProgress({ done: completed, total: chunks.length })
          }
        }
      }
    }

    const workerCount = Math.min(EXTRACTION_CONCURRENCY, chunks.length)
    await Promise.all(Array.from({ length: workerCount }, extractNextChunk))

    if (extractionRunRef.current === runId) {
      setExtracting(false)
      extractingRef.current = false
    }
  }, [])

  const uniqueKPs = useMemo(() => {
    const items = []
    const seenTexts = new Set()
    for (const kp of knowledgePoints) {
      if (!seenTexts.has(kp.text)) {
        seenTexts.add(kp.text)
        items.push(kp)
      }
    }
    return items
  }, [knowledgePoints])

  return {
    extracting,
    knowledgePoints,
    extractProgress,
    extractError,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
    restoreExtraction,
  }
}
