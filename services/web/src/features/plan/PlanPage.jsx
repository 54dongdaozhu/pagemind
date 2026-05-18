import { useReducer, useState } from 'react'
import { analyzeProfile } from '../../api/profile'
import PlanTerminalChat from './PlanTerminalChat'

// ── 计划内容状态机 ────────────────────────────────────────────────────────────

const PLAN_INIT = { status: 'idle', content: '', error: '' }

function planReducer(state, action) {
  switch (action.type) {
    case 'GENERATE': return { status: 'generating', content: '',             error: '' }
    case 'RESOLVE':  return { status: 'ready',      content: action.payload, error: '' }
    case 'REJECT':   return { status: 'error',      content: state.content,  error: action.payload }
    case 'RESET':    return PLAN_INIT
    default:         return state
  }
}

// ── 左侧内容区 ────────────────────────────────────────────────────────────────

function PlanContentArea({ plan, onReset }) {
  const { status, content, error } = plan
  return (
    <div className="plan-content-area">
      {status === 'idle' && (
        <p className="plan-content-hint">在右侧终端输入指令生成学习计划</p>
      )}
      {status === 'generating' && (
        <p className="plan-content-hint">生成中...</p>
      )}
      {status === 'ready' && (
        <div className="plan-content-text">{content}</div>
      )}
      {status === 'error' && (
        <div className="plan-content-error">
          <span>{error}</span>
          <button type="button" onClick={onReset}>重试</button>
        </div>
      )}
    </div>
  )
}

// ── 分屏主界面 ────────────────────────────────────────────────────────────────

function PlanMain({ userProfile }) {
  const [plan, dispatch] = useReducer(planReducer, PLAN_INIT)

  return (
    <div className="plan-page-main">
      <PlanContentArea plan={plan} onReset={() => dispatch({ type: 'RESET' })} />
      <PlanTerminalChat
        userProfile={userProfile}
        planStatus={plan.status}
        onGenerate={() => dispatch({ type: 'GENERATE' })}
        onResolve={content => dispatch({ type: 'RESOLVE', payload: content })}
        onReject={err => dispatch({ type: 'REJECT', payload: err })}
      />
    </div>
  )
}

// ── 引导页 ────────────────────────────────────────────────────────────────────

function PlanOnboarding({ onProfileSave }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleConfirm() {
    if (!text.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      const profile = await analyzeProfile(text.trim())
      onProfileSave(profile)
    } catch (e) {
      setError(e.message || '提交失败，请重试')
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleConfirm()
    }
  }

  return (
    <div className="plan-onboarding-page">
      <div className="plan-dialog">
        <p className="plan-dialog-title"><strong>请输入背景信息</strong></p>
        <textarea
          className="plan-dialog-input"
          placeholder="我是为了从事ai应用开发而学习的"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
          rows={4}
        />
        {error && <p className="plan-dialog-error">{error}</p>}
        <button
          type="button"
          className="plan-dialog-confirm"
          onClick={handleConfirm}
          disabled={loading || !text.trim()}
        >
          {loading ? '分析中...' : '确认'}
        </button>
      </div>
    </div>
  )
}

// ── 入口 ──────────────────────────────────────────────────────────────────────

function PlanPage({ userProfile, profileLoaded, onProfileSave }) {
  if (!profileLoaded) return null
  if (!userProfile)   return <PlanOnboarding onProfileSave={onProfileSave} />
  return <PlanMain userProfile={userProfile} />
}

export default PlanPage
