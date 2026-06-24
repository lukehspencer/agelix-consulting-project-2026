const EXPECTED_LIFESPAN_MONTHS = 240

function rulColor(months) {
  if (months > 120) return 'rul-green'
  if (months >= 60) return 'rul-yellow'
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

          const months = pred.rul_years * 12
          const ciLowMonths = pred.ci_low * 12
          const ciHighMonths = pred.ci_high * 12
          const pct = Math.min((months / EXPECTED_LIFESPAN_MONTHS) * 100, 100)
          const colorClass = rulColor(months)

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
                <span className="rul-main">{months.toFixed(1)} months</span>
                <span className="rul-ci">{ciLowMonths.toFixed(1)} to {ciHighMonths.toFixed(1)} months</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
