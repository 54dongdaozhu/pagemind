function TocSidebar({ tocOpen, tocItems, activeTocId, docLoaded, onSelectHeading }) {
  return (
    <aside className="toc-sidebar">
      {tocOpen && (
        <>
          <div className="toc-section-title">文档目录</div>
          <nav className="toc-nav">
            {tocItems.length === 0 ? (
              <div className="toc-empty">
                {docLoaded ? '此文档无标题结构' : '上传文档后\n自动生成目录'}
              </div>
            ) : (
              tocItems.map(item => (
                <div
                  key={item.id}
                  className={`toc-item toc-level-${item.level}${activeTocId === item.id ? ' toc-active' : ''}`}
                  onClick={() => onSelectHeading(item.id)}
                  title={item.text}
                >
                  {item.text}
                </div>
              ))
            )}
          </nav>
        </>
      )}
    </aside>
  )
}

export default TocSidebar
