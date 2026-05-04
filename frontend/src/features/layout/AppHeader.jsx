function AppHeader({
  fileName,
  extracting,
  extractProgress,
  docLoaded,
  hideKnown,
  onHideKnownChange,
  onFileUpload,
}) {
  return (
    <header className="main-header">
      <div className="header-file">
        {fileName
          ? <span className="file-name">📄 {fileName}</span>
          : <span className="header-hint">上传文档后开始学习</span>
        }
        {extracting && (
          <span className="extract-badge">
            提取中 {extractProgress.done}/{extractProgress.total}
          </span>
        )}
      </div>
      <div className="header-controls">
        {docLoaded && (
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={hideKnown}
              onChange={e => onHideKnownChange(e.target.checked)}
            />
            <span>隐藏已掌握</span>
          </label>
        )}
        <label htmlFor="file-upload" className="upload-button">
          上传文档
        </label>
        <input
          id="file-upload"
          type="file"
          accept=".docx"
          onChange={onFileUpload}
          style={{ display: 'none' }}
        />
      </div>
    </header>
  )
}

export default AppHeader
