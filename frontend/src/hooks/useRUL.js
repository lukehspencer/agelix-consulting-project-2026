import { useState, useEffect, useCallback } from 'react'

export function useRUL(weights, cr, assets) {
  const [rulPredictions, setRulPredictions] = useState({})
  const [rulExplanations, setRulExplanations] = useState({})
  const [isLoadingPredictions, setIsLoadingPredictions] = useState(false)
  const [isLoadingExplanation, setIsLoadingExplanation] = useState({})
  const [error, setError] = useState(null)

  const weightsKey = weights ? JSON.stringify(weights) : ''
  const assetsKey = assets.map(a => a.asset_id).join(',')

  useEffect(() => {
    if (!weights || !assets.length) return

    if (cr === null || cr === undefined || cr > 0.10) {
      setRulPredictions({})
      setError(cr > 0.10 ? 'AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons before requesting RUL predictions.' : null)
      return
    }

    let cancelled = false
    setIsLoadingPredictions(true)
    setError(null)

    async function fetchAll() {
      const results = {}

      await Promise.all(assets.map(async (asset) => {
        const res = await fetch('/rul/predict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pump: asset,
            weights,
            scores: asset.scores,
            cr,
          }),
        })
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}))
          throw new Error(detail?.detail ?? `RUL predict failed for ${asset.asset_id}`)
        }
        const data = await res.json()
        results[data.asset_id] = {
          rul_years: data.rul_years,
          ci_low: data.ci_low,
          ci_high: data.ci_high,
        }
      }))

      if (!cancelled) {
        setRulPredictions(results)
        setIsLoadingPredictions(false)
      }
    }

    fetchAll().catch(err => {
      if (!cancelled) {
        setError(err.message)
        setIsLoadingPredictions(false)
      }
    })

    return () => { cancelled = true }
  }, [weightsKey, assetsKey, cr])

  const fetchExplanation = useCallback(async (pump, scores, riskFactor) => {
    const id = pump.asset_id
    const pred = rulPredictions[id]
    if (!pred || !weights) return

    setIsLoadingExplanation(prev => ({ ...prev, [id]: true }))

    try {
      const res = await fetch('/rul/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pump,
          weights,
          scores,
          risk_factor: riskFactor,
          predicted_rul: pred.rul_years,
          ci_low: pred.ci_low,
          ci_high: pred.ci_high,
          cr: cr ?? 0,
        }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail?.detail ?? `RUL explain failed for ${id}`)
      }
      const data = await res.json()
      setRulExplanations(prev => ({ ...prev, [id]: data.explanation }))
    } catch (err) {
      setRulExplanations(prev => ({ ...prev, [id]: `Error: ${err.message}` }))
    } finally {
      setIsLoadingExplanation(prev => ({ ...prev, [id]: false }))
    }
  }, [rulPredictions, weights, cr])

  return {
    rulPredictions,
    rulExplanations,
    fetchExplanation,
    isLoadingPredictions,
    isLoadingExplanation,
    error,
  }
}
