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

function pmConfidenceDot(confidence) {
  if (confidence === 'high') return { color: '#16a34a', label: 'High' }
  if (confidence === 'medium') return { color: '#ca8a04', label: 'Medium' }
  return { color: '#6b7280', label: 'Low' }
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

function ModeBanner({ mode, trainingResult, modelInfo }) {
  if (mode === 'training') {
    return (
      <div
        className="mode-banner mode-banner-training"
        style={{
          background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '8px',
          padding: '0.75rem 1rem', marginBottom: '0.75rem', fontSize: '0.85rem', color: '#166534',
        }}
      >
        <p style={{ margin: 0, fontWeight: 700 }}>Training mode detected — True_RUL_Days found</p>
        {trainingResult && (
          <p style={{ margin: '0.3rem 0 0' }}>
            Model trained on {trainingResult.n_train_samples} samples — Test RMSE:{' '}
            {Math.round(trainingResult.test_rmse * 365)} days
          </p>
        )}
        <p style={{ margin: '0.3rem 0 0' }}>Model saved for future predictions on this asset type.</p>
        <p style={{ margin: '0.3rem 0 0', fontStyle: 'italic' }}>
          Note: to predict on new data, upload a file without True_RUL_Days.
        </p>
      </div>
    )
  }

  if (mode === 'prediction') {
    return (
      <div
        className="mode-banner mode-banner-prediction"
        style={{
          background: '#eff6ff', border: '1px solid #93c5fd', borderRadius: '8px',
          padding: '0.75rem 1rem', marginBottom: '0.75rem', fontSize: '0.85rem', color: '#1e40af',
        }}
      >
        <p style={{ margin: 0, fontWeight: 700 }}>Prediction mode — using pre-trained model</p>
        <p style={{ margin: '0.3rem 0 0' }}>
          Model: {modelInfo?.model_asset_type ?? 'Unknown'} — trained on{' '}
          {modelInfo?.feature_count ?? '?'} features
        </p>
        <p style={{ margin: '0.3rem 0 0', fontStyle: 'italic' }}>
          Note: predictions are based on patterns learned from historical run-to-failure data.
        </p>
      </div>
    )
  }

  return null
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
  approvedCriteriaConfig,
  trainingResult,
  errorMessage,
  isPredicting,
  hasResults,
  criteriaApproved,
  approvalChanges,
  mode,
  modelInfo,
  onApproveCriteria,
  onEditCriteria,
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
  const [approvedPmInterval, setApprovedPmInterval] = useState(90)
  const fileRef = useRef(null)

  // Re-seeds the editable draft every time we enter (or re-enter) the review
  // screen: from Claude's draft on first analysis, or from the last approved
  // config whenever "Edit Criteria" reopens this screen for a re-approval.
  useEffect(() => {
    if (!criteriaApproved) {
      const base = approvedCriteriaConfig ?? criteriaConfig
      setEditedCriteriaConfig(base ? cloneConfig(base) : null)
      setApprovedPmInterval(
        approvedCriteriaConfig?.approved_pm_interval_days
        ?? base?.recommended_pm_interval_days
        ?? 90
      )
    }
  }, [criteriaApproved, approvedCriteriaConfig, criteriaConfig])

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
    await onApproveCriteria(editedCriteriaConfig, approvedPmInterval)
    setIsApproving(false)
  }

  async function handlePredict() {
    console.log('[UploadPanel] Run Risk & RUL Analysis clicked', { ahpValid, ahpWeights, ahpCr })

    // Always run against the approved config, never against unsaved edits --
    // this button is only shown once criteriaApproved is true.
    const activeConfig = approvedCriteriaConfig
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
  const pmConfidence = pmConfidenceDot(editedCriteriaConfig?.pm_interval_confidence)

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

      {/* States 2-4: Review & Approve Criteria, then Run / Re-run Analysis */}
      {isReady && !criteriaApproved && editedCriteriaConfig && (
        <div className="criteria-preview">
          <h3 className="criteria-preview-title">
            {approvedCriteriaConfig
              ? <>Editing the approved criteria for {editedCriteriaConfig.asset_type}. Adjust thresholds, names, or defaults, then re-approve to unlock analysis again.</>
              : <>Claude has inferred {editedCriteriaConfig.criteria.length} AHP criteria for{' '}
                  {editedCriteriaConfig.asset_type}. Review and adjust before approving.</>}
          </h3>

          <ModeBanner mode={mode} trainingResult={trainingResult} modelInfo={modelInfo} />

          <div className="criteria-card criteria-review-card pm-interval-section" style={{ marginBottom: '0.75rem' }}>
            <div className="criteria-card-header">
              <span style={{ fontWeight: 700, fontSize: '0.88rem', color: '#1e293b', flex: 1 }}>
                PM Interval
              </span>
              {editedCriteriaConfig.pm_interval_source === 'inferred_from_log' ? (
                <span className="criteria-badge badge-auto">Inferred from Log</span>
              ) : (
                <span className="criteria-badge" style={{ background: '#f1f5f9', color: '#64748b' }}>
                  Default
                </span>
              )}
            </div>

            <p className="criteria-card-desc" style={{ fontStyle: 'italic' }}>
              Recommended number of days between preventive maintenance visits for this asset type.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
              <span
                style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: pmConfidence.color,
                }}
              />
              <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                {pmConfidence.label} confidence
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.82rem', color: '#475569', fontWeight: 600 }}>
                Interval (days)
              </label>
              <input
                type="number"
                min={7}
                max={730}
                className="pm-interval-input"
                value={approvedPmInterval}
                disabled={isApproving}
                onChange={e => setApprovedPmInterval(parseNumberInput(e.target.value))}
                style={{
                  width: '80px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontSize: '14px',
                  textAlign: 'center',
                }}
              />
              <span style={{ fontSize: '0.82rem', color: '#475569' }}>days</span>
            </div>

            <p style={{ margin: '0.4rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
              Claude suggests: {editedCriteriaConfig.recommended_pm_interval_days ?? 90} days
            </p>
          </div>

          <div className="criteria-cards">
            {editedCriteriaConfig.criteria.map(crit => (
              <CriteriaReviewCard
                key={crit.id}
                criterion={crit}
                disabled={isApproving}
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
              disabled={isApproving}
            >
              Reset to Claude's Suggestions
            </button>
            <button
              className="btn-approve"
              onClick={handleApprove}
              disabled={isApproving || !isCriteriaConfigValid(editedCriteriaConfig)}
            >
              {isApproving ? 'Locking...' : 'Approve and Lock Criteria'}
            </button>
          </div>
        </div>
      )}

      {isReady && criteriaApproved && (
        <div className="criteria-preview">
          <div className="approval-confirmation">
            Criteria Approved ✓
            {approvalChanges > 0
              ? ` — ${approvalChanges} value${approvalChanges !== 1 ? 's' : ''} changed this round`
              : ' — accepted as-is'}
          </div>

          {!hasResults && (
            <p className="criteria-preview-title">
              Fill in the AHP pairwise comparison matrix above, then run the analysis.
            </p>
          )}

          {errorMessage && (
            <div className="upload-predict-error">
              {errorMessage}
            </div>
          )}

          <div className="upload-panel-actions">
            <button
              className="btn-primary"
              disabled={!ahpValid || isPredicting}
              onClick={handlePredict}
            >
              {isPredicting ? 'Running analysis...' : hasResults ? 'Re-run Analysis' : 'Run Risk and RUL Analysis'}
            </button>
            <button className="btn-reset" onClick={onEditCriteria} disabled={isPredicting}>
              Edit Criteria
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
