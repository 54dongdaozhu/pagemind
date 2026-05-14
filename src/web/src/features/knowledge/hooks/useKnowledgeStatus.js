import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  fetchKnowledgeStatuses,
  markKnowledgeKnown,
  recordKnowledgeClick,
  unmarkKnowledgeKnown,
} from '../../../api/knowledge'


export function useKnowledgeStatus(knowledgePoints) {
  const [kpStatusMap, setKpStatusMap] = useState({})
  const knowledgeTextKey = useMemo(
    () => knowledgePoints.map(kp => kp.text).join('\u0001'),
    [knowledgePoints],
  )
  const knowledgeTexts = useMemo(
    () => (knowledgeTextKey ? knowledgeTextKey.split('\u0001') : []),
    [knowledgeTextKey],
  )

  const getKpStatus = useCallback(
    (kpText) => kpStatusMap[kpText] || 'unknown',
    [kpStatusMap],
  )

  useEffect(() => {
    if (knowledgeTexts.length === 0) return
    fetchKnowledgeStatuses(knowledgeTexts)
      .then(data => {
        if (!data) return
        const map = {}
        for (const item of data.items) map[item.kp_text] = item.status
        setKpStatusMap(prev => ({ ...prev, ...map }))
      })
      .catch(err => console.error('拉取状态失败:', err))
  }, [knowledgeTextKey, knowledgeTexts])

  const recordClick = useCallback(async (kp) => {
    try {
      const data = await recordKnowledgeClick(kp)
      setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
    } catch (err) {
      console.error('上报点击失败:', err)
    }
  }, [])

  const toggleKnown = useCallback(async (kp) => {
    const currentStatus = getKpStatus(kp.text)
    try {
      const data = currentStatus === 'known'
        ? await unmarkKnowledgeKnown(kp)
        : await markKnowledgeKnown(kp)
      setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
    } catch (err) {
      console.error('切换状态失败:', err)
    }
  }, [getKpStatus])

  const stats = useMemo(() => {
    const counts = { unknown: 0, learning: 0, known: 0 }
    for (const kp of knowledgePoints) {
      const status = getKpStatus(kp.text)
      counts[status] = (counts[status] || 0) + 1
    }
    return counts
  }, [knowledgePoints, getKpStatus])

  return {
    kpStatusMap,
    getKpStatus,
    recordClick,
    toggleKnown,
    stats,
  }
}
