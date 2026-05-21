import { markdownToHtml } from '../../utils/markdown'
import { uploadImageAsset } from '../../api/assets'

const SUPPORTED_EXTENSIONS = ['.docx', '.pdf', '.txt', '.md', '.markdown', '.zip']
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

const UPLOAD_CONCURRENCY = 5
const PDF_IMAGE_LIMIT = 20

function base64ToFile(base64, contentType, name) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new File([new Blob([bytes], { type: contentType })], name, { type: contentType })
}

function assetIdFromUrl(url) {
  const match = String(url || '').match(/\/api\/assets\/images\/([a-f0-9]{32})/)
  return match ? match[1] : null
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
  const collectedImages = []

  const result = await mammoth.convertToHtml(
    { arrayBuffer },
    {
      styleMap: DOCX_STYLE_MAP,
      convertImage: mammoth.images.inline(async (element) => {
        const base64 = await element.read('base64')
        const contentType = element.contentType || 'image/png'
        if (contentType === 'image/svg+xml') return { src: '' }
        const idx = collectedImages.length
        collectedImages.push({ base64, contentType, idx })
        return { src: `data:${contentType};base64,${base64}` }
      }),
    }
  )

  const html = result.value

  // Upload to asset server in background — don't block rendering
  const imagesPromise = collectedImages.length === 0 ? Promise.resolve([]) : (async () => {
    const images = []
    let i = 0
    const worker = async () => {
      while (i < collectedImages.length) {
        const img = collectedImages[i++]
        try {
          const ext = img.contentType.split('/')[1]?.split('+')[0] || 'png'
          const imageFile = base64ToFile(img.base64, img.contentType, `docx-image-${img.idx}.${ext}`)
          const uploaded = await uploadImageAsset(imageFile, `docx-image-${img.idx}`)
          const assetId = assetIdFromUrl(uploaded.url)
          if (assetId) images.push({ asset_id: assetId, page_num: null, alt_text: '' })
        } catch { /* upload failed; skip */ }
      }
    }
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, collectedImages.length) }, worker))
    return images
  })()

  return { html, imagesPromise }
}

async function flattenOutline(pdf, nodes, level = 1) {
  const result = []
  for (const node of nodes) {
    let pageNum = null
    try {
      let dest = node.dest
      if (typeof dest === 'string') dest = await pdf.getDestination(dest)
      if (Array.isArray(dest) && dest[0] != null) {
        pageNum = await pdf.getPageIndex(dest[0]) + 1
      }
    } catch { /* dest may be unresolvable; skip */ }
    if (node.title) result.push({ text: node.title, level, pageNum })
    if (node.items?.length) {
      result.push(...await flattenOutline(pdf, node.items, level + 1))
    }
  }
  return result
}

function buildPageHtml(textContent, viewport, pageNum) {
  const raw = textContent.items
    .filter(item => item.str.trim())
    .map(item => ({
      str: item.str,
      x: item.transform[4],
      y: viewport.height - item.transform[5],
      fontSize: Math.abs(item.transform[3]) || 1,
      width: item.width,
    }))
  if (!raw.length) return null

  raw.sort((a, b) => a.y - b.y || a.x - b.x)

  const sizes = raw.map(i => i.fontSize).sort((a, b) => a - b)
  const median = sizes[Math.floor(sizes.length / 2)]
  const lineGap = Math.max(median * 0.6, 2)

  const lines = []
  for (const item of raw) {
    const last = lines[lines.length - 1]
    if (last && Math.abs(item.y - last.y) <= lineGap) {
      last.items.push(item)
    } else {
      lines.push({ y: item.y, items: [item] })
    }
  }

  function joinLine(items) {
    items.sort((a, b) => a.x - b.x)
    let text = items[0].str
    for (let i = 1; i < items.length; i++) {
      const prev = items[i - 1]
      const gap = items[i].x - (prev.x + prev.width)
      if (gap > median * 0.3 && !text.endsWith(' ') && !items[i].str.startsWith(' ')) {
        text += ' '
      }
      text += items[i].str
    }
    return text.trim()
  }

  const parts = [`<section class="pdf-page" id="pdf-page-${pageNum}">`]
  let inP = false

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const text = joinLine(line.items)
    if (!text) continue
    const maxSize = Math.max(...line.items.map(it => it.fontSize))
    const gapAbove = i > 0 ? line.y - lines[i - 1].y : 0
    const isHeading = maxSize > median * 1.25

    if (isHeading) {
      if (inP) { parts.push('</p>'); inP = false }
      const h = maxSize > median * 1.8 ? 1 : maxSize > median * 1.5 ? 2 : 3
      parts.push(`<h${h}>${escapeHtml(text)}</h${h}>`)
    } else if (!inP || gapAbove > median * 1.5) {
      if (inP) parts.push('</p>')
      parts.push(`<p>${escapeHtml(text)}`)
      inP = true
    } else {
      const sep = parts[parts.length - 1].endsWith('-') ? '' : ' '
      parts[parts.length - 1] += sep + escapeHtml(text)
    }
  }
  if (inP) parts.push('</p>')
  parts.push('</section>')
  return parts.join('')
}

