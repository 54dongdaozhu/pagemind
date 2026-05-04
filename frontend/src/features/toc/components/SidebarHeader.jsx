function SidebarHeader({ tocOpen, onToggle }) {
  return (
    <div className="sidebar-header">
      {tocOpen && <span className="app-logo">AI 学习助手</span>}
      <button
        className="toc-toggle-btn"
        onClick={onToggle}
        title={tocOpen ? '收起目录' : '展开目录'}
      >
        {tocOpen ? '◀' : '▶'}
      </button>
    </div>
  )
}

export default SidebarHeader
