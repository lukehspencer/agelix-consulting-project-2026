import { useState, useEffect, useRef } from 'react'

// Single source of truth for every urgency color in this component --
// risk factor, RUL, breach status, health status, and MTBM/PM interval
// recommendations all key off this same red/orange/yellow/green/grey scale.
const COLORS = {
  critical: '#dc2626', // red
  at_risk: '#ea580c',  // orange
  monitor: '#ca8a04',  // yellow
  healthy: '#16a34a',  // green
  neutral: '#6b7280',  // grey
}

const HEALTH_STATUS_PRIORITY = { Critical: 0, 'At Risk': 1, Monitor: 2, Healthy: 3 }

const getHealthStatus = (rul_days, risk_factor) => {
  if (rul_days <= 0) return { status: 'Critical', color: COLORS.critical }
  if (rul_days < 30) return { status: 'Critical', color: COLORS.critical }
  if (rul_days < 90) return { status: 'Critical', color: COLORS.critical }
  if (rul_days < 180) return { status: 'At Risk', color: COLORS.at_risk }
  if (rul_days < 365) return { status: 'Monitor', color: COLORS.monitor }
  if (risk_factor > 7) return { status: 'Critical', color: COLORS.critical }
  if (risk_factor > 5) return { status: 'At Risk', color: COLORS.at_risk }
  if (risk_factor > 3) return { status: 'Monitor', color: COLORS.monitor }
  return { status: 'Healthy', color: COLORS.healthy }
}

// The "RUL days" used everywhere in this component (sorting, Health Status,
// summary counts, banners, the RUL Est. column) is the model-SELECTED primary
// estimate (rul_days, from rul/consensus_rul.py's select_rul()) -- ML,
// physics, or their average, whichever the backend judged most appropriate --
// not always the raw ML value. Falls back to the ML-only computation if
// rul_days is ever absent (older cached results / defensive default).
function computeRulDays(asset) {
  if (asset.rul_days != null) return asset.rul_days
  return asset.rul_years != null ? Math.round(asset.rul_years * 365) : null
}

// CI is a fixed +-6 month band around the primary/selected RUL (rul_days),
// not the raw ML model's own confidence interval -- keeps the displayed
// range consistent with whichever estimate (ML, physics, or their average)
// is actually shown as the headline RUL number.
function computeCiDays(rulDays) {
  if (rulDays == null) return { ciLowDays: null, ciHighDays: null }
  return { ciLowDays: Math.max(0, rulDays - 182), ciHighDays: rulDays + 182 }
}

const SOURCE_LABELS = { ml: 'ML', physics: 'Deg. Proj.', average: 'Avg' }
const SOURCE_COLORS = { ml: '#2563eb', physics: '#9333ea', average: '#16a34a' }

function primarySourceBadge(source) {
  if (!source || !(source in SOURCE_LABELS)) return null
  return { label: SOURCE_LABELS[source], color: SOURCE_COLORS[source] }
}

function riskColor(val) {
  if (val > 7) return COLORS.critical
  if (val > 5) return COLORS.at_risk
  if (val > 3) return COLORS.monitor
  return COLORS.healthy
}

