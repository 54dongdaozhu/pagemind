import { useCallback, useMemo, useRef, useState } from 'react'

import { extractKnowledge } from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


const EXTRACTION_CONCURRENCY = 3


export function useKnowledgeExtraction() {
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extracting, setExtracting] = useState(false)
  const extractingRef = useRef(false)
  const extractionRunRef = useRef(0)

  const resetExtraction = useCallback(() => {
    extractionRunRef.current += 1
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const extractAllChunks = useCallback(async (html) => {
    if (extractingRef.current) return
    extractingRef.current = true
    const runId = extractionRunRef.current + 1
    extractionRunRef.current = runId
    setExtracting(true)
    const chunks = splitIntoChunks(html)
    setExtractProgress({ done: 0, total: chunks.length })
    const allKPs = []
    let nextChunkIndex = 0
    let completed = 0

    const updateKnowledgePoints = () => {
      const orderedKPs = [...allKPs].sort((a, b) => a.chunkIndex - b.chunkIndex)
      setKnowledgePoints(orderedKPs)
    }

    const extractNextChunk = async () => {
      while (nextChunkIndex < chunks.length && extractionRunRef.current === runId) {
        const i = nextChunkIndex
        nextChunkIndex += 1
        const text = chunks[i]
        const chunkId = hashString(text)

        try {
          const data = await extractKnowledge(text, chunkId)
          const kpsWithMeta = data.knowledge_points.map(kp => ({
            ...kp,
            chunkIndex: i,
            id: hashString(kp.text + i),
          }))
          allKPs.push(...kpsWithMeta)
          if (extractionRunRef.current === runId) {
            updateKnowledgePoints()
          }
        } catch (err) {
          console.error(`块 ${i} 提取出错:`, err)
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
    extractProgress,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
  }
}
