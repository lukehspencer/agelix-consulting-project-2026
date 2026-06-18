import { useState } from 'react'
import { useAHP } from '../hooks/useAHP'

const CRITERIA = [
  'Criticality',
  'Condition',
  'Failure Prob.',
  'Downtime Impact',
  'Cost Trend',
]

const CRITERIA_FULL = [
  'Criticality',
  'Condition',
  'Failure Probability',
  'Downtime Impact',
  'Maintenance Cost Trend',
]

const N = 5

// Full Saaty scale: integers 1–9 and their reciprocals.
// Values are stored as exact floats; labels are display-only.
const SAATY_OPTIONS = [
  { label: '9 — Extreme',         value: 9       },
  { label: '8',                   value: 8       },
  { label: '7 — Very Strong',     value: 7       },
  { label: '6',                   value: 6       },
  { label: '5 — Strong',          value: 5       },
  { label: '4',                   value: 4       },
  { label: '3 — Moderate',        value: 3       },
  { label: '2',                   value: 2       },
  { label: '1 — Equal',           value: 1       },
  { label: '1/2',                 value: 1 / 2   },
  { label: '1/3 — Moderate⁻¹',   value: 1 / 3   },
  { label: '1/4',                 value: 1 / 4   },
  { label: '1/5 — Strong⁻¹',     value: 1 / 5   },
  { label: '1/6',                 value: 1 / 6   },
  { label: '1/7 — V. Strong⁻¹',  value: 1 / 7   },
  { label: '1/8',                 value: 1 / 8   },
  { label: '1/9 — Extreme⁻¹',    value: 1 / 9   },
]

function initMatrix() {
  return Array.from({ length: N }, () => Array(N).fill(1))
}

// Format a float for the read-only reciprocal cells.
function fmtReciprocal(val) {
  if (val === 1) return '1'
  if (val > 1)   return String(Math.round(val))
  return `1/${Math.round(1 / val)}`
}

export default function AHPMatrix({ onWeightsUpdate }) {
  const [matrix, setMatrix] = useState(initMatrix)
  const { calculateWeights, result, loading, error } = useAHP()

  function handleChange(i, j, raw) {
    const val = parseFloat(raw)
    if (!isFinite(val) || val <= 0) return
    setMatrix(prev => {
      const next = prev.map(row => [...row])
      next[i][j] = val
      next[j][i] = 1 / val          // reciprocal (exact float arithmetic)
      return next
    })
  }

  async function handleSubmit() {
    const data = await calculateWeights(matrix)
    if (data && onWeightsUpdate) onWeightsUpdate(data)
  }

  return (
    <section className="ahp-section">
      <h2 className="section-title">AHP Pairwise Comparison Matrix</h2>
      <p className="section-sub">
        Rate how much more important the <em>row</em> criterion is than the{' '}
        <em>column</em>. Edit the upper triangle — reciprocals fill automatically.
      </p>

      <div className="matrix-scroll">
        <table className="matrix-table">
          <thead>
            <tr>
              <th className="matrix-corner" />
              {CRITERIA.map(c => (
                <th key={c} className="matrix-col-head">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                <th className="matrix-row-head">{CRITERIA[i]}</th>
                {row.map((val, j) => {
                  if (i === j) {
                    return (
                      <td key={j} className="cell cell-diag">
                        <span className="diag-label">1</span>
                      </td>
                    )
                  }
                  if (i < j) {
                    return (
                      <td key={j} className="cell cell-upper">
                        <select
                          className="saaty-select"
                          value={val}
                          onChange={e => handleChange(i, j, e.target.value)}
                        >
                          {SAATY_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                    )
                  }
                  // lower triangle — read-only reciprocal
                  return (
                    <td key={j} className="cell cell-lower">
                      <span className="reciprocal-label">{fmtReciprocal(val)}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="matrix-actions">
        <button
          className="btn-primary"
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? 'Calculating…' : 'Calculate Weights'}
        </button>
      </div>

      {error && (
        <div className="alert alert-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div className="ahp-results">
          <CRBanner cr={result.cr} valid={result.valid} />
          <WeightsPanel
            weights={result.weights}
            lambdaMax={result.lambda_max}
            ci={result.ci}
          />
        </div>
      )}
    </section>
  )
}

// ── CR Validation Banner ──────────────────────────────────────────────────────

function CRBanner({ cr, valid }) {
  return (
    <div className={`cr-banner ${valid ? 'cr-valid' : 'cr-invalid'}`}>
      <span className="cr-icon">{valid ? '✓' : '⚠'}</span>
      <span>
        {valid ? (
          <>
            <strong>Consistent</strong> — CR = {cr.toFixed(4)}&ensp;
            <span className="cr-threshold">(threshold ≤ 0.10)</span>
          </>
        ) : (
          <>
            <strong>Inconsistent matrix</strong> — CR = {cr.toFixed(4)} exceeds 0.10.
            Revise your pairwise comparisons to reduce contradictions before using
            these weights.
          </>
        )}
      </span>
    </div>
  )
}

// ── Weights Panel ─────────────────────────────────────────────────────────────

function WeightsPanel({ weights, lambdaMax, ci }) {
  const maxW = Math.max(...weights)

  return (
    <div className="weights-panel">
      <h3 className="weights-title">Derived Criteria Weights</h3>
      <table className="weights-table">
        <thead>
          <tr>
            <th>Criterion</th>
            <th>Weight</th>
            <th>Relative importance</th>
          </tr>
        </thead>
        <tbody>
          {weights.map((w, i) => (
            <tr key={i}>
              <td>{CRITERIA_FULL[i]}</td>
              <td className="w-value">{(w * 100).toFixed(2)}%</td>
              <td className="w-bar-cell">
                <div className="w-bar-track">
                  <div
                    className="w-bar-fill"
                    style={{ width: `${(w / maxW) * 100}%` }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="consistency-meta">
        λ<sub>max</sub> = {lambdaMax.toFixed(4)}&ensp;·&ensp;
        CI = {ci.toFixed(4)}
      </p>
    </div>
  )
}
