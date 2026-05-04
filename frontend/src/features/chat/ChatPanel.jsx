import { useState, useRef, useEffect } from 'react'
import { sendChatMessage } from '../../api/chat'

function ChatPanel({ docId, docLoaded }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const data = await sendChatMessage(text, docId)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.reply,
        sources: data.sources || [],
      }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '请求失败，请重试。' }])
    } finally {
      setLoading(false)
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
            <div>{msg.content}</div>
            {msg.sources?.length > 0 && (
              <div className="chat-sources">
                {msg.sources.map(source => (
                  <span key={source.chunk_index} className="chat-source-chip">
                    片段 {source.chunk_index + 1}
                    {source.retrieval_method === 'embedding' ? ' · 向量' : ''}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
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
