function DocumentViewer({ documentAreaRef, docContentRef, loading, error, docLoaded }) {
  return (
    <section className="document-area" ref={documentAreaRef}>
      {loading && <p className="doc-placeholder">正在解析文档...</p>}
      {error && <p className="doc-error">{error}</p>}
      {!loading && !docLoaded && !error && (
        <div className="welcome">
          <div className="welcome-icon">📖</div>
          <p className="welcome-text">上传一份 docx 文档开始整理知识点</p>
          <p className="welcome-hint">单击高亮词语查看简介，双击深入讲解</p>
        </div>
      )}
      <div
        ref={docContentRef}
        className="document-content"
        style={{ display: docLoaded ? 'block' : 'none' }}
      />
    </section>
  )
}

export default DocumentViewer
