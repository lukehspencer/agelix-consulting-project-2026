import { useState } from 'react'
import AHPMatrix from './components/AHPMatrix'

export default function App() {
  const [ahpResult, setAhpResult] = useState(null)

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <h1>Asset Risk Dashboard</h1>
          <p className="header-sub">
            Agelix Consulting — Centrifugal Pump Asset Management
          </p>
        </div>
      </header>

      <main className="app-main">
        <AHPMatrix onWeightsUpdate={setAhpResult} />
      </main>
    </div>
  )
}
