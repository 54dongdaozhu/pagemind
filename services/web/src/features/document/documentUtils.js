export function splitIntoChunks(html) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const blocks = []
  const elements = doc.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, th, td')
  elements.forEach(el => {
    const text = el.textContent.trim()
    if (text.length > 0) blocks.push(text)
    el.querySelectorAll('img[alt]').forEach(img => {
      const alt = img.getAttribute('alt')?.trim()
      if (alt) blocks.push(`[图片：${alt}]`)
    })
  })
  const chunks = []
  let buffer = ''
  for (const block of blocks) {
    if (buffer.length + block.length > 800 && buffer.length > 0) {
      chunks.push(buffer)
      buffer = block
    } else {
      buffer = buffer ? buffer + '\n' + block : block
    }
  }
  if (buffer.length > 0) chunks.push(buffer)
  return chunks
}


export function htmlToPlainText(html) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const blocks = []
  const elements = doc.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, th, td')
  elements.forEach(el => {
    const text = el.textContent.trim()
    if (text.length > 0) blocks.push(text)
    el.querySelectorAll('img[alt]').forEach(img => {
      const alt = img.getAttribute('alt')?.trim()
      if (alt) blocks.push(`[图片：${alt}]`)
    })
  })
  return blocks.join('\n\n')
}
