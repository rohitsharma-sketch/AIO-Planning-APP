import { useState, useEffect } from 'react'
import { getMe } from './lib/api'
import VersionSettingTab from './components/VersionSettingTab'
import CalendarisationTab from './components/CalendarisationTab'
import PeriodSettingTab from './components/PeriodSettingTab'
import StoreClusterMappingTab from './components/StoreClusterMappingTab'
import CalendarisedSalesTab from './components/CalendarisedSalesTab'

const TABS = [
  { id: 'version', label: 'Version Setting', Component: VersionSettingTab },
  { id: 'calendarisation', label: 'Calendarisation', Component: CalendarisationTab },
  { id: 'period', label: 'Period Setting', Component: PeriodSettingTab },
  { id: 'salesdata', label: 'Store-Cluster Mapping', Component: StoreClusterMappingTab },
  { id: 'calendarisedsales', label: 'Calendarised Sales', Component: CalendarisedSalesTab },
]

export default function App() {
  const [activeModule, setActiveModule] = useState('calendarisation')
  const [me, setMe] = useState(null)

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  const isPlanner = me?.role === 'planner'
  const ActiveComponent = TABS.find(t => t.id === activeModule)?.Component

  return (
    <div className="app-shell">
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
      {/* onNavigate lets a tab hand control to another tab by id — used by
          VersionSettingTab's "Create Calendar", which re-syncs festival dates and
          then drops the user on Calendarisation, the way the old app's
          createCalendar() called switchModule('calendarisation'). */}
      {ActiveComponent && <ActiveComponent isPlanner={isPlanner} onNavigate={setActiveModule} />}
    </div>
  )
}
