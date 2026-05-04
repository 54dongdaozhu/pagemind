import DeepExplanationPanel from '../../explanation/DeepExplanationPanel'
import KnowledgeList from './KnowledgeList'
import SelectedKnowledgePanel from './SelectedKnowledgePanel'


function KnowledgePanel({
  selectedKP,
  showDeep,
  deepLoading,
  deepExplanation,
  extracting,
  docLoaded,
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
  return (
    <aside className="kp-panel">
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
    </aside>
  )
}

export default KnowledgePanel
