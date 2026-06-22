const EXPECTED_LIFESPAN = 20

function rulColor(rul) {
  if (rul > 10) return 'rul-green'
  if (rul >= 5) return 'rul-yellow'
  return 'rul-red'
}

export default function RULDisplay({ assets, rulPredictions, isLoadingPredictions, cr }) {
  if (cr !== null && cr !== undefined && cr > 0.10) {
    return (
      <section className="card rul-display">
        <h2 className="section-title">Remaining Useful Life (RUL) Predictions</h2>
        <div className="rul-cr-warning">
          Recalculate AHP matrix to unlock RUL predictions
        </div>
      </section>
    )
  }

  if (isLoadingPredictions) {
    return (
      <section className="card rul-display">
        <h2 className="section-title">Remaining Useful Life (RUL) Predictions</h2>
        <p className="loading-msg">Loading RUL predictions...</p>
      </section>
    )
  }

  if (!Object.keys(rulPredictions).length) return null

  return (
    <section className="card rul-display">
      <h2 className="section-title">Remaining Useful Life (RUL) Predictions</h2>
      <p className="section-sub">
        XGBoost predicted RUL per pump based on current AHP weights and asset condition.
      </p>

      <div className="rul-grid">
        {assets.map(asset => {
          const pred = rulPredictions[asset.asset_id]
          if (!pred) return null

          const pct = Math.min((pred.rul_years / EXPECTED_LIFESPAN) * 100, 100)
          const colorClass = rulColor(pred.rul_years)

          return (
            <div key={asset.asset_id} className={`rul-card ${colorClass}`}>
              <div className="rul-card-header">
                <span className="rul-pump-name">{asset.asset_name}</span>
                <span className="rul-pump-id">{asset.asset_id}</span>
              </div>
              <div className="rul-bar-track">
                <div
                  className={`rul-bar-fill ${colorClass}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="rul-values">
                <span className="rul-main">{pred.rul_years.toFixed(1)} years</span>
                <span className="rul-ci">{pred.ci_low.toFixed(1)} to {pred.ci_high.toFixed(1)} years</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
