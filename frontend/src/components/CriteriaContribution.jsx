import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'

const CRITERIA = [
  { key: 'c1', label: 'Criticality',   color: '#2563eb' },
  { key: 'c2', label: 'Condition',     color: '#16a34a' },
  { key: 'c3', label: 'Failure Prob.', color: '#dc2626' },
  { key: 'c4', label: 'Downtime Imp.', color: '#f59e0b' },
  { key: 'c5', label: 'Cost Trend',    color: '#8b5cf6' },
]

export default function CriteriaContribution({ assets }) {
  if (!assets.length) return null

  const data = assets.map(a => ({
    name: a.asset_id,
    c1: +a.weighted_scores[0].toFixed(3),
    c2: +a.weighted_scores[1].toFixed(3),
    c3: +a.weighted_scores[2].toFixed(3),
    c4: +a.weighted_scores[3].toFixed(3),
    c5: +a.weighted_scores[4].toFixed(3),
  }))

  return (
    <section className="card criteria-contribution">
      <h2 className="section-title">Criteria Contribution Breakdown</h2>
      <p className="section-sub">
        Weighted contribution of each criterion to the overall risk score per pump.
      </p>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: '#475569' }}
            axisLine={{ stroke: '#cbd5e1' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#94a3b8' }}
            axisLine={false}
            tickLine={false}
            label={{ value: 'Weighted Score', angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: '#94a3b8' } }}
          />
          <Tooltip
            formatter={(val, name) => {
              const c = CRITERIA.find(cr => cr.key === name)
              return [val.toFixed(3), c?.label ?? name]
            }}
          />
          <Legend
            formatter={val => {
              const c = CRITERIA.find(cr => cr.key === val)
              return c?.label ?? val
            }}
            wrapperStyle={{ fontSize: 13 }}
          />
          {CRITERIA.map(c => (
            <Bar
              key={c.key}
              dataKey={c.key}
              stackId="stack"
              fill={c.color}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
