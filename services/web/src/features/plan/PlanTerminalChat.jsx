import { useEffect, useRef, useState } from 'react'
import { analyzeProfile } from '../../api/profile'
import { streamPlanChat } from '../../api/plan'

function PlanTerminalChat({ userProfile, onProfileSave, planStatus, onGenerate, onContentChunk, onDone, onReject }) {
  const [messages, setMessages] = useState([
    { role: 'system', text: '已加载用户画像，计划生成模块准备就绪。' },
  ])
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [showProfile, setShowProfile] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleEditOpen() {
    setEditText(userProfile?.background_text || '')
    setEditing(true)
  }

  async function handleSave() {
    if (!editText.trim() || saving) return
    setSaving(true)
    try {
      const profile = await analyzeProfile(editText.trim())
      onProfileSave(profile)
      setEditing(false)
    } catch (e) {
      setMessages(prev => [...prev, { role: 'system', text: `保存失败：${e.message || '请稍后重试'}` }])
    } finally {
      setSaving(false)
    }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || planStatus === 'generating') return
    setMessages(prev => [...prev, { role: 'user', text }])
    setInput('')
    onGenerate()

    try {
      const res = await streamPlanChat(text, history)
      if (!res.ok) {
        const err = `请求失败: ${res.status}`
        onReject(err)
        setMessages(prev => [...prev, { role: 'system', text: err }])
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let terminalReply = ''
      let assistantMsgAdded = false

      function processLine(line) {
        const trimmed = line.trim()
        if (!trimmed) return
        let chunk
        try { chunk = JSON.parse(trimmed) } catch { return }
        const { type, text } = chunk
        if (type === 'content') {
          onContentChunk(text)
        } else if (type === 'terminal') {
          if (!assistantMsgAdded) {
            setMessages(prev => [...prev, { role: 'assistant', text: '' }])
            assistantMsgAdded = true
          }
          terminalReply += text
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = { role: 'assistant', text: terminalReply }
            return next
          })
        } else if (type === 'status') {
          setMessages(prev => [...prev, { role: 'system', text }])
        } else if (type === 'question') {
          setMessages(prev => [...prev, { role: 'system', text }])
          terminalReply += text
        } else if (type === 'error') {
          setMessages(prev => [...prev, { role: 'system', text: `错误：${text}` }])
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) processLine(line)
      }
      for (const line of buffer.split('\n')) processLine(line)

      if (terminalReply) {
        setHistory(prev => [
          ...prev,
          { role: 'user', content: text },
          { role: 'assistant', content: terminalReply },
        ])
      }
      onDone()
    } catch (e) {
      const msg = e.message || '生成失败'
      onReject(msg)
      setMessages(prev => [...prev, { role: 'system', text: `错误：${msg}` }])
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="plan-terminal">
      <div className="plan-terminal-header">
        <span>计划终端</span>
        <button
          type="button"
          className="plan-bg-btn"
          onClick={() => { setShowProfile(v => !v); setEditing(false) }}
        >
          背景信息
        </button>
      </div>

      {showProfile && (
        editing ? (
          <div className="plan-profile-panel plan-profile-panel--editing">
            <textarea
              className="plan-profile-edit-area"
              value={editText}
              onChange={e => setEditText(e.target.value)}
              rows={4}
              autoFocus
            />
            <div className="plan-profile-actions">
              <button
                type="button"
                className="plan-profile-btn"
                onClick={handleSave}
                disabled={saving || !editText.trim()}
              >
                {saving ? '分析中...' : '保存'}
              </button>
              <button
                type="button"
                className="plan-profile-btn plan-profile-btn--cancel"
                onClick={() => setEditing(false)}
                disabled={saving}
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <div className="plan-profile-panel">
            <span>{userProfile?.background_text || '暂无背景信息'}</span>
            <button type="button" className="plan-profile-edit-btn" onClick={handleEditOpen}>
              编辑
            </button>
          </div>
        )
      )}

      <div className="plan-terminal-input-row">
        <span className="plan-terminal-prompt">›</span>
        <input
          className="plan-terminal-input"
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={planStatus === 'generating' ? '生成中...' : '输入指令...'}
          disabled={planStatus === 'generating'}
          autoComplete="off"
          spellCheck={false}
        />
      </div>
      <div className="plan-terminal-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`plan-msg-${msg.role}`}>{msg.text}</div>
        ))}
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}

export default PlanTerminalChat
