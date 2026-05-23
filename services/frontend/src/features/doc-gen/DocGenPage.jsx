import DocGenTerminal from './DocGenTerminal'
import DocGenViewer from './DocGenViewer'
import { useDocGen } from './useDocGen'

function DocGenPage({ user, userProfile }) {
  const {
    status,
    messages,
    htmlContent,
    wordUrl,
    humanPayload,
    generate,
    submitHumanDecision,
    reset,
  } = useDocGen(user?.user_id || 'anonymous', userProfile)

  return (
    <div className="doc-gen-page">
      <DocGenViewer
        htmlContent={htmlContent}
        wordUrl={wordUrl}
        status={status}
      />
      <DocGenTerminal
        status={status}
        messages={messages}
        humanPayload={humanPayload}
        onGenerate={generate}
        onHumanDecide={submitHumanDecision}
        onReset={reset}
      />
    </div>
  )
}

export default DocGenPage
