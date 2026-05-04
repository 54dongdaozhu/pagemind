export function highlightFirstMatch(container, keyword, kpId, kpType, status, importance) {
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
      },
    },
  )
  let textNode
  while ((textNode = walker.nextNode())) {
    const text = textNode.nodeValue
    const idx = text.indexOf(keyword)
    if (idx !== -1) {
      const before = text.slice(0, idx)
      const after = text.slice(idx + keyword.length)
      const mark = document.createElement('mark')
      mark.className = [
        'kp-highlight',
        `kp-highlight-${kpType}`,
        `kp-status-${status || 'unknown'}`,
        importance === 'high' ? 'kp-high' : '',
      ].filter(Boolean).join(' ')
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
