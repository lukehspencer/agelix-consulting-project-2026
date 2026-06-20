import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts'

const CRITERIA_SHORT = ['C1', 'C2', 'C3', 'C4', 'C5']

function riskColor(score) {
  if (score <= 3) return '#22c55e'
  if (score <= 6) return '#eab308'
  return '#ef4444'
}

export default function RiskRanking({ assets }) {
  if (!assets.length) return null

  const chartData = assets.map(a => ({
    name: a.asset_id,
    risk_factor: +a.risk_factor.toFixed(2),
  }))

  return (
    <section className="card risk-ranking">
      <h2 className="section-title">Risk Ranking</h2>
      <p className="section-sub">
        Pumps ranked highest to lowest by overall risk factor.
      </p>

      <div className="registry-scroll">
        <table className="ranking-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Asset Name</th>
              {CRITERIA_SHORT.map(c => (
                <th key={c} className="th-ws">w{c.slice(1)}*s{c.slice(1)}</th>
              ))}
              <th className="th-rf">Risk Factor</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a, i) => (
              <tr key={a.asset_id}>
                <td className="td-rank">{i + 1}</td>
                <td>{a.asset_name}</td>
                {a.weighted_scores.map((ws, j) => (
                  <td key={j} className="td-ws">{ws.toFixed(3)}</td>
                ))}
                <td className="td-rf">
                  <span className="rf-pill" style={{ background: riskColor(a.risk_factor) }}>
                    {a.risk_factor.toFixed(2)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="ranking-chart">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 24, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12, fill: '#475569' }}
              axisLine={{ stroke: '#cbd5e1' }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 9]}
              tick={{ fontSize: 12, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip formatter={val => val.toFixed(2)} />
            <Bar dataKey="risk_factor" radius={[6, 6, 0, 0]} maxBarSize={64}>
              <LabelList
                dataKey="risk_factor"
                position="top"
                style={{ fontSize: 12, fontWeight: 600, fill: '#334155' }}
              />
              {chartData.map((d, i) => (
                <Cell key={i} fill={riskColor(d.risk_factor)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <div className="risk-legend">
          <span className="risk-legend-item">
            <span className="risk-dot" style={{ background: '#22c55e' }} /> 1–3 Low
          </span>
          <span className="risk-legend-item">
            <span className="risk-dot" style={{ background: '#eab308' }} /> 4–6 Medium
          </span>
          <span className="risk-legend-item">
            <span className="risk-dot" style={{ background: '#ef4444' }} /> 7–9 High
          </span>
        </div>
      </div>
    </section>
  )
}
