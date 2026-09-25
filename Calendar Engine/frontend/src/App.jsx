import { useState, useEffect } from 'react'
import { getMe } from './lib/api'
import VersionSettingTab from './components/VersionSettingTab'
import CalendarisationTab from './components/CalendarisationTab'
import StoreClusterMappingTab from './components/StoreClusterMappingTab'
import CalendarisedSalesTab from './components/CalendarisedSalesTab'

const TABS = [
  { id: 'version', label: 'Version Setting', Component: VersionSettingTab },
  { id: 'calendarisation', label: 'Calendarisation', Component: CalendarisationTab },
  { id: 'salesdata', label: 'Store-Cluster Mapping', Component: StoreClusterMappingTab },
  { id: 'calendarisedsales', label: 'Calendarised Sales', Component: CalendarisedSalesTab },
]

export default function App() {
  const [activeModule, setActiveModule] = useState('calendarisation')
  const [me, setMe] = useState(null)
  const [engineVersion, setEngineVersion] = useState(() => {
    try { return parseInt(localStorage.getItem('ce_engine_version') || '1', 10) || 1 }
    catch { return 1 }
  })

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  function handleVersionChange(v) {
    setEngineVersion(v)
    try { localStorage.setItem('ce_engine_version', String(v)) } catch {}
  }

  const isPlanner = me?.role === 'planner'
  const ActiveComponent = TABS.find(t => t.id === activeModule)?.Component

  const displayName = me?.name || me?.email?.split('@')[0] || null

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-brand">
          <div className="app-header-icon">CE</div>
          <div>
            <div className="app-header-title">Calendar Engine</div>
            <div className="app-header-sub">RS Planning · CityKart</div>
          </div>
        </div>
        <div className="app-header-spacer" />
        <div className="app-engine">
          <span>Engine</span>
          <select
            value={engineVersion}
            onChange={e => handleVersionChange(Number(e.target.value))}
            aria-label="Calendar engine version"
          >
            <option value={1}>V1 - LY Same Month</option>
            <option value={2}>V2 - Adjacent Month (+/-1)</option>
          </select>
        </div>
        {displayName && <div className="app-header-user">{displayName}</div>}
      </header>
      <nav className="mod-nav">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`mod-tab${activeModule === t.id ? ' active' : ''}`}
            onClick={() => setActiveModule(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {/* onNavigate lets a tab hand control to another tab by id */}
      {ActiveComponent && <ActiveComponent isPlanner={isPlanner} onNavigate={setActiveModule} engineVersion={engineVersion} />}
    </div>
  )
}
