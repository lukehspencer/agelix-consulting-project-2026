import { useState, useRef, useEffect } from 'react'

function cloneConfig(config) {
  return config ? JSON.parse(JSON.stringify(config)) : config
}

function isThresholdsValid(thresholds) {
  if (!Array.isArray(thresholds) || thresholds.length < 2) return false
  return thresholds.every((t, idx) => {
    const scoreOk = Number.isFinite(t.score) && t.score >= 1 && t.score <= 10
    if (idx === thresholds.length - 1) return scoreOk
    return scoreOk && Number.isFinite(t.max)
  })
}

function isCriteriaConfigValid(config) {
  if (!config?.criteria?.length) return false
  return config.criteria.every(crit => crit.manual_input || isThresholdsValid(crit.thresholds))
}

function parseNumberInput(raw) {
  return raw === '' ? '' : Number(raw)
}

function ThresholdEditor({ thresholds, disabled, onChange, onAdd, onDelete }) {
  const canDelete = thresholds.length > 2

  return (
    <div className="threshold-editor">
      <table className="threshold-table">
        <thead>
          <tr>
            <th>Max Value</th>
            <th>Risk Score</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {thresholds.map((t, idx) => {
            const isCatchAll = idx === thresholds.length - 1
            return (
              <tr key={idx}>
                <td>
                  {isCatchAll ? (
                    <span className="threshold-catchall">catch-all</span>
                  ) : (
                    <input
                      type="number"
                      className="threshold-input"
                      value={t.max ?? ''}
                      disabled={disabled}
                      onChange={e => onChange(idx, 'max', parseNumberInput(e.target.value))}
                    />
                  )}
                </td>
                <td>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    className="threshold-input"
                    value={t.score ?? ''}
                    disabled={disabled}
                    onChange={e => onChange(idx, 'score', parseNumberInput(e.target.value))}
                  />
                </td>
                <td>
                  {!isCatchAll && (
                    <button
                      type="button"
                      className="btn-delete-row"
                      disabled={disabled || !canDelete}
                      onClick={() => onDelete(idx)}
                      aria-label="Delete threshold"
                    >
                      &times;
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <button type="button" className="btn-add-threshold" disabled={disabled} onClick={onAdd}>
        + Add Threshold
      </button>
    </div>
  )
}

function PenaltyEditor({ penalties, disabled, onBandChange }) {
  if (!penalties?.length) return null

  return (
    <details className="penalty-editor">
      <summary>Advanced: Penalty Bands</summary>
      {penalties.map((pen, pi) => (
        <div key={pi} className="penalty-block">
          <div className="penalty-column-name">{pen.column}</div>
          <table className="threshold-table">
            <thead>
              <tr>
                <th>Max Value</th>
                <th>Penalty</th>
              </tr>
            </thead>
            <tbody>
              {pen.bands.map((band, bi) => {
                const isCatchAll = bi === pen.bands.length - 1
                return (
                  <tr key={bi}>
                    <td>
                      {isCatchAll ? (
                        <span className="threshold-catchall">catch-all</span>
                      ) : (
                        <input
                          type="number"
                          className="threshold-input"
                          value={band.max ?? ''}
                          disabled={disabled}
                          onChange={e => onBandChange(pi, bi, 'max', parseNumberInput(e.target.value))}
                        />
                      )}
                    </td>
                    <td>
                      <input
                        type="number"
                        className="threshold-input"
                        value={band.penalty ?? ''}
                        disabled={disabled}
                        onChange={e => onBandChange(pi, bi, 'penalty', parseNumberInput(e.target.value))}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </details>
  )
}

function CriteriaReviewCard({
  criterion, disabled,
  onNameChange, onUiLabelChange, onDefaultScoreChange,
  onThresholdChange, onAddThreshold, onDeleteThreshold, onPenaltyBandChange,
}) {
  return (
    <div className="criteria-card criteria-review-card">
      <div className="criteria-card-header">
        <span className="criteria-card-id">{criterion.id}</span>
        <input
          type="text"
          className="criteria-name-input"
          value={criterion.name}
          disabled={disabled}
          onChange={e => onNameChange(e.target.value)}
        />
        <span className={`criteria-badge ${criterion.manual_input ? 'badge-manual' : 'badge-auto'}`}>
          {criterion.manual_input ? 'Manual Input' : `Auto-derived from ${criterion.primary_column}`}
        </span>
      </div>

      <p className="criteria-card-desc">{criterion.description}</p>

      {criterion.manual_input ? (
        <div className="criteria-manual-review">
          <label className="manual-label">
            Default Score: {criterion.default_score}
          </label>
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={criterion.default_score}
            disabled={disabled}
            onChange={e => onDefaultScoreChange(parseInt(e.target.value, 10))}
            className="default-score-slider"
          />
          <label className="manual-label">UI Label</label>
          <input
            type="text"
            className="ui-label-input"
            value={criterion.ui_label ?? ''}
            disabled={disabled}
            onChange={e => onUiLabelChange(e.target.value)}
          />
        </div>
      ) : (
        <>
          <ThresholdEditor
            thresholds={criterion.thresholds}
            disabled={disabled}
            onChange={onThresholdChange}
            onAdd={onAddThreshold}
            onDelete={onDeleteThreshold}
          />
          <PenaltyEditor
            penalties={criterion.penalties}
            disabled={disabled}
            onBandChange={onPenaltyBandChange}
          />
        </>
      )}
    </div>
  )
}

export default function UploadPanel({
  uploadStatus,
  criteriaConfig,
  trainingResult,
  errorMessage,
  isPredicting,
  hasPredictions,
  criteriaApproved,
  approvalChanges,
  onApproveCriteria,
  onAnalyze,
  onPredict,
  onReset,
  ahpValid,
  ahpWeights,
  ahpCr,
}) {
  const [selectedFile, setSelectedFile] = useState(null)
  const [manualScores, setManualScores] = useState({})
  const [isDragOver, setIsDragOver] = useState(false)
  const [editedCriteriaConfig, setEditedCriteriaConfig] = useState(null)
  const [isApproving, setIsApproving] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    setEditedCriteriaConfig(criteriaConfig ? cloneConfig(criteriaConfig) : null)
  }, [criteriaConfig])

  function handleFileSelect(file) {
    if (file && file.name.endsWith('.xlsx')) {
      setSelectedFile(file)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    handleFileSelect(file)
  }

  function handleDragOver(e) {
    e.preventDefault()
    setIsDragOver(true)
  }

  function handleDragLeave() {
    setIsDragOver(false)
  }

  async function handleAnalyze() {
    if (!selectedFile) return
    await onAnalyze(selectedFile)
  }

  function updateCriterion(id, updater) {
    setEditedCriteriaConfig(prev => {
      if (!prev) return prev
      return {
        ...prev,
        criteria: prev.criteria.map(c => (c.id === id ? updater(c) : c)),
      }
    })
  }

  function handleNameChange(id, value) {
    updateCriterion(id, c => ({ ...c, name: value }))
  }

  function handleUiLabelChange(id, value) {
    updateCriterion(id, c => ({ ...c, ui_label: value }))
  }

  function handleDefaultScoreChange(id, value) {
    updateCriterion(id, c => ({ ...c, default_score: value }))
  }

  function handleThresholdChange(id, idx, field, value) {
    updateCriterion(id, c => ({
      ...c,
      thresholds: c.thresholds.map((t, i) => (i === idx ? { ...t, [field]: value } : t)),
    }))
  }

  function handleAddThreshold(id) {
    updateCriterion(id, c => {
      const thresholds = [...c.thresholds]
      const catchAll = thresholds.pop()
      thresholds.push({ max: 0, score: 5 })
      thresholds.push(catchAll)
      return { ...c, thresholds }
    })
  }

  function handleDeleteThreshold(id, idx) {
    updateCriterion(id, c => {
      if (c.thresholds.length <= 2 || idx === c.thresholds.length - 1) return c
      return { ...c, thresholds: c.thresholds.filter((_, i) => i !== idx) }
    })
  }

  function handlePenaltyBandChange(id, penIdx, bandIdx, field, value) {
    updateCriterion(id, c => ({
      ...c,
      penalties: c.penalties.map((p, pi) => {
        if (pi !== penIdx) return p
        return {
          ...p,
          bands: p.bands.map((b, bi) => (bi === bandIdx ? { ...b, [field]: value } : b)),
        }
      }),
    }))
  }

  function handleResetCriteria() {
    setEditedCriteriaConfig(cloneConfig(criteriaConfig))
  }

  async function handleApprove() {
    if (!editedCriteriaConfig) return
    setIsApproving(true)
    await onApproveCriteria(editedCriteriaConfig)
    setIsApproving(false)
  }

  async function handlePredict() {
    console.log('[UploadPanel] Run Risk & RUL Analysis clicked', { ahpValid, ahpWeights, ahpCr })

    const activeConfig = editedCriteriaConfig ?? criteriaConfig
    const n = activeConfig?.criteria?.length ?? 5
    const weights = ahpWeights ?? Array(n).fill(+(1 / n).toFixed(6))
    const cr = ahpCr ?? 0.0
    const scores = { ...manualScores }

    if (activeConfig) {
      for (const crit of activeConfig.criteria) {
        if (crit.manual_input && !(crit.id in scores)) {
          scores[crit.id] = crit.default_score
        }
      }
    }

    console.log('[UploadPanel] calling onPredict with:', { weights, cr, scores })
    await onPredict(weights, cr, scores)
    console.log('[UploadPanel] onPredict returned')
  }

  function handleReset() {
    onReset()
    setSelectedFile(null)
    setManualScores({})
  }

  const isAnalyzing = uploadStatus === 'uploading' || uploadStatus === 'analyzing' || uploadStatus === 'training'
  const isReady = uploadStatus === 'ready'
  const isError = uploadStatus === 'error'

  return (
    <section className="card upload-panel">
      <h2 className="section-title">Upload Custom Asset Data</h2>
      <p className="section-sub">
        Upload an Excel file with Operational Telemetry and Failure & Maintenance Logs sheets.
        Claude will infer AHP criteria and train a RUL model for your asset type.
      </p>

      {/* Section 1: File Drop Zone */}
      {!isReady && (
        <div
          className={`drop-zone${isDragOver ? ' drop-zone-active' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            onChange={e => handleFileSelect(e.target.files[0])}
            hidden
          />
          {selectedFile
            ? <span className="drop-zone-file">{selectedFile.name}</span>
            : <span className="drop-zone-text">Drop .xlsx file here or click to browse</span>}
        </div>
      )}

      {!isReady && !isAnalyzing && !isError && (
        <div className="upload-panel-actions">
          <button
            className="btn-primary"
            disabled={!selectedFile}
            onClick={handleAnalyze}
          >
            Analyze Dataset
          </button>
        </div>
      )}

      {isAnalyzing && (
        <div className="upload-status-msg">
          {uploadStatus === 'uploading' && 'Uploading file...'}
          {uploadStatus === 'analyzing' && 'Claude is analyzing your asset data...'}
          {uploadStatus === 'training' && 'Training RUL model on your dataset...'}
        </div>
      )}

      {isError && (
        <div className="upload-error-block">
          <p className="upload-error-text">{errorMessage}</p>
          <button className="btn-reset" onClick={handleReset}>Try Again</button>
        </div>
      )}

      {/* Section 2: Review & Approve Criteria */}
      {isReady && editedCriteriaConfig && (
        <div className="criteria-preview">
          <h3 className="criteria-preview-title">
            Claude has inferred {editedCriteriaConfig.criteria.length} AHP criteria for{' '}
            {editedCriteriaConfig.asset_type}. Review and adjust before approving.
          </h3>

          {trainingResult && (
            <div className="training-strip">
              Model trained on {trainingResult.n_train_samples} samples — Test RMSE: {Math.round(trainingResult.test_rmse * 365)} days
            </div>
          )}

          <div className="criteria-cards">
            {editedCriteriaConfig.criteria.map(crit => (
              <CriteriaReviewCard
                key={crit.id}
                criterion={crit}
                disabled={criteriaApproved}
                onNameChange={v => handleNameChange(crit.id, v)}
                onUiLabelChange={v => handleUiLabelChange(crit.id, v)}
                onDefaultScoreChange={v => handleDefaultScoreChange(crit.id, v)}
                onThresholdChange={(idx, field, v) => handleThresholdChange(crit.id, idx, field, v)}
                onAddThreshold={() => handleAddThreshold(crit.id)}
                onDeleteThreshold={idx => handleDeleteThreshold(crit.id, idx)}
                onPenaltyBandChange={(pi, bi, field, v) => handlePenaltyBandChange(crit.id, pi, bi, field, v)}
              />
            ))}
          </div>

          {errorMessage && (
            <div className="upload-predict-error">
              {errorMessage}
            </div>
          )}

          <div className="approval-actions">
            <button
              className="btn-reset"
              onClick={handleResetCriteria}
              disabled={criteriaApproved || isApproving}
            >
              Reset to Claude's Suggestions
            </button>
            <button
              className="btn-approve"
              onClick={handleApprove}
              disabled={criteriaApproved || isApproving || !isCriteriaConfigValid(editedCriteriaConfig)}
            >
              {isApproving ? 'Locking...' : criteriaApproved ? 'Criteria Approved ✓' : 'Approve and Lock Criteria'}
            </button>
          </div>

          {criteriaApproved && (
            <div className="approval-confirmation">
              Criteria Approved ✓
              {approvalChanges > 0
                ? ` — ${approvalChanges} value${approvalChanges !== 1 ? 's' : ''} changed from Claude's suggestion`
                : ' — Claude\'s original suggestion accepted as-is'}
            </div>
          )}

          <div className="upload-panel-actions">
            <button
              className="btn-primary"
              disabled={!ahpValid || !criteriaApproved || isPredicting}
              onClick={handlePredict}
            >
              {isPredicting ? 'Running analysis...' : 'Run Risk and RUL Analysis'}
            </button>
            <button className="btn-reset" onClick={handleReset} disabled={isPredicting}>
              Reset
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
