import { useState } from 'react'

const SAATY_OPTIONS = [
  { label: '9  Extreme',         value: 9       },
  { label: '8',                  value: 8       },
  { label: '7  Very Strong',     value: 7       },
  { label: '6',                  value: 6       },
  { label: '5  Strong',          value: 5       },
  { label: '4',                  value: 4       },
  { label: '3  Moderate',        value: 3       },
  { label: '2',                  value: 2       },
  { label: '1  Equal',           value: 1       },
  { label: '1/2',                value: 1 / 2   },
  { label: '1/3  Moderate inv',  value: 1 / 3   },
  { label: '1/4',                value: 1 / 4   },
  { label: '1/5  Strong inv',    value: 1 / 5   },
  { label: '1/6',                value: 1 / 6   },
  { label: '1/7  V.Strong inv',  value: 1 / 7   },
  { label: '1/8',                value: 1 / 8   },
  { label: '1/9  Extreme inv',   value: 1 / 9   },
]

function fmtReciprocal(val) {
  if (val === 1) return '1'
  if (val > 1) return String(Math.round(val))
  return `1/${Math.round(1 / val)}`
}

export default function DynamicAHPMatrix({ criteriaNames, onWeightsUpdate }) {
  const N = criteriaNames.length

  function initMatrix() {
    return Array.from({ length: N }, () => Array(N).fill(1))
  }

  const [matrix, setMatrix] = useState(initMatrix)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function handleChange(i, j, raw) {
    const val = parseFloat(raw)
    if (!isFinite(val) || val <= 0) return
    setMatrix(prev => {
      const next = prev.map(row => [...row])
      next[i][j] = val
      next[j][i] = 1 / val
      return next
    })
  }

  async function handleSubmit() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/ahp/calculate-weights', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matrix }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `Server error ${res.status}`)
      }
      const data = await res.json()
      setResult(data)
      if (onWeightsUpdate) onWeightsUpdate(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const shortNames = criteriaNames.map(n =>
    n.length > 14 ? n.slice(0, 12) + '..' : n
  )

  return (
    <section className="ahp-section">
      <h2 className="section-title">AHP Pairwise Comparison Matrix</h2>
      <p className="section-sub">
        Rate how much more important the <em>row</em> criterion is than the{' '}
        <em>column</em>. {N}x{N} matrix for {N} AI-inferred criteria.
      </p>

      <div className="matrix-scroll">
        <table className="matrix-table">
          <thead>
            <tr>
              <th className="matrix-corner" />
              {shortNames.map(c => (
                <th key={c} className="matrix-col-head">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                <th className="matrix-row-head">{shortNames[i]}</th>
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
        <button className="btn-primary" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Calculating...' : 'Calculate Weights'}
        </button>
      </div>

      {error && (
        <div className="alert alert-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div className="ahp-results">
          <div className={`cr-banner ${result.valid ? 'cr-valid' : 'cr-invalid'}`}>
            <span className="cr-icon">{result.valid ? '✓' : '⚠'}</span>
            <span>
              {result.valid
                ? <>
                    <strong>Consistent</strong> CR = {result.cr.toFixed(4)}
                    <span className="cr-threshold"> (threshold 0.10)</span>
                  </>
                : <>
                    <strong>Inconsistent matrix</strong> CR = {result.cr.toFixed(4)} exceeds 0.10.
                    Revise your pairwise comparisons.
                  </>
              }
            </span>
          </div>
          <div className="weights-panel">
            <h3 className="weights-title">Derived Criteria Weights</h3>
            <table className="weights-table">
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {result.weights.map((w, i) => (
                  <tr key={i}>
                    <td>{criteriaNames[i]}</td>
                    <td className="w-value">{(w * 100).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
