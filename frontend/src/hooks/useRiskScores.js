import { useState, useEffect } from 'react'

export function useRiskScores(weights) {
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const weightsKey = weights ? JSON.stringify(weights) : ''

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        let url = '/ahp/assets'
        if (weights) {
          const params = weights.map(w => `weights=${w}`).join('&')
          url += `?${params}`
        }
        const res = await fetch(url)
        if (!res.ok) throw new Error(`Server error ${res.status}`)
        const data = await res.json()
        if (!cancelled) setAssets(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [weightsKey])

  return { assets, loading, error }
}
