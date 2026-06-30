import { useState } from 'react'

export function useAHP() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function calculateWeights(matrix) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/ahp/calculate-weights', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matrix }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const d = body?.detail
        const msg = typeof d === 'string'
          ? d
          : Array.isArray(d)
            ? d.map(e => e?.msg ?? String(e)).join('; ')
            : `Server error ${res.status}`
        throw new Error(msg)
      }
      const data = await res.json()
      setResult(data)
      return data
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setLoading(false)
    }
  }

  return { calculateWeights, result, loading, error }
}
