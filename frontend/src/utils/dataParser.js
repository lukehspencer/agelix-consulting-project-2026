const REQUIRED_FIELDS = [
  'asset_id', 'asset_name', 'manufacturer', 'model_number', 'location',
  'install_date', 'expected_lifespan_years',
  'rated_flow_rate_gpm', 'actual_flow_rate_gpm', 'operating_hours_per_day', 'total_runtime_hours',
  'condition_score', 'vibration_level', 'temperature_celsius', 'seal_condition', 'bearing_condition',
  'last_maintenance_date', 'maintenance_frequency_days', 'maintenance_cost_last_year',
  'maintenance_cost_trend', 'number_of_failures_last_3yr',
  'score_criticality', 'score_condition', 'score_failure_probability',
  'score_downtime_impact', 'score_maintenance_cost_trend',
  'age_years', 'usage_intensity_pct', 'days_since_maintenance',
]

const NUMERIC_FIELDS = new Set([
  'expected_lifespan_years', 'rated_flow_rate_gpm', 'actual_flow_rate_gpm',
  'operating_hours_per_day', 'total_runtime_hours', 'condition_score',
  'temperature_celsius', 'maintenance_frequency_days', 'maintenance_cost_last_year',
  'number_of_failures_last_3yr',
  'score_criticality', 'score_condition', 'score_failure_probability',
  'score_downtime_impact', 'score_maintenance_cost_trend',
  'age_years', 'usage_intensity_pct', 'days_since_maintenance',
])

const ENUM_RULES = {
  vibration_level: ['Normal', 'High', 'Critical'],
  seal_condition: ['Good', 'Worn', 'Leaking'],
  bearing_condition: ['Good', 'Worn', 'Failed'],
  maintenance_cost_trend: ['Increasing', 'Stable', 'Decreasing'],
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function parseCSVLine(line) {
  const values = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"'
        i++
      } else if (ch === '"') {
        inQuotes = false
      } else {
        current += ch
      }
    } else if (ch === '"') {
      inQuotes = true
    } else if (ch === ',') {
      values.push(current.trim())
      current = ''
    } else {
      current += ch
    }
  }
  values.push(current.trim())
  return values
}

function parseCSV(text) {
  const lines = text.split(/\r?\n/).filter(l => l.trim())
  if (lines.length < 2) return { pumps: [], errors: ['CSV must have a header row and at least one data row.'] }

  const headers = parseCSVLine(lines[0])
  const pumps = []
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i])
    const obj = {}
    headers.forEach((h, j) => { obj[h] = values[j] ?? '' })
    pumps.push(obj)
  }
  return { pumps, errors: [] }
}

function coerceNumericFields(pumps) {
  return pumps.map(pump => {
    const out = { ...pump }
    for (const key of NUMERIC_FIELDS) {
      if (key in out && typeof out[key] === 'string') {
        out[key] = Number(out[key])
      }
    }
    return out
  })
}

function validatePumps(pumps) {
  const errors = []

  if (pumps.length < 1) {
    errors.push('File must contain at least 1 pump asset.')
    return errors
  }
  if (pumps.length > 20) {
    errors.push(`File contains ${pumps.length} pump assets. Maximum allowed is 20.`)
    return errors
  }

  pumps.forEach((pump, i) => {
    const label = pump.asset_id || `Row ${i + 1}`

    const missing = REQUIRED_FIELDS.filter(f => !(f in pump) || pump[f] === '' || pump[f] === undefined)
    if (missing.length) {
      errors.push(`${label}: missing fields: ${missing.join(', ')}`)
      return
    }

    for (const field of NUMERIC_FIELDS) {
      if (typeof pump[field] !== 'number' || !isFinite(pump[field])) {
        errors.push(`${label}: "${field}" must be a number, got "${pump[field]}"`)
      }
    }

    if (typeof pump.condition_score === 'number' && (pump.condition_score < 1 || pump.condition_score > 10)) {
      errors.push(`${label}: condition_score must be between 1 and 10, got ${pump.condition_score}`)
    }

    for (const [field, allowed] of Object.entries(ENUM_RULES)) {
      if (!allowed.includes(pump[field])) {
        errors.push(`${label}: "${field}" must be one of [${allowed.join(', ')}], got "${pump[field]}"`)
      }
    }

    if (!DATE_RE.test(pump.install_date) || isNaN(new Date(pump.install_date).getTime())) {
      errors.push(`${label}: install_date must be YYYY-MM-DD, got "${pump.install_date}"`)
    }
    if (!DATE_RE.test(pump.last_maintenance_date) || isNaN(new Date(pump.last_maintenance_date).getTime())) {
      errors.push(`${label}: last_maintenance_date must be YYYY-MM-DD, got "${pump.last_maintenance_date}"`)
    }
  })

  return errors
}

export async function parseUploadedFile(file) {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.json') && !name.endsWith('.csv')) {
    return { pumps: [], errors: ['File must be .json or .csv'] }
  }

  const text = await file.text()
  let rawPumps

  if (name.endsWith('.json')) {
    try {
      const parsed = JSON.parse(text)
      rawPumps = Array.isArray(parsed) ? parsed : [parsed]
    } catch {
      return { pumps: [], errors: ['Invalid JSON. Could not parse file.'] }
    }
  } else {
    const result = parseCSV(text)
    if (result.errors.length) return result
    rawPumps = result.pumps
  }

  const pumps = coerceNumericFields(rawPumps)
  const errors = validatePumps(pumps)
  if (errors.length) return { pumps: [], errors }

  return { pumps, errors: [] }
}

export function downloadTemplate() {
  const headers = REQUIRED_FIELDS.join(',')
  const example = [
    'PUMP-001', 'Example Cooling Pump', 'Flowserve', 'PVXM-6x8', '"Plant A / Line 1"',
    '2015-06-01', '20',
    '500', '380', '18', '85000',
    '6', 'Normal', '65', 'Good', 'Worn',
    '2026-04-15', '120', '3200', 'Stable', '2',
    '5.44', '5.44', '4.56', '5.44', '5.44',
    '11.0', '76.0', '67',
  ].join(',')
  const csv = headers + '\n' + example + '\n'
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'pump_template.csv'
  a.click()
  URL.revokeObjectURL(url)
}
