function createHighlightMark(kp, status) {
  const mark = document.createElement('mark')
  mark.className = [
    'kp-highlight',
    `kp-highlight-${kp.type}`,
    `kp-status-${status || 'unknown'}`,
    kp.importance === 'high' ? 'kp-high' : '',
  ].filter(Boolean).join(' ')
  mark.dataset.kpId = kp.id
  mark.dataset.kpText = kp.text
  mark.textContent = kp.text
  return mark
}


function findFirstPendingMatch(text, pendingItems) {
  let bestMatch = null
  for (const kp of pendingItems.values()) {
    const idx = text.indexOf(kp.text)
    if (idx === -1) continue
    if (
      !bestMatch ||
      idx < bestMatch.idx ||
      (idx === bestMatch.idx && kp.text.length > bestMatch.kp.text.length)
    ) {
      bestMatch = { idx, kp }
    }
  }
  return bestMatch
}


function markTextNode(textNode, pendingItems, getStatus, highlightedIds) {
  let currentNode = textNode
  let markedCount = 0

  while (currentNode) {
    const text = currentNode.nodeValue
    const match = findFirstPendingMatch(text, pendingItems)
    if (!match) return markedCount

    const { idx, kp } = match
    const before = text.slice(0, idx)
    const after = text.slice(idx + kp.text.length)
    const mark = createHighlightMark(kp, getStatus(kp.text))
    const parent = currentNode.parentNode
    if (!parent) return markedCount

    if (before) parent.insertBefore(document.createTextNode(before), currentNode)
    parent.insertBefore(mark, currentNode)

    const afterNode = after ? document.createTextNode(after) : null
    if (afterNode) parent.insertBefore(afterNode, currentNode)
    parent.removeChild(currentNode)

    highlightedIds.add(kp.id)
    markedCount += 1
    currentNode = afterNode
  }

  return markedCount
}


export function highlightKnowledgePoints(container, knowledgePoints, getStatus, highlightedIds) {
  if (!container || knowledgePoints.length === 0) return 0

  const pendingItems = new Map()
  for (const kp of knowledgePoints) {
    if (kp?.id && kp?.text && !highlightedIds.has(kp.id)) {
      pendingItems.set(kp.id, kp)
    }
  }
  if (pendingItems.size === 0) return 0

  const textNodes = []
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        if (node.parentElement && node.parentElement.tagName === 'MARK') {
          return NodeFilter.FILTER_REJECT
        }
        return NodeFilter.FILTER_ACCEPT
      },
    },
  )

  let textNode
  while ((textNode = walker.nextNode())) {
    textNodes.push(textNode)
  }

  container.style.visibility = 'hidden'
  let markedCount = 0
  try {
    for (const node of textNodes) {
      if (pendingItems.size === 0) break
      markedCount += markTextNode(node, pendingItems, getStatus, highlightedIds)
    }
  } finally {
    container.style.visibility = ''
  }

  for (const kpId of pendingItems.keys()) {
    highlightedIds.add(kpId)
  }

  return markedCount
}


export function clearKnowledgeHighlights(container) {
  if (!container) return
  container.querySelectorAll('mark.kp-highlight').forEach(mark => {
    mark.replaceWith(document.createTextNode(mark.textContent || ''))
  })
  container.normalize()
}


export function highlightFirstMatch(container, keyword, kpId, kpType, status, importance) {
  const kp = { id: kpId, text: keyword, type: kpType, importance }
  return highlightKnowledgePoints(container, [kp], () => status, new Set()) > 0
}


export function findContextForKP(container, kpId) {
  if (!container) return ''
  const mark = container.querySelector(`mark[data-kp-id="${kpId}"]`)
  if (!mark) return ''
  let node = mark.parentElement
  const blockTags = ['P', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TD', 'DIV']
  while (node && !blockTags.includes(node.tagName)) node = node.parentElement
  return node ? node.textContent.trim() : mark.textContent
}


export function updateMarkStatusInDom(container, kpText, status) {
  if (!container) return
  const marks = container.querySelectorAll(`mark[data-kp-text="${CSS.escape(kpText)}"]`)
  marks.forEach(m => {
    m.classList.remove('kp-status-unknown', 'kp-status-learning', 'kp-status-known')
    m.classList.add(`kp-status-${status}`)
  })
}
