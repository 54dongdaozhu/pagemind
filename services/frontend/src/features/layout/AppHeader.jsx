import { useEffect, useRef, useState } from 'react'
import { ACCEPTED_DOCUMENT_TYPES } from '../document/documentParser'

const MODES = [
  { key: 'plan',     label: '计划模式' },
  { key: 'normal',   label: '普通模式' },
  { key: 'docgen',   label: '文档生成' },
  { key: 'complete', label: '补全模式' },
]

function AppHeader({
  user,
  fileName,
  extracting,
  extractProgress,
  docLoaded,
  hideKnown,
  onHideKnownChange,
  onFileUpload,
  mode,
  onModeChange,
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

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
      <div className="mode-tabs">
        {MODES.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`mode-tab${mode === key ? ' active' : ''}`}
            onClick={() => onModeChange(key)}
          >
            {label}
          </button>
        ))}
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
        <div className="upload-dropdown" ref={menuRef}>
          <button
            type="button"
            className="upload-button"
            onClick={() => setMenuOpen(v => !v)}
          >
            上传
          </button>
          {menuOpen && (
            <div className="upload-menu">
              <button
                type="button"
                className="upload-menu-item"
                onClick={() => { setMenuOpen(false); fileInputRef.current?.click() }}
              >
                上传文件
              </button>
              <button
                type="button"
                className="upload-menu-item"
                onClick={() => { setMenuOpen(false); folderInputRef.current?.click() }}
              >
                上传文件夹
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          className="user-menu"
          title={user?.email}
          onClick={() => onModeChange('profile')}
        >
          <span className="user-avatar">{(user?.username || user?.email || 'U').slice(0, 1).toUpperCase()}</span>
          <span className="user-name">{user?.username || user?.email}</span>
        </button>
        <input
          ref={fileInputRef}
          id="file-upload"
          type="file"
          accept={ACCEPTED_DOCUMENT_TYPES}
          onChange={onFileUpload}
          style={{ display: 'none' }}
        />
        <input
          ref={folderInputRef}
          id="folder-upload"
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          onChange={onFileUpload}
          style={{ display: 'none' }}
        />
      </div>
    </header>
  )
}

export default AppHeader
