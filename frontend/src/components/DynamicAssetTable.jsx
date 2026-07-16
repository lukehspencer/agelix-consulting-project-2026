import { useState, useEffect, useRef } from 'react'

function riskColor(val) {
  if (val > 6) return 'dyn-red'
  if (val >= 4) return 'dyn-yellow'
  return 'dyn-green'
}

function rulDaysColor(days) {
  if (days < 180) return 'dyn-red'
  if (days <= 365) return 'dyn-yellow'
  return 'dyn-green'
}

function stressColor(val) {
  if (val > 0.5) return 'dyn-red'
  if (val >= 0.2) return 'dyn-yellow'
  return 'dyn-green'
}

function formatSensorName(col) {
  return col.replace(/_/g, ' ')
}

function pairDescription(pair) {
  const abs = Math.abs(pair.correlation ?? 0)
  const strength = abs > 0.6 ? 'strongly ' : abs > 0.3 ? 'moderately ' : ''
  const relation = pair.direction === 'co-degrading' ? 'co-degrading' : 'inversely correlated'
  return `${formatSensorName(pair.col_a)} x ${formatSensorName(pair.col_b)}: ${strength}${relation}`
}

function breachStatus(asset) {
  const summary = asset.breach_summary
  const count = summary?.total_breaches ?? 0

  if (!summary || count === 0) {
    return { label: '✓ All Clear', className: 'breach-clear' }
  }
  if (summary.high_severity > 0) {
    return { label: `🚨 Immediate (${count})`, className: 'breach-high' }
  }
  if (summary.medium_severity > 0) {
    return { label: `⚠ Schedule (${count})`, className: 'breach-medium' }
  }
  return { label: `⚠ Monitor (${count})`, className: 'breach-low' }
}

function severityBadgeClass(severity) {
  if (severity === 'high') return 'breach-high'
  if (severity === 'medium') return 'breach-medium'
  return 'breach-low'
}

function mtbmArrow(recommendation) {
  if (recommendation === 'shorten') return { symbol: '↓', className: 'mtbm-arrow-red' }
  if (recommendation === 'extend') return { symbol: '↑', className: 'mtbm-arrow-green' }
  if (recommendation === 'maintain') return { symbol: '—', className: 'mtbm-arrow-grey' }
  return { symbol: '—', className: 'mtbm-arrow-grey' }
}

function mtbmBadge(recommendation) {
  if (recommendation === 'shorten') return { label: 'Shorten ↓', className: 'mp-badge-red' }
  if (recommendation === 'extend') return { label: 'Extend ↑', className: 'mp-badge-green' }
  if (recommendation === 'maintain') return { label: 'On Track ✓', className: 'mp-badge-grey' }
  return { label: 'Insufficient Data', className: 'mp-badge-grey' }
}

function decisionBadge(decision) {
  if (decision === 'replace') return { label: 'Replace', className: 'mp-decision-red' }
  if (decision === 'maintain') return { label: 'Maintain', className: 'mp-decision-green' }
  return { label: 'Insufficient Data', className: 'mp-decision-grey' }
}

function confidenceClass(confidence) {
  if (confidence === 'high') return 'mp-confidence-high'
  if (confidence === 'medium') return 'mp-confidence-medium'
  return 'mp-confidence-low'
}

function topCriterion(asset, criteria) {
  if (!criteria?.length || !asset.scores) return null
  let best = null
  let bestVal = -Infinity
  for (const c of criteria) {
    const v = asset.scores[c.id]
    if (v != null && v > bestVal) { bestVal = v; best = c.name }
  }
  return best
}

