import { NavLink, useLocation, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { theme } from '../theme'
import Icon from './Icon'

const DIVISION_PLAN_SUB = [
  { label: 'Plan Setup', to: '/division-plan' },
]

const DEPARTMENT_PLAN_SUB = [
  { label: 'Master Setup',    to: '/department-plan' },
  { label: 'Growth Matrix',   to: '/department-plan/growth' },
  { label: 'New Depts',       to: '/department-plan/new-depts',       optional: true },
  { label: 'Attr Correction', to: '/department-plan/attr-correction', optional: true },
  { label: 'Base Correction', to: '/department-plan/base-correction', optional: true },
  { label: 'Final Results',   to: '/department-plan/final-results',   final: true },
]

const navItems = [
  { label: 'Home', icon: 'home', to: '/' },
  { label: 'Division Plan',    icon: 'division', to: '/division-plan',   subItems: DIVISION_PLAN_SUB },
  { label: 'Department Plan',  icon: 'dept', to: '/department-plan', subItems: DEPARTMENT_PLAN_SUB },
  { label: 'MRP Plan', icon: 'mrp', to: '/mrp-plan', subItems: [
    { label: 'Buyer\'s Input',   to: '/mrp-plan/import' },
    { label: 'Re-apportionment', to: '/mrp-plan/reapportionment' },
    { label: 'PW/W Deviation',   to: '/deviation/pww',  optional: true },
    { label: 'SOR Deviation',    to: '/deviation/sor',  optional: true },
    { label: 'Plan Output',      to: '/mrp-plan/output', final: true },
  ]},
  { label: 'Display Type Plan', icon: 'display', to: '/display-type' },
  { label: 'Sales Sync',        icon: 'sync', to: '/sync' },
]

const DIV_DOT = {
  GM:     '#F97316',
  KIDS:   '#0EA5E9',
  LADIES: '#EC4899',
  MENS:   '#8B5CF6',
  RETAIL: '#14B8A6',
}

function PlanSnapshot() {
  const [data,      setData]      = useState(null)
  const [open,      setOpen]      = useState(true)
  const [selMonth,  setSelMonth]  = useState(null)
  const [loading,   setLoading]   = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch('/api/planning/dept-sales/plan-summary')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        setData(d)
        if (d?.months?.length) setSelMonth(d.months[0])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ padding: '10px 16px', fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>Loading plan…</div>
  )
  if (!data) return null

  const months = data.months || []
  const cur    = selMonth || months[0]

  return (
    <div style={{ borderTop: '1px solid rgba(255,255,255,0.10)', paddingTop: 10, marginTop: 4 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '4px 16px 8px', cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}>
        <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: 1.2, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', flex: 1 }}>
          Plan Snapshot
        </span>
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>{open ? '▾' : '▸'}</span>
      </div>

      {open && (
        <>
          {/* Month strip */}
          <div style={{ display: 'flex', gap: 4, padding: '0 12px 8px', flexWrap: 'wrap' }}>
            {months.map(m => (
              <button key={m} onClick={() => setSelMonth(m)} style={{
                padding: '2px 7px', borderRadius: 4, fontSize: 9, border: 'none', cursor: 'pointer',
                background: cur === m ? 'rgba(255,255,255,0.18)' : 'transparent',
                color: cur === m ? '#fff' : 'rgba(255,255,255,0.4)',
                fontWeight: cur === m ? 700 : 400,
              }}>{m}</button>
            ))}
          </div>

          {/* Grand total */}
          <div style={{ margin: '0 12px 8px', background: 'rgba(255,255,255,0.06)', borderRadius: 6, padding: '6px 10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', fontWeight: 600, letterSpacing: 0.5 }}>ALL DIVS · {cur}</span>
              {data.grand_growth != null && (
                <span style={{ fontSize: 9, fontWeight: 700, color: data.grand_growth >= 0 ? '#34D399' : '#F87171' }}>
                  {data.grand_growth > 0 ? '+' : ''}{data.grand_growth}%
                </span>
              )}
            </div>
            <div style={{ fontFamily: theme.fontMono, fontSize: 13, fontWeight: 700, color: '#fff', marginTop: 2 }}>
              ₹{Object.values(data.divisions).reduce((s, d) => s + (d[cur]?.ty || 0), 0).toFixed(1)}L
            </div>
          </div>

          {/* Per-division rows */}
          <div style={{ padding: '0 12px' }}>
            {Object.entries(data.divisions).map(([div, months_data]) => {
              const md = months_data[cur] || {}
              const dot = DIV_DOT[div] || '#94A3B8'
              return (
                <div key={div} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: dot, flexShrink: 0 }} />
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)', flex: 1, fontWeight: 500 }}>{div}</span>
                  <span style={{ fontFamily: theme.fontMono, fontSize: 10, color: 'rgba(255,255,255,0.8)', fontWeight: 600 }}>
                    ₹{(md.ty || 0).toFixed(1)}L
                  </span>
                  {md.growth != null && (
                    <span style={{ fontSize: 9, fontWeight: 700, color: md.growth >= 0 ? '#34D399' : '#F87171', minWidth: 32, textAlign: 'right' }}>
                      {md.growth > 0 ? '+' : ''}{md.growth}%
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          {/* Link to full results */}
          <Link to="/department-plan/final-results" style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
            margin: '10px 12px 4px', padding: '7px', borderRadius: 6,
            background: 'rgba(232,169,190,0.14)', border: '1px solid rgba(232,169,190,0.25)',
            color: 'rgba(232,169,190,0.9)', fontSize: 11, fontWeight: 700,
            textDecoration: 'none', letterSpacing: 0.3,
          }}>
            View Full Results →
          </Link>
        </>
      )}
    </div>
  )
}

export default function Sidebar() {
  const location = useLocation()

  return (
    <div style={{
      width: 220,
      minWidth: 220,
      height: '100vh',
      background: theme.sidebar,
      display: 'flex',
      flexDirection: 'column',
      position: 'fixed',
      top: 0,
      left: 0,
      zIndex: 100,
      overflowY: 'auto',
    }} className="sp-nav">
      <div style={{ height: 56, padding: '0 18px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid rgba(255,255,255,0.08)', flexShrink: 0 }}>
        <div style={{
          width: 30, height: 30, borderRadius: 8, background: theme.primary, color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 800, letterSpacing: 0.3,
        }}>SP</div>
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ fontSize: 14.5, fontWeight: 800, color: theme.sidebarText }}>Sales Plan</div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 1 }}>RS Planning · CityKart</div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: '10px 0' }}>
        {navItems.map((item) => {
          if (item.soon) {
            return (
              <div key={item.label} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 20px', color: 'rgba(255,255,255,0.35)',
                fontSize: 14, cursor: 'default', userSelect: 'none',
              }}>
                <Icon name={item.icon} />
                <span style={{ flex: 1 }}>{item.label}</span>
                <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.4)', borderRadius: 4, padding: '2px 5px', letterSpacing: 0.3 }}>Soon</span>
              </div>
            )
          }

          if (item.subItems) {
            const isParentActive = location.pathname.startsWith(item.to)
            return (
              <div key={item.label}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 18px',
                  color: isParentActive ? theme.sidebarText : 'rgba(255,255,255,0.72)',
                  background: 'transparent',
                  fontSize: 13.5, fontWeight: isParentActive ? 700 : 500,
                  borderLeft: '3px solid transparent',
                  marginTop: 6,
                  userSelect: 'none',
                }}>
                  <Icon name={item.icon} />
                  {item.label}
                </div>
                {item.subItems.map(sub => sub.soon ? (
                  <div key={sub.to} style={{
                    display: 'flex', alignItems: 'center',
                    paddingLeft: 36, paddingRight: 20, paddingTop: 7, paddingBottom: 7,
                    color: 'rgba(255,255,255,0.28)', fontSize: 12.5,
                    cursor: 'default', userSelect: 'none',
                    borderLeft: '3px solid transparent',
                  }}>
                    <span style={{ marginRight: 6, fontSize: 10, opacity: 0.5 }}>›</span>
                    <span style={{ flex: 1 }}>{sub.label}</span>
                    <span style={{ fontSize: 9, background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.3)', borderRadius: 4, padding: '1px 5px' }}>soon</span>
                  </div>
                ) : (
                  <NavLink key={sub.to} to={sub.to} end className="sp-navlink"
                    style={({ isActive }) => ({
                      display: 'flex', alignItems: 'center',
                      paddingLeft: 44, paddingRight: 18, paddingTop: 6, paddingBottom: 6,
                      color: isActive ? '#fff' : 'rgba(255,255,255,0.62)',
                      background: isActive ? theme.sidebarActive : 'transparent',
                      fontSize: 12.5, textDecoration: 'none',
                      fontWeight: isActive ? 700 : 500,
                      borderLeft: isActive ? `3px solid ${'#D98BA5'}` : '3px solid transparent',
                      transition: 'background 0.15s',
                    })}
                  >
                    <span style={{ flex: 1 }}>{sub.label}</span>
                    {sub.optional && (
                      <span style={{ fontSize: 9, background: 'rgba(255,255,255,0.10)', color: 'rgba(255,255,255,0.45)', borderRadius: 4, padding: '1px 5px', letterSpacing: 0.3, marginLeft: 4 }}>opt</span>
                    )}
                    {sub.final && (
                      <span style={{ fontSize: 9, background: 'rgba(232,169,190,0.18)', color: 'rgba(232,169,190,0.9)', borderRadius: 4, padding: '1px 5px', letterSpacing: 0.3, marginLeft: 4, fontWeight: 700 }}>out</span>
                    )}
                  </NavLink>
                ))}
              </div>
            )
          }

          return (
            <NavLink key={item.label} to={item.to} end={item.to === '/'} className="sp-navlink"
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 18px', marginTop: 6,
                color: isActive ? theme.sidebarText : 'rgba(255,255,255,0.72)',
                background: isActive ? theme.sidebarActive : 'transparent',
                fontSize: 13.5, textDecoration: 'none',
                fontWeight: isActive ? 700 : 500,
                borderLeft: isActive ? `3px solid ${'#D98BA5'}` : '3px solid transparent',
                transition: 'background 0.15s',
              })}
            >
              <Icon name={item.icon} />
              {item.label}
            </NavLink>
          )
        })}
      </nav>

      {/* ── Plan Snapshot ── */}
      <PlanSnapshot />

      <div style={{ padding: '14px 20px', borderTop: '1px solid rgba(255,255,255,0.12)', marginTop: 8 }}>
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', letterSpacing: 0.3 }}>RS Planning suite · v1.0</span>
      </div>
    </div>
  )
}
