import { useCallback, useMemo, useRef, useState } from 'react'

import {
  extractKnowledge,
  fetchDocumentKnowledgePoints,
  finalizeKnowledgeExtraction,
  startKnowledgeExtraction,
} from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


const EXTRACTION_CONCURRENCY = 3
const REFINEMENT_POLL_DELAY_MS = 1200
const REFINEMENT_TERMINAL_STATUSES = new Set(['completed', 'failed', 'degraded'])


function normalizeKnowledgePoints(points, fallbackPrefix = 'kp') {
  return (points || []).map((kp, index) => {
    const chunkIndex = kp.chunk_index ?? kp.chunkIndex ?? index
    return {
      ...kp,
      chunkIndex,
      id: hashString(`${kp.text}${chunkIndex}`) || `${fallbackPrefix}-${index}`,
    }
  })
}


export function useKnowledgeExtraction() {
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extractError, setExtractError] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [refinementStatus, setRefinementStatus] = useState('not_started')
  const [refinementRunId, setRefinementRunId] = useState(null)
  const [highlightResetToken, setHighlightResetToken] = useState(0)
  const extractingRef = useRef(false)
  const extractionRunRef = useRef(0)
  const refinementPollRef = useRef(null)

  const stopRefinementPolling = useCallback(() => {
    if (refinementPollRef.current) {
      clearTimeout(refinementPollRef.current)
      refinementPollRef.current = null
    }
  }, [])

  const pollRefinedKnowledgePoints = useCallback((docId, localRunId, initialRunId = null) => {
    if (!docId) return
    stopRefinementPolling()
    if (initialRunId) setRefinementRunId(initialRunId)

    const poll = async () => {
      if (extractionRunRef.current !== localRunId) return
      try {
        const data = await fetchDocumentKnowledgePoints(docId)
        if (extractionRunRef.current !== localRunId) return

        const nextStatus = data.refinement_status || (data.is_refined ? 'completed' : 'running')
        setRefinementStatus(nextStatus)
        if (data.refinement_run_id) setRefinementRunId(data.refinement_run_id)

        if (data.is_refined) {
          setKnowledgePoints(normalizeKnowledgePoints(data.knowledge_points, 'refined-kp'))
          setHighlightResetToken(token => token + 1)
          setRefinementStatus(nextStatus === 'not_started' ? 'completed' : nextStatus)
          return
        }

        if (REFINEMENT_TERMINAL_STATUSES.has(nextStatus)) return
        refinementPollRef.current = setTimeout(poll, REFINEMENT_POLL_DELAY_MS)
      } catch (err) {
        console.warn('文档级知识点整理状态获取失败:', err)
        if (extractionRunRef.current === localRunId) {
          refinementPollRef.current = setTimeout(poll, REFINEMENT_POLL_DELAY_MS * 2)
        }
      }
    }

    refinementPollRef.current = setTimeout(poll, REFINEMENT_POLL_DELAY_MS)
  }, [stopRefinementPolling])

  const resetExtraction = useCallback(() => {
    extractionRunRef.current += 1
    stopRefinementPolling()
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })
    setExtractError('')
    setExtracting(false)
    setRefinementStatus('not_started')
    setRefinementRunId(null)
    extractingRef.current = false
  }, [stopRefinementPolling])

  const restoreExtraction = useCallback((snapshot = {}) => {
    extractionRunRef.current += 1
    stopRefinementPolling()
    setKnowledgePoints(snapshot.knowledgePoints || [])
    setExtractProgress(snapshot.extractProgress || { done: 0, total: 0 })
    setExtractError(snapshot.extractError || '')
    setExtracting(false)
    setRefinementStatus(snapshot.refinementStatus || 'not_started')
    setRefinementRunId(snapshot.refinementRunId || null)
    extractingRef.current = false
  }, [stopRefinementPolling])

  const extractAllChunks = useCallback(async (_html, docId = null, options = {}) => {
    if (extractingRef.current) return
    if (!docId) {
      setExtractError('文档索引尚未就绪，暂时无法提取知识点。')
      return false
    }
    extractingRef.current = true
    const runId = extractionRunRef.current + 1
    extractionRunRef.current = runId
    stopRefinementPolling()
    setExtracting(true)
    setExtractError('')
    setRefinementStatus('not_started')
    setRefinementRunId(null)
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
          kpsByChunk[item.chunk_index] = normalizeKnowledgePoints(
            (data.knowledge_points || []).map(kp => ({ ...kp, chunk_index: item.chunk_index })),
            'chunk-kp',
          )
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
      if (backendRunId && extractionRunRef.current === runId) {
        setRefinementStatus(kpsByChunk.flat().length > 0 ? 'queued' : 'not_started')
        try {
          const finalized = await finalizeKnowledgeExtraction(backendRunId, docId, batchItems)
          if (extractionRunRef.current === runId && finalized?.refinement_run_id) {
            setRefinementStatus('running')
            pollRefinedKnowledgePoints(docId, runId, finalized.refinement_run_id)
          } else if (extractionRunRef.current === runId) {
            setRefinementStatus('not_started')
          }
        } catch (err) {
          console.warn('知识提取工作流收尾失败:', err)
          if (extractionRunRef.current === runId) setRefinementStatus('failed')
        }
      }
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
  }, [pollRefinedKnowledgePoints, stopRefinementPolling])

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
    refinementStatus,
    refinementRunId,
    highlightResetToken,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
    restoreExtraction,
  }
}
