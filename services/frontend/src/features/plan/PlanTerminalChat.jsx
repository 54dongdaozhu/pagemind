import { useRef, useState } from 'react'
import { deleteDocGenTask, getWordDownloadUrl, resumeDocGen, startDocGen, streamDocGen } from '../../api/docGen'
import { analyzeProfile } from '../../api/profile'
import HumanReviewModal from '../doc-gen/HumanReviewModal'

const AGENT_LABELS = {
  researcher: '研究员',
  editor: '编辑',
  writer: '写作',
  reviewer: '审阅',
  reviser: '修订',
  publisher: '发布',
}

const READY_MESSAGE = '已加载用户画像，生成模块准备就绪。'

function PlanTerminalChat({ userProfile, onProfileSave, userId, planStatus, onGenerate, onHtmlReady, onDone, onReject, onReset }) {
  const [messages, setMessages] = useState([
    { role: 'system', text: READY_MESSAGE },
  ])
  const [input, setInput] = useState('')
  const [requirements, setRequirements] = useState('')
  const [showProfile, setShowProfile] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const [humanPayload, setHumanPayload] = useState(null)
  const stopStreamRef = useRef(null)
  const messagesEndRef = useRef(null)

  function addMsg(role, text) {
    setMessages(prev => [...prev, { role, text }])
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  function _startStream(tid) {
    stopStreamRef.current?.()
    const stop = streamDocGen(tid, {
      onProgress: (msg) => {
        const label = AGENT_LABELS[msg.agent] ? `[${AGENT_LABELS[msg.agent]}] ` : ''
        addMsg('system', `${label}${msg.message}`)
      },
      onHumanInterrupt: (payload) => {
        setHumanPayload(payload)
        addMsg('system', '等待人工审核...')
      },
      onComplete: (msg) => {
        const wordUrl = msg.word_url ? getWordDownloadUrl(tid) : null
        onHtmlReady(msg.html || '', wordUrl)
        addMsg('assistant', '文档已生成完成！')
        onDone()
      },
      onError: (err) => {
        onReject(err.message)
        addMsg('system', `错误：${err.message}`)
      },
    })
    stopStreamRef.current = stop
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || planStatus === 'generating') return
    addMsg('user', text)
    setInput('')
    const requestText = requirements.trim()
    setRequirements('')
    onGenerate()

    try {
      const { task_id } = await startDocGen(text, requestText, userId || 'anonymous', userProfile)
      setTaskId(task_id)
      _startStream(task_id)
    } catch (e) {
      const msg = e.message || '启动失败'
      onReject(msg)
      addMsg('system', `错误：${msg}`)
    }
  }

  async function handleHumanDecide(decision, feedback) {
    setHumanPayload(null)
    addMsg('system', decision === 'publish' ? '已批准，正在发布...' : '已要求修订，继续优化...')
    try {
      await resumeDocGen(taskId, decision, feedback)
      _startStream(taskId)
    } catch (e) {
      onReject(e.message)
      addMsg('system', `Resume 失败：${e.message}`)
    }
  }

  function handleReset() {
    stopStreamRef.current?.()
    if (taskId) deleteDocGenTask(taskId).catch(() => {})
    setTaskId(null)
    setHumanPayload(null)
    setMessages([{ role: 'system', text: READY_MESSAGE }])
    onReset()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

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
      addMsg('system', `保存失败：${e.message || '请稍后重试'}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="plan-terminal">
      <div className="plan-terminal-header">
        <span>计划模式</span>
        <div className="plan-terminal-header-actions">
          {(planStatus === 'ready' || planStatus === 'error') && (
            <button type="button" className="plan-bg-btn" onClick={handleReset}>
              重新生成
            </button>
          )}
          <button
            type="button"
            className="plan-bg-btn"
            onClick={() => { setShowProfile(v => !v); setEditing(false) }}
          >
            背景信息
          </button>
        </div>
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

      <div className="plan-terminal-compose">
        <div className="plan-terminal-input-row">
          <span className="plan-terminal-prompt">›</span>
          <input
            className="plan-terminal-input"
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={planStatus === 'generating' ? '生成中...' : '输入主题，如：Python 异步编程'}
            disabled={planStatus === 'generating'}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <textarea
          className="plan-terminal-requirements"
          value={requirements}
          onChange={e => setRequirements(e.target.value)}
          placeholder="要求（可选），如：面向初学者，重点讲实践应用"
          rows={3}
          disabled={planStatus === 'generating'}
        />
        <button
          type="button"
          className="plan-terminal-submit"
          onClick={handleSend}
          disabled={planStatus === 'generating' || !input.trim()}
        >
          开始生成
        </button>
      </div>

      <div className="plan-terminal-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`plan-msg-${msg.role}`}>{msg.text}</div>
        ))}
        {planStatus === 'generating' && (
          <div className="plan-msg-system">
            <span className="doc-gen-spinner" style={{ marginRight: 6 }} />
            处理中...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {humanPayload && (
        <HumanReviewModal payload={humanPayload} onDecide={handleHumanDecide} />
      )}
    </div>
  )
}

export default PlanTerminalChat
