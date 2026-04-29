import { useState, useRef, useEffect } from 'react'
import mammoth from 'mammoth'
import './App.css'

const API_BASE = 'http://localhost:8000'

// ========== 工具函数 ==========

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

function highlightFirstMatch(container, keyword, kpId, kpType) {
  if (!keyword || !container) return false

  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        if (node.parentElement && node.parentElement.tagName === 'MARK') {
          return NodeFilter.FILTER_REJECT
        }
        return NodeFilter.FILTER_ACCEPT
      }
    }
  )

  let textNode
  while ((textNode = walker.nextNode())) {
    const text = textNode.nodeValue
    const idx = text.indexOf(keyword)
    if (idx !== -1) {
      const before = text.slice(0, idx)
      const after = text.slice(idx + keyword.length)

      const mark = document.createElement('mark')
      mark.className = `kp-highlight kp-highlight-${kpType}`
      mark.dataset.kpId = kpId
      mark.textContent = keyword

      const parent = textNode.parentNode
      if (before) {
        parent.insertBefore(document.createTextNode(before), textNode)
      }
      parent.insertBefore(mark, textNode)
      if (after) {
        parent.insertBefore(document.createTextNode(after), textNode)
      }
      parent.removeChild(textNode)
      return true
    }
  }
  return false
}

// 在文档中找到知识点所在的段落上下文
function findContextForKP(container, kpId) {
  if (!container) return ''
  const mark = container.querySelector(`mark[data-kp-id="${kpId}"]`)
  if (!mark) return ''
  // 向上找最近的块级祖先(p, li, h1-h6, td)
  let node = mark.parentElement
  const blockTags = ['P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TD', 'DIV']
  while (node && !blockTags.includes(node.tagName)) {
    node = node.parentElement
  }
  return node ? node.textContent.trim() : mark.textContent
}

// ========== React 组件 ==========

