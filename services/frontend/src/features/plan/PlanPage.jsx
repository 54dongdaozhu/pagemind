import { useRef, useReducer, useState } from 'react'
import { saveGeneratedDocumentSnapshot } from '../../api/generatedDocuments'
import { analyzeProfile } from '../../api/profile'
import PlanActivityBar from './PlanActivityBar'
import PlanTerminalChat from './PlanTerminalChat'
import SkillTreePanel from './SkillTreePanel'

// ── 计划内容状态机 ────────────────────────────────────────────────────────────

const PLAN_INIT = { status: 'idle', content: '', isHtml: false, wordUrl: '', error: '', saved: false, saving: false, saveError: '' }

function planReducer(state, action) {
  switch (action.type) {
    case 'GENERATE':     return { status: 'generating', content: '', isHtml: false, wordUrl: '', error: '', saved: false, saving: false, saveError: '' }
    case 'CHUNK':        return { ...state, content: state.content + action.payload }
    case 'RESOLVE':      return { ...state, status: 'ready', error: '' }
    case 'RESOLVE_HTML': return { ...state, status: 'ready', content: action.payload.html, isHtml: true, wordUrl: action.payload.wordUrl || '', error: '', saved: false, saveError: '' }
    case 'REJECT':       return { ...state, status: 'error', error: action.payload }
    case 'SAVE_START':   return { ...state, saving: true, saveError: '' }
    case 'SAVE_DONE':    return { ...state, saving: false, saved: true, saveError: '' }
    case 'SAVE_REJECT':  return { ...state, saving: false, saved: false, saveError: action.payload }
    case 'RESET':        return PLAN_INIT
    default:             return state
  }
}

// ── 左侧内容区 ────────────────────────────────────────────────────────────────

function buildPreviewDoc(html) {
  if (/<html[\s>]/i.test(html)) return html
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {
        box-sizing: border-box;
        color: #222;
        font-family: "Segoe UI", system-ui, sans-serif;
        line-height: 1.7;
        margin: 0;
        padding: 24px;
      }
      h1 { font-size: 1.9rem; border-bottom: 2px solid #e5e7eb; padding-bottom: .4rem; margin-bottom: 1.2rem; }
      h2 { font-size: 1.45rem; margin-top: 2rem; color: #1d4ed8; }
      h3 { font-size: 1.15rem; margin-top: 1.4rem; }
      p { margin: .7rem 0; }
      code { background: #f3f4f6; padding: .15em .4em; border-radius: 4px; font-size: .88em; }
      pre { background: #1e293b; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow-x: auto; }
      pre code { background: none; padding: 0; color: inherit; }
      blockquote { border-left: 4px solid #3b82f6; padding-left: 1rem; color: #555; margin: 1rem 0; }
      table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
      th, td { border: 1px solid #d1d5db; padding: .55rem .85rem; }
      th { background: #f9fafb; font-weight: 600; }
      ul, ol { padding-left: 1.5rem; margin: .7rem 0; }
    </style>
  </head>
  <body>${html || ''}</body>
</html>`
}

function PlanContentArea({ plan, onReset, onSaveSnapshot }) {
  const { status, content, isHtml, wordUrl, error, saved, saving, saveError } = plan

  return (
    <div className="plan-content-area">
      {(wordUrl || isHtml) && (
        <div className="doc-gen-download-bar">
          {wordUrl && <a href={wordUrl} download className="doc-gen-download-btn">下载 Word</a>}
          {isHtml && (
            <button
              type="button"
              className="doc-gen-save-btn"
              onClick={onSaveSnapshot}
              disabled={saving || saved}
            >
              {saving ? '保存中...' : saved ? '已保存' : '保存到个人中心'}
            </button>
          )}
        </div>
      )}
      {saveError && <div className="plan-save-error">{saveError}</div>}
      {status === 'idle' && (
        <p className="plan-content-hint">在右侧终端输入主题生成技术学习材料</p>
      )}
      {status === 'generating' && !content && (
        <p className="plan-content-hint">生成中...</p>
      )}
      {isHtml ? (
        <iframe
          className="plan-content-frame"
          title="生成文档预览"
          srcDoc={buildPreviewDoc(content)}
          sandbox=""
        />
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
  const [generationMeta, setGenerationMeta] = useState({ taskId: '', topic: '', requirements: '' })
  const generationMetaRef = useRef(generationMeta)
  const [activeView, setActiveView] = useState('content')

  function updateGenerationMeta(meta) {
    generationMetaRef.current = meta
    setGenerationMeta(meta)
  }

  async function saveSnapshot(metaOverride = {}) {
    const html = metaOverride.html ?? plan.content
    if (!html) return
    const meta = { ...generationMetaRef.current, ...metaOverride }
    dispatch({ type: 'SAVE_START' })
    try {
      await saveGeneratedDocumentSnapshot({
        sourceTaskId: meta.taskId,
        title: meta.topic,
        topic: meta.topic,
        requirements: meta.requirements,
        html,
      })
      dispatch({ type: 'SAVE_DONE' })
    } catch (err) {
      dispatch({ type: 'SAVE_REJECT', payload: err.message || '保存失败' })
    }
  }

  return (
    <div className="plan-page-main">
      <PlanActivityBar activeView={activeView} onViewChange={setActiveView} />
      {activeView === 'skill-tree' ? (
        <SkillTreePanel />
      ) : (
        <PlanContentArea
          plan={plan}
          onReset={() => dispatch({ type: 'RESET' })}
          onSaveSnapshot={() => saveSnapshot()}
        />
      )}
      <PlanTerminalChat
        userProfile={userProfile}
        onProfileSave={onProfileSave}
        userId={userId}
        planStatus={plan.status}
        onGenerate={() => dispatch({ type: 'GENERATE' })}
        onGenerationMetaChange={updateGenerationMeta}
        onAutoSaveSnapshot={saveSnapshot}
        onContentChunk={chunk => dispatch({ type: 'CHUNK', payload: chunk })}
        onHtmlReady={(html, wordUrl) => dispatch({ type: 'RESOLVE_HTML', payload: { html, wordUrl } })}
        onDone={() => dispatch({ type: 'RESOLVE' })}
        onReject={err => dispatch({ type: 'REJECT', payload: err })}
        onReset={() => dispatch({ type: 'RESET' })}
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
