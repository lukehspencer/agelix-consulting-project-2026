import { useState, useCallback } from 'react'

export default function useKnowledgeBase() {
  const [documents, setDocuments] = useState({ manuals: [], failure_cases: [], criteria_configs: [] })
  const [uploadStatus, setUploadStatus] = useState('idle')
  const [errorMessage, setErrorMessage] = useState(null)
  const [auditLog, setAuditLog] = useState([])
  const [auditLogStatus, setAuditLogStatus] = useState('idle')

  const fetchAuditLog = useCallback(async () => {
    setAuditLogStatus('loading')
    try {
      const res = await fetch('/upload/audit-log')
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setAuditLog(data.entries ?? [])
      setAuditLogStatus('done')
    } catch (err) {
      console.error('Failed to fetch audit log:', err)
      setAuditLogStatus('error')
    }
  }, [])

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch('/rag/documents')
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setDocuments(data)
    } catch (err) {
      console.error('Failed to fetch RAG documents:', err)
    }
  }, [])

  const uploadDocument = useCallback(async (file) => {
    setUploadStatus('uploading')
    setErrorMessage(null)
    const form = new FormData()
    form.append('file', file)
    try {
      setUploadStatus('ingesting')
      const res = await fetch('/rag/upload-document', { method: 'POST', body: form })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Upload failed (${res.status})`)
      }
      setUploadStatus('done')
      await fetchDocuments()
    } catch (err) {
      setUploadStatus('error')
      setErrorMessage(err.message)
    }
  }, [fetchDocuments])

  const deleteDocument = useCallback(async (filename, doc_type) => {
    setErrorMessage(null)
    try {
      const res = await fetch('/rag/document', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, doc_type }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Delete failed (${res.status})`)
      }
      await fetchDocuments()
    } catch (err) {
      setErrorMessage(err.message)
    }
  }, [fetchDocuments])

  return {
    documents,
    uploadStatus,
    errorMessage,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    auditLog,
    auditLogStatus,
    fetchAuditLog,
  }
}
