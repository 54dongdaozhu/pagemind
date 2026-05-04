import { useState, useRef, useEffect, useCallback } from 'react'
import DocumentViewer from '../features/document/components/DocumentViewer'
import { useDocumentUpload } from '../features/document/hooks/useDocumentUpload'
import { useDeepExplanation } from '../features/explanation/useDeepExplanation'
import AppHeader from '../features/layout/AppHeader'
import {
  highlightFirstMatch,
  updateMarkStatusInDom,
} from '../features/knowledge/highlightDom'
import KnowledgePanel from '../features/knowledge/components/KnowledgePanel'
import { useKnowledgeExtraction } from '../features/knowledge/hooks/useKnowledgeExtraction'
import { useKnowledgeStatus } from '../features/knowledge/hooks/useKnowledgeStatus'
import SidebarHeader from '../features/toc/components/SidebarHeader'
import TocSidebar from '../features/toc/components/TocSidebar'
import '../styles/App.css'

// ========== React 组件 ==========

function App() {
  const [selectedKP, setSelectedKP] = useState(null)
  const [hideKnown, setHideKnown] = useState(true)

  // 目录相关
  const [tocItems, setTocItems] = useState([])
  const [tocOpen, setTocOpen] = useState(true)
  const [activeTocId, setActiveTocId] = useState(null)

  const docContentRef = useRef(null)
  const documentAreaRef = useRef(null)
  const highlightedIdsRef = useRef(new Set())

  const {
    extracting,
    extractProgress,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
  } = useKnowledgeExtraction()

  const {
    deepExplanation,
    deepLoading,
    showDeep,
    closeDeep,
    resetDeep,
    startDeepExplain,
  } = useDeepExplanation(docContentRef)

  const resetDocumentState = useCallback(() => {
    resetExtraction()
    setSelectedKP(null)
    resetDeep()
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()
  }, [resetDeep, resetExtraction])

  const {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
  } = useDocumentUpload({
    docContentRef,
    onBeforeLoad: resetDocumentState,
    onHtmlLoaded: extractAllChunks,
  })

  const {
    kpStatusMap,
    getKpStatus,
    recordClick,
    toggleKnown,
    stats,
  } = useKnowledgeStatus(uniqueKPs)

  // 增量高亮
  useEffect(() => {
    if (!docContentRef.current || !docLoaded) return
    for (const kp of uniqueKPs) {
      if (highlightedIdsRef.current.has(kp.id)) continue
      const status = getKpStatus(kp.text)
      highlightFirstMatch(docContentRef.current, kp.text, kp.id, kp.type, status, kp.importance)
      highlightedIdsRef.current.add(kp.id)
    }
  }, [uniqueKPs, docLoaded, kpStatusMap, getKpStatus])

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
  }, [uniqueKPs, kpStatusMap, recordClick, startDeepExplain])

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

  return (
    <div className={`app${tocOpen ? '' : ' toc-collapsed'}`}>
      <SidebarHeader
        tocOpen={tocOpen}
        onToggle={() => setTocOpen(!tocOpen)}
      />

      <AppHeader
        fileName={fileName}
        extracting={extracting}
        extractProgress={extractProgress}
        docLoaded={docLoaded}
        hideKnown={hideKnown}
        onHideKnownChange={setHideKnown}
        onFileUpload={handleFileUpload}
      />

      <TocSidebar
        tocOpen={tocOpen}
        tocItems={tocItems}
        activeTocId={activeTocId}
        docLoaded={docLoaded}
        onSelectHeading={scrollToHeading}
      />

      <DocumentViewer
        documentAreaRef={documentAreaRef}
        docContentRef={docContentRef}
        loading={loading}
        error={error}
        docLoaded={docLoaded}
      />

      <KnowledgePanel
        selectedKP={selectedKP}
        showDeep={showDeep}
        deepLoading={deepLoading}
        deepExplanation={deepExplanation}
        extracting={extracting}
        docLoaded={docLoaded}
        knowledgePoints={uniqueKPs}
        stats={stats}
        getKpStatus={getKpStatus}
        onCloseSelected={() => setSelectedKP(null)}
        onStartDeepExplain={startDeepExplain}
        onToggleKnown={toggleKnown}
        onCloseDeep={closeDeep}
        onCardClick={handleKPCardClick}
        onCardDoubleClick={handleKPCardDblClick}
      />
    </div>
  )
}

export default App
