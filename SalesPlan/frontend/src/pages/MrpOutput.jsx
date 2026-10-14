import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import HierarchyView from '../components/HierarchyView'
import RouteBar from '../components/RouteBar'
import { useEngines } from '../engines'

const MRP_FIELDS = {
  cluster: 'Cluster', store: 'Store', stype: 'Store group', division: 'Division',
  attribute: 'Attribute', department: 'Department', mrp: 'MRP', month: 'Month',
}

// ── Walkthrough step bar ────────────────────────────────────────────────────
function StepBar({ pipeline }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'stretch', gap: 0,
      background: theme.surface, borderRadius: 10,
      border: `1px solid ${theme.border}`, overflow: 'hidden', marginBottom: 20,
    }}>
      {pipeline.map((step, i) => {
        const isLast    = i === pipeline.length - 1
        const isDone    = step.done
        const isCurrent = step.current
        const isOpt     = step.optional

        const bg = isCurrent
          ? `${alpha(theme.primary,'18')}`
          : isDone
            ? `${alpha(theme.success,'10')}`
            : isOpt
              ? 'transparent'
              : 'transparent'

        const textColor = isCurrent
          ? theme.primary
          : isDone
            ? theme.success
            : theme.textMuted

        return (
          <div key={step.label} style={{
            flex: 1, padding: '11px 16px', background: bg,
            borderRight: isLast ? 'none' : `1px solid ${theme.border}`,
            display: 'flex', flexDirection: 'column', gap: 3,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, fontWeight: 800,
                background: isCurrent ? 'var(--st-btn,#A8CBB7)' : isDone ? theme.success : theme.border,
                color: isCurrent ? 'var(--st-btn-text,#1F4D3A)' : isDone ? '#fff' : theme.textMuted,
              }}>
                {isCurrent ? '→' : isDone ? '✓' : isOpt ? '○' : String(i + 1)}
              </span>
              <span style={{ fontSize: 11, fontWeight: isCurrent ? 700 : 600, color: textColor }}>
                {step.label}
              </span>
              {isOpt && (
                <span style={{
                  fontSize: 9, padding: '1px 5px', borderRadius: 3, marginLeft: 'auto',
                  background: isDone ? `${alpha(theme.success,'18')}` : 'rgba(var(--st-ink-rgb,30,39,35),0.05)',
                  color: isDone ? theme.success : theme.textMuted, fontWeight: 700,
                }}>
                  {isDone ? 'applied' : 'opt'}
                </span>
              )}
            </div>
            {step.sub && (
              <div style={{ fontSize: 10, color: theme.textMuted, paddingLeft: 22 }}>{step.sub}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Deviation prompt modal ───────────────────────────────────────────────────
function DeviationPrompt({ pwwDone, sorDone, onProceed }) {
  const navigate = useNavigate()
  const [engineOn] = useEngines()
  const allDone  = pwwDone && sorDone

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: theme.surface, border: `1px solid ${theme.border}`,
        borderRadius: 14, padding: '32px 36px', maxWidth: 480, width: '90%',
        boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
      }}>
        <div style={{ fontSize: 20, marginBottom: 6 }}>📐</div>
        <h2 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 800, color: theme.textPrimary }}>
          Apply Deviations?
        </h2>
        <p style={{ margin: '0 0 24px', fontSize: 13, color: theme.textMuted, lineHeight: 1.6 }}>
          MRP Cont&nbsp;% has been imported. Before viewing the Plan Output, you can optionally
          apply deviation engines to adjust the contribution&nbsp;%. If you skip, the imported
          buyer's Cont&nbsp;% will be used as-is.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
          {[
            { label: 'PW/W Deviation', done: pwwDone, to: '/deviation/pww', desc: 'Price-Width / Width deviation adjustment', k: 'pww' },
            { label: 'SOR Deviation',  done: sorDone, to: '/deviation/sor',  desc: 'Summer / Occasional / Regular deviation', k: 'sor' },
          ].filter(item => engineOn(item.k)).map(item => (
            <button key={item.label}
              onClick={() => navigate(item.to)}
              style={{
                width: '100%', padding: '12px 16px', borderRadius: 9, cursor: 'pointer',
                border: `1.5px solid ${item.done ? theme.success : theme.border}`,
                background: item.done ? `${alpha(theme.success,'10')}` : theme.surfaceAlt,
                display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left',
              }}
            >
              <span style={{
                width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11,
                background: item.done ? theme.success : theme.border,
                color: item.done ? '#fff' : theme.textSecondary, fontWeight: 700,
              }}>{item.done ? '✓' : '→'}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: item.done ? theme.success : theme.textPrimary }}>
                  {item.label}
                </div>
                <div style={{ fontSize: 11, color: theme.textMuted }}>{item.desc}</div>
              </div>
              {item.done && (
                <span style={{ marginLeft: 'auto', fontSize: 10, color: theme.success, fontWeight: 700 }}>Done</span>
              )}
            </button>
          ))}
        </div>

        <button
          onClick={onProceed}
          style={{
            width: '100%', padding: '12px', borderRadius: 9, border: `1.5px solid ${theme.border}`,
            background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}
        >
          Proceed with Imported Cont&nbsp;% →
        </button>
        {allDone && (
          <div style={{ textAlign: 'center', marginTop: 10, fontSize: 11, color: theme.success }}>
            Both deviations applied ✓
          </div>
        )}
      </div>
    </div>
  )
}

