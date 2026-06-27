import { useState, useCallback } from 'react'

export default function useUpload() {
  const [uploadStatus, setUploadStatus] = useState('idle')
  const [criteriaConfig, setCriteriaConfig] = useState(null)
  const [schemaSummary, setSchemaSummary] = useState(null)
  const [trainingResult, setTrainingResult] = useState(null)
  const [uploadedAssets, setUploadedAssets] = useState([])
  const [predictedAssets, setPredictedAssets] = useState([])
  const [modelPath, setModelPath] = useState(null)
  const [errorMessage, setErrorMessage] = useState(null)

  const uploadAndAnalyze = useCallback(async (file) => {
    setUploadStatus('uploading')
    setErrorMessage(null)

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
      setUploadStatus('ready')
    } catch (err) {
      setErrorMessage(err.message)
      setUploadStatus('error')
    }
  }, [])

  const predictAll = useCallback(async (weights, cr, manualScores) => {
    if (!modelPath || !schemaSummary) return

    try {
      const filePath = schemaSummary._file_path ?? uploadedAssets[0]?._file_path
      const analyzeAsset = uploadedAssets[0] ?? {}
      const resolvedFilePath = filePath ?? `data/raw/uploads/${analyzeAsset.asset_id ?? 'unknown'}.xlsx`

      const res = await fetch('/upload/predict-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: resolvedFilePath,
          weights,
          cr,
          manual_scores: manualScores,
          model_path: modelPath,
        }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Predict failed (${res.status})`)
      }

      const data = await res.json()
      setPredictedAssets(data.assets)
    } catch (err) {
      setErrorMessage(err.message)
    }
  }, [modelPath, schemaSummary, uploadedAssets])

  const explainAsset = useCallback(async (assetPayload) => {
    if (!criteriaConfig) return null

    const sensorContext = {}
    for (const crit of criteriaConfig.criteria) {
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

    const body = {
      pump: assetPayload,
      weights: assetPayload.weights ?? [0.2, 0.2, 0.2, 0.2, 0.2],
      scores: assetPayload.scores
        ? Object.values(assetPayload.scores)
        : [5, 5, 5, 5, 5],
      risk_factor: assetPayload.risk_factor ?? 5.0,
      predicted_rul: assetPayload.rul_years ?? 0,
      ci_low: assetPayload.ci_low ?? 0,
      ci_high: assetPayload.ci_high ?? 1.5,
      cr: assetPayload.cr ?? 0.05,
      asset_type: criteriaConfig.asset_type ?? 'Unknown Asset',
      failure_modes: criteriaConfig.failure_modes ?? [],
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
  }, [criteriaConfig])

  const resetUpload = useCallback(() => {
    setUploadStatus('idle')
    setCriteriaConfig(null)
    setSchemaSummary(null)
    setTrainingResult(null)
    setUploadedAssets([])
    setPredictedAssets([])
    setModelPath(null)
    setErrorMessage(null)
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
    uploadAndAnalyze,
    predictAll,
    explainAsset,
    resetUpload,
  }
}
