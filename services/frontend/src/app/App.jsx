import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { fetchCurrentUser, logoutUser } from '../api/auth'
import { fetchGeneratedDocument, fetchGeneratedDocuments } from '../api/generatedDocuments'
import { fetchMyProfile } from '../api/profile'
import { fetchRagDocumentRender, fetchRagDocuments, indexRagDocument } from '../api/rag'
import AuthScreen from '../features/auth/AuthScreen'
import DocumentViewer from '../features/document/components/DocumentViewer'
import { getDocumentSnapshot, saveDocumentSnapshot } from '../features/document/documentCache'
import { useDocumentUpload } from '../features/document/hooks/useDocumentUpload'
import { htmlToPlainText, splitIntoChunks } from '../features/document/documentUtils'
import { useDeepExplanation } from '../features/explanation/useDeepExplanation'
import AppHeader from '../features/layout/AppHeader'
import {
  clearKnowledgeHighlights,
  highlightKnowledgePoints,
  updateMarkStatusInDom,
} from '../features/knowledge/highlightDom'
import KnowledgePanel from '../features/knowledge/components/KnowledgePanel'
import { useKnowledgeExtraction } from '../features/knowledge/hooks/useKnowledgeExtraction'
import { useKnowledgeStatus } from '../features/knowledge/hooks/useKnowledgeStatus'
import PlanPage from '../features/plan/PlanPage'
import ProfilePage from '../features/profile/ProfilePage'
import SidebarHeader from '../features/toc/components/SidebarHeader'
import TocSidebar from '../features/toc/components/TocSidebar'
import { hashString } from '../utils/hash'
import '../styles/App.css'

const TOC_MIN_WIDTH = 240
const TOC_MAX_WIDTH = Math.round(TOC_MIN_WIDTH * 1.3)

// ========== React 组件 ==========

