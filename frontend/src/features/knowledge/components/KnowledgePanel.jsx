import { useState } from 'react'
import DeepExplanationPanel from '../../explanation/DeepExplanationPanel'
import KnowledgeList from './KnowledgeList'
import SelectedKnowledgePanel from './SelectedKnowledgePanel'
import ChatPanel from '../../chat/ChatPanel'


function KnowledgePanel({
  selectedKP,
  showDeep,
  deepLoading,
  deepExplanation,
  extracting,
  docLoaded,
  docId,
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
            <span className="kp-panel-title">知识点</span>
            {!extracting && knowledgePoints.length > 0 && (
              <span className="kp-stats">
                {stats.known} 掌握 · {stats.learning} 学习中 · {stats.unknown} 未学
              </span>
            )}
          </div>

          <KnowledgeList
            docLoaded={docLoaded}
            extracting={extracting}
            knowledgePoints={knowledgePoints}
            selectedKP={selectedKP}
            getKpStatus={getKpStatus}
            onCardClick={onCardClick}
            onCardDoubleClick={onCardDoubleClick}
          />
        </>
      ) : (
        <ChatPanel docId={docId} docLoaded={docLoaded} />
      )}
    </aside>
  )
}

export default KnowledgePanel
