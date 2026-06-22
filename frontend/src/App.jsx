import Dashboard from './components/Dashboard'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <h1>Asset Management Dashboard</h1>
          <p className="header-sub">
            Agelix Consulting
          </p>
        </div>
      </header>

      <main className="app-main">
        <Dashboard />
      </main>
    </div>
  )
}
