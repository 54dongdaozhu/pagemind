import { useCallback, useRef, useState } from 'react'
import { deleteDocGenTask, getWordDownloadUrl, resumeDocGen, startDocGen, streamDocGen } from '../../api/docGen'

export function useDocGen(userId, userProfile) {
  const [taskId, setTaskId] = useState(null)
  const [status, setStatus] = useState('idle')  // idle | running | waiting_human | done | error
  const [messages, setMessages] = useState([])
  const [htmlContent, setHtmlContent] = useState('')
  const [wordUrl, setWordUrl] = useState(null)
  const [humanPayload, setHumanPayload] = useState(null)
  const [error, setError] = useState('')

  const stopStreamRef = useRef(null)

  const _appendMessage = useCallback((type, text, agent = '') => {
    setMessages(prev => [...prev, { type, text, agent, ts: Date.now() }])
  }, [])

  const _startStream = useCallback((tid) => {
    stopStreamRef.current?.()
    const stop = streamDocGen(tid, {
      onProgress: (msg) => {
        _appendMessage('progress', msg.message, msg.agent)
      },
      onHumanInterrupt: (msg) => {
        setStatus('waiting_human')
        setHumanPayload(msg)
        _appendMessage('system', '等待人工审核...')
      },
      onComplete: (msg) => {
        setHtmlContent(msg.html || '')
        setWordUrl(msg.word_url ? getWordDownloadUrl(tid) : null)
        setStatus('done')
        _appendMessage('system', '文档生成完成！')
      },
      onError: (err) => {
        setStatus('error')
        setError(err.message)
        _appendMessage('error', `错误: ${err.message}`)
      },
    })
    stopStreamRef.current = stop
  }, [_appendMessage])

  const generate = useCallback(async (topic, requirements) => {
    setStatus('running')
    setMessages([])
    setHtmlContent('')
    setWordUrl(null)
    setHumanPayload(null)
    setError('')

    try {
      _appendMessage('system', `开始生成「${topic}」教学文档...`)
      const { task_id } = await startDocGen(topic, requirements, userId, userProfile)
      setTaskId(task_id)
      _startStream(task_id)
    } catch (err) {
      setStatus('error')
      setError(err.message)
      _appendMessage('error', `启动失败: ${err.message}`)
    }
  }, [userId, userProfile, _appendMessage, _startStream])

  const submitHumanDecision = useCallback(async (decision, feedback = '') => {
    if (!taskId) return
    try {
      setStatus('running')
      setHumanPayload(null)
      await resumeDocGen(taskId, decision, feedback)
      _appendMessage('system', decision === 'publish' ? '已批准，正在发布...' : '已要求修订，继续优化...')
      _startStream(taskId)
    } catch (err) {
      setStatus('error')
      setError(err.message)
    }
  }, [taskId, _appendMessage, _startStream])

  const reset = useCallback(() => {
    stopStreamRef.current?.()
    if (taskId) deleteDocGenTask(taskId).catch(() => {})
    setTaskId(null)
    setStatus('idle')
    setMessages([])
    setHtmlContent('')
    setWordUrl(null)
    setHumanPayload(null)
    setError('')
  }, [taskId])

  return {
    status,
    messages,
    htmlContent,
    wordUrl,
    humanPayload,
    error,
    generate,
    submitHumanDecision,
    reset,
  }
}
