function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

function closeLists(htmlParts, listStack, targetDepth = 0) {
  while (listStack.length > targetDepth) {
    htmlParts.push(`</${listStack.pop()}>`)
  }
}

function ensureListDepth(htmlParts, listStack, depth, tagName) {
  if (listStack.length >= depth && listStack[depth - 1] !== tagName) {
    closeLists(htmlParts, listStack, depth - 1)
  } else {
    closeLists(htmlParts, listStack, depth)
  }

  while (listStack.length < depth) {
    htmlParts.push(`<${tagName}>`)
    listStack.push(tagName)
  }
}

function flushParagraph(htmlParts, paragraph) {
  if (paragraph.length === 0) return
  htmlParts.push(`<p>${renderInlineMarkdown(paragraph.join(' '))}</p>`)
  paragraph.length = 0
}

export function markdownToHtml(markdown) {
  const htmlParts = []
  const paragraph = []
  const listStack = []
  let inCodeBlock = false
  let codeLines = []

  for (const line of String(markdown || '').replace(/\r\n/g, '\n').split('\n')) {
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        htmlParts.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        inCodeBlock = false
      } else {
        flushParagraph(htmlParts, paragraph)
        closeLists(htmlParts, listStack)
        inCodeBlock = true
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    if (!trimmed) {
      flushParagraph(htmlParts, paragraph)
      closeLists(htmlParts, listStack)
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushParagraph(htmlParts, paragraph)
      closeLists(htmlParts, listStack)
      htmlParts.push('<hr>')
      continue
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed)
    if (heading) {
      flushParagraph(htmlParts, paragraph)
      closeLists(htmlParts, listStack)
      const level = heading[1].length
      htmlParts.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    const listItem = /^(\s*)[-*+]\s+(.+)$/.exec(line)
    if (listItem) {
      flushParagraph(htmlParts, paragraph)
      const depth = Math.min(Math.floor(listItem[1].replace(/\t/g, '  ').length / 2) + 1, 6)
      ensureListDepth(htmlParts, listStack, depth, 'ul')
      htmlParts.push(`<li>${renderInlineMarkdown(listItem[2].trim())}</li>`)
      continue
    }

    const orderedItem = /^(\s*)\d+[.)]\s+(.+)$/.exec(line)
    if (orderedItem) {
      flushParagraph(htmlParts, paragraph)
      const depth = Math.min(Math.floor(orderedItem[1].replace(/\t/g, '  ').length / 2) + 1, 6)
      ensureListDepth(htmlParts, listStack, depth, 'ol')
      htmlParts.push(`<li>${renderInlineMarkdown(orderedItem[2].trim())}</li>`)
      continue
    }

    const quote = /^>\s?(.+)$/.exec(trimmed)
    if (quote) {
      flushParagraph(htmlParts, paragraph)
      closeLists(htmlParts, listStack)
      htmlParts.push(`<blockquote><p>${renderInlineMarkdown(quote[1])}</p></blockquote>`)
      continue
    }

    closeLists(htmlParts, listStack)
    paragraph.push(trimmed)
  }

  if (inCodeBlock) {
    htmlParts.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  flushParagraph(htmlParts, paragraph)
  closeLists(htmlParts, listStack)

  return htmlParts.join('')
}
