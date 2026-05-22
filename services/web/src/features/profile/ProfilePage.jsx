function formatDate(value) {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return ''
  }
}

function ProfilePage({
  user,
  documents = [],
  documentsLoading = false,
  documentsError = '',
  onOpenDocument,
  onLogout,
}) {
  return (
    <div className="profile-page">
      <div className="profile-layout">
        <div className="profile-card">
          <div className="profile-avatar-lg">
            {(user?.username || user?.email || 'U').slice(0, 1).toUpperCase()}
          </div>
          <div className="profile-username">{user?.username || '—'}</div>
          <div className="profile-email">{user?.email}</div>
          <button type="button" className="profile-logout-btn" onClick={onLogout}>
            退出登录
          </button>
        </div>

        <section className="profile-documents">
          <div className="profile-section-header">
            <h2>文档</h2>
            <span>{documents.length} 份</span>
          </div>

          {documentsLoading ? (
            <div className="profile-doc-empty">正在加载文档...</div>
          ) : documentsError ? (
            <div className="profile-doc-error">{documentsError}</div>
          ) : documents.length === 0 ? (
            <div className="profile-doc-empty">还没有保存过渲染快照的文档</div>
          ) : (
            <div className="profile-doc-list">
              {documents.map(doc => (
                <button
                  key={doc.id}
                  type="button"
                  className="profile-doc-item"
                  onClick={() => onOpenDocument?.(doc.id)}
                  disabled={!doc.renderAvailable}
                  title={doc.renderAvailable ? doc.name : '这份文档还没有可恢复的渲染快照'}
                >
                  <span className="profile-doc-icon">📄</span>
                  <span className="profile-doc-main">
                    <span className="profile-doc-name">{doc.name}</span>
                    <span className="profile-doc-meta">
                      {doc.renderAvailable ? '可打开' : '未保存快照'}
                      {doc.chunkCount ? ` · ${doc.chunkCount} 段` : ''}
                      {doc.updatedAt ? ` · ${formatDate(doc.updatedAt)}` : ''}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default ProfilePage
