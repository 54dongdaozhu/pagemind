import { useState, useRef, useEffect } from 'react'
import { sendChatMessageStream } from '../../api/chat'
import { markdownToHtml } from '../../utils/markdown'

const STREAM_DONE_MARKER = '\n[STREAM_DONE]\n'
const STREAM_META_MARKER = '\n[STREAM_META]\n'


function ChatPanel({ docId, docLoaded, messages, setMessages, loading, setLoading }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    const history = messages
      .filter(msg => msg.role === 'user' || msg.role === 'assistant')
      .filter(msg => msg.content && msg.content.trim())
      .slice(-8)
      .map(msg => ({ role: msg.role, content: msg.content }))

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      const response = await sendChatMessageStream(text, docId, history, controller.signal)
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      if (!response.body) throw new Error('响应不支持流式读取')
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let pendingText = ''
      let readingMetadata = false
      let metadataText = ''
      let streamComplete = false
      const appendAssistantChunk = (chunk) => {
        if (!chunk) return
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: next[next.length - 1].content + chunk,
          }
          return next
        })
      }
      const applyAssistantMetadata = () => {
        const doneIndex = metadataText.indexOf(STREAM_DONE_MARKER)
        const rawMetadata = (doneIndex === -1 ? metadataText : metadataText.slice(0, doneIndex)).trim()
        if (!rawMetadata) return
        try {
          const metadata = JSON.parse(rawMetadata)
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = {
              ...next[next.length - 1],
              agent: metadata.agent,
              intent: metadata.intent,
              tools_used: metadata.tools_used || [],
              stop_reason: metadata.stop_reason,
              sources: metadata.sources || [],
            }
            return next
          })
        } catch {
          // Ignore malformed stream metadata; the answer text has already rendered.
        }
      }
      const consumeStreamText = (chunk) => {
        if (readingMetadata) {
          metadataText += chunk
          if (metadataText.includes(STREAM_DONE_MARKER)) {
            streamComplete = true
          }
          return streamComplete
        }

        const text = pendingText + chunk
        const metaIndex = text.indexOf(STREAM_META_MARKER)
        if (metaIndex !== -1) {
          appendAssistantChunk(text.slice(0, metaIndex))
          metadataText += text.slice(metaIndex + STREAM_META_MARKER.length)
          pendingText = ''
          readingMetadata = true
          streamComplete = metadataText.includes(STREAM_DONE_MARKER)
          return streamComplete
        }

        const markerIndex = text.indexOf(STREAM_DONE_MARKER)
        if (markerIndex !== -1) {
          appendAssistantChunk(text.slice(0, markerIndex))
          pendingText = ''
          streamComplete = true
          return true
        }

        const markerTailLength = Math.max(STREAM_DONE_MARKER.length, STREAM_META_MARKER.length) - 1
        const keepLength = Math.min(markerTailLength, text.length)
        appendAssistantChunk(text.slice(0, text.length - keepLength))
        pendingText = text.slice(text.length - keepLength)
        return false
      }
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (consumeStreamText(decoder.decode(value, { stream: true }))) break
        }
        if (!streamComplete) {
          consumeStreamText(decoder.decode())
        }
        if (readingMetadata) {
          applyAssistantMetadata()
        } else {
          appendAssistantChunk(pendingText)
          pendingText = ''
        }
      } finally {
        if (streamComplete) {
          await reader.cancel().catch(() => {})
        }
        reader.releaseLock()
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { ...next[next.length - 1], content: '请求失败，请重试。' }
          return next
        })
      }
    } finally {
      setLoading(false)
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">
            {docLoaded ? '可以围绕当前文档提问' : '上传文档后可以围绕内容提问'}
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
            {msg.role === 'assistant' ? (
              <>
                {msg.content ? (
                  <div
                    className="chat-markdown"
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(msg.content) }}
                  />
                ) : null}
                {loading && i === messages.length - 1 && (
                  <span className="cursor-blink">▋</span>
                )}
              </>
            ) : (
              <div className="chat-plain-text">{msg.content}</div>
            )}
            {msg.sources?.length > 0 && (
              <div className="chat-sources">
                {msg.sources.map(source => (
                  <span
                    key={`${source.retrieval_method}-${source.chunk_index}`}
                    className="chat-source-chip"
                    title={source.content}
                  >
                    片段 {source.chunk_index + 1}
                    {source.retrieval_method === 'embedding' ? ' · 向量' : ' · 关键词'}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="chat-msg chat-msg-assistant chat-msg-loading">
            <span className="thinking-dot">●</span>
            <span className="thinking-dot">●</span>
            <span className="thinking-dot">●</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          placeholder="输入消息，Enter 发送"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading || !docLoaded}
        />
        <button className="chat-send-btn" onClick={send} disabled={loading || !docLoaded || !input.trim()}>
          发送
        </button>
      </div>
    </div>
  )
}

export default ChatPanel
