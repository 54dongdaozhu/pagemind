import { useEffect, useRef, useState } from 'react'

function PlanTerminalChat({ userProfile, planStatus, onGenerate, onResolve, onReject }) {
  const [messages, setMessages] = useState([
    { role: 'system', text: '已加载用户画像，计划生成模块准备就绪。' },
  ])
  const [input, setInput] = useState('')
  const [showProfile, setShowProfile] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    const text = input.trim()
    if (!text || planStatus === 'generating') return
    setMessages(prev => [...prev, { role: 'user', text }])
    setInput('')

    // 触发状态机：进入 generating 状态（接入后端后在此处发起请求）
    onGenerate()
    setTimeout(() => {
      try {
        onResolve(`（计划生成功能开发中，指令已记录：${text}）`)
        setMessages(prev => [...prev, {
          role: 'assistant',
          text: '计划生成功能开发中，敬请期待。',
        }])
      } catch (e) {
        onReject(e.message || '生成失败')
      }
    }, 800)
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
          onClick={() => setShowProfile(v => !v)}
        >
          背景信息
        </button>
      </div>
      {showProfile && (
        <div className="plan-profile-panel">
          {userProfile?.background_text || '暂无背景信息'}
        </div>
      )}
      <div className="plan-terminal-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`plan-msg-${msg.role}`}>{msg.text}</div>
        ))}
        <div ref={messagesEndRef} />
      </div>
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
    </div>
  )
}

export default PlanTerminalChat
