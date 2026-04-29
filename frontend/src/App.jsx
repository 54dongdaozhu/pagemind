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
    if (text.length > 0) blocks.push(text)
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
  if (buffer.length > 0) chunks.push(buffer)
  return chunks
}

function highlightFirstMatch(container, keyword, kpId, kpType, status) {
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
      mark.className = `kp-highlight kp-highlight-${kpType} kp-status-${status || 'unknown'}`
      mark.dataset.kpId = kpId
      mark.dataset.kpText = keyword
      mark.textContent = keyword
      const parent = textNode.parentNode
      if (before) parent.insertBefore(document.createTextNode(before), textNode)
      parent.insertBefore(mark, textNode)
      if (after) parent.insertBefore(document.createTextNode(after), textNode)
      parent.removeChild(textNode)
      return true
    }
  }
  return false
}

function findContextForKP(container, kpId) {
  if (!container) return ''
  const mark = container.querySelector(`mark[data-kp-id="${kpId}"]`)
  if (!mark) return ''
  let node = mark.parentElement
  const blockTags = ['P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TD', 'DIV']
  while (node && !blockTags.includes(node.tagName)) node = node.parentElement
  return node ? node.textContent.trim() : mark.textContent
}

function updateMarkStatusInDom(container, kpText, status) {
  if (!container) return
  const marks = container.querySelectorAll(`mark[data-kp-text="${CSS.escape(kpText)}"]`)
  marks.forEach(m => {
    m.classList.remove('kp-status-unknown', 'kp-status-learning', 'kp-status-known')
    m.classList.add(`kp-status-${status}`)
  })
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
  const [deepExplanation, setDeepExplanation] = useState('')
  const [deepLoading, setDeepLoading] = useState(false)
  const [showDeep, setShowDeep] = useState(false)
  const [kpStatusMap, setKpStatusMap] = useState({})
  const [hideKnown, setHideKnown] = useState(true)

  // 目录相关
  const [tocItems, setTocItems] = useState([])
  const [tocOpen, setTocOpen] = useState(true)
  const [activeTocId, setActiveTocId] = useState(null)

  const extractingRef = useRef(false)
  const docContentRef = useRef(null)
  const documentAreaRef = useRef(null)
  const highlightedIdsRef = useRef(new Set())
  const deepAbortRef = useRef(null)

  const getKpStatus = (kpText) => kpStatusMap[kpText] || 'unknown'

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
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()

    if (docContentRef.current) docContentRef.current.innerHTML = ''

    try {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      if (docContentRef.current) docContentRef.current.innerHTML = result.value
      setDocLoaded(true)
      await extractAllChunks(result.value)
    } catch (err) {
      setError('文档解析失败：' + err.message)
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

  // 拉取知识点状态
  useEffect(() => {
    if (uniqueKPs.length === 0) return
    const texts = uniqueKPs.map(kp => kp.text)
    fetch(`${API_BASE}/api/knowledge/status-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kp_texts: texts })
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        const map = {}
        for (const item of data.items) map[item.kp_text] = item.status
        setKpStatusMap(prev => ({ ...prev, ...map }))
      })
      .catch(err => console.error('拉取状态失败:', err))
  }, [uniqueKPs.length])

  // 增量高亮
  useEffect(() => {
    if (!docContentRef.current || !docLoaded) return
    for (const kp of uniqueKPs) {
      if (highlightedIdsRef.current.has(kp.id)) continue
      const status = getKpStatus(kp.text)
      highlightFirstMatch(docContentRef.current, kp.text, kp.id, kp.type, status)
      highlightedIdsRef.current.add(kp.id)
    }
  }, [uniqueKPs, docLoaded, kpStatusMap])

  // 同步 mark 状态 class
  useEffect(() => {
    if (!docContentRef.current) return
    for (const kpText in kpStatusMap) {
      updateMarkStatusInDom(docContentRef.current, kpText, kpStatusMap[kpText])
    }
  }, [kpStatusMap])

  // hideKnown 开关
  useEffect(() => {
    if (!docContentRef.current) return
    if (hideKnown) {
      docContentRef.current.classList.add('hide-known')
    } else {
      docContentRef.current.classList.remove('hide-known')
    }
  }, [hideKnown, docLoaded])

  // 文档点击/双击委托
  useEffect(() => {
    const container = docContentRef.current
    if (!container) return

    const selectMark = async (mark) => {
      const kpId = mark.dataset.kpId
      const kp = uniqueKPs.find(k => k.id === kpId)
      if (kp) {
        setSelectedKP(kp)
        container.querySelectorAll('mark.active').forEach(el => el.classList.remove('active'))
        mark.classList.add('active')
        recordClick(kp)
      }
      return kp
    }

    const handleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) selectMark(target)
    }

    const handleDoubleClick = (event) => {
      const target = event.target
      if (target.tagName === 'MARK' && target.dataset.kpId) {
        selectMark(target).then(kp => { if (kp) startDeepExplain(kp) })
      }
    }

    container.addEventListener('click', handleClick)
    container.addEventListener('dblclick', handleDoubleClick)
    return () => {
      container.removeEventListener('click', handleClick)
      container.removeEventListener('dblclick', handleDoubleClick)
    }
  }, [uniqueKPs, kpStatusMap])

  // 提取目录（文档加载后）
  useEffect(() => {
    if (!docLoaded || !docContentRef.current) return
    const items = []
    let counter = 0
    docContentRef.current.querySelectorAll('h1, h2, h3, h4').forEach(h => {
      const level = parseInt(h.tagName[1])
      const text = h.textContent.trim()
      if (!text) return
      const id = `doc-h-${counter++}`
      h.id = id
      items.push({ id, text, level })
    })
    setTocItems(items)
    setActiveTocId(null)
  }, [docLoaded])

  // IntersectionObserver 跟踪当前章节
  useEffect(() => {
    if (!docLoaded || tocItems.length === 0 || !documentAreaRef.current) return
    const root = documentAreaRef.current
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter(e => e.isIntersecting)
        if (visible.length > 0) setActiveTocId(visible[0].target.id)
      },
      { root, rootMargin: '0px 0px -65% 0px', threshold: 0 }
    )
    tocItems.forEach(item => {
      const el = document.getElementById(item.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [docLoaded, tocItems])

  const scrollToHeading = (id) => {
    const el = document.getElementById(id)
    const container = documentAreaRef.current
    if (el && container) {
      const elTop = el.getBoundingClientRect().top
      const containerTop = container.getBoundingClientRect().top
      container.scrollBy({ top: elTop - containerTop - 24, behavior: 'smooth' })
      setActiveTocId(id)
    }
  }

  const recordClick = async (kp) => {
    try {
      const response = await fetch(`${API_BASE}/api/knowledge/click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kp_text: kp.text, kp_type: kp.type })
      })
      if (response.ok) {
        const data = await response.json()
        setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
      }
    } catch (err) {
      console.error('上报点击失败:', err)
    }
  }

  const toggleKnown = async (kp) => {
    const currentStatus = getKpStatus(kp.text)
    const url = currentStatus === 'known'
      ? `${API_BASE}/api/knowledge/unmark-known`
      : `${API_BASE}/api/knowledge/mark-known`
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kp_text: kp.text, kp_type: kp.type })
      })
      if (response.ok) {
        const data = await response.json()
        setKpStatusMap(prev => ({ ...prev, [kp.text]: data.status }))
      }
    } catch (err) {
      console.error('切换状态失败:', err)
    }
  }

  const startDeepExplain = async (kp) => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(true)
    setDeepExplanation('')
    setDeepLoading(true)
    const context = findContextForKP(docContentRef.current, kp.id) || kp.text
    const controller = new AbortController()
    deepAbortRef.current = controller
    try {
      const response = await fetch(`${API_BASE}/api/explain-deep`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: kp.text, kp_type: kp.type, context }),
        signal: controller.signal
      })
      if (!response.ok) throw new Error(`请求失败: ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        setDeepExplanation(prev => prev + decoder.decode(value, { stream: true }))
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
      docContentRef.current.querySelectorAll('mark.active').forEach(el => el.classList.remove('active'))
      mark.classList.add('active')
    }
    recordClick(kp)
  }

  const handleKPCardDblClick = (kp) => {
    setSelectedKP(kp)
    startDeepExplain(kp)
  }

  const closeDeep = () => {
    if (deepAbortRef.current) deepAbortRef.current.abort()
    setShowDeep(false)
    setDeepExplanation('')
    setDeepLoading(false)
  }

  const stats = { unknown: 0, learning: 0, known: 0 }
  for (const kp of uniqueKPs) {
    const s = getKpStatus(kp.text)
    stats[s] = (stats[s] || 0) + 1
  }

  return (
    <div className={`app${tocOpen ? '' : ' toc-collapsed'}`}>

      {/* 左侧栏顶部（Logo 区域） */}
      <div className="sidebar-header">
        {tocOpen && <span className="app-logo">AI 学习助手</span>}
        <button
          className="toc-toggle-btn"
          onClick={() => setTocOpen(!tocOpen)}
          title={tocOpen ? '收起目录' : '展开目录'}
        >
          {tocOpen ? '◀' : '▶'}
        </button>
      </div>

      {/* 主区域顶部 Header */}
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
                onChange={e => setHideKnown(e.target.checked)}
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
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />
        </div>
      </header>

      {/* 目录侧边栏 */}
      <aside className="toc-sidebar">
        {tocOpen && (
          <>
            <div className="toc-section-title">文档目录</div>
            <nav className="toc-nav">
              {tocItems.length === 0 ? (
                <div className="toc-empty">
                  {docLoaded ? '此文档无标题结构' : '上传文档后\n自动生成目录'}
                </div>
              ) : (
                tocItems.map(item => (
                  <div
                    key={item.id}
                    className={`toc-item toc-level-${item.level}${activeTocId === item.id ? ' toc-active' : ''}`}
                    onClick={() => scrollToHeading(item.id)}
                    title={item.text}
                  >
                    {item.text}
                  </div>
                ))
              )}
            </nav>
          </>
        )}
      </aside>

      {/* 文档主区域 */}
      <section className="document-area" ref={documentAreaRef}>
        {loading && <p className="doc-placeholder">正在解析文档...</p>}
        {error && <p className="doc-error">{error}</p>}
        {!loading && !docLoaded && !error && (
          <div className="welcome">
            <div className="welcome-icon">📖</div>
            <p className="welcome-text">上传一份 docx 文档开始学习</p>
            <p className="welcome-hint">单击高亮词语查看简介，双击深入讲解</p>
          </div>
        )}
        <div
          ref={docContentRef}
          className="document-content"
          style={{ display: docLoaded ? 'block' : 'none' }}
        />
      </section>

      {/* 知识点面板 */}
      <aside className="kp-panel">

        {/* 选中的知识点详情 */}
        {selectedKP && (
          <div className="selected-kp-panel">
            <div className="selected-kp-header">
              <span className={`kp-type-badge kp-type-badge-${selectedKP.type}`}>
                {selectedKP.type === 'term' ? '术语' : '公式'}
              </span>
              <h3 className="selected-kp-title">{selectedKP.text}</h3>
              <button className="close-btn" onClick={() => setSelectedKP(null)} title="关闭">×</button>
            </div>
            <div className="selected-kp-content">{selectedKP.explanation}</div>
            <div className="kp-actions">
              {!showDeep && (
                <button className="deep-btn" onClick={() => startDeepExplain(selectedKP)}>
                  深入讲解
                </button>
              )}
              <button
                className={`known-btn${getKpStatus(selectedKP.text) === 'known' ? ' is-known' : ''}`}
                onClick={() => toggleKnown(selectedKP)}
              >
                {getKpStatus(selectedKP.text) === 'known' ? '✓ 已掌握' : '标记已掌握'}
              </button>
            </div>
          </div>
        )}

        {/* 深度讲解面板 */}
        {showDeep && (
          <div className="deep-panel">
            <div className="deep-header">
              <span className="deep-title">
                详细讲解
                {deepLoading && <span className="thinking-dot">●</span>}
              </span>
              <button className="close-btn" onClick={closeDeep} title="关闭">×</button>
            </div>
            <div className="deep-content">
              {deepExplanation || (deepLoading && <span className="placeholder-inline">AI 正在思考...</span>)}
              {deepLoading && deepExplanation && <span className="cursor-blink">▋</span>}
            </div>
          </div>
        )}

        {/* 知识点列表标题 */}
        <div className="kp-panel-header">
          <span className="kp-panel-title">知识点</span>
          {!extracting && uniqueKPs.length > 0 && (
            <span className="kp-stats">
              {stats.known} 掌握 · {stats.learning} 学习中 · {stats.unknown} 未学
            </span>
          )}
        </div>

        {/* 知识点列表 */}
        <div className="kp-list">
          {!docLoaded && <p className="placeholder">上传文档后将自动提取知识点</p>}
          {docLoaded && uniqueKPs.length === 0 && !extracting && (
            <p className="placeholder">暂无提取到的知识点</p>
          )}
          {uniqueKPs.map((kp) => {
            const status = getKpStatus(kp.text)
            return (
              <div
                key={kp.id}
                className={`kp-card kp-${kp.type} kp-card-${status}${selectedKP?.id === kp.id ? ' selected' : ''}`}
                onClick={() => handleKPCardClick(kp)}
                onDoubleClick={() => handleKPCardDblClick(kp)}
                title="单击定位 | 双击深入讲解"
              >
                <div className="kp-header">
                  <span className="kp-type-badge">
                    {kp.type === 'term' ? '术语' : '公式'}
                  </span>
                  <span className="kp-text">{kp.text}</span>
                  {status === 'known' && <span className="status-icon" title="已掌握">✓</span>}
                  {status === 'learning' && <span className="status-icon learning" title="学习中">●</span>}
                </div>
                <div className="kp-explanation">{kp.explanation}</div>
              </div>
            )
          })}
        </div>
      </aside>
    </div>
  )
}

export default App
