import { useEffect, useMemo, useState } from 'react'
import DeepExplanationPanel from '../../explanation/DeepExplanationPanel'
import KnowledgeList from './KnowledgeList'
import SelectedKnowledgePanel from './SelectedKnowledgePanel'
import ChatPanel from '../../chat/ChatPanel'


const CHAT_STORAGE_PREFIX = 'ai-study-chat-messages'


function loadStoredChatMessages(storageKey) {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      msg =>
        (msg.role === 'user' || msg.role === 'assistant') &&
        typeof msg.content === 'string'
    )
  } catch {
    return []
  }
}


function KnowledgePanel({
  selectedKP,
  showDeep,
  deepLoading,
  deepExplanation,
  extracting,
  extractProgress,
  extractError,
  docLoaded,
  docId,
  ragReady,
  ragError,
  knowledgePoints,
  stats,
  getKpStatus,
  onCloseSelected,
  onStartDeepExplain,
  onToggleKnown,
  onCloseDeep,
  onCardClick,
  onCardDoubleClick,
}) {
  const [activeTab, setActiveTab] = useState('knowledge')
  const chatStorageKey = useMemo(
    () => `${CHAT_STORAGE_PREFIX}:${docId || 'no-document'}`,
    [docId]
  )
  const [chatMessages, setChatMessages] = useState(() => loadStoredChatMessages(chatStorageKey))
  const [chatLoading, setChatLoading] = useState(false)

  useEffect(() => {
    try {
      if (chatMessages.length === 0) {
        localStorage.removeItem(chatStorageKey)
      } else {
        localStorage.setItem(chatStorageKey, JSON.stringify(chatMessages))
      }
    } catch {
      // Ignore storage quota or privacy-mode failures; in-memory chat still works.
    }
  }, [chatMessages, chatStorageKey])

  return (
    <aside className="kp-panel">
      <div className="kp-tabs">
        <button
          className={`kp-tab${activeTab === 'knowledge' ? ' kp-tab-active' : ''}`}
          onClick={() => setActiveTab('knowledge')}
        >
          知识点
        </button>
        <button
          className={`kp-tab${activeTab === 'chat' ? ' kp-tab-active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          对话
        </button>
      </div>

      {activeTab === 'knowledge' ? (
        <>
          <SelectedKnowledgePanel
            selectedKP={selectedKP}
            showDeep={showDeep}
            status={selectedKP ? getKpStatus(selectedKP.text) : 'unknown'}
            onClose={onCloseSelected}
            onStartDeepExplain={onStartDeepExplain}
            onToggleKnown={onToggleKnown}
          />

          <DeepExplanationPanel
            showDeep={showDeep}
            deepLoading={deepLoading}
            deepExplanation={deepExplanation}
            onClose={onCloseDeep}
          />

          <div className="kp-panel-header">
            {!extracting && knowledgePoints.length > 0 && (
              <span className="kp-stats">
                {stats.known} 掌握 · {stats.learning} 理解中 · {stats.unknown} 未掌握
              </span>
            )}
          </div>

          <KnowledgeList
            docLoaded={docLoaded}
            extracting={extracting}
            extractProgress={extractProgress}
            extractError={extractError}
            knowledgePoints={knowledgePoints}
            selectedKP={selectedKP}
            getKpStatus={getKpStatus}
            onCardClick={onCardClick}
            onCardDoubleClick={onCardDoubleClick}
          />
        </>
      ) : (
        <ChatPanel
          docId={docId}
          docLoaded={docLoaded}
          ragReady={ragReady}
          ragError={ragError}
          messages={chatMessages}
          setMessages={setChatMessages}
          loading={chatLoading}
          setLoading={setChatLoading}
        />
      )}
    </aside>
  )
}

export default KnowledgePanel
