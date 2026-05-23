import { useEffect, useReducer, useRef, useState } from 'react'
import { analyzeProfile } from '../../api/profile'
import PlanTerminalChat from './PlanTerminalChat'

// ── 计划内容状态机 ────────────────────────────────────────────────────────────

const PLAN_INIT = { status: 'idle', content: '', isHtml: false, wordUrl: '', error: '' }

function planReducer(state, action) {
  switch (action.type) {
    case 'GENERATE':     return { status: 'generating', content: '', isHtml: false, wordUrl: '', error: '' }
    case 'CHUNK':        return { ...state, content: state.content + action.payload }
    case 'RESOLVE':      return { ...state, status: 'ready', error: '' }
    case 'RESOLVE_HTML': return { status: 'ready', content: action.payload.html, isHtml: true, wordUrl: action.payload.wordUrl || '', error: '' }
    case 'REJECT':       return { ...state, status: 'error', error: action.payload }
    case 'RESET':        return PLAN_INIT
    default:             return state
  }
}

// ── 左侧内容区 ────────────────────────────────────────────────────────────────

function PlanContentArea({ plan, onReset }) {
  const { status, content, isHtml, wordUrl, error } = plan
  const htmlRef = useRef(null)

  useEffect(() => {
    if (isHtml && htmlRef.current) {
      htmlRef.current.innerHTML = content || ''
    }
  }, [isHtml, content])

  return (
    <div className="plan-content-area">
      {wordUrl && (
        <div className="doc-gen-download-bar">
          <a href={wordUrl} download className="doc-gen-download-btn">下载 Word</a>
        </div>
      )}
      {status === 'idle' && (
        <p className="plan-content-hint">在右侧终端输入主题生成教学文档</p>
      )}
      {status === 'generating' && !content && (
        <p className="plan-content-hint">生成中...</p>
      )}
      {isHtml ? (
        <div ref={htmlRef} className="plan-content-text doc-gen-html-content" />
      ) : (
        (status === 'generating' || status === 'ready') && content && (
          <pre className="plan-content-pre">{content}</pre>
        )
      )}
      {status === 'error' && (
        <div className="plan-content-error">
          {content && <pre className="plan-content-pre">{content}</pre>}
          <span>{error}</span>
          <button type="button" onClick={onReset}>重试</button>
        </div>
      )}
    </div>
  )
}

// ── 分屏主界面 ────────────────────────────────────────────────────────────────

function PlanMain({ userProfile, onProfileSave, userId }) {
  const [plan, dispatch] = useReducer(planReducer, PLAN_INIT)

  return (
    <div className="plan-page-main">
      <PlanContentArea plan={plan} onReset={() => dispatch({ type: 'RESET' })} />
      <PlanTerminalChat
        userProfile={userProfile}
        onProfileSave={onProfileSave}
        userId={userId}
        planStatus={plan.status}
        onGenerate={() => dispatch({ type: 'GENERATE' })}
        onContentChunk={chunk => dispatch({ type: 'CHUNK', payload: chunk })}
        onHtmlReady={(html, wordUrl) => dispatch({ type: 'RESOLVE_HTML', payload: { html, wordUrl } })}
        onDone={() => dispatch({ type: 'RESOLVE' })}
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

function PlanPage({ userProfile, profileLoaded, onProfileSave, userId }) {
  if (!profileLoaded) return null
  if (!userProfile)   return <PlanOnboarding onProfileSave={onProfileSave} />
  return <PlanMain userProfile={userProfile} onProfileSave={onProfileSave} userId={userId} />
}

export default PlanPage
