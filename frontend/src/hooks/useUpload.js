import { useState, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

// FastAPI error bodies come in two shapes: a plain string detail (from our own
// HTTPException calls) or a list of Pydantic validation-error objects (from
// automatic request validation). Coercing either straight into `new Error()`
// silently stringifies objects/arrays to "[object Object]" -- extract a real
// readable string here instead.
function extractErrorDetail(detail, fallback) {
  const d = detail?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(e => e?.msg ?? String(e)).join('; ')
  return fallback
}

export default function useUpload() {
  const [uploadStatus, setUploadStatus] = useState('idle')
  const [criteriaConfig, setCriteriaConfig] = useState(null)
  const [schemaSummary, setSchemaSummary] = useState(null)
  const [trainingResult, setTrainingResult] = useState(null)
  const [uploadedAssets, setUploadedAssets] = useState([])
  const [predictedAssets, setPredictedAssets] = useState([])
  const [modelPath, setModelPath] = useState(null)
  const [uploadedFileName, setUploadedFileName] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [isPredicting, setIsPredicting] = useState(false)
  const [criteriaApproved, setCriteriaApproved] = useState(false)
  const [approvedCriteriaConfig, setApprovedCriteriaConfig] = useState(null)
  const [approvalChanges, setApprovalChanges] = useState(0)
  const [hasResults, setHasResults] = useState(false)

  const uploadAndAnalyze = useCallback(async (file) => {
    setUploadStatus('uploading')
    setErrorMessage(null)
    setUploadedFileName(file.name)
    console.log('[useUpload] uploadAndAnalyze: file =', file.name)

    const formData = new FormData()
    formData.append('file', file)

    try {
      setUploadStatus('analyzing')

      const res = await fetch(`${API_BASE}/upload/analyze`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Upload failed (${res.status})`)
      }

      const data = await res.json()

      setCriteriaConfig(data.criteria_config)
      setSchemaSummary(data.schema_summary)
      setTrainingResult(data.training_result)
      setUploadedAssets(data.assets)
      setModelPath(data.model_path)
      setPredictedAssets([])
      setCriteriaApproved(false)
      setApprovedCriteriaConfig(null)
      setApprovalChanges(0)
      setHasResults(false)
      setUploadStatus('ready')
    } catch (err) {
      setErrorMessage(err.message)
      setUploadStatus('error')
    }
  }, [])

  const approveCriteria = useCallback(async (editedCriteriaConfig, pmIntervalDays) => {
    if (!modelPath) return null

    setErrorMessage(null)

    // editedCriteriaConfig must be a plain object here, not an already-
    // JSON.stringify'd string -- JSON.stringify(body) below serializes it
    // exactly once. UploadPanel builds it via JSON.parse(JSON.stringify(...))
    // (a deep clone), so it is always a plain object by the time it gets here.
    const requestBody = {
      criteria_config: editedCriteriaConfig,
      model_path: modelPath,
      file_path: uploadedFileName ? `data/raw/uploads/${uploadedFileName}` : null,
      // On re-approval, diff against the previously approved version (not
      // Claude's original draft) so the change count reflects this round.
      previous_config: approvedCriteriaConfig ?? null,
      approved_pm_interval_days: pmIntervalDays ?? null,
    }
    console.log('[useUpload] approveCriteria: request body =', requestBody)

    try {
      const res = await fetch(`${API_BASE}/upload/approve-criteria`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      })

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}))
        console.error('[useUpload] approveCriteria: error response', res.status, errBody)
        throw new Error(extractErrorDetail(errBody, `Approve failed (${res.status})`))
      }

      const data = await res.json()
      console.log('[useUpload] approveCriteria: response =', data)
      setCriteriaApproved(true)
      // Merge the server-confirmed approved PM interval onto the config so
      // every downstream consumer (predict-all, DynamicAssetTable) can read
      // it straight off approvedCriteriaConfig without a separate prop.
      setApprovedCriteriaConfig({
        ...data.criteria_config,
        approved_pm_interval_days: data.approved_pm_interval_days ?? null,
      })
      setApprovalChanges(data.changes_from_original)
      return data
    } catch (err) {
      setErrorMessage(err.message)
      return null
    }
  }, [modelPath, uploadedFileName, approvedCriteriaConfig])

  // Reopens the approval screen (pre-populated with the current approved config)
  // without discarding existing results -- only threshold/name edits require
  // going through approve-criteria again; weight-only re-runs never need this.
  const editCriteria = useCallback(() => {
    setErrorMessage(null)
    setCriteriaApproved(false)
  }, [])

  const predictAll = useCallback(async (weights, cr, manualScores) => {
    console.log('[useUpload] predictAll called with weights:', weights, '| cr:', cr, '| manualScores:', manualScores)

    if (!modelPath || !uploadedFileName) {
      console.warn('[useUpload] predictAll: missing modelPath or uploadedFileName — aborting', { modelPath, uploadedFileName })
      return
    }

    // First approval is always required before any prediction can run. Once
    // approved at least once, weight-only re-runs never need re-approval --
    // only a fresh threshold/name edit (which clears criteriaApproved via
    // editCriteria()) blocks this until the user re-approves.
    if (!approvedCriteriaConfig) {
      console.warn('[useUpload] predictAll: criteria have never been approved — aborting')
      setErrorMessage('Criteria have not been approved. Complete the review step before running predictions.')
      return
    }

    setIsPredicting(true)
    setErrorMessage(null)

    const resolvedFilePath = `data/raw/uploads/${uploadedFileName}`

    try {
      const body = {
        file_path: resolvedFilePath,
        weights,
        cr,
        manual_scores: manualScores,
        model_path: modelPath,
        approved_criteria_config: approvedCriteriaConfig,
      }
      console.log('[useUpload] predictAll: POST /upload/predict-all body =', JSON.stringify(body))

      const res = await fetch(`${API_BASE}/upload/predict-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}))
        console.error('[useUpload] predictAll: error response', res.status, errBody)
        const d = errBody?.detail
        const msg = typeof d === 'string'
          ? d
          : Array.isArray(d)
            ? d.map(e => e?.msg ?? String(e)).join('; ')
            : `Predict failed (${res.status})`
        throw new Error(msg)
      }

      const data = await res.json()
      console.log('[useUpload] predictAll: response weights used, assets count =', data.assets?.length,
        '| first asset risk_factor =', data.assets?.[0]?.risk_factor)
      setPredictedAssets(data.assets)
      setHasResults(true)
    } catch (err) {
      console.error('[useUpload] predictAll: caught error =', err.message)
      setErrorMessage(err.message)
    } finally {
      setIsPredicting(false)
    }
  }, [modelPath, uploadedFileName, approvedCriteriaConfig])

  const explainAsset = useCallback(async (assetPayload) => {
    const activeCriteriaConfig = approvedCriteriaConfig ?? criteriaConfig
    if (!activeCriteriaConfig) return null

    const sensorContext = {}
    for (const crit of activeCriteriaConfig.criteria) {
      if (crit.manual_input) continue
      const col = crit.primary_column
      if (col) {
        const meanKey = `rolling_${col}_mean`
        if (meanKey in assetPayload) {
          sensorContext[col] = assetPayload[meanKey]
        }
      }
      for (const sc of crit.secondary_columns ?? []) {
        const scMeanKey = `rolling_${sc}_mean`
        if (scMeanKey in assetPayload) {
          sensorContext[sc] = assetPayload[scMeanKey]
        }
      }
    }

    const n = activeCriteriaConfig?.criteria?.length ?? 5
    const body = {
      pump: assetPayload,
      weights: assetPayload.weights ?? Array(n).fill(+(1 / n).toFixed(6)),
      scores: assetPayload.scores
        ? Object.values(assetPayload.scores)
        : Array(n).fill(5),
      risk_factor: assetPayload.risk_factor ?? 5.0,
      predicted_rul: assetPayload.rul_years ?? 0,
      ci_low: assetPayload.ci_low ?? 0,
      ci_high: assetPayload.ci_high ?? 1.5,
      cr: assetPayload.cr ?? 0.05,
      asset_type: activeCriteriaConfig.asset_type ?? 'Unknown Asset',
      failure_modes: activeCriteriaConfig.failure_modes ?? [],
      sensor_context: sensorContext,
    }

    try {
      const res = await fetch(`${API_BASE}/upload/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Explain failed (${res.status})`)
      }

      const data = await res.json()
      return data.explanation
    } catch (err) {
      return `Error: ${err.message}`
    }
  }, [criteriaConfig, approvedCriteriaConfig])

  const explainBreach = useCallback(async (asset, cr) => {
    const activeCriteriaConfig = approvedCriteriaConfig ?? criteriaConfig
    if (!activeCriteriaConfig) return null

    const body = {
      asset_snapshot: asset,
      breaches: asset.breaches ?? [],
      criteria_config: activeCriteriaConfig,
      model_path: modelPath ?? 'rul/dynamic_model.pkl',
      cr: cr ?? 0,
    }

    try {
      const res = await fetch(`${API_BASE}/upload/explain-breach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Explain breach failed (${res.status})`)
      }

      const data = await res.json()
      return data.breach_alerts
    } catch (err) {
      return [{
        criterion_id: null,
        criterion_name: null,
        column: null,
        severity: 'high',
        alert_text: `Error: ${err.message}`,
      }]
    }
  }, [criteriaConfig, approvedCriteriaConfig, modelPath])

  const resetUpload = useCallback(() => {
    setUploadStatus('idle')
    setCriteriaConfig(null)
    setSchemaSummary(null)
    setTrainingResult(null)
    setUploadedAssets([])
    setPredictedAssets([])
    setModelPath(null)
    setUploadedFileName(null)
    setErrorMessage(null)
    setIsPredicting(false)
    setCriteriaApproved(false)
    setApprovedCriteriaConfig(null)
    setApprovalChanges(0)
    setHasResults(false)
  }, [])

  return {
    uploadStatus,
    criteriaConfig,
    schemaSummary,
    trainingResult,
    uploadedAssets,
    predictedAssets,
    modelPath,
    errorMessage,
    isPredicting,
    criteriaApproved,
    approvedCriteriaConfig,
    approvalChanges,
    hasResults,
    approveCriteria,
    editCriteria,
    uploadAndAnalyze,
    predictAll,
    explainAsset,
    explainBreach,
    resetUpload,
  }
}
