import { useState, useCallback } from 'react'

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

  const uploadAndAnalyze = useCallback(async (file) => {
    setUploadStatus('uploading')
    setErrorMessage(null)
    setUploadedFileName(file.name)
    console.log('[useUpload] uploadAndAnalyze: file =', file.name)

    const formData = new FormData()
    formData.append('file', file)

    try {
      setUploadStatus('analyzing')

      const res = await fetch('/upload/analyze', {
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
      setUploadStatus('ready')
    } catch (err) {
      setErrorMessage(err.message)
      setUploadStatus('error')
    }
  }, [])

  const approveCriteria = useCallback(async (editedCriteriaConfig) => {
    if (!modelPath) return null

    setErrorMessage(null)

    try {
      const res = await fetch('/upload/approve-criteria', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          criteria_config: editedCriteriaConfig,
          model_path: modelPath,
          file_path: uploadedFileName ? `data/raw/uploads/${uploadedFileName}` : null,
        }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Approve failed (${res.status})`)
      }

      const data = await res.json()
      setCriteriaApproved(true)
      setApprovedCriteriaConfig(data.criteria_config)
      setApprovalChanges(data.changes_from_original)
      return data
    } catch (err) {
      setErrorMessage(err.message)
      return null
    }
  }, [modelPath, uploadedFileName])

  const predictAll = useCallback(async (weights, cr, manualScores) => {
    console.log('[useUpload] predictAll called with weights:', weights, '| cr:', cr, '| manualScores:', manualScores)

    if (!modelPath || !uploadedFileName) {
      console.warn('[useUpload] predictAll: missing modelPath or uploadedFileName — aborting', { modelPath, uploadedFileName })
      return
    }

    if (!criteriaApproved) {
      console.warn('[useUpload] predictAll: criteria not approved — aborting')
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
      }
      console.log('[useUpload] predictAll: POST /upload/predict-all body =', JSON.stringify(body))

      const res = await fetch('/upload/predict-all', {
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
    } catch (err) {
      console.error('[useUpload] predictAll: caught error =', err.message)
      setErrorMessage(err.message)
    } finally {
      setIsPredicting(false)
    }
  }, [modelPath, uploadedFileName, criteriaApproved])

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
      const res = await fetch('/upload/explain', {
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
      const res = await fetch('/upload/explain-breach', {
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
    approveCriteria,
    uploadAndAnalyze,
    predictAll,
    explainAsset,
    explainBreach,
    resetUpload,
  }
}
