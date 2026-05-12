import { ACCEPTED_DOCUMENT_TYPES } from '../document/documentParser'

function AppHeader({
  user,
  fileName,
  extracting,
  extractProgress,
  docLoaded,
  hideKnown,
  onHideKnownChange,
  onFileUpload,
  onLogout,
}) {
  return (
    <header className="main-header">
      <div className="header-file">
        {fileName
          ? <span className="file-name">📄 {fileName}</span>
          : <span className="header-hint">上传文档后开始整理知识点</span>
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
        <div className="user-menu" title={user?.email}>
          <span className="user-avatar">{(user?.username || user?.email || 'U').slice(0, 1).toUpperCase()}</span>
          <span className="user-name">{user?.username || user?.email}</span>
          <button type="button" className="logout-button" onClick={onLogout}>
            退出
          </button>
        </div>
        <input
          id="file-upload"
          type="file"
          accept={ACCEPTED_DOCUMENT_TYPES}
          onChange={onFileUpload}
          style={{ display: 'none' }}
        />
      </div>
    </header>
  )
}

export default AppHeader
