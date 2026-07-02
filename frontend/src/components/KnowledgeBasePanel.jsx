import { useState, useRef, useEffect } from 'react'
import useKnowledgeBase from '../hooks/useKnowledgeBase'

export default function KnowledgeBasePanel() {
  const [expanded, setExpanded] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileRef = useRef(null)

  const {
    documents,
    uploadStatus,
    errorMessage,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
  } = useKnowledgeBase()

  useEffect(() => {
    if (expanded) fetchDocuments()
  }, [expanded, fetchDocuments])

  function handleFileSelect(file) {
    if (file && file.name.toLowerCase().endsWith('.pdf')) {
      uploadDocument(file)
    }
  }

  const isUploading = uploadStatus === 'uploading' || uploadStatus === 'ingesting'
  const isDone = uploadStatus === 'done'
  const isError = uploadStatus === 'error'

  return (
    <section className="card kb-panel">
      <button className="kb-toggle" onClick={() => setExpanded(e => !e)}>
        <span className="section-title kb-title">RAG Knowledge Base</span>
        <span className={`kb-arrow${expanded ? ' kb-arrow-open' : ''}`}>&#9654;</span>
      </button>

      {expanded && (
        <div className="kb-body">
          <p className="section-sub kb-sub">
            Upload OEM manuals to ground AI explanations in manufacturer documentation.
            Failure cases and criteria configs are auto-generated.
          </p>

          {/* OEM Manuals */}
          <div className="kb-section">
            <h3 className="kb-section-title">OEM Manuals</h3>

            <div
              className={`drop-zone kb-drop-zone${isDragOver ? ' drop-zone-active' : ''}`}
              onDrop={e => { e.preventDefault(); setIsDragOver(false); handleFileSelect(e.dataTransfer.files[0]) }}
              onDragOver={e => { e.preventDefault(); setIsDragOver(true) }}
              onDragLeave={() => setIsDragOver(false)}
              onClick={() => !isUploading && fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                onChange={e => handleFileSelect(e.target.files[0])}
                hidden
              />
              <span className="drop-zone-text">
                {isUploading ? 'Ingesting document...' : 'Drop PDF here or click to browse'}
              </span>
            </div>

            {isDone && (
              <p className="kb-status-ok">Document ingested and added to knowledge base</p>
            )}
            {isError && (
              <p className="kb-status-err">{errorMessage}</p>
            )}

            {documents.manuals.length === 0 ? (
              <p className="kb-empty">No manuals uploaded yet.</p>
            ) : (
              <ul className="kb-file-list">
                {documents.manuals.map(name => (
                  <li key={name} className="kb-file-item">
                    <span className="kb-file-name">{name}</span>
                    <button
                      className="kb-delete-btn"
                      onClick={() => deleteDocument(name, 'manual')}
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Failure Cases */}
          <div className="kb-section">
            <h3 className="kb-section-title">
              Failure Cases <span className="kb-badge">Auto-generated</span>
            </h3>
            {documents.failure_cases.length === 0 ? (
              <p className="kb-empty">No failure cases generated yet.</p>
            ) : (
              <ul className="kb-file-list">
                {documents.failure_cases.map(name => (
                  <li key={name} className="kb-file-item kb-file-item-ro">
                    <span className="kb-file-name">{name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Criteria Configs */}
          <div className="kb-section">
            <h3 className="kb-section-title">
              Criteria Configs <span className="kb-badge">Auto-generated</span>
            </h3>
            {documents.criteria_configs.length === 0 ? (
              <p className="kb-empty">No criteria configs stored yet.</p>
            ) : (
              <ul className="kb-file-list">
                {documents.criteria_configs.map(name => (
                  <li key={name} className="kb-file-item kb-file-item-ro">
                    <span className="kb-file-name">{name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
