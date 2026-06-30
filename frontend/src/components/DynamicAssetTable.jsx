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

export default function DynamicAssetTable({ assets, criteriaConfig, onExplain, explanations }) {
  const [activeId, setActiveId] = useState(null)
  const [loadingId, setLoadingId] = useState(null)
  const popupRef = useRef(null)

  console.log('[DynamicAssetTable] render: assets.length =', assets?.length ?? 0)

  if (!assets || !assets.length || !criteriaConfig) return null

  const sorted = [...assets].sort((a, b) => (b.risk_factor ?? 0) - (a.risk_factor ?? 0))
  const criteria = criteriaConfig.criteria ?? []

  const activeAsset = sorted.find(a => a.asset_id === activeId) ?? null
  const activeExplanation = activeId ? explanations?.[activeId] ?? null : null
  const isLoading = loadingId != null

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

  return (
    <section className="card dyn-table-section">
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
              <th className="th-score">RUL (days)</th>
              <th className="th-score">CI</th>
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

              return (
                <tr key={asset.asset_id} className={isActive ? 'row-expanded' : ''}>
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
                    {rulDays != null ? (
                      <span className={`rul-pill ${rulDaysColor(rulDays)}`}>
                        {rulDays}
                      </span>
                    ) : '-'}
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
    </section>
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
