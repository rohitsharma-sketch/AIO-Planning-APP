import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EngineCard from '../components/EngineCard'
import { theme, alpha } from '../theme'
import { API, call, openPlanVersion, openVersionId, when } from '../planVersion'
import { Changes } from '../components/PlanVersions'

// Saved plans as tiles (user, 2026-10-14: "i want the saved plans to be highlighted here as a tile so that i can easily
// view the plan and compare it with the new iteration if required"): every saved iteration, newest first (the live
// plan's tile removed - user, 2026-10-14: "remove live plan") - View opens it on Final Results, Compare opens "What changed" (any iteration or the live plan, either side).
const Cr = v => `₹${((v ?? 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr`
const pct = (a, b) => (b ? `${a >= b ? '+' : ''}${((a / b - 1) * 100).toFixed(1)}%` : '–')

function SavedPlans() {
  const navigate = useNavigate()
  const [list, setList] = useState(null)
  const [err, setErr] = useState('')
  const [cmp, setCmp] = useState(null)   // {id, base}
  const [open, setOpen] = useState(openVersionId)
  useEffect(() => {
    const reload = () => call(API).then(setList).catch(e => setErr(e.message))
    const v = e => setOpen(e.detail ? e.detail.id : '')
    reload()
    window.addEventListener('sp-versions', reload)
    window.addEventListener('sp-version', v)
    return () => { window.removeEventListener('sp-versions', reload); window.removeEventListener('sp-version', v) }
  }, [])
  const vs = list?.versions || []
  const view = v => { openPlanVersion(v); navigate('/department-plan/final-results') }
  const btn = primary => ({ padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 700, cursor: 'pointer',
    border: `1px solid ${primary ? theme.primary : theme.border}`, background: primary ? theme.primary : theme.surface, color: primary ? '#fff' : theme.textPrimary })
  const tile = (key, title, sub, ly, ty, v, isLive) => {
    const on = isLive ? !open || !vs.some(x => x.id === open) : open === v.id
    return (
      <div key={key} style={{ background: theme.surface, borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8,
        border: `1px solid ${on ? theme.primary : theme.border}`, boxShadow: on ? `0 0 0 3px ${alpha(theme.primary, '1f')}` : 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <b style={{ fontSize: 15, color: theme.navy, flex: 1 }}>{title}</b>
          {on && <span style={{ fontSize: 10.5, fontWeight: 800, color: theme.primary, background: alpha(theme.primary, '14'), borderRadius: 999, padding: '2px 8px' }}>OPEN</span>}
          {isLive && <span style={{ fontSize: 10.5, fontWeight: 800, color: theme.textMuted, border: `1px solid ${theme.border}`, borderRadius: 999, padding: '2px 8px' }}>LIVE</span>}
        </div>
        <div style={{ fontSize: 12, color: theme.textMuted }}>{sub}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, fontSize: 12 }}>
          <div><div style={{ color: theme.textMuted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.4 }}>Plan TY</div><b style={{ fontFamily: theme.fontMono }}>{Cr(ty)}</b></div>
          <div><div style={{ color: theme.textMuted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.4 }}>LY</div><span style={{ fontFamily: theme.fontMono }}>{Cr(ly)}</span></div>
          <div><div style={{ color: theme.textMuted, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.4 }}>Growth</div><b style={{ fontFamily: theme.fontMono, color: theme.primary }}>{pct(ty, ly)}</b></div>
        </div>
        {!isLive && list && <div style={{ fontSize: 11.5, color: theme.textMuted }}>Live plan now: <b style={{ fontFamily: theme.fontMono, color: Math.abs(list.live.ty - ty) < 0.005 ? theme.textMuted : theme.textPrimary }}>
          {Math.abs(list.live.ty - ty) < 0.005 ? 'the same TY' : `${list.live.ty >= ty ? '+' : '−'}${Cr(Math.abs(list.live.ty - ty))} (${pct(list.live.ty, ty)})`}</b>{Math.abs(list.live.ty - ty) < 0.005 ? '' : ' vs this'}</div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
          <button type="button" style={btn(true)} onClick={() => view(isLive ? null : v)}>View</button>
          {vs.length > 0 && <button type="button" style={btn(false)} onClick={() => setCmp(isLive ? { id: '', base: vs[vs.length - 1].id } : { id: '', base: v.id })}
            title="What changed - pick the two plans to compare">Compare…</button>}
        </div>
      </div>
    )
  }
  return (
    <>
      <div style={{ fontSize: 11, fontWeight: 800, color: theme.textMuted, letterSpacing: 1.2, textTransform: 'uppercase', margin: '36px 0 6px' }}>
        Saved plans
      </div>
      <div style={{ fontSize: 12.5, color: theme.textSecondary, marginBottom: 14 }}>
        Save an iteration from the plan picker in the top bar (or Final Results' version bar). View opens it as saved; Compare shows what changed between any two.
      </div>
      {err && <div style={{ fontSize: 12.5, color: theme.danger }}>{err}</div>}
      {!list && !err && <div style={{ fontSize: 12.5, color: theme.textMuted }}>Loading saved plans…</div>}
      {list && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {[...vs].reverse().map(v => tile(v.id, v.name, `Saved ${when(v.updated_at)}${v.saved_by ? ` by ${v.saved_by}` : ''}`, v.ly, v.ty, v, false))}
        </div>
      )}
      {list && !vs.length && <div style={{ fontSize: 12.5, color: theme.textMuted }}>No saved plans yet.</div>}
      {cmp && <Changes id={cmp.id} base={cmp.base} versions={vs} onClose={() => setCmp(null)} />}
    </>
  )
}

const engines = [
  {
    title: 'Division Based Plan',
    description: 'Build annual sales targets by division with growth rates, seasonality index, and monthly distribution.',
    status: 'active',
    icon: 'division',
    route: '/division-plan',
  },
  {
    title: 'Department Based Plan',
    description: 'Drill down to department level within each division for granular sales planning.',
    status: 'active',
    icon: 'dept',
    route: '/department-plan',
  },
  {
    title: 'MRP / Article Plan',
    description: 'Buyer-supplied MRP price points with P1/P2 contribution % splits feeding the department plan.',
    status: 'active',
    icon: 'mrp',
    route: '/mrp-plan/import',
  },
  {
    title: 'Display Type Plan',
    description: 'The MRP plan split into Table / Non-Table by each store’s last-year sales mix, with ASP and unit quantities.',
    status: 'active',
    icon: 'display',
    route: '/display-type',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, padding: '36px 40px 48px', overflowY: 'auto', background: theme.surfaceAlt }}>
        <div style={{ maxWidth: 1080 }}>
          {/* Hero - same landing pattern as the AOP Forecaster */}
          <span style={{
            display: 'inline-block', fontSize: 11, fontWeight: 800, letterSpacing: 1.2, textTransform: 'uppercase',
            color: theme.primary, background: theme.primaryLight, border: '1px solid var(--st-tint-b,#CBE2D5)',
            borderRadius: 999, padding: '4px 12px',
          }}>Sales Plan · FY 2027–28</span>
          <h1 style={{ fontSize: 30, fontWeight: 800, color: theme.navy, margin: '14px 0 8px', letterSpacing: '-0.02em' }}>
            Sales Plan Engine
          </h1>
          <p style={{ fontSize: 15, color: theme.textSecondary, margin: 0, maxWidth: 620, lineHeight: 1.6 }}>
            Build, review, and export structured sales plans across divisions, departments, and articles.
            Pick an engine to get started.
          </p>

          <div style={{ fontSize: 11, fontWeight: 800, color: theme.textMuted, letterSpacing: 1.2, textTransform: 'uppercase', margin: '36px 0 14px' }}>
            Planning engines
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
            {engines.map(eng => (
              <EngineCard
                key={eng.title}
                title={eng.title}
                description={eng.description}
                status={eng.status}
                icon={eng.icon}
                onClick={eng.route ? () => navigate(eng.route) : undefined}
              />
            ))}
          </div>

          <SavedPlans />
        </div>
      </div>
    </div>
  )
}
