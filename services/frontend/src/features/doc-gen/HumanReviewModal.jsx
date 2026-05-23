import { useRef, useState } from 'react'

function HumanReviewModal({ payload, onDecide }) {
  const [feedback, setFeedback] = useState('')
  const [tab, setTab] = useState('preview')
  const previewRef = useRef(null)

  const handlePublish = () => onDecide('publish', '')
  const handleRevise = () => {
    if (feedback.trim()) onDecide('revise', feedback.trim())
  }

  return (
    <div className="doc-gen-modal-overlay">
      <div className="doc-gen-modal">
        <div className="doc-gen-modal-header">
          <h3>人工审核</h3>
          <div className="doc-gen-modal-tabs">
            <button
              type="button"
              className={`doc-gen-modal-tab${tab === 'preview' ? ' active' : ''}`}
              onClick={() => setTab('preview')}
            >
              预览草稿
            </button>
            <button
              type="button"
              className={`doc-gen-modal-tab${tab === 'feedback' ? ' active' : ''}`}
              onClick={() => setTab('feedback')}
            >
              修改意见
            </button>
          </div>
        </div>

        <div className="doc-gen-modal-body">
          {tab === 'preview' ? (
            <div
              ref={previewRef}
              className="doc-gen-modal-preview"
              dangerouslySetInnerHTML={{ __html: payload?.draft_html || '' }}
            />
          ) : (
            <textarea
              className="doc-gen-modal-feedback"
              placeholder="描述需要修改的内容（可选），点击「要求修订」提交..."
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
              rows={8}
            />
          )}
        </div>

        <div className="doc-gen-modal-footer">
          <button
            type="button"
            className="doc-gen-btn-revise"
            onClick={handleRevise}
            disabled={tab === 'feedback' && !feedback.trim()}
          >
            要求修订
          </button>
          <button
            type="button"
            className="doc-gen-btn-publish"
            onClick={handlePublish}
          >
            批准发布
          </button>
        </div>
      </div>
    </div>
  )
}

export default HumanReviewModal
