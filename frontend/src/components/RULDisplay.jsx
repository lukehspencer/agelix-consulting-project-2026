const EXPECTED_LIFESPAN_DAYS = 7300  // 20 years * 365

function rulColor(days) {
  if (days > 365) return 'rul-green'
  if (days >= 180) return 'rul-yellow'
  return 'rul-red'
}

export default function RULDisplay({ assets, rulPredictions, isLoadingPredictions, cr }) {
  if (cr !== null && cr !== undefined && cr > 0.10) {
    return (
      <section className="card rul-display">
        <h2 className="section-title">Remaining Useful Life (RUL) Predictions</h2>
        <div className="rul-cr-warning">
          Recalculate AHP matrix to unlock RUL predictions.
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

  const sorted = [...assets]
    .filter(a => rulPredictions[a.asset_id])
    .sort((a, b) => (rulPredictions[a.asset_id]?.rul_years ?? 0) - (rulPredictions[b.asset_id]?.rul_years ?? 0))

  return (
    <section className="card rul-display">
      <h2 className="section-title">Remaining Useful Life (RUL) Predictions</h2>
      <p className="section-sub">
        XGBoost predicted RUL per pump, adjusted by AHP risk factor. Most critical first.
      </p>

      <div className="rul-grid">
        {sorted.map(asset => {
          const pred = rulPredictions[asset.asset_id]
          if (!pred) return null

          const days = Math.round(pred.rul_years * 365)
          const ciLowDays = Math.round(pred.ci_low * 365)
          const ciHighDays = Math.round(pred.ci_high * 365)
          const pct = Math.min((days / EXPECTED_LIFESPAN_DAYS) * 100, 100)
          const colorClass = rulColor(days)

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
                <span className="rul-main">{days} days</span>
                <span className="rul-ci">{ciLowDays} to {ciHighDays} days</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
