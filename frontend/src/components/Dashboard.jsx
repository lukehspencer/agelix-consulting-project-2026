import { useState, useRef, useEffect } from 'react'
import AHPMatrix from './AHPMatrix'
import WeightDisplay from './WeightDisplay'
import AssetRegistry from './AssetRegistry'
import RiskRanking from './RiskRanking'
import CriteriaContribution from './CriteriaContribution'
import RiskScatterPlot from './RiskScatterPlot'
import { useRiskScores } from '../hooks/useRiskScores'

export default function Dashboard() {
  const [ahpResult, setAhpResult] = useState(null)
  const [history, setHistory] = useState([])
  const pendingLogRef = useRef(null)

  const weights = ahpResult?.weights ?? null
  const { assets, loading, error } = useRiskScores(weights)

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

  const avgRisk = assets.length
    ? assets.reduce((sum, a) => sum + a.risk_factor, 0) / assets.length
    : 0
  const highestRisk = assets.length ? assets[0] : null
  const highRiskCount = assets.filter(a => a.risk_factor > 7).length

  return (
    <>
      <AHPMatrix onWeightsUpdate={handleWeightsUpdate} />

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
                    <td className="td-ts">{entry.timestamp.toLocaleString()}</td>
                    {entry.weights.map((w, j) => (
                      <td key={j} className="td-hw">{w.toFixed(2)}</td>
                    ))}
                    {entry.pumpScores.map(p => (
                      <td key={p.id} className="td-hw">{p.risk.toFixed(2)}</td>
                    ))}
                    <td className="td-hw">{entry.cr.toFixed(4)}</td>
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
