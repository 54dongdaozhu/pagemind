function PlanActivityBar({ activeView, onViewChange }) {
  return (
    <div className="plan-activity-bar">
      <button
        type="button"
        className={`plan-activity-btn${activeView === 'content' ? ' active' : ''}`}
        title="生成内容"
        onClick={() => onViewChange('content')}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="20" height="20">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <line x1="3" y1="9" x2="21" y2="9"/>
          <line x1="9" y1="21" x2="9" y2="9"/>
        </svg>
      </button>
      <button
        type="button"
        className={`plan-activity-btn${activeView === 'skill-tree' ? ' active' : ''}`}
        title="技能树"
        onClick={() => onViewChange('skill-tree')}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="20" height="20">
          <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/>
        </svg>
      </button>
    </div>
  )
}

export default PlanActivityBar
