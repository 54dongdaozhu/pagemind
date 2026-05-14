import { useCallback, useMemo, useRef, useState } from 'react'

import {
  extractKnowledge,
  finalizeKnowledgeExtraction,
  startKnowledgeExtraction,
} from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


const EXTRACTION_CONCURRENCY = 3


function finalizeDocumentExtraction(runId, docId, batchItems) {
  if (!runId || !docId || !batchItems.length) return
  finalizeKnowledgeExtraction(runId, docId, batchItems).catch(err => {
    console.warn('知识提取工作流收尾失败:', err)
  })
}


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

  const extractAllChunks = useCallback(async (_html, docId = null, options = {}) => {
    if (extractingRef.current) return
    if (!docId) {
      setExtractError('文档索引尚未就绪，暂时无法提取知识点。')
      return false
    }
    extractingRef.current = true
    const runId = extractionRunRef.current + 1
    extractionRunRef.current = runId
    setExtracting(true)
    setExtractError('')
    const chunks = options.chunks || splitIntoChunks(_html)
    const canonicalChunks = chunks.map(text => String(text || '').trim()).filter(Boolean)
    setExtractProgress({ done: 0, total: canonicalChunks.length })
    const kpsByChunk = Array.from({ length: canonicalChunks.length }, () => [])
    const batchItems = canonicalChunks.map((text, index) => ({
      text,
      chunk_id: hashString(`${docId}:${index}:${text}`),
      doc_id: docId,
      chunk_index: index,
    }))
    let backendRunId = null
    try {
      const started = await startKnowledgeExtraction(docId, batchItems, options.title)
      backendRunId = started.run_id
    } catch (err) {
      console.warn('知识提取工作流启动失败，将继续使用本地进度:', err)
    }
    let nextChunkIndex = 0
    let completed = 0

    const updateKnowledgePoints = () => {
      setKnowledgePoints(kpsByChunk.flat())
    }

    const extractNextChunk = async () => {
      while (nextChunkIndex < batchItems.length && extractionRunRef.current === runId) {
        const item = batchItems[nextChunkIndex]
        nextChunkIndex += 1

        try {
          const data = await extractKnowledge(item.text, item.chunk_id, item.doc_id, item.chunk_index, backendRunId)
          kpsByChunk[item.chunk_index] = (data.knowledge_points || []).map(kp => ({
            ...kp,
            chunkIndex: item.chunk_index,
            id: hashString(kp.text + item.chunk_index),
          }))
          if (extractionRunRef.current === runId) {
            updateKnowledgePoints()
          }
        } catch (err) {
          console.error(`块 ${item.chunk_index} 提取出错:`, err)
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
            setExtractProgress({ done: completed, total: canonicalChunks.length })
          }
        }
      }
    }

    try {
      const workerCount = Math.min(EXTRACTION_CONCURRENCY, batchItems.length)
      await Promise.all(Array.from({ length: workerCount }, extractNextChunk))
      finalizeDocumentExtraction(backendRunId, docId, batchItems)
      return true
    } catch (err) {
      console.error('文档知识点提取出错:', err)
      if (extractionRunRef.current === runId) {
        if (err?.status === 401) {
          setExtractError('登录状态已失效，请重新登录后再提取知识点。')
        } else {
          setExtractError(err?.message || '知识点接口暂时不可用，请确认后端服务已启动并可访问。')
        }
      }
      return false
    } finally {
      if (extractionRunRef.current === runId) {
        setExtracting(false)
        extractingRef.current = false
      }
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
