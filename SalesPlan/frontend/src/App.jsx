import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useEffect } from 'react'
import { theme } from './theme'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Header from './components/Header'
import Home from './pages/Home'
import DivisionPlan from './pages/DivisionPlan'
import DivisionGrowthStructure from './pages/DivisionGrowthStructure'
import DepartmentPlan from './pages/DepartmentPlan'
import DepartmentGrowthMatrix from './pages/DepartmentGrowthMatrix'
import NewDeptPlan from './pages/NewDeptPlan'
import AttributeCorrection from './pages/AttributeCorrection'
import BaseCorrection from './pages/BaseCorrection'
import FinalResults from './pages/FinalResults'
import MrpImport from './pages/MrpImport'
import MrpOutput from './pages/MrpOutput'
import PwwDeviation from './pages/PwwDeviation'
import SorDeviation from './pages/SorDeviation'
import DisplayTypePlan from './pages/DisplayTypePlan'
import MrpReapportionment from './pages/MrpReapportionment'
import SyncEngine from './pages/SyncEngine'
import Reconciliation from './pages/Reconciliation'

// Served standalone at the root (:8002) or mounted under /planning/* on the
// unified platform (:8010) - detect which at runtime so deep links, hard
// refreshes, and browser back/forward all resolve against the real server
// route rather than assuming one deployment.
const basename = window.location.pathname.startsWith('/planning') ? '/planning' : '/'

export default function App() {
  useEffect(() => {
    const root = document.documentElement
    Object.entries(theme).forEach(([key, val]) => {
      root.style.setProperty(`--${key}`, val)
    })
    document.body.style.margin = '0'
    document.body.style.fontFamily = theme.fontUI
    document.body.style.background = theme.surfaceAlt
    document.body.style.color = theme.textPrimary
  }, [])

  // <details class="sp-menu|sp-info"> popovers (index.css): an outside click, a click on a menu item, or Escape
  // closes them; Escape hands focus back to the summary.
  useEffect(() => {
    const SEL = 'details.sp-menu[open], details.sp-info[open]'
    const onDown = e => {
      const keep = e.target.closest?.('details.sp-menu, details.sp-info')
      document.querySelectorAll(SEL).forEach(d => { if (d !== keep) d.open = false })
    }
    const onClick = e => {
      const item = e.target.closest?.('details.sp-menu > .sp-menu-pop > button, details.sp-menu > .sp-menu-pop > a')
      if (item) item.closest('details').open = false
    }
    const onKey = e => {
      if (e.key !== 'Escape') return
      const open = [...document.querySelectorAll(SEL)]
      if (!open.length) return
      const back = open.find(d => d.contains(document.activeElement)) || open[open.length - 1]
      open.forEach(d => { d.open = false })
      back.querySelector('summary')?.focus()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('click', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('click', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  return (
    <BrowserRouter basename={basename}>
      <TopBar />
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        <Sidebar />
        <div style={{ marginLeft: 220, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Header />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/division-plan" element={<DivisionPlan />} />
            <Route path="/division-plan/growth" element={<DivisionGrowthStructure />} />
            <Route path="/department-plan" element={<DepartmentPlan />} />
            <Route path="/department-plan/growth" element={<DepartmentGrowthMatrix />} />
            <Route path="/department-plan/new-depts" element={<NewDeptPlan />} />
            <Route path="/department-plan/attr-correction" element={<AttributeCorrection />} />
            <Route path="/department-plan/base-correction" element={<BaseCorrection />} />
            <Route path="/department-plan/final-results" element={<FinalResults />} />
            <Route path="/mrp-plan/import" element={<MrpImport />} />
            <Route path="/mrp-plan/output" element={<MrpOutput />} />
            <Route path="/deviation/pww" element={<PwwDeviation />} />
            <Route path="/deviation/sor" element={<SorDeviation />} />
            <Route path="/display-type" element={<DisplayTypePlan />} />
            <Route path="/mrp-plan/reapportionment" element={<MrpReapportionment />} />
            <Route path="/sync" element={<SyncEngine />} />
            <Route path="/reconciliation" element={<Reconciliation />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
