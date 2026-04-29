import { useState, useRef } from 'react'
import mammoth from 'mammoth'
import './App.css'

const API_BASE = 'http://localhost:8000'

function hashString(str) {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash |= 0
  }
  return Math.abs(hash).toString(36)
}

function splitIntoChunks(html) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const blocks = []
  const elements = doc.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, td')
  elements.forEach(el => {
    const text = el.textContent.trim()
    if (text.length > 0) {
      blocks.push(text)
    }
  })
  const chunks = []
  let buffer = ''
  for (const block of blocks) {
    if (buffer.length + block.length > 800 && buffer.length > 0) {
      chunks.push(buffer)
      buffer = block
    } else {
      buffer = buffer ? buffer + '\n' + block : block
    }
  }
  if (buffer.length > 0) {
    chunks.push(buffer)
  }
  return chunks
}

function App() {
  const [docHtml, setDocHtml] = useState('')
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extracting, setExtracting] = useState(false)
  const extractingRef = useRef(false)

  const handleFileUpload = async (event) => {
    const file = event.target.files[0]
    if (!file) return
    if (!file.name.endsWith('.docx')) {
      setError('请上传 .docx 格式的文件')
      return
    }
    setError('')
    setLoading(true)
    setFileName(file.name)
    setKnowledgePoints([])
    setExtractProgress({ done: 0, total: 0 })

    try {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      setDocHtml(result.value)
      if (result.messages.length > 0) {
        console.log('解析警告:', result.messages)
      }
      await extractAllChunks(result.value)
    } catch (err) {
      setError('文档解析失败：' + err.message)
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const extractAllChunks = async (html) => {
    if (extractingRef.current) return
    extractingRef.current = true
    setExtracting(true)
    const chunks = splitIntoChunks(html)
    setExtractProgress({ done: 0, total: chunks.length })
    const allKPs = []

    for (let i = 0; i < chunks.length; i++) {
      const text = chunks[i]
      const chunkId = hashString(text)
      try {
        const response = await fetch(`${API_BASE}/api/extract-knowledge`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, chunk_id: chunkId })
        })
        if (response.ok) {
          const data = await response.json()
          const kpsWithMeta = data.knowledge_points.map(kp => ({
            ...kp,
            chunkIndex: i
          }))
          allKPs.push(...kpsWithMeta)
          setKnowledgePoints([...allKPs])
        } else {
          console.error(`块 ${i} 提取失败:`, response.status)
        }
      } catch (err) {
        console.error(`块 ${i} 提取出错:`, err)
      }
      setExtractProgress({ done: i + 1, total: chunks.length })
    }
    setExtracting(false)
    extractingRef.current = false
  }

  const uniqueKPs = []
  const seen = new Set()
  for (const kp of knowledgePoints) {
    if (!seen.has(kp.text)) {
      seen.add(kp.text)
      uniqueKPs.push(kp)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>AI 学习助手</h1>
        <div className="upload-area">
          <label htmlFor="file-upload" className="upload-button">
            {fileName ? `📄 ${fileName}` : '📁 上传 docx 文档'}
          </label>
          <input
            id="file-upload"
            type="file"
            accept=".docx"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />
        </div>
      </header>

      <main className="app-main">
        <section className="document-area">
          {loading && <p className="placeholder">正在解析文档...</p>}
          {error && <p className="error">{error}</p>}
          {!loading && !docHtml && !error && (
            <p className="placeholder">请上传一份 docx 文档开始学习</p>
          )}
          {docHtml && (
            <div
              className="document-content"
              dangerouslySetInnerHTML={{ __html: docHtml }}
            />
          )}
        </section>

        <aside className="chat-area">
          <h2>
            知识点
            {extracting && (
              <span className="progress">
                （提取中 {extractProgress.done}/{extractProgress.total}）
              </span>
            )}
            {!extracting && uniqueKPs.length > 0 && (
              <span className="progress">（共 {uniqueKPs.length} 个）</span>
            )}
          </h2>

          <div className="kp-list">
            {!docHtml && (
              <p className="placeholder">上传文档后将自动提取知识点</p>
            )}
            {docHtml && uniqueKPs.length === 0 && !extracting && (
              <p className="placeholder">暂无提取到的知识点</p>
            )}
            {uniqueKPs.map((kp, i) => (
              <div key={i} className={`kp-card kp-${kp.type}`}>
                <div className="kp-header">
                  <span className="kp-type-badge">
                    {kp.type === 'term' ? '术语' : '公式'}
                  </span>
                  <span className="kp-text">{kp.text}</span>
                </div>
                <div className="kp-explanation">{kp.explanation}</div>
              </div>
            ))}
          </div>
        </aside>
      </main>
    </div>
  )
}

export default App