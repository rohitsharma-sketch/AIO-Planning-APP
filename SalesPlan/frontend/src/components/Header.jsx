import { useLocation } from 'react-router-dom'
import { theme } from '../theme'

// Title per route - one header for every page (pages used to add their own,
// and only 3 of 16 did, so the navy frame came and went between pages).
const TITLES = [
  ['/division-plan/growth', 'Division Plan · Growth Structure'],
  ['/division-plan', 'Division Plan · Plan Setup'],
  ['/department-plan/growth', 'Department Plan · Growth Matrix'],
  ['/department-plan/new-depts', 'Department Plan · New Depts'],
  ['/department-plan/attr-correction', 'Department Plan · Attribute Correction'],
  ['/department-plan/base-correction', 'Department Plan · Base Correction'],
  ['/department-plan/final-results', 'Department Plan · Final Results'],
  ['/department-plan', 'Department Plan · Master Setup'],
  ['/mrp-plan/import', "MRP Plan · Buyer's Input"],
  ['/mrp-plan/reapportionment', 'MRP Plan · Re-apportionment'],
  ['/mrp-plan/output', 'MRP Plan · Plan Output'],
  ['/deviation/pww', 'MRP Plan · PW/W Deviation'],
  ['/deviation/sor', 'MRP Plan · SOR Deviation'],
  ['/display-type', 'Display Type Plan'],
  ['/sync', 'Sales Sync'],
]

// Page header - same navy as the sidebar, so the chrome reads as one frame
// around the light data area (RS Planning suite look, 2026-09-25).
export default function Header() {
  const { pathname } = useLocation()
  const title = TITLES.find(([p]) => pathname.startsWith(p))?.[1] || 'Home'
  const today = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

  return (
    <div style={{
      height: 56,
      background: theme.navy,
      borderBottom: '1px solid rgba(255,255,255,0.08)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 28px',
      flexShrink: 0,
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      <span style={{ fontSize: 16, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>{title}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>{today}</span>
        <span style={{
          fontSize: 11.5,
          fontWeight: 700,
          background: 'rgba(255,255,255,0.10)',
          border: '1px solid rgba(255,255,255,0.18)',
          color: '#fff',
          borderRadius: 999,
          padding: '3px 11px',
          letterSpacing: 0.3,
        }}>FY 2027–28</span>
      </div>
    </div>
  )
}
