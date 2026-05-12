import { useCallback, useRef, useState } from 'react'

import { requestDeepExplanation } from '../../api/knowledge'
import { findContextForKP } from '../knowledge/highlightDom'


const STREAM_DONE_MARKER = '\n[STREAM_DONE]\n'


export function useDeepExplanation(docContentRef) {
  const [deepExplanation, setDeepExplanation] = useState('')
  const [deepLoading, setDeepLoading] = useState(false)
  const [showDeep, setShowDeep] = useState(false)
  const deepAbortRef = useRef(null)

  const closeDeep = useCallback(() => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(false)
    setDeepExplanation('')
    setDeepLoading(false)
  }, [])

  const resetDeep = useCallback(() => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setDeepExplanation('')
    setDeepLoading(false)
    setShowDeep(false)
    deepAbortRef.current = null
  }, [])

  const startDeepExplain = useCallback(async (kp) => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(true)
    setDeepExplanation('')
    setDeepLoading(true)
    const context = findContextForKP(docContentRef.current, kp.id) || kp.text
    const controller = new AbortController()
    deepAbortRef.current = controller
    try {
      const response = await requestDeepExplanation(kp, context, controller.signal)
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      if (!response.body) throw new Error('响应不支持流式读取')
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let pendingText = ''
      const appendExplanationChunk = (chunk) => {
        if (chunk) setDeepExplanation(prev => prev + chunk)
      }
      const consumeStreamText = (chunk) => {
        const text = pendingText + chunk
        const markerIndex = text.indexOf(STREAM_DONE_MARKER)
        if (markerIndex !== -1) {
          appendExplanationChunk(text.slice(0, markerIndex))
          pendingText = ''
          return true
        }

        const keepLength = Math.min(STREAM_DONE_MARKER.length - 1, text.length)
        appendExplanationChunk(text.slice(0, text.length - keepLength))
        pendingText = text.slice(text.length - keepLength)
        return false
      }
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (consumeStreamText(decoder.decode(value, { stream: true }))) break
        }
        consumeStreamText(decoder.decode())
        appendExplanationChunk(pendingText)
        pendingText = ''
      } finally {
        reader.releaseLock()
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setDeepExplanation(prev => prev + `\n\n[错误] ${err.message}`)
      }
    } finally {
      if (deepAbortRef.current === controller) {
        setDeepLoading(false)
        deepAbortRef.current = null
      }
    }
  }, [docContentRef])

  return {
    deepExplanation,
    deepLoading,
    showDeep,
    closeDeep,
    resetDeep,
    startDeepExplain,
  }
}