function App() {
  const [currentUser, setCurrentUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [mode, setMode] = useState('normal')
  const [userProfile, setUserProfile] = useState(null)
  const [profileLoaded, setProfileLoaded] = useState(false)
  const [selectedKP, setSelectedKP] = useState(null)
  const [hideKnown, setHideKnown] = useState(true)
  const [documents, setDocuments] = useState([])
  const [persistedDocuments, setPersistedDocuments] = useState([])
  const [persistedDocumentsLoading, setPersistedDocumentsLoading] = useState(false)
  const [persistedDocumentsError, setPersistedDocumentsError] = useState('')
  const [generatedDocuments, setGeneratedDocuments] = useState([])
  const [generatedDocumentsLoading, setGeneratedDocumentsLoading] = useState(false)
  const [generatedDocumentsError, setGeneratedDocumentsError] = useState('')
  const [generatedDocumentPreview, setGeneratedDocumentPreview] = useState(null)
  const [generatedDocumentPreviewLoading, setGeneratedDocumentPreviewLoading] = useState(false)
  const [generatedDocumentPreviewError, setGeneratedDocumentPreviewError] = useState('')
  const [activeDocId, setActiveDocId] = useState('')
  const [documentRenderToken, setDocumentRenderToken] = useState(0)
  const [ragReadyDocIds, setRagReadyDocIds] = useState(() => new Set())
  const [ragIndexErrors, setRagIndexErrors] = useState(() => new Map())

  // 目录相关
  const [tocItems, setTocItems] = useState([])
  const [tocOpen, setTocOpen] = useState(true)
  const [tocWidth, setTocWidth] = useState(TOC_MIN_WIDTH)
  const [tocResizing, setTocResizing] = useState(false)
  const [docListOpen, setDocListOpen] = useState(true)
  const [tocSectionOpen, setTocSectionOpen] = useState(true)
  const [activeTocId, setActiveTocId] = useState(null)

  const docContentRef = useRef(null)
  const documentAreaRef = useRef(null)
  const highlightedIdsRef = useRef(new Set())
  const documentSnapshotsRef = useRef(new Map())

  const activeDoc = useMemo(
    () => documents.find(d => d.id === activeDocId) ?? null,
    [documents, activeDocId]
  )

  useEffect(() => {
    let active = true
    fetchCurrentUser()
      .then(user => {
        if (active) setCurrentUser(user)
      })
      .catch(() => {
        if (active) setCurrentUser(null)
      })
      .finally(() => {
        if (active) setAuthChecked(true)
      })

    const handleExpired = () => setCurrentUser(null)
    window.addEventListener('auth:expired', handleExpired)
    return () => {
      active = false
      window.removeEventListener('auth:expired', handleExpired)
    }
  }, [])

  useEffect(() => {
    if (!currentUser) return
    fetchMyProfile()
      .then(p => { if (p) setUserProfile(p) })
      .finally(() => setProfileLoaded(true))
  }, [currentUser])

  const reloadGeneratedDocuments = useCallback(() => {
    if (!currentUser) return () => {}
    let active = true
    setGeneratedDocumentsLoading(true)
    setGeneratedDocumentsError('')
    fetchGeneratedDocuments()
      .then(data => {
        if (!active) return
        setGeneratedDocuments((data.documents || []).map(doc => ({
          id: doc.generated_doc_id,
          name: doc.title || doc.topic || '生成文档',
          topic: doc.topic || '',
          requirements: doc.requirements || '',
          sourceTaskId: doc.source_task_id || '',
          createdAt: doc.created_at,
          updatedAt: doc.updated_at,
        })))
      })
      .catch(err => {
        console.warn('生成文档列表加载失败:', err)
        if (active) setGeneratedDocumentsError(err.message || '生成文档加载失败')
      })
      .finally(() => {
        if (active) setGeneratedDocumentsLoading(false)
      })
    return () => { active = false }
  }, [currentUser])

  useEffect(() => {
    return reloadGeneratedDocuments()
  }, [reloadGeneratedDocuments])

  useEffect(() => {
    if (mode !== 'profile') return
    return reloadGeneratedDocuments()
  }, [mode, reloadGeneratedDocuments])

  useEffect(() => {
    if (!currentUser) return
    let active = true
    setPersistedDocumentsLoading(true)
    setPersistedDocumentsError('')
    fetchRagDocuments()
      .then(data => {
        if (!active) return
        const history = (data.documents || []).map(doc => ({
          id: doc.doc_id,
          name: doc.title || '未命名文档',
          summary: doc.summary || '',
          chunkCount: doc.chunk_count || 0,
          renderAvailable: doc.render_available,
          updatedAt: doc.updated_at,
        }))
        setPersistedDocuments(history)
        setRagReadyDocIds(prev => {
          const next = new Set(prev)
          for (const doc of data.documents || []) {
            if ((doc.chunk_count || 0) > 0) next.add(doc.doc_id)
          }
          return next
        })
      })
      .catch(err => {
        console.warn('历史文档列表加载失败:', err)
        if (active) setPersistedDocumentsError(err.message || '历史文档加载失败')
      })
      .finally(() => {
        if (active) setPersistedDocumentsLoading(false)
      })
    return () => { active = false }
  }, [currentUser])

  const {
    extracting,
    extractProgress,
    extractError,
    refinementStatus,
    refinementRunId,
    highlightResetToken,
    knowledgePoints,
    uniqueKPs,
    extractAllChunks,
    resetExtraction,
    restoreExtraction,
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
    setActiveDocId('')
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()
  }, [resetDeep, resetExtraction])

  const handleHtmlLoaded = useCallback(async (document) => {
    const { html, name, rawText, assets, outline, imagesPromise, renderHtmlPromise } = document
    imagesPromise?.catch(() => {})
    renderHtmlPromise?.catch(() => {})
    const plainText = htmlToPlainText(html)
    const chunks = splitIntoChunks(html)
    const docId = hashString(`${currentUser?.user_id || 'anonymous'}:${name}:${plainText}`)
    setActiveDocId(docId)
    setDocuments(prev => {
      const nextDoc = {
        id: docId,
        name,
        html,
        plainText,
        rawText,
        assets,
        outline: outline ?? [],
      }
      const index = prev.findIndex(doc => doc.id === docId)
      if (index === -1) return [nextDoc, ...prev]
      const next = [...prev]
      next[index] = { ...prev[index], ...nextDoc }
      return next
    })
    documentSnapshotsRef.current.set(docId, {
      knowledgePoints: [],
      extractProgress: { done: 0, total: 0 },
      extractError: '',
      refinementStatus: 'not_started',
      refinementRunId: null,
    })
    setRagIndexErrors(prev => {
      const next = new Map(prev)
      next.delete(docId)
      return next
    })

    const persistedHtmlPromise = renderHtmlPromise || Promise.resolve(html)
    Promise.all([
      persistedHtmlPromise.catch(() => html),
      imagesPromise?.catch(() => []) || Promise.resolve([]),
    ]).then(([persistedHtml, images]) => {
      const persistedDoc = {
        id: docId,
        name,
        html: persistedHtml,
        plainText,
        rawText,
        outline: outline ?? [],
      }
      saveDocumentSnapshot(persistedDoc).catch(() => {})
      setDocuments(prev => prev.map(doc => (
        doc.id === docId ? { ...doc, html: persistedHtml, renderAvailable: true } : doc
      )))
      return indexRagDocument(docId, plainText, name, chunks, images?.length ? images : null, {
        html: persistedHtml,
        outline: outline ?? [],
      })
    })
      .then(() => {
        setPersistedDocuments(prev => {
          const nextDoc = {
            id: docId,
            name,
            summary: plainText.slice(0, 160),
            chunkCount: chunks.length,
            renderAvailable: true,
            updatedAt: new Date().toISOString(),
          }
          const index = prev.findIndex(doc => doc.id === docId)
          if (index === -1) return [nextDoc, ...prev]
          const next = [...prev]
          next[index] = { ...prev[index], ...nextDoc }
          return next
        })
        setRagReadyDocIds(prev => {
          const next = new Set(prev)
          next.add(docId)
          return next
        })
      })
      .catch((err) => {
        console.error('RAG 索引失败:', err)
        setRagIndexErrors(prev => {
          const next = new Map(prev)
          next.set(docId, err.name === 'AbortError' ? '问答索引超时，请稍后重新上传或检查后端日志。' : (err.message || '问答索引失败'))
          return next
        })
      })

    extractAllChunks(html, docId, { chunks, title: name }).catch(err => {
      console.error('知识点提取任务启动失败:', err)
    })
  }, [currentUser?.user_id, extractAllChunks])

  const {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
    showParsedDocument,
  } = useDocumentUpload({
    docContentRef,
    onBeforeLoad: resetDocumentState,
    onHtmlLoaded: handleHtmlLoaded,
  })

  const {
    kpStatusMap,
    getKpStatus,
    recordClick,
    toggleKnown,
    stats,
  } = useKnowledgeStatus(uniqueKPs)

  useEffect(() => {
    if (!activeDocId) return
    documentSnapshotsRef.current.set(activeDocId, {
      knowledgePoints,
      extractProgress,
      extractError,
      refinementStatus,
      refinementRunId,
    })
  }, [activeDocId, extractError, extractProgress, knowledgePoints, refinementRunId, refinementStatus])

  useEffect(() => {
    if (mode !== 'normal' || !docLoaded || !activeDoc || !docContentRef.current) return

    const container = docContentRef.current
    if (container.dataset.docId === activeDoc.id && container.innerHTML.trim()) return

    container.innerHTML = activeDoc.html
    container.dataset.docId = activeDoc.id
    highlightedIdsRef.current = new Set()
    setDocumentRenderToken(token => token + 1)
  }, [activeDoc, docLoaded, mode])

  const handleSelectDocument = useCallback(async (docId) => {
    if (docId === activeDocId && docLoaded) return
    let doc = documents.find(item => item.id === docId)
    if (!doc) return

    resetExtraction()
    setSelectedKP(null)
    resetDeep()
    setActiveDocId(docId)
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()

    if (!doc.html) {
      const cached = await getDocumentSnapshot(docId)
      if (cached?.html) {
        doc = { ...doc, ...cached }
      } else {
        try {
          const restored = await fetchRagDocumentRender(docId)
          doc = { ...doc, ...restored }
          saveDocumentSnapshot(doc).catch(() => {})
        } catch (err) {
          console.error('文档渲染恢复失败:', err)
          setRagIndexErrors(prev => {
            const next = new Map(prev)
            next.set(docId, err.message || '文档渲染恢复失败，请重新上传。')
            return next
          })
          return
        }
      }
      setDocuments(prev => prev.map(item => item.id === docId ? { ...item, ...doc } : item))
    }

    showParsedDocument({ name: doc.name, html: doc.html })
    const snapshot = documentSnapshotsRef.current.get(docId) || {}
    restoreExtraction({
      knowledgePoints: snapshot.knowledgePoints,
      extractProgress: snapshot.extractProgress,
      extractError: snapshot.extractError,
      refinementStatus: snapshot.refinementStatus,
      refinementRunId: snapshot.refinementRunId,
    })
  }, [activeDocId, docLoaded, documents, resetDeep, resetExtraction, restoreExtraction, showParsedDocument])

  const handleOpenPersistedDocument = useCallback(async (docId) => {
    const persisted = persistedDocuments.find(item => item.id === docId)
    if (!persisted) return

    resetExtraction()
    setSelectedKP(null)
    resetDeep()
    setTocItems([])
    setActiveTocId(null)
    highlightedIdsRef.current = new Set()

    let doc = documents.find(item => item.id === docId)
    if (!doc?.html) {
      const cached = await getDocumentSnapshot(docId)
      if (cached?.html) {
        doc = { ...persisted, ...cached, name: cached.name || persisted.name }
      } else {
        try {
          const restored = await fetchRagDocumentRender(docId)
          doc = { ...persisted, ...restored, name: restored.name || persisted.name }
          saveDocumentSnapshot(doc).catch(() => {})
        } catch (err) {
          console.error('文档渲染恢复失败:', err)
          setPersistedDocumentsError(err.message || '文档渲染恢复失败，请重新上传。')
          return
        }
      }
      setDocuments(prev => {
        const index = prev.findIndex(item => item.id === docId)
        if (index === -1) return [doc, ...prev]
        const next = [...prev]
        next[index] = { ...next[index], ...doc }
        return next
      })
    }

    setActiveDocId(docId)
    showParsedDocument({ name: doc.name, html: doc.html })
    const snapshot = documentSnapshotsRef.current.get(docId) || {}
    restoreExtraction({
      knowledgePoints: snapshot.knowledgePoints,
      extractProgress: snapshot.extractProgress,
      extractError: snapshot.extractError,
      refinementStatus: snapshot.refinementStatus,
      refinementRunId: snapshot.refinementRunId,
    })
    setMode('normal')
  }, [documents, persistedDocuments, resetDeep, resetExtraction, restoreExtraction, showParsedDocument])

  const handleOpenGeneratedDocument = useCallback(async (generatedDocId) => {
    setGeneratedDocumentPreviewLoading(true)
    setGeneratedDocumentPreviewError('')
    try {
      const doc = await fetchGeneratedDocument(generatedDocId)
      setGeneratedDocumentPreview(doc)
    } catch (err) {
      console.error('生成文档打开失败:', err)
      setGeneratedDocumentPreviewError(err.message || '生成文档打开失败')
    } finally {
      setGeneratedDocumentPreviewLoading(false)
    }
  }, [])

  useEffect(() => {
    if (mode !== 'normal' || !highlightResetToken || !docContentRef.current || !docLoaded) return
    clearKnowledgeHighlights(docContentRef.current)
    highlightedIdsRef.current = new Set()
    setSelectedKP(null)
  }, [docLoaded, documentRenderToken, highlightResetToken, mode])

  // 增量高亮
  useEffect(() => {
    if (mode !== 'normal' || !docContentRef.current || !docLoaded) return
    highlightKnowledgePoints(docContentRef.current, uniqueKPs, getKpStatus, highlightedIdsRef.current)
    if (selectedKP) {
      const mark = docContentRef.current.querySelector(`mark[data-kp-id="${selectedKP.id}"]`)
      if (mark) mark.classList.add('active')
    }
  }, [uniqueKPs, docLoaded, documentRenderToken, getKpStatus, mode, selectedKP])

  // 同步 mark 状态 class
  useEffect(() => {
    if (mode !== 'normal' || !docContentRef.current) return
    for (const kpText in kpStatusMap) {
      updateMarkStatusInDom(docContentRef.current, kpText, kpStatusMap[kpText])
    }
  }, [documentRenderToken, kpStatusMap, mode])

  // hideKnown 开关
  useEffect(() => {
    if (mode !== 'normal' || !docContentRef.current) return
    if (hideKnown) {
      docContentRef.current.classList.add('hide-known')
    } else {
      docContentRef.current.classList.remove('hide-known')
    }
  }, [hideKnown, docLoaded, documentRenderToken, mode])

  // 文档点击/双击委托
  useEffect(() => {
    if (mode !== 'normal' || !docLoaded) return
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
  }, [uniqueKPs, kpStatusMap, recordClick, startDeepExplain, docLoaded, documentRenderToken, mode])

  // 提取目录（文档加载后）
  useEffect(() => {
    if (mode !== 'normal' || !docLoaded || !docContentRef.current) return
    let items
    if (activeDoc?.outline?.length > 0) {
      items = activeDoc.outline.map((item, i) => ({
        id: `pdf-outline-${i}`,
        text: item.text,
        level: Math.min(item.level, 4),
        pageNum: item.pageNum,
      }))
    } else {
      const headingItems = []
      let counter = 0
      docContentRef.current.querySelectorAll('h1, h2, h3, h4').forEach(h => {
        const level = parseInt(h.tagName[1])
        const text = h.textContent.trim()
        if (!text) return
        const id = `doc-h-${counter++}`
        h.id = id
        headingItems.push({ id, text, level })
      })
      items = headingItems
    }
    setTocItems(items)
    setActiveTocId(null)
  }, [activeDocId, docLoaded, activeDoc?.outline, documentRenderToken, mode])

  // IntersectionObserver 跟踪当前章节
  useEffect(() => {
    if (mode !== 'normal' || !docLoaded || tocItems.length === 0 || !documentAreaRef.current) return
    const root = documentAreaRef.current
    const hasPdfOutline = tocItems.some(i => i.pageNum != null)

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter(e => e.isIntersecting)
        if (visible.length === 0) return
        if (hasPdfOutline) {
          const pageNums = visible
            .map(e => parseInt(e.target.id.replace('pdf-page-', ''), 10))
            .filter(n => !isNaN(n))
          if (!pageNums.length) return
          const currentPage = Math.min(...pageNums)
          let activeItem = null
          for (const item of tocItems) {
            if (item.pageNum != null && item.pageNum <= currentPage) activeItem = item
          }
          if (activeItem) setActiveTocId(activeItem.id)
        } else {
          setActiveTocId(visible[0].target.id)
        }
      },
      { root, rootMargin: '0px 0px -65% 0px', threshold: 0 }
    )

    if (hasPdfOutline) {
      docContentRef.current?.querySelectorAll('section.pdf-page').forEach(el => observer.observe(el))
    } else {
      tocItems.forEach(item => {
        const el = document.getElementById(item.id)
        if (el) observer.observe(el)
      })
    }
    return () => observer.disconnect()
  }, [docLoaded, documentRenderToken, mode, tocItems])

  const scrollToTocItem = (item) => {
    const container = documentAreaRef.current
    if (!container) return
    const el = item.pageNum != null
      ? docContentRef.current?.querySelector(`#pdf-page-${item.pageNum}`)
      : document.getElementById(item.id)
    if (el) {
      const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top - 24
      container.scrollBy({ top: offset, behavior: 'smooth' })
      setActiveTocId(item.id)
    }
  }

  const handleLogout = () => {
    logoutUser()
    setCurrentUser(null)
    resetDocumentState()
    setDocuments([])
    setPersistedDocuments([])
    setPersistedDocumentsError('')
    setPersistedDocumentsLoading(false)
    setRagReadyDocIds(new Set())
    setRagIndexErrors(new Map())
    documentSnapshotsRef.current = new Map()
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

  if (!authChecked) {
    return (
      <div className="auth-loading">
        正在检查登录状态...
      </div>
    )
  }

  if (!currentUser) {
    return <AuthScreen onAuthenticated={setCurrentUser} />
  }

  const appClassName = `app${tocOpen ? '' : ' toc-collapsed'}${tocResizing ? ' toc-resizing' : ''}`

  return (
    <div
      className={appClassName}
      style={{ '--toc-width': `${tocWidth}px` }}
    >
      <SidebarHeader
        tocOpen={tocOpen}
        onToggle={() => setTocOpen(!tocOpen)}
      />

      <AppHeader
        user={currentUser}
        fileName={fileName}
        extracting={extracting}
        extractProgress={extractProgress}
        docLoaded={docLoaded}
        hideKnown={hideKnown}
        onHideKnownChange={setHideKnown}
        onFileUpload={handleFileUpload}
        mode={mode}
        onModeChange={setMode}
      />

      <div className={`mode-pane${mode === 'normal' ? ' active' : ''}`} aria-hidden={mode !== 'normal'}>
          <TocSidebar
            tocOpen={tocOpen}
            width={tocWidth}
            minWidth={TOC_MIN_WIDTH}
            maxWidth={TOC_MAX_WIDTH}
            documents={documents}
            activeDocId={activeDocId}
            docListOpen={docListOpen}
            tocSectionOpen={tocSectionOpen}
            tocItems={tocItems}
            activeTocId={activeTocId}
            docLoaded={docLoaded}
            onToggleDocList={() => setDocListOpen(open => !open)}
            onToggleTocSection={() => setTocSectionOpen(open => !open)}
            onSelectDocument={handleSelectDocument}
            onSelectHeading={scrollToTocItem}
            onWidthChange={setTocWidth}
            onResizeActiveChange={setTocResizing}
          />

          <DocumentViewer
            documentAreaRef={documentAreaRef}
            docContentRef={docContentRef}
            loading={loading}
            error={error}
            docLoaded={docLoaded}
          />

          <KnowledgePanel
            key={activeDocId || 'empty-document'}
            selectedKP={selectedKP}
            showDeep={showDeep}
            deepLoading={deepLoading}
            deepExplanation={deepExplanation}
            extracting={extracting}
            extractProgress={extractProgress}
            extractError={extractError}
            refinementStatus={refinementStatus}
            refinementRunId={refinementRunId}
            docLoaded={docLoaded}
            docId={activeDocId}
            ragReady={Boolean(activeDocId && ragReadyDocIds.has(activeDocId))}
            ragError={activeDocId ? ragIndexErrors.get(activeDocId) : ''}
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

      <div className={`mode-pane${mode === 'profile' ? ' active' : ''}`} aria-hidden={mode !== 'profile'}>
        <ProfilePage
          user={currentUser}
          documents={persistedDocuments}
          documentsLoading={persistedDocumentsLoading}
          documentsError={persistedDocumentsError}
          generatedDocuments={generatedDocuments}
          generatedDocumentsLoading={generatedDocumentsLoading}
          generatedDocumentsError={generatedDocumentsError}
          generatedDocumentPreview={generatedDocumentPreview}
          generatedDocumentPreviewLoading={generatedDocumentPreviewLoading}
          generatedDocumentPreviewError={generatedDocumentPreviewError}
          onOpenDocument={handleOpenPersistedDocument}
          onOpenGeneratedDocument={handleOpenGeneratedDocument}
          onLogout={handleLogout}
        />
      </div>

      <div className={`mode-pane${mode === 'plan' ? ' active' : ''}`} aria-hidden={mode !== 'plan'}>
        <PlanPage userProfile={userProfile} profileLoaded={profileLoaded} onProfileSave={setUserProfile} userId={currentUser?.user_id} />
      </div>

      <div className={`mode-pane${mode === 'complete' ? ' active' : ''}`} aria-hidden={mode !== 'complete'}>
        <div className="blank-mode-page">补全模式（开发中）</div>
      </div>
    </div>
  )
}

export default App
