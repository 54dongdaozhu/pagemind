import { useEffect, useRef, useState } from 'react'
import { generateSkillTree, getSkillTree, getSkillTreeStatus } from '../../api/skillTree'

const PRIORITY_LABEL = { high: '高优先', medium: '中优先', low: '低优先' }
const STATUS_LABEL = { gap: '待学', learning: '学习中', known: '已掌握' }

function SkillTreePanel() {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef(null)
  const activeRef = useRef(true)

  const stopPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => {
    activeRef.current = true
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      try {
        const data = await getSkillTree(controller.signal)
        if (!controller.signal.aborted) setSnapshot(data)
      } catch (e) {
        if (!controller.signal.aborted && e.name !== 'AbortError') setError(e.message || '加载失败')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    load()
    return () => {
      activeRef.current = false
      controller.abort()
      stopPoll()
    }
  }, [])

  const reloadSnapshot = async (signal) => {
    setError('')
    try {
      const data = await getSkillTree(signal)
      if (activeRef.current) setSnapshot(data)
    } catch (e) {
      if (activeRef.current && e.name !== 'AbortError') setError(e.message || '加载失败')
    }
  }

  const startPoll = (snapshotId) => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const status = await getSkillTreeStatus(snapshotId)
        if (status.status === 'ready') {
          stopPoll()
          if (activeRef.current) {
            setGenerating(false)
            await reloadSnapshot()
          }
        } else if (status.status === 'failed') {
          stopPoll()
          if (activeRef.current) {
            setGenerating(false)
            setError(`生成失败：${status.error_detail || '未知错误'}`)
          }
        }
      } catch {
        // keep polling
      }
    }, 3000)
  }

  const handleGenerate = async () => {
    if (generating) return
    setGenerating(true)
    setError('')
    try {
      const result = await generateSkillTree()
      startPoll(result.snapshot_id)
    } catch (e) {
      setGenerating(false)
      setError(e.message || '触发失败，请重试')
    }
  }

  const nodes = snapshot?.tree?.nodes || []
  const summary = snapshot?.tree?.summary || ''

  return (
    <div className="skill-tree-panel">
      <div className="skill-tree-header">
        <span className="skill-tree-title">技能树</span>
        <button
          type="button"
          className="skill-tree-generate-btn"
          onClick={handleGenerate}
          disabled={generating}
        >
          {generating ? '生成中...' : snapshot ? '重新生成' : '生成技能树'}
        </button>
      </div>

      {snapshot?.web_search_used && (
        <div className="skill-tree-web-badge">已联网验证</div>
      )}

      {error && <div className="skill-tree-error">{error}</div>}

      {loading && !snapshot && (
        <div className="skill-tree-loading">加载中...</div>
      )}

      {!loading && !snapshot && !generating && !error && (
        <div className="skill-tree-empty">
          <p>点击"生成技能树"，AI 将根据你的学习行为分析推荐技能</p>
        </div>
      )}

      {generating && !snapshot && (
        <div className="skill-tree-loading">AI 正在分析你的学习行为，约需 15-30 秒...</div>
      )}

      {summary && <p className="skill-tree-summary">{summary}</p>}

      {nodes.length > 0 && (
        <div className="skill-tree-nodes">
          {nodes.map((node) => (
            <div key={node.id} className={`skill-tree-card skill-tree-card-${node.status}`}>
              <div className="skill-tree-card-top">
                <span className="skill-tree-skill">{node.skill}</span>
                <div className="skill-tree-badges">
                  <span className={`skill-tree-priority skill-tree-priority-${node.priority}`}>
                    {PRIORITY_LABEL[node.priority] || node.priority}
                  </span>
                  <span className={`skill-tree-status-badge skill-tree-status-${node.status}`}>
                    {STATUS_LABEL[node.status] || node.status}
                  </span>
                  {node.web_validated && (
                    <span className="skill-tree-web-chip">联网验证</span>
                  )}
                </div>
              </div>
              {node.category && (
                <div className="skill-tree-category">{node.category}</div>
              )}
              {node.evidence?.length > 0 && (
                <ul className="skill-tree-evidence">
                  {node.evidence.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
              {node.web_snippet && (
                <div className="skill-tree-snippet">{node.web_snippet}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default SkillTreePanel
