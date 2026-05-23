import { useEffect, useRef } from 'react'

function DocGenViewer({ htmlContent, wordUrl, status }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.innerHTML = htmlContent || ''
  }, [htmlContent])

  const showHint = !htmlContent && status !== 'done'

  return (
    <div className="doc-gen-viewer-wrap">
      {wordUrl && (
        <div className="doc-gen-download-bar">
          <a
            href={wordUrl}
            download
            className="doc-gen-download-btn"
          >
            下载 Word
          </a>
        </div>
      )}
      <div className="doc-gen-viewer-scroll">
        {showHint ? (
          <p className="doc-gen-viewer-hint">
            {status === 'running' ? '文档生成中，请稍候...' : '在右侧输入主题，开始生成教学文档'}
          </p>
        ) : (
          <div ref={containerRef} className="doc-gen-html-content" />
        )}
      </div>
    </div>
  )
}

export default DocGenViewer