function rulDaysColor(days) {
  if (days <= 90) return COLORS.critical
  if (days <= 180) return COLORS.at_risk
  if (days <= 365) return COLORS.monitor
  return COLORS.healthy
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

// Bolds **text** markdown emphasis within a plain string, returning an
// array of strings and <strong> elements suitable as React children.
function formatBoldSegments(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((segment, idx) => {
    if (segment.startsWith('**') && segment.endsWith('**') && segment.length > 4) {
      return <strong key={`${keyPrefix}-b${idx}`}>{segment.slice(2, -2)}</strong>
    }
    return segment
  })
}

const EXPLANATION_SECTION_HEADER_STYLE = {
  fontWeight: 'bold',
  color: '#1e40af',
  marginTop: '12px',
  marginBottom: '4px',
  fontSize: '13px',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

// Renders Claude-generated explanation/breach-alert text as styled React
// elements instead of a raw string: [SECTION MARKER] headers (if present)
// become labeled blocks, **bold** markdown becomes real emphasis, and
// plain prose without any markers falls back to paragraphs split on blank
// lines. Used wherever explanation text is displayed in this component.
function renderExplanation(text) {
  if (!text) return null

  const markerRe = /\[([A-Z][A-Z \-]*)\]/g
  const matches = [...text.matchAll(markerRe)]

  if (matches.length === 0) {
    return text
      .split(/\n{2,}/)
      .map(p => p.trim())
      .filter(Boolean)
      .map((paragraph, idx) => (
        <p key={`p-${idx}`} className="explain-popup-text" style={{ margin: idx === 0 ? 0 : '8px 0 0' }}>
          {formatBoldSegments(paragraph, `p${idx}`)}
        </p>
      ))
  }

  const blocks = []
  const leading = text.slice(0, matches[0].index).trim()
  if (leading) blocks.push({ header: null, content: leading })

  matches.forEach((m, i) => {
    const start = m.index + m[0].length
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length
    blocks.push({ header: m[1].trim(), content: text.slice(start, end).trim() })
  })

  return blocks.map((block, idx) => (
    <div key={`s-${idx}`} style={{ marginBottom: '8px' }}>
      {block.header && <div style={EXPLANATION_SECTION_HEADER_STYLE}>{block.header}</div>}
      <p className="explain-popup-text" style={{ margin: 0 }}>
        {formatBoldSegments(block.content, `s${idx}`)}
      </p>
    </div>
  ))
}

function breachStatus(asset) {
  const summary = asset.breach_summary
  const count = summary?.total_breaches ?? 0

  if (!summary || count === 0) {
    return { label: '✓ All Clear', color: COLORS.healthy }
  }
  if (summary.high_severity > 0) {
    return { label: `🚨 Immediate (${count})`, color: COLORS.critical }
  }
  if (summary.medium_severity > 0) {
    return { label: `⚠ Schedule (${count})`, color: COLORS.at_risk }
  }
  return { label: `⚠ Monitor (${count})`, color: COLORS.monitor }
}

function severityBadgeClass(severity) {
  if (severity === 'high') return 'breach-high'
  if (severity === 'medium') return 'breach-medium'
  return 'breach-low'
}

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// next_maintenance_date is always an ISO "YYYY-MM-DD" string from mtbf_mtbm.py.
// Parsed as a local-midnight Date (not `new Date(isoString)`, which parses as
// UTC and can shift the displayed calendar day in negative-UTC-offset zones).
function _parseIsoDate(dateStr) {
  if (!dateStr) return null
  const [y, m, d] = dateStr.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
}

function daysUntil(dateStr) {
  const target = _parseIsoDate(dateStr)
  if (!target) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  return Math.round((target - today) / 86400000)
}

function formatShortDate(dateStr) {
  const parsed = _parseIsoDate(dateStr)
  if (!parsed) return null
  return `${MONTH_ABBR[parsed.getMonth()]} ${String(parsed.getDate()).padStart(2, '0')}`
}

function pmIntervalColor(recommendation) {
  if (recommendation === 'immediate') return COLORS.critical
  if (recommendation === 'shorten') return COLORS.critical
  if (recommendation === 'maintain' || recommendation === 'extend') return COLORS.healthy
  return COLORS.neutral
}

function pmDateColor(days) {
  if (days == null) return COLORS.neutral
  if (days <= 30) return COLORS.critical
  if (days <= 90) return COLORS.monitor
  return COLORS.healthy
}

// Shared by the Decomm. Year table column and the Lifecycle popup's Life
// RUL card -- both key off the same years-until-decommissioning value
// (asset.rul_2_years), just displayed differently (a calendar year vs. a
// year count).
function lifeRulColor(years) {
  if (years == null) return COLORS.neutral
  if (years < 5) return COLORS.critical
  if (years <= 10) return COLORS.monitor
  return COLORS.healthy
}

function lifeConsumedColorClass(pct) {
  if (pct > 80) return 'dyn-red'
  if (pct >= 60) return 'dyn-yellow'
  return 'dyn-green'
}

function consensusBadge(consensus) {
  if (consensus === 'high') return { symbol: '✓', label: 'Models agree', color: COLORS.healthy }
  if (consensus === 'medium') return { symbol: '~', label: 'Similar', color: COLORS.monitor }
  if (consensus === 'low') return { symbol: '⚠', label: 'Models diverge', color: COLORS.critical }
  return null
}

function mtbmBadge(recommendation) {
  if (recommendation === 'immediate') return { label: 'Overdue', color: COLORS.critical }
  if (recommendation === 'shorten') return { label: 'Shorten ↓', color: COLORS.critical }
  if (recommendation === 'extend') return { label: 'Extend ↑', color: COLORS.monitor }
  if (recommendation === 'maintain') return { label: 'On Track ✓', color: COLORS.healthy }
  return { label: 'Insufficient Data', color: COLORS.neutral }
}

function decisionBadge(decision) {
  if (decision === 'replace') return { label: 'Replace', className: 'mp-decision-red' }
  if (decision === 'maintain') return { label: 'Maintain', className: 'mp-decision-green' }
  return { label: 'Insufficient Data', className: 'mp-decision-grey' }
}

// PM Interval card basis breakdown, one entry per basis. For
// "degradation_projection" this pulls the limiting sensor's detail from
// pm_projection (rul/physics_rul.py's project_asset_pm()) rather than mtbm
// alone, since mtbm only carries the already-composed recommendation_text,
// not the individual threshold/value/trend numbers.
function pmBasisDetailLines(mtbm, pmProjection) {
  const basis = mtbm?.basis

  if (basis === 'degradation_projection' || basis === 'physics') {
    return ['Based on sensor degradation rate']
  }
  if (basis === 'rul_based') {
    const days = mtbm.rul_days_used != null ? Math.round(mtbm.rul_days_used) : '?'
    return [`Scheduled at 75% of predicted RUL (${days} days)`]
  }
  if (basis === 'risk_adjusted') return ['Adjusted from current interval based on risk level']
  if (basis === 'domain_knowledge' || basis === 'mtbf_based') return ['Based on historical MTBF data']
  if (basis === 'no_trend_detected') return ['No clear degradation trend -- using RUL estimate']
  return null
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

  // While either popup is open: Escape closes it, and the body can't scroll
  // behind the modal. Runs before the early-return below so hook order stays
  // stable across renders regardless of whether assets/criteriaConfig exist.
  useEffect(() => {
    if (activeId == null && activeBreachId == null) return undefined

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setActiveId(null)
        setActiveBreachId(null)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [activeId, activeBreachId])

  console.log('[DynamicAssetTable] render: assets.length =', assets?.length ?? 0)

  if (!assets || !assets.length || !criteriaConfig) return null

  // Sort by health urgency (Critical -> At Risk -> Monitor -> Healthy), then
  // by RUL ascending within each group so the least remaining life is first.
  const sorted = [...assets].sort((a, b) => {
    const aDays = computeRulDays(a) ?? Infinity
    const bDays = computeRulDays(b) ?? Infinity
    const aStatus = getHealthStatus(aDays, a.risk_factor ?? 0).status
    const bStatus = getHealthStatus(bDays, b.risk_factor ?? 0).status
    const priorityDiff = HEALTH_STATUS_PRIORITY[aStatus] - HEALTH_STATUS_PRIORITY[bStatus]
    if (priorityDiff !== 0) return priorityDiff
    return aDays - bDays
  })
  const criteria = criteriaConfig.criteria ?? []

  const healthCounts = sorted.reduce((acc, asset) => {
    const status = getHealthStatus(computeRulDays(asset) ?? Infinity, asset.risk_factor ?? 0).status
    acc[status] = (acc[status] ?? 0) + 1
    return acc
  }, { Critical: 0, 'At Risk': 0, Monitor: 0, Healthy: 0 })

  const activeAsset = sorted.find(a => a.asset_id === activeId) ?? null
  const activeExplanation = activeId ? explanations?.[activeId] ?? null : null
  const isLoading = loadingId != null

  const activeBreachAsset = sorted.find(a => a.asset_id === activeBreachId) ?? null
  const activeBreachAlerts = activeBreachId ? breachAlerts?.[activeBreachId] ?? null : null
  const isBreachLoading = loadingBreachId != null

  // The "immediate attention" (red) banner is strictly getHealthStatus()-driven,
  // same as the Health Status column, so the two never disagree about which
  // assets are in the worst tier.
  const criticalAssets = sorted.filter(asset => {
    const health = getHealthStatus(computeRulDays(asset) ?? Infinity, asset.risk_factor ?? 0)
    return health.status === 'Critical'
  })

  // The "require scheduling" (orange) banner is broader than the Health Status
  // column: an asset lands in it if its RUL/risk-factor health is 'At Risk',
  // OR it has an unresolved high/medium severity breach, OR its next PM date
  // is due within 30 days -- signals the RUL-based Health Status badge alone
  // doesn't capture. This means an asset can appear here while its own row
  // still shows a Healthy/Monitor badge; that's intentional (breach/PM-date
  // urgency and RUL-health urgency are genuinely different signals), not a
  // bug -- just don't assume this banner and the Health Status column always
  // agree the way the red banner and column do.
  const needsSchedulingAssets = sorted.filter(asset => {
    const health = getHealthStatus(computeRulDays(asset) ?? Infinity, asset.risk_factor ?? 0)
    if (health.status === 'At Risk') return true

    const hasUnresolvedBreach = (asset.breach_summary?.high_severity ?? 0) > 0
      || (asset.breach_summary?.medium_severity ?? 0) > 0
    if (hasUnresolvedBreach) return true

    const pmDays = daysUntil(asset.mtbm?.next_maintenance_date)
    if (pmDays != null && pmDays <= 30) return true

    return false
  })

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
      {criticalAssets.length > 0 && (
        <div className="high-severity-banner">
          🚨 {criticalAssets.length} asset{criticalAssets.length !== 1 ? 's' : ''} require immediate attention: {criticalAssets.map(a => a.asset_id).join(', ')}
        </div>
      )}

      {criticalAssets.length === 0 && needsSchedulingAssets.length > 0 && (
        <div
          className="high-severity-banner"
          style={{ background: '#fff7ed', border: '1px solid #fed7aa', color: COLORS.at_risk }}
        >
          ⚠ {needsSchedulingAssets.length} asset{needsSchedulingAssets.length !== 1 ? 's' : ''} require scheduling: {needsSchedulingAssets.map(a => a.asset_id).join(', ')}
        </div>
      )}

      {assets && assets.length > 0 && criteriaConfig.failure_modes && (
        <div className="failure-modes-strip">
          Identified Failure Modes: {criteriaConfig.failure_modes.join(' . ')}
        </div>
      )}

      <h2 className="section-title">Risk Ranking and RUL Summary</h2>
      <p className="section-sub">
        Assets ranked by overall risk factor. Scores derived from AI-inferred criteria for {criteriaConfig?.asset_type || 'uploaded asset type'}.
      </p>

      <div className="health-status-summary" style={{ display: 'flex', gap: '1.5rem', margin: '0.5rem 0 1rem' }}>
        <span style={{ color: COLORS.critical, fontWeight: 'bold' }}>{healthCounts.Critical} Critical</span>
        <span style={{ color: COLORS.at_risk, fontWeight: 'bold' }}>{healthCounts['At Risk']} At Risk</span>
        <span style={{ color: COLORS.monitor, fontWeight: 'bold' }}>{healthCounts.Monitor} Monitor</span>
        <span style={{ color: COLORS.healthy, fontWeight: 'bold' }}>{healthCounts.Healthy} Healthy</span>
      </div>

      <div className="registry-scroll">
        <table className="dyn-table">
          <thead>
            <tr>
              <th>Asset ID</th>
              <th>Health Status</th>
              {criteria.map(c => (
                <th key={c.id} className="th-score">
                  {c.name}{c.manual_input ? ' (Manual)' : ''}
                </th>
              ))}
              <th className="th-score">Risk Factor</th>
              <th className="th-score">Breach Status</th>
              <th className="th-score">RUL Est. (days)</th>
              <th className="th-score">Decomm. Year</th>
              <th className="th-score">PM Interval</th>
              <th className="th-score">Next PM Date</th>
              <th className="th-score">CI</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(asset => {
              const rulDays = computeRulDays(asset)
              const { ciLowDays, ciHighDays } = computeCiDays(rulDays)
              const isActive = activeId === asset.asset_id
              const isRowLoading = loadingId === asset.asset_id
              const isBreachActive = activeBreachId === asset.asset_id
              const isBreachRowLoading = loadingBreachId === asset.asset_id
              const status = breachStatus(asset)
              const alertRequired = asset.breach_summary?.alert_required ?? false
              const pmDays = daysUntil(asset.mtbm?.next_maintenance_date)
              const pmDateLabel = formatShortDate(asset.mtbm?.next_maintenance_date)
              const health = getHealthStatus(rulDays ?? Infinity, asset.risk_factor ?? 0)
              const consensus = consensusBadge(asset.consensus)
              const sourceBadge = primarySourceBadge(asset.rul_primary_source)

              return (
                <tr key={asset.asset_id} className={isActive || isBreachActive ? 'row-expanded' : ''}>
                  <td className="td-id">{asset.asset_id}</td>
                  <td>
                    <span style={{
                      backgroundColor: health.color,
                      color: 'white',
                      padding: '2px 8px',
                      borderRadius: '12px',
                      fontSize: '12px',
                      fontWeight: 'bold',
                    }}>
                      {health.status}
                    </span>
                  </td>
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
                      <span className="rf-pill" style={{ backgroundColor: riskColor(asset.risk_factor) }}>
                        {asset.risk_factor.toFixed(2)}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="td-score">
                    <span className="breach-pill" style={{ backgroundColor: status.color, color: 'white' }}>
                      {status.label}
                    </span>
                  </td>
                  <td className="td-score">
                    {rulDays != null ? (
                      <>
                        <span className="rul-pill" style={{ backgroundColor: rulDaysColor(rulDays) }}>
                          {rulDays}
                        </span>
                        {sourceBadge && (
                          <div style={{ fontSize: '10px', color: sourceBadge.color, fontWeight: 'bold', marginTop: '2px' }}>
                            {sourceBadge.label}
                          </div>
                        )}
                        {consensus && (
                          <div style={{ fontSize: '10px', color: consensus.color, marginTop: '2px' }}>
                            {consensus.symbol} {consensus.label}
                          </div>
                        )}
                      </>
                    ) : '-'}
                  </td>
                  <td className="td-score">
                    {asset.rul_2_available && asset.decommission_year != null ? (
                      <span style={{ color: lifeRulColor(asset.rul_2_years), fontWeight: 'bold' }}>
                        {asset.decommission_year}
                      </span>
                    ) : 'N/A'}
                  </td>
                  <td className="td-score">
                    {asset.mtbm?.mtbm_recommended_days != null ? (
                      <span className="mtbm-arrow" style={{ color: pmIntervalColor(asset.mtbm.recommendation) }}>
                        {asset.mtbm.mtbm_recommended_days === 0 ? 'Immediate' : `${asset.mtbm.mtbm_recommended_days} d`}
                      </span>
                    ) : 'N/A'}
                  </td>
                  <td className="td-score">
                    {pmDateLabel != null ? (
                      <span style={{ color: pmDateColor(pmDays), fontWeight: 'bold' }}>
                        {pmDateLabel}
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

            {activeAsset.rul_calibrated && (
              <p className="mp-card-note" style={{ margin: '0.3rem 0 0.6rem', fontSize: '0.78rem', color: '#6b7280' }}>
                Note: Raw ML model prediction was {activeAsset.rul_raw_days} days. Calibrated to {activeAsset.rul_ml_days ?? computeRulDays(activeAsset)} days based on this asset type's observed training range.
              </p>
            )}

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Model Details (collapsed by default) */}
            <ModelDetails asset={activeAsset} />

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
              pmIntervalSource={criteriaConfig.pm_interval_source}
              pmIntervalConfidence={criteriaConfig.pm_interval_confidence}
              pmProjection={activeAsset.pm_projection}
            />

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Lifecycle (decommissioning RUL / RUL 2) */}
            <Lifecycle asset={activeAsset} />

            {/* Divider */}
            <div className="explain-popup-divider" />

            {/* Degradation Projection */}
            <PhysicsProjection
              physics={activeAsset.physics_projection}
              mlRulDays={activeAsset.rul_ml_days ?? computeRulDays(activeAsset)}
              consensus={activeAsset.consensus}
            />

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
                  : <div>{renderExplanation(activeExplanation)}</div>
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
                      <div>{renderExplanation(alert.alert_text)}</div>
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

function MaintenancePlanning({ mtbf, mtbm, replaceVsMaintain, pmIntervalSource, pmIntervalConfidence, pmProjection }) {
  if (!mtbf && !mtbm && !replaceVsMaintain) return null

  const badge = mtbmBadge(mtbm?.recommendation)
  const decision = decisionBadge(replaceVsMaintain?.decision)
  const basisLines = pmBasisDetailLines(mtbm, pmProjection)

  return (
    <div className="maintenance-planning">
      <h4 className="multi-sensor-title">Maintenance Planning</h4>

      <div className="mp-cards">
        <div className="mp-card">
          <span className="mp-card-title">Historical MTBF</span>
          <span className="mp-card-value">
            {mtbf?.mtbf_days != null ? `${mtbf.mtbf_days} days` : 'N/A*'}
          </span>
          {mtbf?.mtbf_confidence && (
            <span className={`mp-confidence-badge ${confidenceClass(mtbf.mtbf_confidence)}`}>
              {mtbf.mtbf_confidence.charAt(0).toUpperCase() + mtbf.mtbf_confidence.slice(1)}
            </span>
          )}
          {mtbf?.mtbf_note && <p className="mp-card-note">{mtbf.mtbf_note}</p>}
          <p className="mp-card-note">Requires 2+ observed failures to calculate. Based on failure log history only.</p>
        </div>

        <div className="mp-card">
          <span className="mp-card-title">Recommended MTBM</span>
          <span className="mp-card-value">
            {mtbm?.mtbm_recommended_days != null ? `${mtbm.mtbm_recommended_days} days` : 'Insufficient data'}
          </span>
          <span className="mp-card-sub">Optimal interval based on asset risk and degradation rate</span>
          {basisLines && basisLines.map((line, idx) => (
            <span key={idx} className="mp-card-sub">{line}</span>
          ))}
          {(pmIntervalSource || pmIntervalConfidence) && (
            <span className="mp-card-sub">
              Based on: {pmIntervalSource ?? 'default'} ({pmIntervalConfidence ?? 'low'} confidence)
            </span>
          )}
          {mtbm?.current_interval_days != null && (
            <span className="mp-card-sub">Current approved interval: {mtbm.current_interval_days} days</span>
          )}
          <span className="mp-badge" style={{ backgroundColor: badge.color, color: 'white' }}>{badge.label}</span>
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

const _DESIGN_LIFE_YEARS = 25

function Lifecycle({ asset }) {
  if (!asset) return null

  if (!asset.rul_2_available) {
    return (
      <div className="maintenance-planning">
        <h4 className="multi-sensor-title">Lifecycle</h4>
        <p className="mp-card-note">
          Life RUL model not available. Train with True_RUL_2_Years column to enable.
        </p>
      </div>
    )
  }

  const rul2Years = asset.rul_2_years
  const pctLifeRemaining = asset.pct_life_remaining ?? 0
  const pctConsumed = Math.min(100, Math.max(0, 100 - pctLifeRemaining))

  return (
    <div className="maintenance-planning">
      <h4 className="multi-sensor-title">Lifecycle</h4>

      <div className="mp-cards">
        <div className="mp-card">
          <span className="mp-card-title">Life RUL</span>
          <span className="mp-card-value" style={{ color: lifeRulColor(rul2Years) }}>
            {rul2Years != null ? `${rul2Years} years` : '-'}
          </span>
          <span className="mp-card-sub">
            Est. decommission: {asset.decommission_year ?? 'N/A'}
          </span>
        </div>

        <div className="mp-card">
          <span className="mp-card-title">Life Consumed</span>
          <span className="mp-card-value">{pctConsumed.toFixed(0)}%</span>
          <div className="stress-index-bar-track">
            <div
              className={`stress-index-bar-fill ${lifeConsumedColorClass(pctConsumed)}`}
              style={{ width: `${pctConsumed}%` }}
            />
          </div>
        </div>

        <div className="mp-card">
          <span className="mp-card-title">Design Life</span>
          <span className="mp-card-value">{_DESIGN_LIFE_YEARS} years</span>
          <span className="mp-card-sub">ISO/OEM specification</span>
        </div>
      </div>
    </div>
  )
}

function PhysicsProjection({ physics, mlRulDays, consensus }) {
  const projections = physics?.sensor_projections ?? {}
  if (Object.keys(projections).length === 0) return null

  const trendingUp = Object.entries(projections).filter(
    ([, p]) => p.trend_direction === 'increasing' && p.days_to_threshold != null
  )
  const physicsRulDays = physics?.physics_rul_days ?? null

  return (
    <div className="physics-projection">
      <h4 className="multi-sensor-title">Degradation Projection</h4>

      {trendingUp.length > 0 && (
        <ul className="correlated-pairs-list">
          {trendingUp.map(([sensor, p]) => (
            <li key={sensor} style={{ color: pmDateColor(p.days_to_threshold) }}>
              {formatSensorName(sensor)}: {p.current_value.toFixed(2)} → threshold {p.threshold.toFixed(2)}{' '}
              in ~{Math.round(p.days_to_threshold)} days ({p.projected_date})
            </li>
          ))}
        </ul>
      )}

      {physics?.limiting_sensor && physicsRulDays != null && (
        <p className="mp-card-note" style={{ color: COLORS.at_risk, fontWeight: 'bold' }}>
          ⚠ Limiting factor: {formatSensorName(physics.limiting_sensor)} projected to reach critical
          threshold in {Math.round(physicsRulDays)} days
        </p>
      )}

      {consensus && consensus !== 'unknown' && physicsRulDays != null && (
        <p className="mp-card-note">
          ML vs Degradation Projection consensus: {consensus} — ML predicts {mlRulDays != null ? Math.round(mlRulDays) : '-'}d,
          projection estimates {Math.round(physicsRulDays)}d
        </p>
      )}
    </div>
  )
}

function ModelDetails({ asset }) {
  const [expanded, setExpanded] = useState(false)

  if (asset.rul_days == null) return null

  const sourceLabel = SOURCE_LABELS[asset.rul_primary_source] ?? asset.rul_primary_source ?? '-'

  return (
    <div className="model-details">
      <button
        type="button"
        className="model-details-toggle"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        {expanded ? 'Hide model details ▲' : 'Show model details ▼'}
      </button>

      {expanded && (
        <div className="mp-card model-details-body">
          <span className="mp-card-title">How this RUL was calculated:</span>
          <p className="mp-card-note">Primary estimate: {asset.rul_days} days ({sourceLabel})</p>
          {asset.rul_reason && <p className="mp-card-note">Reason: {asset.rul_reason}</p>}
          <span className="mp-card-sub">
            ML Model: {asset.rul_ml_days != null ? `${asset.rul_ml_days} days` : '-'}
          </span>
          <span className="mp-card-sub">
            Degradation Projection: {asset.rul_physics_days != null ? `${asset.rul_physics_days} days` : 'N/A'}
          </span>
          <span className="mp-card-sub">Consensus: {asset.consensus ?? 'unknown'}</span>
          <span className="mp-card-sub">Physics confidence: {asset.physics_confidence ?? 'low'}</span>
        </div>
      )}
    </div>
  )
}

function StatsRow({ asset, criteria }) {
  const rulDays = computeRulDays(asset)
  const { ciLowDays, ciHighDays } = computeCiDays(rulDays)
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
