import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LabelList,
} from 'recharts'

const CRITERIA = [
  'Criticality',
  'Condition',
  'Failure Prob.',
  'Downtime Impact',
  'Cost Trend',
]

export default function WeightDisplay({ weights }) {
  if (!weights) return null

  const data = CRITERIA.map((name, i) => ({
    name,
    weight: +(weights[i] * 100).toFixed(1),
  }))

  return (
    <section className="card weight-display">
      <h2 className="section-title">AHP Weight Distribution</h2>
      <p className="section-sub">
        Relative importance of each criterion based on pairwise comparisons.
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 24, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 13, fill: '#475569' }}
            axisLine={{ stroke: '#cbd5e1' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#94a3b8' }}
            axisLine={false}
            tickLine={false}
            domain={[0, 'auto']}
            unit="%"
          />
          <Tooltip formatter={val => `${val}%`} />
          <Bar dataKey="weight" fill="#2563eb" radius={[6, 6, 0, 0]} maxBarSize={72}>
            <LabelList
              dataKey="weight"
              position="top"
              formatter={val => `${val}%`}
              style={{ fontSize: 12, fontWeight: 600, fill: '#334155' }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
