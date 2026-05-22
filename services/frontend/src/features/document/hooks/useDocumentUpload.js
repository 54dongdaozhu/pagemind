import { useCallback, useState } from 'react'
import { parseDocumentSelection, SUPPORTED_DOCUMENT_LABEL } from '../documentParser'


export function useDocumentUpload({ docContentRef, onBeforeLoad, onHtmlLoaded }) {
  const [fileName, setFileName] = useState('')
  const [docLoaded, setDocLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFileUpload = useCallback(async (event) => {
    const files = event.target.files
    if (!files || files.length === 0) return

    setError('')
    setLoading(true)
    setFileName(files.length === 1 ? files[0].name : 'Markdown 文件夹')
    setDocLoaded(false)
    onBeforeLoad()

    if (docContentRef.current) docContentRef.current.innerHTML = ''

    try {
      const document = await parseDocumentSelection(files)
      if (!document) return
      setFileName(document.name)
      if (docContentRef.current) docContentRef.current.innerHTML = document.html
      setDocLoaded(true)
      await onHtmlLoaded(document)
    } catch (err) {
      setError('文档解析失败：' + (err.message || `请上传 ${SUPPORTED_DOCUMENT_LABEL} 格式的文件`))
    } finally {
      setLoading(false)
      event.target.value = ''
    }
  }, [docContentRef, onBeforeLoad, onHtmlLoaded])

  const showParsedDocument = useCallback(({ name, html }) => {
    setError('')
    setLoading(false)
    setFileName(name)
    setDocLoaded(true)
    if (docContentRef.current) docContentRef.current.innerHTML = html
  }, [docContentRef])

  const clearDocument = useCallback(() => {
    setError('')
    setLoading(false)
    setFileName('')
    setDocLoaded(false)
    if (docContentRef.current) docContentRef.current.innerHTML = ''
  }, [docContentRef])

  return {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
    showParsedDocument,
    clearDocument,
  }
}
