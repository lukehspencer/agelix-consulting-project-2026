import { useState, useRef, useEffect } from 'react'
import AHPMatrix from './AHPMatrix'
import WeightDisplay from './WeightDisplay'
import AssetRegistry from './AssetRegistry'
import RiskRanking from './RiskRanking'
import CriteriaContribution from './CriteriaContribution'
import RiskScatterPlot from './RiskScatterPlot'
import DataUpload from './DataUpload'
import { useRiskScores } from '../hooks/useRiskScores'

const SCORE_KEYS = [
  'score_criticality', 'score_condition', 'score_failure_probability',
  'score_downtime_impact', 'score_maintenance_cost_trend',
]
const CRITERIA_LABELS = [
  'Criticality', 'Condition', 'Failure Probability',
  'Downtime Impact', 'Maintenance Cost Trend',
]
const EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]

export default function Dashboard() {
  const [ahpResult, setAhpResult] = useState(null)
  const [history, setHistory] = useState([])
  const pendingLogRef = useRef(null)

  const [customPumps, setCustomPumps] = useState(null)
  const [customAssets, setCustomAssets] = useState(null)
  const [uploadInfo, setUploadInfo] = useState(null)
  const [scoringCustom, setScoringCustom] = useState(false)
  const [scoringError, setScoringError] = useState(null)
  const uploadPendingLogRef = useRef(false)

  const weights = ahpResult?.weights ?? null
  const weightsKey = weights ? JSON.stringify(weights) : ''

  const { assets: defaultAssets, loading: defaultLoading, error: defaultError } = useRiskScores(weights)

  const assets = customAssets ?? defaultAssets
  const loading = customPumps ? scoringCustom : defaultLoading
  const error = customPumps ? scoringError : defaultError

  function handleWeightsUpdate(data) {
    setAhpResult(data)
    pendingLogRef.current = {
      timestamp: new Date(),
      weights: data.weights,
      cr: data.cr,
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
        const installDate = new Date(pump.install_date)
        const lastMaintDate = new Date(pump.last_maintenance_date)
        const age_years = +((today - installDate) / (365.25 * 86400000)).toFixed(2)
        const usage_intensity_pct = +(pump.actual_flow_rate_gpm / pump.rated_flow_rate_gpm * 100).toFixed(1)
        const days_since_maintenance = Math.round((today - lastMaintDate) / 86400000)

        const criticality_raw = 1 + (pump.score_criticality - 1) * (9 / 8)
        const downtime_impact_raw = 1 + (pump.score_downtime_impact - 1) * (9 / 8)

        const res = await fetch('/ahp/score-asset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            asset_id: pump.asset_id,
            criticality_raw,
            condition_score: pump.condition_score,
            vibration_level: pump.vibration_level,
            seal_condition: pump.seal_condition,
            bearing_condition: pump.bearing_condition,
            age_years,
            expected_lifespan_years: pump.expected_lifespan_years,
            number_of_failures_last_3yr: Math.round(pump.number_of_failures_last_3yr),
            days_since_maintenance,
            maintenance_frequency_days: pump.maintenance_frequency_days,
            downtime_impact_raw,
            maintenance_cost_trend: pump.maintenance_cost_trend,
            maintenance_cost_last_year: pump.maintenance_cost_last_year,
          }),
        })
        if (!res.ok) throw new Error(`Scoring failed for ${pump.asset_id}`)
        const scores = await res.json()

        return { ...pump, ...scores, age_years, usage_intensity_pct, days_since_maintenance }
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

  return (
    <>
      <AHPMatrix onWeightsUpdate={handleWeightsUpdate} />

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

      {history.length > 0 && (
        <section className="card history-log">
          <div className="history-header">
            <div>
              <h2 className="section-title">Score History Log</h2>
              <p className="section-sub">
                Each row records a matrix submission with the resulting weights, pump risk scores, and CR.
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
  )
}
