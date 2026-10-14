import { useEffect, useRef, useState } from 'react'
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
  const [layer, setLayer] = useState(false)   // the other iterations' dropdown
  const box = useRef(null)
  useEffect(() => {
    if (!layer) return
    const out = e => { if (box.current && !box.current.contains(e.target)) setLayer(false) }
    const esc = e => { if (e.key === 'Escape') setLayer(false) }
    document.addEventListener('mousedown', out); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc) }
  }, [layer])
  const view = v => { setLayer(false); openPlanVersion(v); navigate('/department-plan/final-results') }
  const compare = v => { setLayer(false); setCmp({ id: '', base: v.id }) }
  const btn = (primary, small) => ({ padding: small ? '3px 9px' : '5px 12px', borderRadius: 7, fontSize: small ? 11.5 : 12, fontWeight: 700, cursor: 'pointer',
    border: `1px solid ${primary ? theme.primary : theme.border}`, background: primary ? theme.primary : theme.surface, color: primary ? '#fff' : theme.textPrimary })
  const tag = (t, c) => <span style={{ fontSize: 10, fontWeight: 800, color: c, background: alpha(c, '14'), borderRadius: 999, padding: '1px 7px' }}>{t}</span>
  // the small gist of a version: TY, LY, growth on one line, then how far the live plan has moved since
  const gist = v => (<>
    <div style={{ fontSize: 12, display: 'flex', gap: 10, flexWrap: 'wrap', fontFamily: theme.fontMono }}>
      <span><span style={{ color: theme.textMuted }}>TY </span><b>{Cr(v.ty)}</b></span>
      <span><span style={{ color: theme.textMuted }}>LY </span>{Cr(v.ly)}</span>
      <b style={{ color: theme.primary }}>{pct(v.ty, v.ly)}</b>
    </div>
    {list && <div style={{ fontSize: 11, color: theme.textMuted }}>Live plan now: {Math.abs(list.live.ty - v.ty) < 0.005 ? 'the same TY'
      : <b style={{ color: theme.textPrimary, fontFamily: theme.fontMono }}>{list.live.ty >= v.ty ? '+' : '−'}{Cr(Math.abs(list.live.ty - v.ty))} ({pct(list.live.ty, v.ty)})</b>}{Math.abs(list.live.ty - v.ty) < 0.005 ? '' : ' vs this'}</div>}
  </>)
  const first = vs[0], rest = vs.slice(1).reverse()
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
      {list && !vs.length && <div style={{ fontSize: 12.5, color: theme.textMuted }}>No saved plans yet.</div>}
      {/* one squeezed tile - the first version (user, 2026-10-14: "keep ver 1 and squeeze the tiles and give a layer where
          the versions open afterwards on clicking like a dropdown with a small gist") - the later iterations in its layer */}
      {first && (
        <div ref={box} style={{ position: 'relative', maxWidth: 380 }}>
          <div style={{ background: theme.surface, borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6,
            border: `1px solid ${open === first.id ? theme.primary : theme.border}`, boxShadow: open === first.id ? `0 0 0 3px ${alpha(theme.primary, '1f')}` : 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <b style={{ fontSize: 14, color: theme.navy }}>{first.name}</b>
              {tag('FIRST', theme.textMuted)}
              {open === first.id && tag('OPEN', theme.primary)}
              <span style={{ flex: 1 }} />
              <span style={{ fontSize: 11, color: theme.textMuted }}>{when(first.updated_at)}</span>
            </div>
            {gist(first)}
            <div style={{ display: 'flex', gap: 6, marginTop: 2, alignItems: 'center' }}>
              <button type="button" style={btn(true, true)} onClick={() => view(first)}>View</button>
              <button type="button" style={btn(false, true)} onClick={() => compare(first)} title="What changed - pick the two plans to compare">Compare…</button>
              <span style={{ flex: 1 }} />
              {rest.length > 0 && (
                <button type="button" aria-expanded={layer} aria-haspopup="true" onClick={() => setLayer(o => !o)}
                  style={{ ...btn(false, true), borderColor: layer ? theme.primary : theme.border, color: theme.primary }}>
                  {rest.length} later iteration{rest.length > 1 ? 's' : ''} {layer ? '▴' : '▾'}
                </button>
              )}
            </div>
          </div>
          {layer && (
            <div role="menu" aria-label="Later iterations" style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0, zIndex: 30, background: theme.surface,
              border: `1px solid ${theme.border}`, borderRadius: 12, boxShadow: '0 14px 34px rgba(0,0,0,.16)', maxHeight: 380, overflowY: 'auto' }}>
              {rest.map((v, i) => (
                <div key={v.id} role="menuitem" style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 4,
                  borderTop: i ? `1px solid ${theme.border}` : 'none', background: open === v.id ? alpha(theme.primary, '0d') : undefined }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <b style={{ fontSize: 13, color: theme.navy }}>{v.name}</b>
                    {i === 0 && tag('LATEST', theme.textMuted)}
                    {open === v.id && tag('OPEN', theme.primary)}
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, color: theme.textMuted }}>{when(v.updated_at)}</span>
                  </div>
                  {gist(v)}
                  <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
                    <button type="button" style={btn(true, true)} onClick={() => view(v)}>View</button>
                    <button type="button" style={btn(false, true)} onClick={() => compare(v)}>Compare…</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
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
