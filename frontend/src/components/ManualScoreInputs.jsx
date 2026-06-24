import { useState } from 'react'

const C1_GUIDE = [
  { range: '1-2', desc: 'Fully redundant, failure has no operational impact' },
  { range: '3-4', desc: 'Backup exists, minor slowdown only' },
  { range: '5-6', desc: 'No backup, non-critical process' },
  { range: '7-8', desc: 'No backup, critical process (DEFAULT)' },
  { range: '9-10', desc: 'Single point of failure, immediate production halt' },
]

const C4_GUIDE = [
  { range: '1-2', desc: 'Negligible, no production loss' },
  { range: '3-4', desc: 'Minor, < 2 hours, < $500/hr' },
  { range: '5-6', desc: 'Moderate, 2-8 hours, $500-$2,000/hr (DEFAULT)' },
  { range: '7-8', desc: 'High, 8-24 hours, $2,000-$10,000/hr' },
  { range: '9-10', desc: 'Severe, > 24 hours or safety risk' },
]

export default function ManualScoreInputs({ c1Value, c4Value, onManualScoresUpdate }) {
  const [c1, setC1] = useState(c1Value)
  const [c4, setC4] = useState(c4Value)
  const [error, setError] = useState(null)

  function handleSubmit() {
    const c1Int = Math.round(Number(c1))
    const c4Int = Math.round(Number(c4))

    if (!Number.isFinite(c1Int) || c1Int < 1 || c1Int > 10
        || !Number.isFinite(c4Int) || c4Int < 1 || c4Int > 10) {
      setError('Both values must be integers between 1 and 10.')
      return
    }

    setError(null)
    onManualScoresUpdate(c1Int, c4Int)
  }

  return (
    <section className="card manual-inputs">
      <h2 className="section-title">Manual Score Inputs</h2>
      <p className="section-sub">
        C1 (Criticality) and C4 (Downtime Impact) cannot be derived from sensors.
        Set these manually on a 1-10 scale.
      </p>

      <div className="manual-grid">
        <div className="manual-group">
          <label className="manual-label">C1 Criticality Score</label>
          <div className="manual-input-row">
            <input
              type="number"
              className="manual-number"
              min={1}
              max={10}
              value={c1}
              onChange={e => setC1(e.target.value)}
            />
            <span className="manual-range">(1-10)</span>
          </div>
          <ul className="score-guide">
            {C1_GUIDE.map(g => (
              <li key={g.range}>
                <span className="guide-range">{g.range}:</span> {g.desc}
              </li>
            ))}
          </ul>
        </div>

        <div className="manual-group">
          <label className="manual-label">C4 Downtime Impact Score</label>
          <div className="manual-input-row">
            <input
              type="number"
              className="manual-number"
              min={1}
              max={10}
              value={c4}
              onChange={e => setC4(e.target.value)}
            />
            <span className="manual-range">(1-10)</span>
          </div>
          <ul className="score-guide">
            {C4_GUIDE.map(g => (
              <li key={g.range}>
                <span className="guide-range">{g.range}:</span> {g.desc}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {error && (
        <div className="manual-error">{error}</div>
      )}

      <div className="manual-actions">
        <button className="btn-primary" onClick={handleSubmit}>
          Update Risk Scores
        </button>
      </div>
    </section>
  )
}
