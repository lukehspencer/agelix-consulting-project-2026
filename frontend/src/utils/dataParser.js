const REQUIRED_FIELDS = [
  'asset_id', 'asset_name', 'manufacturer', 'model_number', 'location',
  'total_runtime_hours', 'operating_hours_per_day',
  'condition_score', 'vibration_level', 'temperature_celsius',
  'seal_condition', 'bearing_condition',
  'number_of_failures_last_3yr', 'days_since_maintenance',
  'maintenance_frequency_days', 'maintenance_cost_last_year',
  'maintenance_cost_trend', 'criticality_raw', 'downtime_impact_raw',
  'rolling_vibration_mean', 'rolling_vibration_std',
  'rolling_winding_temp_mean', 'rolling_spm_temp_mean',
  'rolling_current_mean', 'voltage_anomaly_count', 'true_rul_days',
]

const NUMERIC_FIELDS = new Set([
  'total_runtime_hours', 'operating_hours_per_day',
  'condition_score', 'temperature_celsius',
  'number_of_failures_last_3yr', 'days_since_maintenance',
  'maintenance_frequency_days', 'maintenance_cost_last_year',
  'criticality_raw', 'downtime_impact_raw',
  'rolling_vibration_mean', 'rolling_vibration_std',
  'rolling_winding_temp_mean', 'rolling_spm_temp_mean',
  'rolling_current_mean', 'voltage_anomaly_count', 'true_rul_days',
])

const ENUM_RULES = {
  vibration_level: ['Normal', 'High', 'Critical'],
  seal_condition: ['Good', 'Worn', 'Leaking'],
  bearing_condition: ['Good', 'Worn', 'Failed'],
  maintenance_cost_trend: ['Increasing', 'Stable', 'Decreasing'],
}

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
    if (typeof pump.criticality_raw === 'number' && (pump.criticality_raw < 1 || pump.criticality_raw > 10)) {
      errors.push(`${label}: criticality_raw must be between 1 and 10, got ${pump.criticality_raw}`)
    }
    if (typeof pump.downtime_impact_raw === 'number' && (pump.downtime_impact_raw < 1 || pump.downtime_impact_raw > 10)) {
      errors.push(`${label}: downtime_impact_raw must be between 1 and 10, got ${pump.downtime_impact_raw}`)
    }
    if (typeof pump.total_runtime_hours === 'number' && pump.total_runtime_hours <= 0) {
      errors.push(`${label}: total_runtime_hours must be > 0, got ${pump.total_runtime_hours}`)
    }
    if (typeof pump.rolling_vibration_mean === 'number' && pump.rolling_vibration_mean < 0) {
      errors.push(`${label}: rolling_vibration_mean must be >= 0, got ${pump.rolling_vibration_mean}`)
    }
    if (typeof pump.rolling_vibration_std === 'number' && pump.rolling_vibration_std < 0) {
      errors.push(`${label}: rolling_vibration_std must be >= 0, got ${pump.rolling_vibration_std}`)
    }
    if (typeof pump.voltage_anomaly_count === 'number' && pump.voltage_anomaly_count < 0) {
      errors.push(`${label}: voltage_anomaly_count must be >= 0, got ${pump.voltage_anomaly_count}`)
    }
    if (typeof pump.true_rul_days === 'number' && pump.true_rul_days < 0) {
      errors.push(`${label}: true_rul_days must be >= 0, got ${pump.true_rul_days}`)
    }

    for (const [field, allowed] of Object.entries(ENUM_RULES)) {
      if (!allowed.includes(pump[field])) {
        errors.push(`${label}: "${field}" must be one of [${allowed.join(', ')}], got "${pump[field]}"`)
      }
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
    'KSB-CALIO-3040-9000', '"KSB Calio 3040 - Unit 9000"', 'KSB', 'Calio 30-40', '"Plant 2"',
    '8500', '22',
    '6', 'High', '68.4', 'Worn', 'Good',
    '1', '45', '90', '2500', 'Stable',
    '7', '6',
    '1.8', '0.4', '68.4', '72.1', '0.61',
    '2', '280',
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
