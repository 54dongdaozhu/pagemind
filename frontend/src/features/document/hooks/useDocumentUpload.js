import { useCallback, useState } from 'react'
import { parseDocumentFile, SUPPORTED_DOCUMENT_LABEL } from '../documentParser'


export function useDocumentUpload({ docContentRef, onBeforeLoad, onHtmlLoaded }) {
  const [fileName, setFileName] = useState('')
  const [docLoaded, setDocLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFileUpload = useCallback(async (event) => {
    const file = event.target.files[0]
    if (!file) return

    setError('')
    setLoading(true)
    setFileName(file.name)
    setDocLoaded(false)
    onBeforeLoad()

    if (docContentRef.current) docContentRef.current.innerHTML = ''

    try {
      const html = await parseDocumentFile(file)
      if (docContentRef.current) docContentRef.current.innerHTML = html
      setDocLoaded(true)
      await onHtmlLoaded(html, file)
    } catch (err) {
      setError('文档解析失败：' + (err.message || `请上传 ${SUPPORTED_DOCUMENT_LABEL} 格式的文件`))
    } finally {
      setLoading(false)
    }
  }, [docContentRef, onBeforeLoad, onHtmlLoaded])

  return {
    fileName,
    docLoaded,
    loading,
    error,
    handleFileUpload,
  }
}
