import { useMemo, useState } from 'react'

function TocSidebar({
  tocOpen,
  documents,
  activeDocId,
  docListOpen,
  tocSectionOpen,
  tocItems,
  activeTocId,
  docLoaded,
  onToggleDocList,
  onToggleTocSection,
  onSelectDocument,
  onSelectHeading,
}) {
  const tocSignature = useMemo(() => tocItems.map(item => item.id).join('|'), [tocItems])
  const [collapsedState, setCollapsedState] = useState(() => ({
    signature: '',
    ids: new Set(),
  }))
  const collapsedIds = useMemo(() => {
    return collapsedState.signature === tocSignature ? collapsedState.ids : new Set()
  }, [collapsedState, tocSignature])

  const decoratedItems = useMemo(() => {
    const collapsedAncestors = []

    return tocItems.map((item, index) => {
      while (
        collapsedAncestors.length > 0
        && collapsedAncestors[collapsedAncestors.length - 1].level >= item.level
      ) {
        collapsedAncestors.pop()
      }

      const hidden = collapsedAncestors.length > 0
      const hasChildren = tocItems[index + 1]?.level > item.level
      const collapsed = collapsedIds.has(item.id)

      if (collapsed && hasChildren) {
        collapsedAncestors.push(item)
      }

      return {
        ...item,
        hidden,
        hasChildren,
        collapsed,
      }
    })
  }, [collapsedIds, tocItems])

  const toggleItem = (event, id) => {
    event.stopPropagation()
    setCollapsedState(prev => {
      const next = prev.signature === tocSignature ? new Set(prev.ids) : new Set()
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return {
        signature: tocSignature,
        ids: next,
      }
    })
  }

  return (
    <aside className="toc-sidebar">
      {tocOpen && (
        <>
          <section className="toc-section">
            <button
              className="toc-section-toggle"
              type="button"
              onClick={onToggleDocList}
              aria-expanded={docListOpen}
            >
              <span className="toc-section-arrow" />
              <span>文档</span>
            </button>
            {docListOpen && (
              <nav className="doc-list-nav">
                {documents.length === 0 ? (
                  <div className="toc-empty">上传文档后显示列表</div>
                ) : (
                  documents.map(doc => (
                    <button
                      key={doc.id}
                      className={`doc-list-item${activeDocId === doc.id ? ' doc-list-active' : ''}`}
                      type="button"
                      onClick={() => onSelectDocument(doc.id)}
                      title={doc.name}
                    >
                      <span className="doc-list-icon">📄</span>
                      <span className="doc-list-name">{doc.name}</span>
                    </button>
                  ))
                )}
              </nav>
            )}
          </section>

          <section className="toc-section">
            <button
              className="toc-section-toggle"
              type="button"
              onClick={onToggleTocSection}
              aria-expanded={tocSectionOpen}
            >
              <span className="toc-section-arrow" />
              <span>文档目录</span>
            </button>
            {tocSectionOpen && (
              <nav className="toc-nav">
                {tocItems.length === 0 ? (
                  <div className="toc-empty">
                    {docLoaded ? '此文档无标题结构' : '上传文档后\n自动生成目录'}
                  </div>
                ) : (
                  decoratedItems.map(item => item.hidden ? null : (
                    <div
                      key={item.id}
                      className={`toc-item toc-level-${item.level}${activeTocId === item.id ? ' toc-active' : ''}${item.hasChildren ? ' toc-has-children' : ''}`}
                      onClick={() => onSelectHeading(item.id)}
                      title={item.text}
                    >
                      <button
                        className="toc-collapse-btn"
                        type="button"
                        onClick={(event) => toggleItem(event, item.id)}
                        title={item.collapsed ? '展开小节' : '收起小节'}
                        aria-label={item.collapsed ? '展开小节' : '收起小节'}
                        aria-expanded={!item.collapsed}
                        disabled={!item.hasChildren}
                      >
                        {item.hasChildren && <span className="toc-collapse-icon" />}
                      </button>
                      <span className="toc-item-text">{item.text}</span>
                    </div>
                  ))
                )}
              </nav>
            )}
          </section>
        </>
      )}
    </aside>
  )
}

export default TocSidebar
