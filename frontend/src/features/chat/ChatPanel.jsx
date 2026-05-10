import { useState, useRef, useEffect } from 'react'
import { sendChatMessageStream } from '../../api/chat'
import { markdownToHtml } from '../../utils/markdown'

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
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      const response = await sendChatMessageStream(text, docId, controller.signal)
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: next[next.length - 1].content + chunk,
          }
          return next
        })
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
      abortRef.current = null
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
