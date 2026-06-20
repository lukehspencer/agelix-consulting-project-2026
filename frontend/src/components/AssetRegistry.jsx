import { useState, Fragment } from 'react'

const SCORE_HEADERS = ['C1', 'C2', 'C3', 'C4', 'C5']

const VIBRATION_CLASS = {
  Normal: 'badge-ok',
  High: 'badge-warn',
  Critical: 'badge-crit',
}

export default function AssetRegistry({ assets, loading }) {
  const [expandedId, setExpandedId] = useState(null)

  function toggle(id) {
    setExpandedId(prev => (prev === id ? null : id))
  }

  if (loading) {
    return (
      <section className="card asset-registry">
        <p className="loading-msg">Loading assets...</p>
      </section>
    )
  }

  if (!assets.length) return null

  return (
    <section className="card asset-registry">
      <h2 className="section-title">Asset Registry</h2>
      <p className="section-sub">Click a row to view full pump details.</p>

      <div className="registry-scroll">
        <table className="registry-table">
          <thead>
            <tr>
              <th>Asset ID</th>
              <th>Asset Name</th>
              <th>Location</th>
              <th>Cond.</th>
              <th>Vibration</th>
              <th>Seal</th>
              <th>Bearing</th>
              <th>Failures</th>
              <th>Maint. Cost</th>
              <th>Trend</th>
              {SCORE_HEADERS.map(h => (
                <th key={h} className="th-score">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {assets.map(pump => (
              <Fragment key={pump.asset_id}>
                <tr
                  className={`registry-row${expandedId === pump.asset_id ? ' row-expanded' : ''}`}
                  onClick={() => toggle(pump.asset_id)}
                >
                  <td className="td-id">{pump.asset_id}</td>
                  <td>{pump.asset_name}</td>
                  <td>{pump.location}</td>
                  <td className="td-num">{pump.condition_score}</td>
                  <td>
                    <span className={`badge ${VIBRATION_CLASS[pump.vibration_level] || ''}`}>
                      {pump.vibration_level}
                    </span>
                  </td>
                  <td>{pump.seal_condition}</td>
                  <td>{pump.bearing_condition}</td>
                  <td className="td-num">{pump.number_of_failures_last_3yr}</td>
                  <td className="td-num">${pump.maintenance_cost_last_year.toLocaleString()}</td>
                  <td>{pump.maintenance_cost_trend}</td>
                  {pump.scores.map((s, i) => (
                    <td key={i} className="td-score">{s.toFixed(2)}</td>
                  ))}
                </tr>

                {expandedId === pump.asset_id && (
                  <tr className="detail-row">
                    <td colSpan={15}>
                      <PumpDetail pump={pump} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function PumpDetail({ pump }) {
  return (
    <div className="pump-detail">
      <div className="detail-group">
        <h4>Identity</h4>
        <dl>
          <dt>Asset ID</dt>        <dd>{pump.asset_id}</dd>
          <dt>Name</dt>            <dd>{pump.asset_name}</dd>
          <dt>Manufacturer</dt>    <dd>{pump.manufacturer}</dd>
          <dt>Model</dt>           <dd>{pump.model_number}</dd>
          <dt>Location</dt>        <dd>{pump.location}</dd>
          <dt>Install Date</dt>    <dd>{pump.install_date}</dd>
          <dt>Expected Lifespan</dt><dd>{pump.expected_lifespan_years} yrs</dd>
        </dl>
      </div>

      <div className="detail-group">
        <h4>Operational</h4>
        <dl>
          <dt>Rated Flow</dt>       <dd>{pump.rated_flow_rate_gpm} GPM</dd>
          <dt>Actual Flow</dt>      <dd>{pump.actual_flow_rate_gpm} GPM</dd>
          <dt>Hours / Day</dt>      <dd>{pump.operating_hours_per_day}</dd>
          <dt>Total Runtime</dt>    <dd>{pump.total_runtime_hours.toLocaleString()} hrs</dd>
        </dl>
      </div>

      <div className="detail-group">
        <h4>Condition / Health</h4>
        <dl>
          <dt>Condition Score</dt>  <dd>{pump.condition_score} / 10</dd>
          <dt>Vibration</dt>       <dd>{pump.vibration_level}</dd>
          <dt>Temperature</dt>     <dd>{pump.temperature_celsius} °C</dd>
          <dt>Seal</dt>            <dd>{pump.seal_condition}</dd>
          <dt>Bearing</dt>         <dd>{pump.bearing_condition}</dd>
        </dl>
      </div>

      <div className="detail-group">
        <h4>Maintenance</h4>
        <dl>
          <dt>Last Maintenance</dt><dd>{pump.last_maintenance_date}</dd>
          <dt>PM Interval</dt>     <dd>{pump.maintenance_frequency_days} days</dd>
          <dt>Cost Last Year</dt>  <dd>${pump.maintenance_cost_last_year.toLocaleString()}</dd>
          <dt>Cost Trend</dt>      <dd>{pump.maintenance_cost_trend}</dd>
          <dt>Failures (3 yr)</dt> <dd>{pump.number_of_failures_last_3yr}</dd>
        </dl>
      </div>

      <div className="detail-group">
        <h4>AHP Scores (Saaty 1-9)</h4>
        <dl>
          <dt>C1 Criticality</dt>     <dd>{pump.score_criticality}</dd>
          <dt>C2 Condition</dt>       <dd>{pump.score_condition}</dd>
          <dt>C3 Failure Prob.</dt>    <dd>{pump.score_failure_probability}</dd>
          <dt>C4 Downtime Impact</dt> <dd>{pump.score_downtime_impact}</dd>
          <dt>C5 Cost Trend</dt>      <dd>{pump.score_maintenance_cost_trend}</dd>
        </dl>
      </div>

      <div className="detail-group">
        <h4>Calculated</h4>
        <dl>
          <dt>Age</dt>              <dd>{pump.age_years} yrs</dd>
          <dt>Usage Intensity</dt>  <dd>{pump.usage_intensity_pct}%</dd>
          <dt>Days Since Maint.</dt><dd>{pump.days_since_maintenance}</dd>
        </dl>
      </div>
    </div>
  )
}
