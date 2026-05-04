import { useCallback, useRef, useState } from 'react'

import { requestDeepExplanation } from '../../api/knowledge'
import { findContextForKP } from '../knowledge/highlightDom'


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
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        setDeepExplanation(prev => prev + decoder.decode(value, { stream: true }))
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setDeepExplanation(prev => prev + `\n\n[错误] ${err.message}`)
      }
    } finally {
      setDeepLoading(false)
      deepAbortRef.current = null
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
