import { useCallback, useMemo, useRef, useState } from 'react'

import { extractKnowledge } from '../../../api/knowledge'
import { splitIntoChunks } from '../../document/documentUtils'
import { hashString } from '../../../utils/hash'


export function useKnowledgeExtraction() {
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extracting, setExtracting] = useState(false)
  const extractingRef = useRef(false)

  const resetExtraction = useCallback(() => {
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })
    setExtracting(false)
    extractingRef.current = false
  }, [])

  const extractAllChunks = useCallback(async (html) => {
    if (extractingRef.current) return
    extractingRef.current = true
    setExtracting(true)
    const chunks = splitIntoChunks(html)
    setExtractProgress({ done: 0, total: chunks.length })
    const allKPs = []

    for (let i = 0; i < chunks.length; i++) {
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
        setKnowledgePoints([...allKPs])
      } catch (err) {
        console.error(`块 ${i} 提取出错:`, err)
      }
      setExtractProgress({ done: i + 1, total: chunks.length })
    }
    setExtracting(false)
    extractingRef.current = false
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