async function extractPdfPageImages(page, pageNum, pdfjsLib) {
  const pageImages = []
  try {
    const opList = await page.getOperatorList()
    const seen = new Set()
    for (let j = 0; j < opList.fnArray.length; j++) {
      if (opList.fnArray[j] !== pdfjsLib.OPS.paintImageXObject) continue
      const name = opList.argsArray[j][0]
      if (seen.has(name)) continue
      seen.add(name)
      const imgData = await Promise.race([
        new Promise((resolve) => { try { page.objs.get(name, resolve) } catch { resolve(null) } }),
        new Promise((resolve) => setTimeout(() => resolve(null), 5000)),
      ])
      if (!imgData?.data || imgData.width < 20 || imgData.height < 20) continue
      try {
        const canvas = document.createElement('canvas')
        canvas.width = imgData.width
        canvas.height = imgData.height
        const ctx = canvas.getContext('2d')
        const id = ctx.createImageData(imgData.width, imgData.height)
        id.data.set(imgData.data)
        ctx.putImageData(id, 0, 0)
        const base64 = canvas.toDataURL('image/png').split(',')[1]
        if (base64) pageImages.push({ base64, pageNum, name })
      } catch { /* canvas conversion failed; skip */ }
    }
  } catch { /* op list extraction failed; skip */ }
  return pageImages
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
      const pageNum = i + 1
      const page = await pdf.getPage(pageNum)
      const [textContent, viewport] = await Promise.all([
        page.getTextContent(),
        Promise.resolve(page.getViewport({ scale: 1 })),
      ])
      return buildPageHtml(textContent, viewport, pageNum)
    })
  )
  const pages = pageResults.filter(Boolean)

  if (pages.length === 0) {
    throw new Error('PDF 未提取到可阅读文本，扫描版 PDF 请先 OCR 后再上传')
  }

  const rawOutline = await pdf.getOutline()
  const outline = rawOutline ? await flattenOutline(pdf, rawOutline) : []

  // Extract and upload images in background — don't block text rendering
  const imagesPromise = (async () => {
    const images = []
    const allPageImages = []
    for (let i = 0; i < pdf.numPages && allPageImages.length < PDF_IMAGE_LIMIT; i++) {
      const page = await pdf.getPage(i + 1)
      const pageImages = await extractPdfPageImages(page, i + 1, pdfjsLib)
      for (const img of pageImages) {
        if (allPageImages.length >= PDF_IMAGE_LIMIT) break
        allPageImages.push(img)
      }
    }
    if (allPageImages.length > 0) {
      let idx = 0
      const worker = async () => {
        while (idx < allPageImages.length) {
          const img = allPageImages[idx++]
          try {
            const imageFile = base64ToFile(img.base64, 'image/png', `pdf-p${img.pageNum}-${img.name}.png`)
            const uploaded = await uploadImageAsset(imageFile, `pdf-p${img.pageNum}-${img.name}`)
            const assetId = assetIdFromUrl(uploaded.url)
            if (assetId) images.push({ asset_id: assetId, page_num: img.pageNum, alt_text: '' })
          } catch { /* upload failed; skip */ }
        }
      }
      await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, allPageImages.length) }, worker))
    }
    return images
  })()

  return { html: pages.join(''), outline, imagesPromise }
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

  // Build blob URL map immediately — no upload needed for rendering
  const imageFiles = files.filter(f => isImageFileName(getFilePath(f)))
  const assets = new Map()
  for (const file of imageFiles) {
    assets.set(getFilePath(file), URL.createObjectURL(file))
  }

  const markdownPath = getFilePath(markdownFile)
  const rawMarkdown = await markdownFile.text()
  const html = markdownToHtml(rawMarkdown, {
    resolveImageUrl: createImageResolver(markdownPath, assets),
  })

  // Upload to asset server in background — don't block rendering
  const imagesPromise = imageFiles.length === 0 ? Promise.resolve([]) : (async () => {
    const images = []
    let idx = 0
    const worker = async () => {
      while (idx < imageFiles.length) {
        const file = imageFiles[idx++]
        const path = getFilePath(file)
        try {
          const asset = await uploadImageAsset(file, path)
          const assetId = assetIdFromUrl(asset.url)
          if (assetId) images.push({ asset_id: assetId, page_num: null, alt_text: '' })
        } catch { /* upload failed; skip */ }
      }
    }
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, imageFiles.length) }, worker))
    return images
  })()

  return {
    name: markdownFile.name || fallbackName,
    html,
    rawText: rawMarkdown,
    assets,
    imagesPromise,
  }
}

export async function parseDocumentFile(file) {
  const extension = getFileExtension(file.name)

  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    throw new Error(`请上传 ${SUPPORTED_DOCUMENT_LABEL} 格式的文件`)
  }

  if (extension === '.docx') {
    const { html, imagesPromise } = await parseDocx(file)
    return { name: file.name, html, imagesPromise }
  }
  if (extension === '.pdf') {
    const pdfResult = await parsePdf(file)
    return { name: file.name, ...pdfResult }
  }
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
