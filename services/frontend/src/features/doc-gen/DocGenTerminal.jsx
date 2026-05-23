import { useEffect, useRef, useState } from 'react'
import HumanReviewModal from './HumanReviewModal'

const AGENT_LABELS = {
  researcher: '研究员',
  editor: '编辑',
  writer: '写作',
  reviewer: '审阅',
  reviser: '修订',
  publisher: '发布',
  human: '人工',
}

function DocGenTerminal({ status, messages, humanPayload, onGenerate, onHumanDecide, onReset }) {
  const [topic, setTopic] = useState('')
  const [requirements, setRequirements] = useState('')
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (topic.trim()) onGenerate(topic.trim(), requirements.trim())
  }

  const isRunning = status === 'running'
  const isDone = status === 'done'
  const isWaiting = status === 'waiting_human'

  return (
    <div className="doc-gen-terminal">
      <div className="doc-gen-terminal-header">
        <span>文档生成</span>
        {(isDone || status === 'error') && (
          <button type="button" className="doc-gen-reset-btn" onClick={onReset}>
            重新生成
          </button>
        )}
      </div>

      {status === 'idle' && (
        <form className="doc-gen-form" onSubmit={handleSubmit}>
          <label className="doc-gen-label">主题</label>
          <input
            className="doc-gen-input"
            type="text"
            placeholder="如：Python 异步编程"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            required
          />
          <label className="doc-gen-label">要求（可选）</label>
          <textarea
            className="doc-gen-textarea"
            placeholder="如：面向初学者，重点讲解实践应用"
            value={requirements}
            onChange={e => setRequirements(e.target.value)}
            rows={3}
          />
          <button type="submit" className="doc-gen-start-btn" disabled={!topic.trim()}>
            开始生成
          </button>
        </form>
      )}

      {status !== 'idle' && (
        <div className="doc-gen-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`doc-gen-msg doc-gen-msg-${msg.type}`}>
              {msg.agent && AGENT_LABELS[msg.agent] ? (
                <span className="doc-gen-msg-agent">[{AGENT_LABELS[msg.agent]}]</span>
              ) : null}
              <span className="doc-gen-msg-text">{msg.text}</span>
            </div>
          ))}
          {isRunning && (
            <div className="doc-gen-msg doc-gen-msg-system">
              <span className="doc-gen-spinner" /> 处理中...
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      {isWaiting && humanPayload && (
        <HumanReviewModal payload={humanPayload} onDecide={onHumanDecide} />
      )}
    </div>
  )
}

export default DocGenTerminal
