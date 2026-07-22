import { useState, useEffect, useCallback } from 'react'
import AHPMatrix from './AHPMatrix'
import UploadPanel from './UploadPanel'
import KnowledgeBasePanel from './KnowledgeBasePanel'
import DynamicAssetTable from './DynamicAssetTable'
import useUpload from '../hooks/useUpload'

function buildSensorContext(asset, criteriaConfig) {
  const ctx = {}
  if (!criteriaConfig?.criteria) return ctx
  for (const crit of criteriaConfig.criteria) {
    if (crit.manual_input) continue
    const col = crit.primary_column
    if (col) {
      const key = `rolling_${col}_mean`
      if (key in asset) ctx[col] = asset[key]
    }
    for (const sc of crit.secondary_columns ?? []) {
      const key = `rolling_${sc}_mean`
      if (key in asset) ctx[sc] = asset[key]
    }
  }
  return ctx
}

export default function Dashboard() {
  // --- Uploaded mode: single useUpload instance owned by Dashboard ---
  const {
    uploadStatus, criteriaConfig, trainingResult,
    uploadedAssets, predictedAssets, modelPath, errorMessage, isPredicting,
    criteriaApproved, approvedCriteriaConfig, approvalChanges, hasResults,
    mode, modelInfo,
    approveCriteria, editCriteria,
    uploadAndAnalyze, predictAll, resetUpload, explainAsset, explainBreach,
  } = useUpload()

  // SME-approved config drives all downstream scoring/display once approval is complete;
  // the raw draft is only used by UploadPanel's own review screen before that point.
  const activeCriteriaConfig = approvedCriteriaConfig ?? criteriaConfig

  const [uploadedExplanations, setUploadedExplanations] = useState({})
  const [uploadedBreachAlerts, setUploadedBreachAlerts] = useState({})
  const [uploadedAhpResult, setUploadedAhpResult] = useState(null)

  useEffect(() => {
    console.log('[Dashboard] predictedAssets updated, count =', predictedAssets.length,
      '| first risk_factor =', predictedAssets[0]?.risk_factor)
    if (predictedAssets.length > 0) {
      setUploadedExplanations({})
      setUploadedBreachAlerts({})
    }
  }, [predictedAssets])

  const handleDynamicExplain = useCallback(async (asset) => {
    if (!activeCriteriaConfig) return
    const sensorContext = buildSensorContext(asset, activeCriteriaConfig)

    const explanation = await explainAsset({
      ...asset,
      asset_type: activeCriteriaConfig.asset_type,
      failure_modes: activeCriteriaConfig.failure_modes,
      sensor_context: sensorContext,
    })

    setUploadedExplanations(prev => ({ ...prev, [asset.asset_id]: explanation }))
  }, [activeCriteriaConfig, explainAsset])

  const handleExplainBreach = useCallback(async (asset) => {
    if (!activeCriteriaConfig) return
    const alerts = await explainBreach(asset, uploadedAhpResult?.cr ?? 0)
    setUploadedBreachAlerts(prev => ({ ...prev, [asset.asset_id]: alerts }))
  }, [activeCriteriaConfig, explainBreach, uploadedAhpResult])

  return (
    <>
      {activeCriteriaConfig && (
        <AHPMatrix
          criteriaNames={activeCriteriaConfig.criteria.map(c => c.name)}
          onWeightsUpdate={setUploadedAhpResult}
        />
      )}

      <UploadPanel
        uploadStatus={uploadStatus}
        criteriaConfig={criteriaConfig}
        approvedCriteriaConfig={approvedCriteriaConfig}
        trainingResult={trainingResult}
        errorMessage={errorMessage}
        isPredicting={isPredicting}
        hasResults={hasResults}
        criteriaApproved={criteriaApproved}
        approvalChanges={approvalChanges}
        mode={mode}
        modelInfo={modelInfo}
        onApproveCriteria={approveCriteria}
        onEditCriteria={editCriteria}
        onAnalyze={uploadAndAnalyze}
        onPredict={predictAll}
        onReset={resetUpload}
        ahpValid={uploadedAhpResult?.valid ?? false}
        ahpWeights={uploadedAhpResult?.weights ?? null}
        ahpCr={uploadedAhpResult?.cr ?? null}
      />

      <KnowledgeBasePanel />

      {predictedAssets.length > 0 && (
        <DynamicAssetTable
          assets={predictedAssets}
          criteriaConfig={activeCriteriaConfig}
          onExplain={handleDynamicExplain}
          explanations={uploadedExplanations}
          onExplainBreach={handleExplainBreach}
          breachAlerts={uploadedBreachAlerts}
        />
      )}
    </>
  )
}
