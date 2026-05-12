const SUPPORTED_EXTENSIONS = ['.docx', '.pdf', '.txt', '.md']
const DOCX_STYLE_MAP = [
  "p[style-name='Title'] => h1:fresh",
  "p[style-name='标题'] => h1:fresh",
  "p[style-name='一级标题'] => h1:fresh",
  "p[style-name='二级标题'] => h2:fresh",
  "p[style-name='三级标题'] => h3:fresh",
  "p[style-name='四级标题'] => h4:fresh",
  "p[style-name='五级标题'] => h4:fresh",
  "p[style-name='六级标题'] => h4:fresh",
  "p[style-name='半括号标题（五级）'] => h4:fresh",
  "p[style-name='圆括号标题（六级标题）'] => h4:fresh",
]

export const ACCEPTED_DOCUMENT_TYPES = SUPPORTED_EXTENSIONS.join(',')
export const SUPPORTED_DOCUMENT_LABEL = SUPPORTED_EXTENSIONS.join('、')

function getFileExtension(fileName) {
  const normalized = fileName.toLowerCase()
  const dotIndex = normalized.lastIndexOf('.')
  return dotIndex >= 0 ? normalized.slice(dotIndex) : ''
}

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function paragraphsToHtml(text) {
  return text
    .split(/\n{2,}/)
    .map(block => block.trim())
    .filter(Boolean)
    .map(block => `<p>${escapeHtml(block).replace(/\n/g, '<br>')}</p>`)
    .join('')
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function flushList(htmlParts, listItems) {
  if (listItems.length === 0) return
  htmlParts.push(`<ul>${listItems.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</ul>`)
  listItems.length = 0
}

function markdownToHtml(markdown) {
  const htmlParts = []
  const paragraph = []
  const listItems = []
  let inCodeBlock = false
  let codeLines = []

  const flushParagraph = () => {
    if (paragraph.length === 0) return
    htmlParts.push(`<p>${renderInlineMarkdown(paragraph.join(' '))}</p>`)
    paragraph.length = 0
  }

  for (const line of markdown.replace(/\r\n/g, '\n').split('\n')) {
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        htmlParts.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        inCodeBlock = false
      } else {
        flushParagraph()
        flushList(htmlParts, listItems)
        inCodeBlock = true
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    if (!trimmed) {
      flushParagraph()
      flushList(htmlParts, listItems)
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed)
    if (heading) {
      flushParagraph()
      flushList(htmlParts, listItems)
      const level = heading[1].length
      htmlParts.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    const listItem = /^[-*+]\s+(.+)$/.exec(trimmed)
    if (listItem) {
      flushParagraph()
      listItems.push(listItem[1])
      continue
    }

    const quote = /^>\s?(.+)$/.exec(trimmed)
    if (quote) {
      flushParagraph()
      flushList(htmlParts, listItems)
      htmlParts.push(`<blockquote><p>${renderInlineMarkdown(quote[1])}</p></blockquote>`)
      continue
    }

    paragraph.push(trimmed)
  }

  if (inCodeBlock) {
    htmlParts.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  flushParagraph()
  flushList(htmlParts, listItems)

  return htmlParts.join('')
}

async function parseDocx(file) {
  const { default: mammoth } = await import('mammoth')
  const arrayBuffer = await file.arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer }, { styleMap: DOCX_STYLE_MAP })
  return result.value
}

async function parsePdf(file) {
  const [pdfjsLib, { default: pdfWorkerUrl }] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.mjs?url'),
  ])
  pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

  const arrayBuffer = await file.arrayBuffer()
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise
  const pages = []

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
    const page = await pdf.getPage(pageNumber)
    const content = await page.getTextContent()
    const text = content.items
      .map(item => item.str)
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (text) pages.push(`<section class="pdf-page"><h2>第 ${pageNumber} 页</h2>${paragraphsToHtml(text)}</section>`)
  }

  if (pages.length === 0) {
    throw new Error('PDF 未提取到可阅读文本，扫描版 PDF 请先 OCR 后再上传')
  }

  return pages.join('')
}

export async function parseDocumentFile(file) {
  const extension = getFileExtension(file.name)

  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    throw new Error(`请上传 ${SUPPORTED_DOCUMENT_LABEL} 格式的文件`)
  }

  if (extension === '.docx') return parseDocx(file)
  if (extension === '.pdf') return parsePdf(file)

  const text = await file.text()
  if (extension === '.md') return markdownToHtml(text)
  return paragraphsToHtml(text)
}
