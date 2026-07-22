import { useState, useRef, useEffect, Fragment } from 'react'
import useKnowledgeBase from '../hooks/useKnowledgeBase'

function AuditLogSection({ auditLog, auditLogStatus, fetchAuditLog }) {
  const [expanded, setExpanded] = useState(false)
  const [expandedRow, setExpandedRow] = useState(null)

  function handleToggle() {
    const next = !expanded
    setExpanded(next)
    if (next) fetchAuditLog()
  }

  const isLoading = auditLogStatus === 'loading'
  const isError = auditLogStatus === 'error'

  return (
    <div className="kb-section">
      <button className="kb-subsection-toggle" onClick={handleToggle}>
        <h3 className="kb-section-title">Approval Audit Log</h3>
        <span className={`kb-arrow${expanded ? ' kb-arrow-open' : ''}`}>&#9654;</span>
      </button>

      {expanded && (
        <div className="kb-audit-body">
          {isLoading && <p className="kb-empty">Loading audit log...</p>}
          {isError && <p className="kb-status-err">Failed to load audit log.</p>}
          {!isLoading && !isError && auditLog.length === 0 && (
            <p className="kb-empty">No approvals logged yet.</p>
          )}
          {!isLoading && !isError && auditLog.length > 0 && (
            <div className="registry-scroll">
              <table className="audit-log-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Asset Type</th>
                    <th>File</th>
                    <th>Changes Made</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.map((entry, idx) => {
                    const isRowExpanded = expandedRow === idx
                    return (
                      <Fragment key={idx}>
                        <tr
                          className="audit-log-row"
                          onClick={() => setExpandedRow(isRowExpanded ? null : idx)}
                        >
                          <td>{entry.timestamp}</td>
                          <td>{entry.asset_type}</td>
                          <td className="audit-log-file">{entry.file_path}</td>
                          <td>{entry.changes_from_claude}</td>
                        </tr>
                        {isRowExpanded && (
                          <tr className="audit-log-diff-row">
                            <td colSpan={4}>
                              {(entry.diff ?? []).length === 0 ? (
                                <p className="kb-empty">No field-level changes recorded.</p>
                              ) : (
                                <table className="audit-diff-table">
                                  <thead>
                                    <tr>
                                      <th>Criterion</th>
                                      <th>Field</th>
                                      <th>Claude's Value</th>
                                      <th>Approved Value</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {entry.diff.map((d, di) => (
                                      <tr key={di}>
                                        <td>{d.criterion_id}</td>
                                        <td>{d.field}</td>
                                        <td>{JSON.stringify(d.claude_value)}</td>
                                        <td>{JSON.stringify(d.approved_value)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TrainedModelsSection({ trainedModels, trainedModelsStatus }) {
  const isLoading = trainedModelsStatus === 'loading'
  const isError = trainedModelsStatus === 'error'

  return (
    <div className="kb-section">
      <h3 className="kb-section-title">
        Trained Models <span className="kb-badge">Auto-generated</span>
      </h3>
      {isLoading && <p className="kb-empty">Loading trained models...</p>}
      {isError && <p className="kb-status-err">Failed to load trained models.</p>}
      {!isLoading && !isError && trainedModels.length === 0 && (
        <p className="kb-empty">
          No trained models yet. Train one with: python -m rul.dynamic_train_cli --file &lt;historical_data.xlsx&gt;
        </p>
      )}
      {!isLoading && !isError && trainedModels.length > 0 && (
        <div className="registry-scroll">
          <table className="audit-log-table">
            <thead>
              <tr>
                <th>Asset Type</th>
                <th>Trained At</th>
                <th>Feature Count</th>
              </tr>
            </thead>
            <tbody>
              {trainedModels.map(m => (
                <tr key={m.filename}>
                  <td>{m.asset_type}</td>
                  <td>{m.trained_at}</td>
                  <td>{m.feature_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

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
    auditLog,
    auditLogStatus,
    fetchAuditLog,
    trainedModels,
    trainedModelsStatus,
    fetchTrainedModels,
  } = useKnowledgeBase()

  useEffect(() => {
    if (expanded) {
      fetchDocuments()
      fetchTrainedModels()
    }
  }, [expanded, fetchDocuments, fetchTrainedModels])

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

          {/* Trained Models */}
          <TrainedModelsSection
            trainedModels={trainedModels}
            trainedModelsStatus={trainedModelsStatus}
          />

          {/* Approval Audit Log */}
          <AuditLogSection
            auditLog={auditLog}
            auditLogStatus={auditLogStatus}
            fetchAuditLog={fetchAuditLog}
          />
        </div>
      )}
    </section>
  )
}
