function splitLastSentence(text) {
  const sentences = text.match(/[^.!?]+[.!?]+/g)
  if (!sentences || sentences.length < 2) return { body: text, action: null }
  const action = sentences[sentences.length - 1].trim()
  const body = sentences.slice(0, -1).join('').trim()
  return { body, action }
}

export default function RULExplanation({
  assets,
  rulPredictions,
  rulExplanations,
  fetchExplanation,
  isLoadingExplanation,
}) {
  if (!Object.keys(rulPredictions).length) return null

  return (
    <section className="card rul-explanation-section">
      <h2 className="section-title">AI-Powered Maintenance Recommendations</h2>
      <p className="section-sub">
        Claude analyzes each pump's risk profile and RUL prediction to recommend maintenance actions. Click to generate.
      </p>

      <div className="explanation-grid">
        {assets.map(asset => {
          const pred = rulPredictions[asset.asset_id]
          if (!pred) return null

          const explanation = rulExplanations[asset.asset_id]
          const loading = isLoadingExplanation[asset.asset_id]

          return (
            <div key={asset.asset_id} className="explanation-card">
              <div className="explanation-header">
                <div>
                  <span className="explanation-name">{asset.asset_name}</span>
                  <span className="explanation-meta">
                    RUL: {(pred.rul_years * 12).toFixed(1)} months | Risk: {asset.risk_factor.toFixed(2)}
                  </span>
                </div>
                <button
                  className="btn-explain"
                  onClick={() => fetchExplanation(asset, asset.scores, asset.risk_factor)}
                  disabled={loading}
                >
                  {loading ? 'Generating...' : explanation ? 'Refresh' : 'Generate Explanation'}
                </button>
              </div>

              <div className="explanation-body">
                {loading && <div className="explanation-spinner">Analyzing pump data...</div>}
                {!loading && !explanation && (
                  <p className="explanation-placeholder">
                    Click Generate Explanation to get an AI-powered maintenance recommendation for this pump.
                  </p>
                )}
                {!loading && explanation && <ExplanationText text={explanation} />}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ExplanationText({ text }) {
  if (text.startsWith('Error:')) {
    return <p className="explanation-error">{text}</p>
  }

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
