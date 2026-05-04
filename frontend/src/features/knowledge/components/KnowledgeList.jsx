function KnowledgeList({
  docLoaded,
  extracting,
  knowledgePoints,
  selectedKP,
  getKpStatus,
  onCardClick,
  onCardDoubleClick,
}) {
  return (
    <div className="kp-list">
      {!docLoaded && <p className="placeholder">上传文档后将自动提取知识点</p>}
      {docLoaded && knowledgePoints.length === 0 && !extracting && (
        <p className="placeholder">暂无提取到的知识点</p>
      )}
      {knowledgePoints.map((kp) => {
        const status = getKpStatus(kp.text)
        return (
          <div
            key={kp.id}
            className={`kp-card kp-${kp.type} kp-card-${status}${selectedKP?.id === kp.id ? ' selected' : ''}`}
            onClick={() => onCardClick(kp)}
            onDoubleClick={() => onCardDoubleClick(kp)}
            title="单击定位 | 双击深入讲解"
          >
            <div className="kp-header">
              <span className="kp-type-badge">
                {kp.type === 'term' ? '术语' : '公式'}
              </span>
              <span className="kp-text">{kp.text}</span>
              {status === 'known' && <span className="status-icon" title="已掌握">✓</span>}
              {status === 'learning' && <span className="status-icon learning" title="学习中">●</span>}
            </div>
            <div className="kp-explanation">{kp.explanation}</div>
          </div>
        )
      })}
    </div>
  )
}

export default KnowledgeList