export default function DynamicAssetTable({
  assets, criteriaConfig, onExplain, explanations, onExplainBreach, breachAlerts,
}) {
  const [activeId, setActiveId] = useState(null)
  const [loadingId, setLoadingId] = useState(null)
  const popupRef = useRef(null)

  const [activeBreachId, setActiveBreachId] = useState(null)
  const [loadingBreachId, setLoadingBreachId] = useState(null)
  const breachPopupRef = useRef(null)

  console.log('[DynamicAssetTable] render: assets.length =', assets?.length ?? 0)

  if (!assets || !assets.length || !criteriaConfig) return null

  const sorted = [...assets].sort((a, b) => (b.risk_factor ?? 0) - (a.risk_factor ?? 0))
  const criteria = criteriaConfig.criteria ?? []

  const activeAsset = sorted.find(a => a.asset_id === activeId) ?? null
  const activeExplanation = activeId ? explanations?.[activeId] ?? null : null
  const isLoading = loadingId != null

  const activeBreachAsset = sorted.find(a => a.asset_id === activeBreachId) ?? null
  const activeBreachAlerts = activeBreachId ? breachAlerts?.[activeBreachId] ?? null : null
  const isBreachLoading = loadingBreachId != null

  const highSeverityAssets = sorted.filter(a => (a.breach_summary?.high_severity ?? 0) > 0)

  async function handleExplain(asset) {
    setActiveId(asset.asset_id)
    if (!explanations?.[asset.asset_id]) {
      setLoadingId(asset.asset_id)
      await onExplain(asset)
      setLoadingId(null)
    }
  }

  function handleClose() {
    setActiveId(null)
  }

  function handleBackdropClick(e) {
    if (popupRef.current && !popupRef.current.contains(e.target)) {
      handleClose()
    }
  }

  async function handleExplainBreach(asset) {
    setActiveBreachId(asset.asset_id)
    if (!breachAlerts?.[asset.asset_id]) {
      setLoadingBreachId(asset.asset_id)
      await onExplainBreach(asset)
      setLoadingBreachId(null)
    }
  }

  function handleCloseBreach() {
    setActiveBreachId(null)
  }

  function handleBreachBackdropClick(e) {
    if (breachPopupRef.current && !breachPopupRef.current.contains(e.target)) {
      handleCloseBreach()
    }
  }

  return (
    <section className="card dyn-table-section">
      {highSeverityAssets.length > 0 && (
        <div className="high-severity-banner">
          🚨 {highSeverityAssets.length} asset{highSeverityAssets.length !== 1 ? 's' : ''} require immediate attention: {highSeverityAssets.map(a => a.asset_id).join(', ')}
        </div>
      )}

      {assets && assets.length > 0 && criteriaConfig.failure_modes && (
        <div className="failure-modes-strip">
          Identified Failure Modes: {criteriaConfig.failure_modes.join(' . ')}
        </div>
      )}

      <h2 className="section-title">Risk Ranking and RUL Summary</h2>
      <p className="section-sub">
        Assets ranked by overall risk factor. Scores derived from AI-inferred criteria for {criteriaConfig.asset_type}.
      </p>

      <div className="registry-scroll">
        <table className="dyn-table">
          <thead>
            <tr>
              <th>Asset ID</th>
              {criteria.map(c => (
                <th key={c.id} className="th-score">
                  {c.name}{c.manual_input ? ' (Manual)' : ''}
                </th>
              ))}
              <th className="th-score">Risk Factor</th>
              <th className="th-score">Breach Status</th>
              <th className="th-score">RUL (days)</th>
              <th className="th-score">Est. MTBF</th>
              <th className="th-score">PM Interval</th>
              <th className="th-score">CI</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(asset => {
              const rulDays = asset.rul_years != null ? Math.round(asset.rul_years * 365) : null
              const ciLowDays = asset.ci_low != null ? Math.round(asset.ci_low * 365) : null
              const ciHighDays = asset.ci_high != null ? Math.round(asset.ci_high * 365) : null
              const isActive = activeId === asset.asset_id
              const isRowLoading = loadingId === asset.asset_id
              const isBreachActive = activeBreachId === asset.asset_id
              const isBreachRowLoading = loadingBreachId === asset.asset_id
              const status = breachStatus(asset)
              const alertRequired = asset.breach_summary?.alert_required ?? false
              const mtbmInfo = asset.mtbm?.mtbm_recommended_days != null ? mtbmArrow(asset.mtbm.recommendation) : null

              return (
                <tr key={asset.asset_id} className={isActive || isBreachActive ? 'row-expanded' : ''}>
                  <td className="td-id">{asset.asset_id}</td>
                  {criteria.map(c => {
                    const val = asset.scores?.[c.id]
                    return (
                      <td key={c.id} className="td-score">
                        {val != null ? val.toFixed(1) : '-'}
                      </td>
                    )
                  })}
                  <td className="td-score">
                    {asset.risk_factor != null ? (
                      <span className={`rf-pill ${riskColor(asset.risk_factor)}`}>
                        {asset.risk_factor.toFixed(2)}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="td-score">
                    <span className={`breach-pill ${status.className}`}>{status.label}</span>
                  </td>
                  <td className="td-score">
                    {rulDays != null ? (
                      <span className={`rul-pill ${rulDaysColor(rulDays)}`}>
                        {rulDays}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="td-score">
                    {asset.mtbf?.mtbf_days != null ? `${Math.round(asset.mtbf.mtbf_days)} d` : 'N/A'}
                  </td>
                  <td className="td-score">
                    {mtbmInfo ? (
                      <span className={`mtbm-arrow ${mtbmInfo.className}`}>
                        {asset.mtbm.mtbm_recommended_days} d {mtbmInfo.symbol}
                      </span>
                    ) : 'N/A'}
                  </td>
                  <td className="td-score">
                    {ciLowDays != null && ciHighDays != null ? `${ciLowDays}–${ciHighDays} d` : '-'}
                  </td>
                  <td>
                    <button
                      className="btn-explain"
                      onClick={() => handleExplain(asset)}
                      disabled={isRowLoading}
                    >
                      {isRowLoading ? 'Loading...' : isActive ? 'Hide' : explanations?.[asset.asset_id] ? 'View' : 'Explain'}
                    </button>
                  </td>
                  <td>
                    <button
                      className="btn-breach-alerts"
                      onClick={() => handleExplainBreach(asset)}
                      disabled={isBreachRowLoading || !alertRequired}
                      title={!alertRequired ? 'No significant breaches detected' : undefined}
                    >
                      {isBreachRowLoading ? 'Loading...' : isBreachActive ? 'Hide' : 'Breach Alerts'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {activeId && activeAsset && (
        <div className="explain-backdrop" onClick={handleBackdropClick}>
          <div className="explain-popup" ref={popupRef}>
            {/* Header */}
            <div className="explain-popup-header">
              <div>
                <span className="explain-popup-asset-id">{activeAsset.asset_id}</span>
                <span className="explain-popup-asset-type">{criteriaConfig.asset_type}</span>
              </div>
              <button className="explain-popup-close" onClick={handleClose} aria-label="Close">
                &times;
              </button>
            </div>

            {/* Stats row */}
            <StatsRow asset={activeAsset} criteria={criteria} />

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Multi-Sensor Analysis */}
            <MultiSensorAnalysis correlationSummary={activeAsset.correlation_summary} />

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Maintenance Planning */}
            <MaintenancePlanning
              mtbf={activeAsset.mtbf}
              mtbm={activeAsset.mtbm}
              replaceVsMaintain={activeAsset.replace_vs_maintain}
            />

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Explanation body */}
            <div className="explain-popup-body">
              {isLoading && (
                <p className="explanation-spinner">Analyzing asset data...</p>
              )}
              {!isLoading && !activeExplanation && (
                <p className="explanation-placeholder">Fetching AI analysis...</p>
              )}
              {!isLoading && activeExplanation && (
                activeExplanation.startsWith('Error:')
                  ? <p className="explanation-error">{activeExplanation}</p>
                  : <p className="explain-popup-text">{activeExplanation}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {activeBreachId && activeBreachAsset && (
        <div className="explain-backdrop" onClick={handleBreachBackdropClick}>
          <div className="explain-popup" ref={breachPopupRef}>
            <div className="explain-popup-header">
              <div>
                <span className="explain-popup-asset-id">
                  ⚠ Threshold Breach Alerts — {activeBreachAsset.asset_id}
                </span>
              </div>
              <button className="explain-popup-close" onClick={handleCloseBreach} aria-label="Close">
                &times;
              </button>
            </div>

            <div className="explain-popup-body">
              {isBreachLoading && (
                <p className="explanation-spinner">Generating breach alerts...</p>
              )}
              {!isBreachLoading && !activeBreachAlerts && (
                <p className="explanation-placeholder">Fetching breach alerts...</p>
              )}
              {!isBreachLoading && activeBreachAlerts && activeBreachAlerts.length === 0 && (
                <p className="explanation-placeholder">No high or medium severity breaches to report.</p>
              )}
              {!isBreachLoading && activeBreachAlerts && activeBreachAlerts.length > 0 && (
                activeBreachAlerts.map((alert, idx) => {
                  const breach = (activeBreachAsset.breaches ?? []).find(
                    b => b.criterion_id === alert.criterion_id && b.column === alert.column
                  )
                  return (
                    <div key={idx} className="breach-alert-entry">
                      <div className="breach-alert-header">
                        <span className={`breach-pill ${severityBadgeClass(alert.severity)}`}>
                          {alert.severity}
                        </span>
                        <span className="breach-alert-criterion">
                          {alert.criterion_name} — {formatSensorName(alert.column ?? '')}
                        </span>
                      </div>
                      {breach && (
                        <p className="breach-alert-metrics">
                          Current: {breach.current_value} | Limit: {breach.threshold_max} | {(breach.exceeded_pct * 100).toFixed(0)}% over
                        </p>
                      )}
                      <p className="explain-popup-text">{alert.alert_text}</p>
                      {idx < activeBreachAlerts.length - 1 && <div className="explain-popup-divider" />}
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function MultiSensorAnalysis({ correlationSummary }) {
  if (!correlationSummary) return null

  const stressIndex = correlationSummary.composite_stress_index ?? 0
  const clampedStressIndex = Math.min(1, Math.max(0, stressIndex))
  const degradingTogether = correlationSummary.sensors_degrading_together ?? 0
  const topPairs = (correlationSummary.top_correlated_pairs ?? []).slice(0, 2)

  return (
    <div className="multi-sensor-analysis">
      <h4 className="multi-sensor-title">Multi-Sensor Analysis</h4>

      <div className="stress-index-row">
        <span className="stress-index-label">Composite Stress Index</span>
        <div className="stress-index-bar-track">
          <div
            className={`stress-index-bar-fill ${stressColor(clampedStressIndex)}`}
            style={{ width: `${clampedStressIndex * 100}%` }}
          />
        </div>
        <span className="stress-index-value">{clampedStressIndex.toFixed(2)}</span>
      </div>

      {degradingTogether > 0 && (
        <p className="degrading-together-note">
          {degradingTogether} sensor pair{degradingTogether !== 1 ? 's' : ''} degrading together
        </p>
      )}

      {topPairs.length > 0 && (
        <ul className="correlated-pairs-list">
          {topPairs.map((pair, idx) => (
            <li key={idx}>{pairDescription(pair)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MaintenancePlanning({ mtbf, mtbm, replaceVsMaintain }) {
  if (!mtbf && !mtbm && !replaceVsMaintain) return null

  const badge = mtbmBadge(mtbm?.recommendation)
  const decision = decisionBadge(replaceVsMaintain?.decision)

  return (
    <div className="maintenance-planning">
      <h4 className="multi-sensor-title">Maintenance Planning</h4>

      <div className="mp-cards">
        <div className="mp-card">
          <span className="mp-card-title">Est. MTBF</span>
          <span className="mp-card-value">
            {mtbf?.mtbf_days != null ? `${mtbf.mtbf_days} days` : 'Insufficient data'}
          </span>
          {mtbf?.mtbf_confidence && (
            <span className={`mp-confidence-badge ${confidenceClass(mtbf.mtbf_confidence)}`}>
              {mtbf.mtbf_confidence.charAt(0).toUpperCase() + mtbf.mtbf_confidence.slice(1)}
            </span>
          )}
          {mtbf?.mtbf_note && <p className="mp-card-note">{mtbf.mtbf_note}</p>}
        </div>

        <div className="mp-card">
          <span className="mp-card-title">Optimal PM Interval</span>
          <span className="mp-card-value">
            {mtbm?.mtbm_recommended_days != null ? `${mtbm.mtbm_recommended_days} days` : 'Insufficient data'}
          </span>
          {mtbm?.current_interval_days != null && (
            <span className="mp-card-sub">Current: {mtbm.current_interval_days} days</span>
          )}
          <span className={`mp-badge ${badge.className}`}>{badge.label}</span>
          {mtbm?.recommendation_text && <p className="mp-card-note">{mtbm.recommendation_text}</p>}
        </div>

        <div className="mp-card">
          <span className="mp-card-title">Economic Decision</span>
          <span className={`mp-decision-value ${decision.className}`}>{decision.label}</span>
          {replaceVsMaintain?.rationale && (
            <p className="mp-card-note mp-card-note-clamp">{replaceVsMaintain.rationale}</p>
          )}
        </div>
      </div>

      {mtbm?.next_maintenance_date && (
        <p className="mp-next-maintenance">
          Next Recommended Maintenance: <strong>{mtbm.next_maintenance_date}</strong>
        </p>
      )}
    </div>
  )
}

function StatsRow({ asset, criteria }) {
  const rulDays = asset.rul_years != null ? Math.round(asset.rul_years * 365) : null
  const ciLowDays = asset.ci_low != null ? Math.round(asset.ci_low * 365) : null
  const ciHighDays = asset.ci_high != null ? Math.round(asset.ci_high * 365) : null
  const top = topCriterion(asset, criteria)

  const stats = [
    { label: 'Risk Factor', value: asset.risk_factor != null ? asset.risk_factor.toFixed(2) : '-' },
    { label: 'RUL', value: rulDays != null ? `${rulDays} days` : '-' },
    { label: 'CI Range', value: ciLowDays != null && ciHighDays != null ? `${ciLowDays}–${ciHighDays} d` : '-' },
    { label: 'Top Risk Driver', value: top ?? '-' },
  ]

  return (
    <div className="explain-stats-row">
      {stats.map(s => (
        <div key={s.label} className="explain-stat-box">
          <span className="explain-stat-label">{s.label}</span>
          <span className="explain-stat-value">{s.value}</span>
        </div>
      ))}
    </div>
  )
}
