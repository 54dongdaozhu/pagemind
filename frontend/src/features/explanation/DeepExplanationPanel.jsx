import { markdownToHtml } from '../../utils/markdown'

function injectCursor(html) {
  if (!html) return '<span class="cursor-blink">▋</span>'
  const lastClose = html.lastIndexOf('</')
  if (lastClose === -1) return html + '<span class="cursor-blink">▋</span>'
  return html.slice(0, lastClose) + '<span class="cursor-blink">▋</span>' + html.slice(lastClose)
}

function DeepExplanationPanel({ showDeep, deepLoading, deepExplanation, onClose }) {
  if (!showDeep) return null

  const html = markdownToHtml(deepExplanation)
  const rendered = deepLoading ? injectCursor(html) : html

  return (
    <div className="deep-panel">
      <div className="deep-header">
        <span className="deep-title">
          详细讲解
          {deepLoading && <span className="thinking-dot">●</span>}
        </span>
        <button className="close-btn" onClick={onClose} title="关闭">×</button>
      </div>
      <div className="deep-content">
        {deepExplanation || deepLoading ? (
          deepExplanation ? (
            <div
              className="chat-markdown"
              dangerouslySetInnerHTML={{ __html: rendered }}
            />
          ) : (
            <span className="placeholder-inline">AI 正在思考...</span>
          )
        ) : null}
      </div>
    </div>
  )
}

export default DeepExplanationPanel
