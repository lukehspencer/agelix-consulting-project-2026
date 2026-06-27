import { useState, Fragment } from 'react'

function riskColor(val) {
  if (val > 6) return 'dyn-red'
  if (val >= 4) return 'dyn-yellow'
  return 'dyn-green'
}

function rulMonthsColor(months) {
  if (months < 60) return 'dyn-red'
  if (months <= 120) return 'dyn-yellow'
  return 'dyn-green'
}

function splitLastSentence(text) {
  const sentences = text.match(/[^.!?]+[.!?]+/g)
  if (!sentences || sentences.length < 2) return { body: text, action: null }
  return {
    body: sentences.slice(0, -1).join('').trim(),
    action: sentences[sentences.length - 1].trim(),
  }
}

export default function DynamicAssetTable({ assets, criteriaConfig, onExplain, explanations }) {
  const [expandedId, setExpandedId] = useState(null)
  const [loadingId, setLoadingId] = useState(null)

  if (!assets || !assets.length || !criteriaConfig) return null

  const sorted = [...assets].sort((a, b) => (b.risk_factor ?? 0) - (a.risk_factor ?? 0))

  const criteria = criteriaConfig.criteria ?? []

  async function handleExplain(asset) {
    setExpandedId(asset.asset_id)
    if (explanations?.[asset.asset_id]) return
    setLoadingId(asset.asset_id)
    await onExplain(asset)
    setLoadingId(null)
  }

  return (
    <section className="card dyn-table-section">
      {criteriaConfig.failure_modes && (
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
              <th className="th-score">RUL (months)</th>
              <th className="th-score">CI</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(asset => {
              const isExpanded = expandedId === asset.asset_id
              const explanation = explanations?.[asset.asset_id]
              const isLoading = loadingId === asset.asset_id
              const rulMonths = asset.rul_months ?? (asset.rul_years != null ? +(asset.rul_years * 12).toFixed(1) : null)
              const ciHalf = asset.ci_low != null && asset.ci_high != null
                ? +((asset.ci_high - asset.ci_low) / 2 * 12).toFixed(1)
                : null

              return (
                <Fragment key={asset.asset_id}>
                  <tr className={isExpanded ? 'row-expanded' : ''}>
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
                      {rulMonths != null ? (
                        <span className={`rul-pill ${rulMonthsColor(rulMonths)}`}>
                          {rulMonths.toFixed(1)}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="td-score">
                      {ciHalf != null ? `+/- ${ciHalf} mo` : '-'}
                    </td>
                    <td>
                      <button
                        className="btn-explain"
                        onClick={() => handleExplain(asset)}
                        disabled={isLoading}
                      >
                        {isLoading ? 'Loading...' : explanation ? 'View' : 'Explain'}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="detail-row">
                      <td colSpan={criteria.length + 5}>
                        <div className="dyn-explanation">
                          {isLoading && <p className="explanation-spinner">Analyzing asset data...</p>}
                          {!isLoading && !explanation && (
                            <p className="explanation-placeholder">Click Explain to generate an AI analysis.</p>
                          )}
                          {!isLoading && explanation && (
                            explanation.startsWith('Error:')
                              ? <p className="explanation-error">{explanation}</p>
                              : <ExplanationBody text={explanation} />
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ExplanationBody({ text }) {
  const { body, action } = splitLastSentence(text)
  return (
    <>
      <p className="explanation-content">{body}</p>
      {action && (
        <div className="explanation-action">
          <span className="action-label">Recommended Action</span>
          <p className="action-text">{action}</p>
        </div>
      )}
    </>
  )
}