function App() {
  const [fileName, setFileName] = useState('')
  const [docLoaded, setDocLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [extractProgress, setExtractProgress] = useState({ done: 0, total: 0 })
  const [extracting, setExtracting] = useState(false)
  const [selectedKP, setSelectedKP] = useState(null)
  
  // 深度讲解相关
  const [deepExplanation, setDeepExplanation] = useState('')
  const [deepLoading, setDeepLoading] = useState(false)
  const [showDeep, setShowDeep] = useState(false)

  const extractingRef = useRef(false)
  const docContentRef = useRef(null)
  const highlightedIdsRef = useRef(new Set())
  const deepAbortRef = useRef(null)  // 用于中止请求

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
    setSelectedKP(null)
    setDocLoaded(false)
    setDeepExplanation('')
    setShowDeep(false)
    highlightedIdsRef.current = new Set()

    if (docContentRef.current) {
      docContentRef.current.innerHTML = ''
    }

    try {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })

      if (docContentRef.current) {
        docContentRef.current.innerHTML = result.value
      }
      setDocLoaded(true)

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
            chunkIndex: i,
            id: hashString(kp.text + i)
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
  const seenTexts = new Set()
  for (const kp of knowledgePoints) {
    if (!seenTexts.has(kp.text)) {
      seenTexts.add(kp.text)
      uniqueKPs.push(kp)
    }
  }

  // 增量高亮
  useEffect(() => {
    if (!docContentRef.current || !docLoaded) return

    for (const kp of uniqueKPs) {
      if (highlightedIdsRef.current.has(kp.id)) continue
      const success = highlightFirstMatch(docContentRef.current, kp.text, kp.id, kp.type)
      highlightedIdsRef.current.add(kp.id)
      if (!success) {
        console.log(`未能在文档中找到知识点: "${kp.text}"`)
      }
    }
  }, [uniqueKPs, docLoaded])

  // 文档点击/双击委托
  useEffect(() => {
    const container = docContentRef.current
    if (!container) return

    const selectMark = (mark) => {
      const kpId = mark.dataset.kpId
      const kp = uniqueKPs.find(k => k.id === kpId)
      if (kp) {
        setSelectedKP(kp)
        container.querySelectorAll('mark.active').forEach(el => {
          el.classList.remove('active')
        })
        mark.classList.add('active')
      }
      return kp
    }

    const handleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) {
        selectMark(target)
        // 单击不再额外做事(双击会单独处理)
      }
    }

    const handleDoubleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) {
        const kp = selectMark(target)
        if (kp) {
          startDeepExplain(kp)
        }
      }
    }

    container.addEventListener('click', handleClick)
    container.addEventListener('dblclick', handleDoubleClick)
    return () => {
      container.removeEventListener('click', handleClick)
      container.removeEventListener('dblclick', handleDoubleClick)
    }
  }, [uniqueKPs])

  // 开始深度讲解(流式)
  const startDeepExplain = async (kp) => {
    // 如果有正在进行的请求,先中止
    if (deepAbortRef.current) {
      deepAbortRef.current.abort()
    }

    setShowDeep(true)
    setDeepExplanation('')
    setDeepLoading(true)

    // 找上下文
    const context = findContextForKP(docContentRef.current, kp.id) || kp.text

    const controller = new AbortController()
    deepAbortRef.current = controller

    try {
      const response = await fetch(`${API_BASE}/api/explain-deep`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keyword: kp.text,
          kp_type: kp.type,
          context: context
        }),
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error(`请求失败: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        setDeepExplanation(prev => prev + chunk)
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setDeepExplanation(prev => prev + `\n\n[错误] ${err.message}`)
      }
    } finally {
      setDeepLoading(false)
      deepAbortRef.current = null
    }
  }

  const handleKPCardClick = (kp) => {
    setSelectedKP(kp)
    if (!docContentRef.current) return

    const mark = docContentRef.current.querySelector(`mark[data-kp-id="${kp.id}"]`)
    if (mark) {
      mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
      docContentRef.current.querySelectorAll('mark.active').forEach(el => {
        el.classList.remove('active')
      })
      mark.classList.add('active')
    }
  }

  const handleKPCardDblClick = (kp) => {
    setSelectedKP(kp)
    startDeepExplain(kp)
  }

  const closeDeep = () => {
    if (deepAbortRef.current) {
      deepAbortRef.current.abort()
    }
    setShowDeep(false)
    setDeepExplanation('')
    setDeepLoading(false)
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
          {!loading && !docLoaded && !error && (
            <p className="placeholder">请上传一份 docx 文档开始学习。提示：单击高亮看简介，双击看详细讲解。</p>
          )}
          <div
            ref={docContentRef}
            className="document-content"
            style={{ display: docLoaded ? 'block' : 'none' }}
          />
        </section>

        <aside className="chat-area">
          {/* 选中的知识点简介 */}
          {selectedKP && (
            <div className="selected-kp-panel">
              <div className="selected-kp-header">
                <span className={`kp-type-badge kp-type-badge-${selectedKP.type}`}>
                  {selectedKP.type === 'term' ? '术语' : '公式'}
                </span>
                <h3 className="selected-kp-title">{selectedKP.text}</h3>
                <button
                  className="close-btn"
                  onClick={() => setSelectedKP(null)}
                  title="关闭"
                >
                  ×
                </button>
              </div>
              <div className="selected-kp-content">
                {selectedKP.explanation}
              </div>
              {!showDeep && (
                <button
                  className="deep-btn"
                  onClick={() => startDeepExplain(selectedKP)}
                >
                  📚 深入讲解
                </button>
              )}
            </div>
          )}

          {/* 深度讲解面板 */}
          {showDeep && (
            <div className="deep-panel">
              <div className="deep-header">
                <span className="deep-title">
                  📚 详细讲解
                  {deepLoading && <span className="thinking-dot">●</span>}
                </span>
                <button
                  className="close-btn"
                  onClick={closeDeep}
                  title="关闭"
                >
                  ×
                </button>
              </div>
              <div className="deep-content">
                {deepExplanation || (deepLoading && <span className="placeholder-inline">AI 正在思考...</span>)}
                {deepLoading && deepExplanation && <span className="cursor-blink">▋</span>}
              </div>
            </div>
          )}

          <h2>
            知识点列表
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
            {!docLoaded && (
              <p className="placeholder">上传文档后将自动提取知识点</p>
            )}
            {docLoaded && uniqueKPs.length === 0 && !extracting && (
              <p className="placeholder">暂无提取到的知识点</p>
            )}
            {uniqueKPs.map((kp) => (
              <div
                key={kp.id}
                className={`kp-card kp-${kp.type} ${selectedKP?.id === kp.id ? 'selected' : ''}`}
                onClick={() => handleKPCardClick(kp)}
                onDoubleClick={() => handleKPCardDblClick(kp)}
                title="单击定位 | 双击深入讲解"
              >
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
