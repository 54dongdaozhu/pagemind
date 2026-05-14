function KnowledgeList({
  docLoaded,
  extracting,
  extractProgress,
  extractError,
  refinementStatus,
  knowledgePoints,
  selectedKP,
  getKpStatus,
  onCardClick,
  onCardDoubleClick,
}) {
  const showRefinementStatus = docLoaded && knowledgePoints.length > 0 && !extracting
  const refinementText = {
    queued: '文档级整理排队中',
    running: '文档级整理中',
    completed: '已完成文档级整理',
    degraded: '文档级整理已降级完成',
    failed: '文档级整理失败，当前为初步结果',
  }[refinementStatus]

  return (
    <div className="kp-list">
      {!docLoaded && <p className="placeholder">上传文档后将自动提取知识点</p>}
      {docLoaded && extractError && knowledgePoints.length === 0 && (
        <p className="placeholder">{extractError}</p>
      )}
      {docLoaded && extracting && knowledgePoints.length === 0 && !extractError && (
        <p className="placeholder">
          正在提取知识点
          {extractProgress.total > 0 ? `（${extractProgress.done}/${extractProgress.total}）` : ''}
        </p>
      )}
      {docLoaded && knowledgePoints.length === 0 && !extracting && !extractError && (
        <p className="placeholder">暂无提取到的知识点</p>
      )}
      {showRefinementStatus && refinementText && (
        <div className={`kp-refinement-status kp-refinement-${refinementStatus}`}>
          {refinementText}
        </div>
      )}
      {knowledgePoints.map((kp) => {
        const status = getKpStatus(kp.text)
        const isHigh = kp.importance === 'high'
        return (
          <div
            key={kp.id}
            className={[
              'kp-card',
              `kp-${kp.type}`,
              `kp-card-${status}`,
              selectedKP?.id === kp.id ? 'selected' : '',
              isHigh ? 'kp-high' : '',
            ].filter(Boolean).join(' ')}
            onClick={() => onCardClick(kp)}
            onDoubleClick={() => onCardDoubleClick(kp)}
            title="单击定位 | 双击深入讲解"
          >
            <div className="kp-header">
              <span className="kp-type-badge">
                {kp.type === 'term' ? '术语' : '公式'}
              </span>
              {isHigh && <span className="kp-importance-badge">★ 重点</span>}
              <span className="kp-text">{kp.text}</span>
              {status === 'known' && <span className="status-icon" title="已掌握">✓</span>}
              {status === 'learning' && <span className="status-icon learning" title="理解中">●</span>}
            </div>
            <div className="kp-explanation">{kp.explanation}</div>
          </div>
        )
      })}
    </div>
  )
}

export default KnowledgeList
