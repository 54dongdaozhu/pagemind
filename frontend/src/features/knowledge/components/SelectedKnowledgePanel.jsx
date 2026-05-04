function SelectedKnowledgePanel({
  selectedKP,
  showDeep,
  status,
  onClose,
  onStartDeepExplain,
  onToggleKnown,
}) {
  if (!selectedKP) return null

  return (
    <div className="selected-kp-panel">
      <div className="selected-kp-header">
        <span className={`kp-type-badge kp-type-badge-${selectedKP.type}`}>
          {selectedKP.type === 'term' ? '术语' : '公式'}
        </span>
        <h3 className="selected-kp-title">{selectedKP.text}</h3>
        <button className="close-btn" onClick={onClose} title="关闭">×</button>
      </div>
      <div className="selected-kp-content">{selectedKP.explanation}</div>
      <div className="kp-actions">
        {!showDeep && (
          <button className="deep-btn" onClick={() => onStartDeepExplain(selectedKP)}>
            深入讲解
          </button>
        )}
        <button
          className={`known-btn${status === 'known' ? ' is-known' : ''}`}
          onClick={() => onToggleKnown(selectedKP)}
        >
          {status === 'known' ? '✓ 已掌握' : '标记已掌握'}
        </button>
      </div>
    </div>
  )
}

export default SelectedKnowledgePanel
