import { useState, useRef } from 'react'
import useUpload from '../hooks/useUpload'

export default function UploadPanel({ onAssetsReady, ahpValid, ahpWeights, ahpCr }) {
  const {
    uploadStatus, criteriaConfig, trainingResult,
    uploadedAssets, predictedAssets, modelPath, errorMessage,
    uploadAndAnalyze, predictAll, resetUpload,
  } = useUpload()

  const [selectedFile, setSelectedFile] = useState(null)
  const [manualScores, setManualScores] = useState({})
  const [isDragOver, setIsDragOver] = useState(false)
  const fileRef = useRef(null)

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
    await uploadAndAnalyze(selectedFile)
  }

  async function handlePredict() {
    const weights = ahpWeights ?? [0.2, 0.2, 0.2, 0.2, 0.2]
    const cr = ahpCr ?? 0.0
    const scores = { ...manualScores }

    if (criteriaConfig) {
      for (const crit of criteriaConfig.criteria) {
        if (crit.manual_input && !(crit.id in scores)) {
          scores[crit.id] = crit.default_score
        }
      }
    }

    await predictAll(weights, cr, scores)
  }

  function handleReset() {
    resetUpload()
    setSelectedFile(null)
    setManualScores({})
  }

  const isAnalyzing = uploadStatus === 'uploading' || uploadStatus === 'analyzing' || uploadStatus === 'training'
  const isReady = uploadStatus === 'ready'
  const isError = uploadStatus === 'error'

  if (predictedAssets.length > 0 && onAssetsReady) {
    onAssetsReady(predictedAssets, criteriaConfig, modelPath)
  }

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

      {/* Section 2: Criteria Preview */}
      {isReady && criteriaConfig && (
        <>
          <div className="criteria-preview">
            <h3 className="criteria-preview-title">
              AI-Identified AHP Criteria for {criteriaConfig.asset_type}
            </h3>

            {trainingResult && (
              <div className="training-strip">
                Trained on {trainingResult.n_train_samples} samples. Test RMSE: {trainingResult.test_rmse.toFixed(4)} years
              </div>
            )}

            <div className="criteria-cards">
              {criteriaConfig.criteria.map(crit => (
                <div key={crit.id} className="criteria-card">
                  <div className="criteria-card-header">
                    <span className="criteria-card-id">{crit.id}</span>
                    <span className="criteria-card-name">{crit.name}</span>
                    <span className={`criteria-badge ${crit.manual_input ? 'badge-manual' : 'badge-auto'}`}>
                      {crit.manual_input
                        ? 'Manual Input'
                        : `Auto-derived from ${crit.primary_column}`}
                    </span>
                  </div>
                  <p className="criteria-card-desc">{crit.description}</p>
                  {crit.manual_input ? (
                    <div className="criteria-manual-input">
                      <label>{crit.ui_label} (1-10):</label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={manualScores[crit.id] ?? crit.default_score}
                        onChange={e => setManualScores(prev => ({
                          ...prev,
                          [crit.id]: parseInt(e.target.value) || crit.default_score,
                        }))}
                        className="manual-number"
                      />
                    </div>
                  ) : (
                    <div className="criteria-threshold-range">
                      Thresholds: {crit.thresholds[0]?.max != null
                        ? `${crit.thresholds[0].max} (score ${crit.thresholds[0].score})`
                        : ''} to {crit.thresholds[crit.thresholds.length - 1]?.score != null
                        ? `catch-all (score ${crit.thresholds[crit.thresholds.length - 1].score})`
                        : ''}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Section 3: Failure Modes */}
            {criteriaConfig.failure_modes && (
              <div className="failure-modes-strip">
                Identified Failure Modes: {criteriaConfig.failure_modes.join(' . ')}
              </div>
            )}

            <div className="upload-panel-actions">
              <button
                className="btn-primary"
                disabled={!ahpValid}
                onClick={handlePredict}
              >
                Run Risk and RUL Analysis
              </button>
              <button className="btn-reset" onClick={handleReset}>
                Reset
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
