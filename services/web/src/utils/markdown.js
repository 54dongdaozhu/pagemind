function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('`', '&#96;')
}

function isSafeImageUrl(url) {
  return /^(blob:|https?:\/\/)/i.test(url)
}

function renderInlineText(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

function parseImageTarget(target) {
  const trimmed = String(target || '').trim()
  if (trimmed.startsWith('<')) {
    const endIndex = trimmed.indexOf('>')
    if (endIndex > 0) {
      return {
        src: trimmed.slice(1, endIndex).trim(),
        title: trimmed.slice(endIndex + 1).trim().replace(/^"|"$/g, ''),
      }
    }
  }

  const match = /^(.*?)(?:\s+"([^"]*)")?$/.exec(trimmed)
  return {
    src: (match?.[1] || '').trim(),
    title: match?.[2] || '',
  }
}

function renderInlineMarkdown(text, options = {}) {
  const imageTokens = []
  const withImageTokens = String(text || '').replace(/!\[([^\]]*)\]\(([^)]*)\)/g, (_match, alt, target) => {
    const { src: rawSrc, title } = parseImageTarget(target)
    const resolvedSrc = options.resolveImageUrl ? options.resolveImageUrl(rawSrc) : rawSrc
    if (!resolvedSrc || !isSafeImageUrl(resolvedSrc)) {
      return alt ? `[图片：${alt}]` : '[图片]'
    }

    const attrs = [
      `src="${escapeAttr(resolvedSrc)}"`,
      `alt="${escapeAttr(alt)}"`,
      'loading="lazy"',
    ]
    if (title) attrs.push(`title="${escapeAttr(title)}"`)
    imageTokens.push(`<img ${attrs.join(' ')}>`)
    return `@@IMG_TOKEN_${imageTokens.length - 1}@@`
  })

  return renderInlineText(withImageTokens).replace(/@@IMG_TOKEN_(\d+)@@/g, (_match, index) => imageTokens[Number(index)] || '')
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

function flushParagraph(htmlParts, paragraph, options) {
  if (paragraph.length === 0) return
  htmlParts.push(`<p>${renderInlineMarkdown(paragraph.join(' '), options)}</p>`)
  paragraph.length = 0
}

export function markdownToHtml(markdown, options = {}) {
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
        flushParagraph(htmlParts, paragraph, options)
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
      flushParagraph(htmlParts, paragraph, options)
      closeLists(htmlParts, listStack)
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushParagraph(htmlParts, paragraph, options)
      closeLists(htmlParts, listStack)
      htmlParts.push('<hr>')
      continue
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed)
    if (heading) {
      flushParagraph(htmlParts, paragraph, options)
      closeLists(htmlParts, listStack)
      const level = heading[1].length
      htmlParts.push(`<h${level}>${renderInlineMarkdown(heading[2], options)}</h${level}>`)
      continue
    }

    const listItem = /^(\s*)[-*+]\s+(.+)$/.exec(line)
    if (listItem) {
      flushParagraph(htmlParts, paragraph, options)
      const depth = Math.min(Math.floor(listItem[1].replace(/\t/g, '  ').length / 2) + 1, 6)
      ensureListDepth(htmlParts, listStack, depth, 'ul')
      htmlParts.push(`<li>${renderInlineMarkdown(listItem[2].trim(), options)}</li>`)
      continue
    }

    const orderedItem = /^(\s*)\d+[.)]\s+(.+)$/.exec(line)
    if (orderedItem) {
      flushParagraph(htmlParts, paragraph, options)
      const depth = Math.min(Math.floor(orderedItem[1].replace(/\t/g, '  ').length / 2) + 1, 6)
      ensureListDepth(htmlParts, listStack, depth, 'ol')
      htmlParts.push(`<li>${renderInlineMarkdown(orderedItem[2].trim(), options)}</li>`)
      continue
    }

    const quote = /^>\s?(.+)$/.exec(trimmed)
    if (quote) {
      flushParagraph(htmlParts, paragraph, options)
      closeLists(htmlParts, listStack)
      htmlParts.push(`<blockquote><p>${renderInlineMarkdown(quote[1], options)}</p></blockquote>`)
      continue
    }

    closeLists(htmlParts, listStack)
    paragraph.push(trimmed)
  }

  if (inCodeBlock) {
    htmlParts.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  flushParagraph(htmlParts, paragraph, options)
  closeLists(htmlParts, listStack)

  return htmlParts.join('')
}
