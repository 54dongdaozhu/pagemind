import { useState } from 'react'

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
  generatedDocuments = [],
  generatedDocumentsLoading = false,
  generatedDocumentsError = '',
  generatedDocumentPreview = null,
  generatedDocumentPreviewLoading = false,
  generatedDocumentPreviewError = '',
  onOpenDocument,
  onOpenGeneratedDocument,
  onLogout,
}) {
  const [section, setSection] = useState('documents')

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
            <div className="profile-section-tabs">
              <button
                type="button"
                className={`profile-section-tab${section === 'documents' ? ' active' : ''}`}
                onClick={() => setSection('documents')}
              >
                文档
              </button>
              <button
                type="button"
                className={`profile-section-tab${section === 'generated' ? ' active' : ''}`}
                onClick={() => setSection('generated')}
              >
                生成文档
              </button>
            </div>
            <span>{section === 'documents' ? documents.length : generatedDocuments.length} 份</span>
          </div>

          {section === 'documents' ? (
            documentsLoading ? (
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
            )
          ) : (
            generatedDocumentsLoading ? (
              <div className="profile-doc-empty">正在加载生成文档...</div>
            ) : generatedDocumentsError ? (
              <div className="profile-doc-error">{generatedDocumentsError}</div>
            ) : generatedDocuments.length === 0 ? (
              <div className="profile-doc-empty">还没有生成过文档</div>
            ) : (
              <div className="profile-generated-layout">
                <div className="profile-doc-list profile-generated-list">
                  {generatedDocuments.map(doc => (
                    <button
                      key={doc.id}
                      type="button"
                      className={`profile-doc-item${generatedDocumentPreview?.id === doc.id ? ' active' : ''}`}
                      onClick={() => onOpenGeneratedDocument?.(doc.id)}
                    >
                      <span className="profile-doc-icon">📝</span>
                      <span className="profile-doc-main">
                        <span className="profile-doc-name">{doc.name}</span>
                        <span className="profile-doc-meta">
                          HTML 快照
                          {doc.updatedAt ? ` · ${formatDate(doc.updatedAt)}` : ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
                <div className="profile-generated-preview">
                  {generatedDocumentPreviewLoading ? (
                    <div className="profile-doc-empty">正在打开生成文档...</div>
                  ) : generatedDocumentPreviewError ? (
                    <div className="profile-doc-error">{generatedDocumentPreviewError}</div>
                  ) : generatedDocumentPreview?.html ? (
                    <iframe
                      title={generatedDocumentPreview.name}
                      className="profile-generated-frame"
                      srcDoc={generatedDocumentPreview.html}
                      sandbox=""
                    />
                  ) : (
                    <div className="profile-doc-empty">选择一份生成文档查看 HTML 快照</div>
                  )}
                </div>
              </div>
            )
          )}
        </section>
      </div>
    </div>
  )
}

export default ProfilePage
