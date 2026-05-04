function DeepExplanationPanel({ showDeep, deepLoading, deepExplanation, onClose }) {
  if (!showDeep) return null

  return (
    <div className="deep-panel">
      <div className="deep-header">
        <span className="deep-title">
          详细讲解
          {deepLoading && <span className="thinking-dot">●</span>}
        </span>
        <button className="close-btn" onClick={onClose} title="关闭">×</button>
      </div>
      <div className="deep-content">
        {deepExplanation || (deepLoading && <span className="placeholder-inline">AI 正在思考...</span>)}
        {deepLoading && deepExplanation && <span className="cursor-blink">▋</span>}
      </div>
    </div>
  )
}

export default DeepExplanationPanel
