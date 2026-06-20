import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea, LabelList,
} from 'recharts'

export default function RiskScatterPlot({ assets }) {
  if (!assets.length) return null

  const data = assets.map(a => ({
    condition: a.condition_score,
    risk: +a.risk_factor.toFixed(2),
    label: a.asset_id,
  }))

  return (
    <section className="card risk-scatter">
      <h2 className="section-title">Risk vs Condition</h2>
      <p className="section-sub">
        Each pump plotted by raw condition score and overall risk factor.
        Reference lines divide four quadrants at condition = 5 and risk = 6.
      </p>

      <ResponsiveContainer width="100%" height={380}>
        <ScatterChart margin={{ top: 20, right: 30, left: 10, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />

          <ReferenceArea x1={1} x2={5} y1={6} y2={9.5} fill="#fef2f2" fillOpacity={0.4} />
          <ReferenceArea x1={5} x2={10.5} y1={6} y2={9.5} fill="#fffbeb" fillOpacity={0.4} />
          <ReferenceArea x1={1} x2={5} y1={0.5} y2={6} fill="#f0f9ff" fillOpacity={0.4} />
          <ReferenceArea x1={5} x2={10.5} y1={0.5} y2={6} fill="#f0fdf4" fillOpacity={0.4} />

          <XAxis
            type="number"
            dataKey="condition"
            name="Condition Score"
            domain={[1, 10]}
            tick={{ fontSize: 12, fill: '#475569' }}
            axisLine={{ stroke: '#cbd5e1' }}
            tickLine={false}
            label={{ value: 'Condition Score (1-10)', position: 'insideBottom', offset: -10, style: { fontSize: 13, fill: '#64748b' } }}
          />
          <YAxis
            type="number"
            dataKey="risk"
            name="Risk Factor"
            domain={[1, 9]}
            tick={{ fontSize: 12, fill: '#475569' }}
            axisLine={{ stroke: '#cbd5e1' }}
            tickLine={false}
            label={{ value: 'Risk Factor (1-9)', angle: -90, position: 'insideLeft', offset: 5, style: { fontSize: 13, fill: '#64748b' } }}
          />

          <ReferenceLine x={5} stroke="#94a3b8" strokeDasharray="6 4" strokeWidth={1.5} />
          <ReferenceLine y={6} stroke="#94a3b8" strokeDasharray="6 4" strokeWidth={1.5} />

          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            formatter={(val, name) => {
              if (name === 'Condition Score') return [val, 'Condition']
              return [val, 'Risk Factor']
            }}
          />

          <Scatter data={data} fill="#2563eb" r={7}>
            <LabelList
              dataKey="label"
              position="top"
              offset={10}
              style={{ fontSize: 11, fontWeight: 600, fill: '#334155' }}
            />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      <div className="quadrant-legend">
        <span className="ql-item">
          <span className="ql-swatch" style={{ background: '#fef2f2' }} />
          High Risk / Poor Condition
        </span>
        <span className="ql-item">
          <span className="ql-swatch" style={{ background: '#fffbeb' }} />
          High Risk / Good Condition
        </span>
        <span className="ql-item">
          <span className="ql-swatch" style={{ background: '#f0f9ff' }} />
          Low Risk / Poor Condition
        </span>
        <span className="ql-item">
          <span className="ql-swatch" style={{ background: '#f0fdf4' }} />
          Low Risk / Good Condition
        </span>
      </div>
    </section>
  )
}
