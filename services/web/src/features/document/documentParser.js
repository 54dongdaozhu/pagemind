import { markdownToHtml } from '../../utils/markdown'
import { uploadImageAsset } from '../../api/assets'

const SUPPORTED_EXTENSIONS = ['.docx', '.pdf', '.txt', '.md', '.zip']
const MARKDOWN_EXTENSIONS = ['.md', '.markdown']
const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']
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
  return String(value || '')
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

function normalizePath(path) {
  const decoded = safeDecodeURIComponent(String(path || ''))
  const parts = []
  for (const part of decoded.replaceAll('\\', '/').split('/')) {
    if (!part || part === '.') continue
    if (part === '..') {
      if (parts.length === 0) return ''
      parts.pop()
      continue
    }
    parts.push(part)
  }
  return parts.join('/')
}

function safeDecodeURIComponent(value) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function dirname(path) {
  const normalized = normalizePath(path)
  const slashIndex = normalized.lastIndexOf('/')
  return slashIndex >= 0 ? normalized.slice(0, slashIndex) : ''
}

function joinPath(basePath, relativePath) {
  return normalizePath(basePath ? `${basePath}/${relativePath}` : relativePath)
}

function isImageFileName(fileName) {
  return IMAGE_EXTENSIONS.includes(getFileExtension(fileName))
}

function getFilePath(file) {
  return normalizePath(file.webkitRelativePath || file.relativePath || file.name)
}

async function createAssetMap(files) {
  const assets = new Map()
  await Promise.all(files.map(async file => {
    const path = getFilePath(file)
    if (!path || !isImageFileName(path)) return
    const asset = await uploadImageAsset(file, path)
    assets.set(path, asset.url)
  }))
  return assets
}

function pickMarkdownFile(files) {
  const markdownFiles = files.filter(file => MARKDOWN_EXTENSIONS.includes(getFileExtension(file.name)))
  if (markdownFiles.length === 0) return null
  return markdownFiles.find(file => /(^|\/)readme\.md$/i.test(getFilePath(file))) || markdownFiles[0]
}

function createImageResolver(markdownPath, assets) {
  const basePath = dirname(markdownPath)

  return (rawSrc) => {
    const src = String(rawSrc || '').trim()
    if (/^(https?:\/\/|blob:)/i.test(src)) return src
    if (/^(data:|javascript:|file:)/i.test(src)) return ''
    const withoutHash = src.split('#')[0].split('?')[0]
    const assetPath = joinPath(basePath, withoutHash)
    return assets.get(assetPath) || assets.get(normalizePath(withoutHash)) || ''
  }
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

  const pageResults = await Promise.all(
    Array.from({ length: pdf.numPages }, async (_, i) => {
      const pageNumber = i + 1
      const page = await pdf.getPage(pageNumber)
      const content = await page.getTextContent()
      const text = content.items.map(item => item.str).join(' ').replace(/\s+/g, ' ').trim()
      return text ? `<section class="pdf-page"><h2>第 ${pageNumber} 页</h2>${paragraphsToHtml(text)}</section>` : null
    })
  )
  const pages = pageResults.filter(Boolean)

  if (pages.length === 0) {
    throw new Error('PDF 未提取到可阅读文本，扫描版 PDF 请先 OCR 后再上传')
  }

  return pages.join('')
}

async function parseZipBundle(file) {
  const { default: JSZip } = await import('jszip')
  const zip = await JSZip.loadAsync(await file.arrayBuffer())
  const files = []

  await Promise.all(Object.values(zip.files).map(async entry => {
    if (entry.dir) return
    const blob = await entry.async('blob')
    files.push(new File([blob], entry.name.split('/').pop(), {
      type: blob.type,
      lastModified: file.lastModified,
    }))
    files[files.length - 1].relativePath = entry.name
  }))

  return parseMarkdownBundle(files, file.name)
}

async function parseMarkdownBundle(files, fallbackName) {
  const markdownFile = pickMarkdownFile(files)
  if (!markdownFile) {
    throw new Error('未找到 Markdown 文件，请上传包含 .md 的文件夹或 zip')
  }

  const assets = await createAssetMap(files)
  const markdownPath = getFilePath(markdownFile)
  const rawMarkdown = await markdownFile.text()
  const html = markdownToHtml(rawMarkdown, {
    resolveImageUrl: createImageResolver(markdownPath, assets),
  })

  return {
    name: markdownFile.name || fallbackName,
    html,
    rawText: rawMarkdown,
    assets,
  }
}

export async function parseDocumentFile(file) {
  const extension = getFileExtension(file.name)

  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    throw new Error(`请上传 ${SUPPORTED_DOCUMENT_LABEL} 格式的文件`)
  }

  if (extension === '.docx') return { name: file.name, html: await parseDocx(file) }
  if (extension === '.pdf') return { name: file.name, html: await parsePdf(file) }
  if (extension === '.zip') return parseZipBundle(file)

  const text = await file.text()
  if (MARKDOWN_EXTENSIONS.includes(extension)) {
    return {
      name: file.name,
      html: markdownToHtml(text),
      rawText: text,
      assets: new Map(),
    }
  }
  return { name: file.name, html: paragraphsToHtml(text), rawText: text }
}

export async function parseDocumentSelection(fileList) {
  const files = Array.from(fileList || [])
  if (files.length === 0) return null
  if (files.length === 1 && !files[0].webkitRelativePath) return parseDocumentFile(files[0])
  return parseMarkdownBundle(files, files[0]?.name)
}
