import { useCallback, useState } from 'react'
import mammoth from 'mammoth'


export function useDocumentUpload({ docContentRef, onBeforeLoad, onHtmlLoaded }) {
  const [fileName, setFileName] = useState('')
  const [docLoaded, setDocLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFileUpload = useCallback(async (event) => {
    const file = event.target.files[0]
    if (!file) return
    if (!file.name.endsWith('.docx')) {
      setError('请上传 .docx 格式的文件')
      return
    }

    setError('')
    setLoading(true)
    setFileName(file.name)
    setDocLoaded(false)
    onBeforeLoad()

    if (docContentRef.current) docContentRef.current.innerHTML = ''

    try {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.convertToHtml({ arrayBuffer })
      if (docContentRef.current) docContentRef.current.innerHTML = result.value
      setDocLoaded(true)
      await onHtmlLoaded(result.value)
    } catch (err) {
      setError('文档解析失败：' + err.message)
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
