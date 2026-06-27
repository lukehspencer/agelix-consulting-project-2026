import { useState, useRef, useEffect, useCallback } from 'react'
import AHPMatrix from './AHPMatrix'
import ManualScoreInputs from './ManualScoreInputs'
import WeightDisplay from './WeightDisplay'
import AssetRegistry from './AssetRegistry'
import RiskRanking from './RiskRanking'
import CriteriaContribution from './CriteriaContribution'
import RiskScatterPlot from './RiskScatterPlot'
import RULDisplay from './RULDisplay'
import RULExplanation from './RULExplanation'
import DataUpload from './DataUpload'
import UploadPanel from './UploadPanel'
import DynamicAssetTable from './DynamicAssetTable'
import DynamicAHPMatrix from './DynamicAHPMatrix'
import { useRiskScores } from '../hooks/useRiskScores'
import { useRUL } from '../hooks/useRUL'
import useUpload from '../hooks/useUpload'

const SCORE_KEYS = [
  'score_criticality', 'score_condition', 'score_failure_probability',
  'score_downtime_impact', 'score_maintenance_cost_trend',
]
const CRITERIA_LABELS = [
  'Criticality', 'Condition', 'Failure Probability',
  'Downtime Impact', 'Maintenance Cost Trend',
]
const EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]

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
  const [mode, setMode] = useState('default')

  // --- Existing Phase 1+2 state (unchanged) ---
  const [ahpResult, setAhpResult] = useState(null)
  const [history, setHistory] = useState([])
  const pendingLogRef = useRef(null)

  const [manualScores, setManualScores] = useState({ c1: 7, c4: 6 })
  const [manualAssets, setManualAssets] = useState(null)
  const [manualLoading, setManualLoading] = useState(false)
  const [hasManualOverride, setHasManualOverride] = useState(false)
  const manualPendingLogRef = useRef(false)

  const [customPumps, setCustomPumps] = useState(null)
  const [customAssets, setCustomAssets] = useState(null)
  const [uploadInfo, setUploadInfo] = useState(null)
  const [scoringCustom, setScoringCustom] = useState(false)
  const [scoringError, setScoringError] = useState(null)
  const uploadPendingLogRef = useRef(false)

  const weights = ahpResult?.weights ?? null
  const weightsKey = weights ? JSON.stringify(weights) : ''

  const { assets: defaultAssets, loading: defaultLoading, error: defaultError } = useRiskScores(weights)

  const baseAssets = hasManualOverride ? (manualAssets ?? []) : defaultAssets
  const baseLoading = hasManualOverride ? manualLoading : defaultLoading

  const assets = customAssets ?? baseAssets
  const loading = customPumps ? scoringCustom : baseLoading
  const error = customPumps ? scoringError : defaultError

  const cr = ahpResult?.cr ?? null
  const {
    rulPredictions, rulExplanations, fetchExplanation,
    isLoadingPredictions, isLoadingExplanation, error: rulError,
  } = useRUL(weights, cr, assets)

  function handleWeightsUpdate(data) {
    setAhpResult(data)
    pendingLogRef.current = {
      timestamp: new Date(),
      weights: data.weights,
      cr: data.cr,
      note: 'AHP matrix updated',
    }
  }

  useEffect(() => {
    if (!pendingLogRef.current || loading || !assets.length) return
    const pending = pendingLogRef.current
    pendingLogRef.current = null
    const sorted = [...assets].sort((a, b) => a.asset_id.localeCompare(b.asset_id))
    setHistory(prev => [{
      ...pending,
      pumpScores: sorted.map(a => ({ id: a.asset_id, risk: a.risk_factor })),
    }, ...prev])
  }, [assets, loading])

  function handleManualScoresUpdate(c1, c4) {
    setManualScores({ c1, c4 })
    setHasManualOverride(true)
    manualPendingLogRef.current = `C1=${c1}, C4=${c4}`
  }

  useEffect(() => {
    if (!hasManualOverride) return

    let cancelled = false
    setManualLoading(true)

    async function load() {
      const w = weights ?? EQUAL_WEIGHTS
      const params = w.map(v => `weights=${v}`).join('&')
      const url = `/ahp/assets?${params}&c1_score=${manualScores.c1}&c4_score=${manualScores.c4}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()

      if (cancelled) return

      setManualAssets(data)
      setManualLoading(false)

      if (manualPendingLogRef.current) {
        const note = manualPendingLogRef.current
        manualPendingLogRef.current = false
        const sorted = [...data].sort((a, b) => a.asset_id.localeCompare(b.asset_id))
        setHistory(prev => [{
          timestamp: new Date(),
          weights: [...w],
          cr: ahpResult?.cr ?? 0,
          pumpScores: sorted.map(a => ({ id: a.asset_id, risk: a.risk_factor })),
          note: `Manual override: ${note}`,
        }, ...prev])
      }
    }

    load().catch(err => {
      if (!cancelled) setManualLoading(false)
    })

    return () => { cancelled = true }
  }, [hasManualOverride, manualScores.c1, manualScores.c4, weightsKey])

  useEffect(() => {
    if (!customPumps) {
      setCustomAssets(null)
      setScoringError(null)
      return
    }

    let cancelled = false
    setScoringCustom(true)
    setScoringError(null)

    async function score() {
      const w = weights ?? EQUAL_WEIGHTS
      const today = new Date()

      const enriched = await Promise.all(customPumps.map(async pump => {
        const age_years = +(pump.total_runtime_hours / 22 / 365).toFixed(2)

        const res = await fetch('/ahp/score-asset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            asset_id: pump.asset_id,
            criticality_raw: pump.criticality_raw,
            condition_score: pump.condition_score,
            vibration_level: pump.vibration_level,
            seal_condition: pump.seal_condition,
            bearing_condition: pump.bearing_condition,
            age_years,
            expected_lifespan_years: pump.expected_lifespan_years ?? 20,
            number_of_failures_last_3yr: Math.round(pump.number_of_failures_last_3yr),
            days_since_maintenance: pump.days_since_maintenance,
            maintenance_frequency_days: pump.maintenance_frequency_days,
            downtime_impact_raw: pump.downtime_impact_raw,
            maintenance_cost_trend: pump.maintenance_cost_trend,
            maintenance_cost_last_year: pump.maintenance_cost_last_year,
          }),
        })
        if (!res.ok) throw new Error(`Scoring failed for ${pump.asset_id}`)
        const scores = await res.json()

        return { ...pump, ...scores, age_years, expected_lifespan_years: pump.expected_lifespan_years ?? 20 }
      }))

      if (cancelled) return

      const ranked = enriched.map(pump => {
        const scores = SCORE_KEYS.map(k => pump[k])
        const weighted_scores = scores.map((s, i) => +(w[i] * s).toFixed(6))
        const risk_factor = +weighted_scores.reduce((sum, v) => sum + v, 0).toFixed(4)
        return { ...pump, risk_factor, weights: [...w], scores, weighted_scores, criteria: CRITERIA_LABELS }
      }).sort((a, b) => b.risk_factor - a.risk_factor)

      if (cancelled) return

      setCustomAssets(ranked)
      setScoringCustom(false)

      if (uploadPendingLogRef.current) {
        const fn = uploadPendingLogRef.current
        uploadPendingLogRef.current = false
        const sorted = [...ranked].sort((a, b) => a.asset_id.localeCompare(b.asset_id))
        setHistory(prev => [{
          timestamp: new Date(),
          weights: [...w],
          cr: ahpResult?.cr ?? 0,
          pumpScores: sorted.map(a => ({ id: a.asset_id, risk: a.risk_factor })),
          note: `Uploaded: ${fn}`,
        }, ...prev])
      }
    }

    score().catch(err => {
      if (!cancelled) {
        setScoringError(err.message)
        setScoringCustom(false)
      }
    })

    return () => { cancelled = true }
  }, [customPumps, weightsKey])

  function handleDataLoaded(pumps, filename) {
    setCustomPumps(pumps)
    setUploadInfo({ filename, count: pumps.length })
    uploadPendingLogRef.current = filename
  }

  function handleDataReset() {
    setCustomPumps(null)
    setCustomAssets(null)
    setUploadInfo(null)
    setScoringError(null)
  }

  const avgRisk = assets.length
    ? assets.reduce((sum, a) => sum + a.risk_factor, 0) / assets.length
    : 0
  const highestRisk = assets.length ? assets[0] : null
  const highRiskCount = assets.filter(a => a.risk_factor > 7).length

  // --- Uploaded mode state ---
  const [uploadedPredictedAssets, setUploadedPredictedAssets] = useState([])
  const [uploadedCriteriaConfig, setUploadedCriteriaConfig] = useState(null)
  const [uploadedExplanations, setUploadedExplanations] = useState({})
  const [uploadedAhpResult, setUploadedAhpResult] = useState(null)

  const { explainAsset } = useUpload()

  const handleAssetsReady = useCallback((assetsData, config) => {
    setUploadedPredictedAssets(assetsData)
    setUploadedCriteriaConfig(config)
    setUploadedExplanations({})
  }, [])

  const handleDynamicExplain = useCallback(async (asset) => {
    if (!uploadedCriteriaConfig) return
    const sensorContext = buildSensorContext(asset, uploadedCriteriaConfig)

    const explanation = await explainAsset({
      ...asset,
      asset_type: uploadedCriteriaConfig.asset_type,
      failure_modes: uploadedCriteriaConfig.failure_modes,
      sensor_context: sensorContext,
    })

    setUploadedExplanations(prev => ({ ...prev, [asset.asset_id]: explanation }))
  }, [uploadedCriteriaConfig, explainAsset])

  const ahpValid = ahpResult?.valid ?? false

  return (
    <>
      {/* Mode Toggle */}
      <div className="mode-toggle">
        <button
          className={`mode-btn${mode === 'default' ? ' mode-btn-active' : ''}`}
          onClick={() => setMode('default')}
        >
          Default KSB Fleet
        </button>
        <button
          className={`mode-btn${mode === 'uploaded' ? ' mode-btn-active' : ''}`}
          onClick={() => setMode('uploaded')}
        >
          Upload Custom Data
        </button>
      </div>

      {mode === 'default' && (
        <>
          <AHPMatrix onWeightsUpdate={handleWeightsUpdate} />

          <ManualScoreInputs
            c1Value={manualScores.c1}
            c4Value={manualScores.c4}
            onManualScoresUpdate={handleManualScoresUpdate}
          />

          <DataUpload
            onDataLoaded={handleDataLoaded}
            onReset={handleDataReset}
            uploadInfo={uploadInfo}
          />

          <section className="kpi-grid">
            <div className="kpi-card">
              <span className="kpi-label">Avg Risk Score</span>
              <span className="kpi-value">{assets.length ? avgRisk.toFixed(2) : '-'}</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Highest Risk Pump</span>
              <span className="kpi-value kpi-value-sm">
                {highestRisk
                  ? <>{highestRisk.asset_name} <span className="kpi-accent">({highestRisk.risk_factor.toFixed(2)})</span></>
                  : '-'}
              </span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">High Risk Pumps (&gt;7)</span>
              <span className="kpi-value">{assets.length ? highRiskCount : '-'}</span>
            </div>

            <div className={`kpi-card${ahpResult ? (ahpResult.valid ? ' kpi-cr-ok' : ' kpi-cr-bad') : ''}`}>
              <span className="kpi-label">Consistency Ratio (CR)</span>
              <span className="kpi-value">
                {ahpResult
                  ? <><span className="cr-status-icon">{ahpResult.valid ? '✓' : '⚠'}</span> {ahpResult.cr.toFixed(4)}</>
                  : '-'}
              </span>
            </div>
          </section>

          <WeightDisplay weights={weights} />

          {error && (
            <div className="alert alert-error">
              <strong>Error loading assets:</strong> {error}
            </div>
          )}

          <AssetRegistry assets={assets} loading={loading} />

          <RiskRanking assets={assets} />

          <CriteriaContribution assets={assets} />

          <RiskScatterPlot assets={assets} />

          <RULDisplay
            assets={assets}
            rulPredictions={rulPredictions}
            isLoadingPredictions={isLoadingPredictions}
            cr={cr}
          />

          <RULExplanation
            assets={assets}
            rulPredictions={rulPredictions}
            rulExplanations={rulExplanations}
            fetchExplanation={fetchExplanation}
            isLoadingExplanation={isLoadingExplanation}
          />

          {rulError && (
            <div className="alert alert-error">
              <strong>RUL Error:</strong> {rulError}
            </div>
          )}

          {history.length > 0 && (
            <section className="card history-log">
              <div className="history-header">
                <div>
                  <h2 className="section-title">Score History Log</h2>
                  <p className="section-sub">
                    Each row records a weight or score change with the resulting pump risk scores and CR.
                  </p>
                </div>
                <button className="btn-clear" onClick={() => setHistory([])}>
                  Clear History
                </button>
              </div>
              <div className="registry-scroll">
                <table className="history-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>W1</th>
                      <th>W2</th>
                      <th>W3</th>
                      <th>W4</th>
                      <th>W5</th>
                      {history[0].pumpScores.map(p => (
                        <th key={p.id}>{p.id}</th>
                      ))}
                      <th>CR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((entry, i) => (
                      <tr key={i}>
                        <td className="td-ts">
                          {entry.timestamp.toLocaleString()}
                          {entry.note && <span className="history-note">{entry.note}</span>}
                        </td>
                        {entry.weights.map((w, j) => (
                          <td key={j} className="td-hw">{w.toFixed(2)}</td>
                        ))}
                        {entry.pumpScores.map(p => (
                          <td key={p.id} className="td-hw">{p.risk.toFixed(2)}</td>
                        ))}
                        <td className="td-hw">{entry.cr ? entry.cr.toFixed(4) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}

      {mode === 'uploaded' && (
        <>
          <UploadPanel
            onAssetsReady={handleAssetsReady}
            ahpValid={uploadedAhpResult?.valid ?? false}
            ahpWeights={uploadedAhpResult?.weights ?? null}
            ahpCr={uploadedAhpResult?.cr ?? null}
          />

          {uploadedCriteriaConfig && (
            <DynamicAHPMatrix
              criteriaNames={uploadedCriteriaConfig.criteria.map(c => c.name)}
              onWeightsUpdate={setUploadedAhpResult}
            />
          )}

          {uploadedPredictedAssets.length > 0 && (
            <DynamicAssetTable
              assets={uploadedPredictedAssets}
              criteriaConfig={uploadedCriteriaConfig}
              onExplain={handleDynamicExplain}
              explanations={uploadedExplanations}
            />
          )}
        </>
      )}
    </>
  )
}