export default function MrpOutput() {
  const [data, setData]               = useState(null)
  const [loading, setLoading]         = useState(true)
  const [err, setErr]                 = useState('')
  // pipeline status
  const [pipeline, setPipeline]       = useState(null)
  const [showPrompt, setShowPrompt]   = useState(false)
  const [engineOn, , engLoaded] = useEngines()   // switched-off deviations leave the flow (2026-10-14)

  useEffect(() => {
    // Fetch pipeline status for walkthrough header + deviation prompt
    Promise.all([
      fetch('/api/planning/mrp-plan/status').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('/api/planning/mrp-reapportionment/status').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('/api/planning/deviation/pww/status').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('/api/planning/deviation/sor/status').then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([mrp, reapp, pww, sor]) => {
      const mrpDone   = !!mrp?.imported
      const reappDone = !!reapp?.has_result
      const pwwDone   = !!pww?.has_result
      const sorDone   = !!sor?.has_result

      setPipeline([
        { label: "Buyer's Input",    done: mrpDone,   sub: mrpDone   ? `${mrp.dept_count || ''} depts` : 'Not synced',    current: false },
        { label: 'Re-apportionment', done: reappDone, sub: reappDone ? 'Completed'        : 'Pending',                    current: false },
        { label: 'PW/W Deviation',   done: pwwDone,   optional: true, sub: pwwDone ? 'Applied' : 'Skipped',               current: false, engine: 'pww' },
        { label: 'SOR Deviation',    done: sorDone,   optional: true, sub: sorDone ? 'Applied' : 'Skipped',               current: false, engine: 'sor' },
        { label: 'Plan Output',      done: false,     current: true,  sub: 'Viewing now' },
      ])

      // Show deviation prompt only if MRP is loaded and neither deviation has been run
      if (mrpDone && !pwwDone && !sorDone) {
        setShowPrompt(true)
      }
    })
  }, [])

  useEffect(() => {
    // a proxy error page (8010 restarting - Landing answers 502 in HTML) is retried, not shown as a JSON error (2026-10-14)
    const load = async (left = 8) => {
      const r = await fetch('/api/planning/mrp-plan/data').catch(() => null)
      if (!r || !(r.headers.get('content-type') || '').includes('json')) {
        if (left > 0) { setErr(''); setLoading('restart'); setTimeout(() => load(left - 1), 5000); return }
        throw new Error('The planning server is restarting or unreachable - reload the page in a minute.')
      }
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
      setData(d); setLoading(false)
    }
    load().catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  if (loading) return <div style={{ padding: '28px 32px', color: theme.textMuted, fontSize: 13 }}>{loading === 'restart' ? 'The planning server is restarting - trying again…' : 'Loading MRP plan…'}</div>

  if (err) return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ padding: 32, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
        <div style={{ fontSize: 28, marginBottom: 10 }}>📦</div>
        <div style={{ fontSize: 14, color: theme.danger, fontWeight: 600, marginBottom: 6 }}>{err}</div>
        {!/server/.test(err) && <div style={{ fontSize: 12, color: theme.textMuted }}>MRP Plan → Buyer's Input sets where the MRP Cont % comes from.</div>}
      </div>
    </div>
  )

  const periods     = data.periods || []
  const noSplit     = data.divisions.flatMap(dv => Object.values(data.data[dv] || {}).filter(x => x.no_split))
  const noSplitTy   = noSplit.reduce((t, x) => t + (x.dept_total_ty || 0), 0)

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      {/* Deviation prompt */}
      {showPrompt && pipeline && engLoaded && (engineOn('pww') || engineOn('sor')) && (
        <DeviationPrompt
          pwwDone={pipeline[2]?.done}
          sorDone={pipeline[3]?.done}
          onProceed={() => setShowPrompt(false)}
        />
      )}

      {/* MRP or Article Name: which branch the Sales Plan runs on (2026-10-13) */}
      <RouteBar here="mrp" />
      {data.split_source?.kind === 'promoted' && (
        <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 8, fontSize: 12.5, border: `1px solid ${alpha(theme.primary, '55')}`, background: alpha(theme.primary, '0e') }}>
          MRP split <b>promoted from the Article Name plan</b> ({data.split_source.promoted_at}{data.split_source.by ? `, by ${data.split_source.by}` : ''}; LY article × MRP mix by {data.split_source.grain}),
          not the buyers' MRP Cont % - because the Sales Plan runs on the Article Name route. Switch the route to MRP to use the buyers' split again.
        </div>
      )}

      {/* Walkthrough step bar */}
      {pipeline && <StepBar pipeline={pipeline.filter(s => !s.engine || engineOn(s.engine))} />}

      {/* Header */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div className="sp-sub" style={{ margin: 0 }}>
          The department plan split over its MRP price points - by month or P1 / P2, store or cluster.
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {!data.has_plan && (
            <span style={{ fontSize: 11, color: theme.accent, background: `${alpha(theme.accent,'18')}`, border: `1px solid ${alpha(theme.accent,'44')}`, borderRadius: 6, padding: '4px 10px' }}>
              No dept plan — TY values will show 0
            </span>
          )}
          <details className="sp-menu">
            <summary>More ▾</summary>
            <div className="sp-menu-pop">
              <button onClick={() => setShowPrompt(true)}>
                📐 Deviations
              </button>
              <button onClick={() => window.open('/api/planning/mrp-plan/export', '_blank')}>
                Export CSV ↓
              </button>
            </div>
          </details>
        </div>
      </div>

      {/* Summary cards */}
      <div className="sp-slim" style={{ marginBottom: 16, padding: '0 4px' }}>
        {[
          { label: 'Divisions',   value: data.divisions.length, color: theme.primary },
          { label: 'Departments', value: data.total_depts,       color: theme.textPrimary },
          { label: 'MRP Bands',   value: data.total_bands,        color: theme.accent },
          { label: 'Periods',     value: periods.length,          color: theme.success },
        ].map(c => (
          <span key={c.label}>{c.label} <b style={{ color: c.color, fontFamily: theme.fontMono }}>{c.value}</b></span>
        ))}
      </div>

      {noSplit.length > 0 && (
        <div style={{ fontSize: 12, color: theme.danger, fontWeight: 600, margin: '0 4px 10px' }}>
          {noSplit.length} departments have no MRP split (₹ {noSplitTy.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L) - in the tree under MRP "No MRP split", so every department still adds back to its plan
        </div>
      )}

      {/* the department plan's tree with an MRP level (user, 2026-10-14: "merge all the views similarly to the
          department view which is the final design") - Division / Department / MRP / Month, Store / Cluster, filters,
          the ⓘ pop-up, Month or P1 / P2 and Export Excel, as Final Results */}
      <HierarchyView api="/api/planning/grain/mrp-view" levels={MRP_FIELDS} defaults={['division', 'department', 'mrp', 'month']}
        store="sp.mrp" versions={false} halves />
    </div>
  )
}
