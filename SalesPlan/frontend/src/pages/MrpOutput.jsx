import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import SearchSlicer from '../components/SearchSlicer'

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

const CELL = { fontFamily: theme.fontMono, fontSize: 11, textAlign: 'right', padding: '4px 7px', whiteSpace: 'nowrap' }
const HDR  = { ...CELL, fontSize: 10, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }

// Build month groups from periods list e.g. ["Mar'27 P1","Mar'27 P2","Apr'27 P1","Apr'27 P2"]
function buildMonthGroups(periods) {
  const map = {}
  const order = []
  for (const p of periods) {
    const m = p.replace(/ P[12]$/, '')
    if (!map[m]) { map[m] = []; order.push(m) }
    map[m].push(p)
  }
  return order.map(m => ({ month: m, periods: map[m] }))
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
            { label: 'PW/W Deviation', done: pwwDone, to: '/deviation/pww', desc: 'Price-Width / Width deviation adjustment' },
            { label: 'SOR Deviation',  done: sorDone, to: '/deviation/sor',  desc: 'Summer / Occasional / Regular deviation' },
          ].map(item => (
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
  const [activeDiv, setActiveDiv]     = useState(null)
  const [deptFilters, setDeptFilters] = useState(new Set())
  const [showBad, setShowBad]         = useState(false)
  const [viewMode, setViewMode]       = useState('ty')   // 'contrib' | 'ty'
  const [expandedDept, setExpandedDept] = useState(null)

  // pipeline status
  const [pipeline, setPipeline]       = useState(null)
  const [showPrompt, setShowPrompt]   = useState(false)

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
        { label: 'PW/W Deviation',   done: pwwDone,   optional: true, sub: pwwDone ? 'Applied' : 'Skipped',               current: false },
        { label: 'SOR Deviation',    done: sorDone,   optional: true, sub: sorDone ? 'Applied' : 'Skipped',               current: false },
        { label: 'Plan Output',      done: false,     current: true,  sub: 'Viewing now' },
      ])

      // Show deviation prompt only if MRP is loaded and neither deviation has been run
      if (mrpDone && !pwwDone && !sorDone) {
        setShowPrompt(true)
      }
    })
  }, [])

  useEffect(() => {
    fetch('/api/planning/mrp-plan/data')
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail) }))
      .then(d => { setData(d); setActiveDiv(d.divisions?.[0] || null); setLoading(false) })
      .catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  if (loading) return <div style={{ padding: '28px 32px', color: theme.textMuted, fontSize: 13 }}>Loading MRP plan…</div>

  if (err) return (
    <div style={{ padding: '28px 32px' }}>
      <div style={{ padding: 32, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, textAlign: 'center' }}>
        <div style={{ fontSize: 28, marginBottom: 10 }}>📦</div>
        <div style={{ fontSize: 14, color: theme.danger, fontWeight: 600, marginBottom: 6 }}>{err}</div>
        <div style={{ fontSize: 12, color: theme.textMuted }}>Go to MRP Plan → Import to upload buyer MRP data.</div>
      </div>
    </div>
  )

  const periods     = data.periods || []
  const monthGroups = buildMonthGroups(periods)
  const divData     = activeDiv ? (data.data[activeDiv] || {}) : {}
  const allDepts    = Object.keys(divData).sort()
  const badDepts    = allDepts.filter(d => !divData[d].all_ok)

  const visibleDepts = allDepts.filter(d => {
    if (deptFilters.size > 0 && !deptFilters.has(d)) return false
    if (showBad && divData[d].all_ok) return false
    return true
  })

  const divTotals = {}
  for (const div of data.divisions) {
    let ty = 0, depts = 0, bands = 0
    for (const dept of Object.values(data.data[div] || {})) {
      ty += dept.dept_total_ty; depts++; bands += dept.bands.length
    }
    divTotals[div] = { ty, depts, bands }
  }

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      {/* Deviation prompt */}
      {showPrompt && pipeline && (
        <DeviationPrompt
          pwwDone={pipeline[2]?.done}
          sorDone={pipeline[3]?.done}
          onProceed={() => setShowPrompt(false)}
        />
      )}

      {/* Walkthrough step bar */}
      {pipeline && <StepBar pipeline={pipeline} />}

      {/* Header */}
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>MRP Plan Output</h1>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: theme.textMuted }}>
            Department TY plan split by MRP price point × buyer contribution % — P1 &amp; P2 per month.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {!data.has_plan && (
            <span style={{ fontSize: 11, color: theme.accent, background: `${alpha(theme.accent,'18')}`, border: `1px solid ${alpha(theme.accent,'44')}`, borderRadius: 6, padding: '4px 10px' }}>
              No dept plan — TY values will show 0
            </span>
          )}
          <button onClick={() => setShowPrompt(true)}
            style={{ padding: '7px 16px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted }}>
            📐 Deviations
          </button>
          <button onClick={() => window.open('/api/planning/mrp-plan/export', '_blank')}
            style={{ padding: '7px 16px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: 'none', border: `1px solid ${theme.border}`, color: theme.textMuted }}>
            Export CSV ↓
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Divisions',   value: data.divisions.length, color: theme.primary },
          { label: 'Departments', value: data.total_depts,       color: theme.textPrimary },
          { label: 'MRP Bands',   value: data.total_bands,        color: theme.accent },
          { label: 'Periods',     value: periods.length,          color: theme.success },
        ].map(c => (
          <div key={c.label} style={{ background: theme.surface, borderRadius: 10, padding: '14px 18px', border: `1px solid ${theme.border}` }}>
            <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: c.color, fontFamily: theme.fontMono }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Division tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {data.divisions.map(div => {
          const tot = divTotals[div]
          const isActive = activeDiv === div
          return (
            <button key={div} onClick={() => { setActiveDiv(div); setDeptFilters(new Set()); setShowBad(false); setExpandedDept(null) }} style={{
              padding: '8px 18px', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
              border: `2px solid ${isActive ? DIV_COLOR[div] : theme.border}`,
              background: isActive ? `${alpha(DIV_COLOR[div],'18')}` : theme.surface,
              color: isActive ? DIV_COLOR[div] : theme.textMuted,
              fontWeight: isActive ? 700 : 400, fontSize: 12,
            }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{div}</div>
              <div style={{ fontSize: 10, opacity: 0.8, marginTop: 1 }}>{tot.depts} depts · {tot.bands} bands</div>
            </button>
          )
        })}
      </div>

      {activeDiv && (
        <>
          {/* Toolbar */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            <SearchSlicer
              items={allDepts}
              selected={deptFilters}
              onChange={setDeptFilters}
              label="All Departments"
              placeholder="Search department…"
              width={180}
              accentColor={DIV_COLOR[activeDiv]}
            />

            <div style={{ display: 'flex', borderRadius: 7, overflow: 'hidden', border: `1px solid ${theme.border}` }}>
              {[['contrib', 'Contrib %'], ['ty', 'TY Split (₹L)']].map(([mode, label]) => (
                <button key={mode} onClick={() => setViewMode(mode)} style={{
                  padding: '5px 14px', fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
                  background: viewMode === mode ? 'var(--st-btn,#A8CBB7)' : theme.surface,
                  color: viewMode === mode ? 'var(--st-btn-text,#1F4D3A)' : theme.textMuted,
                }}>{label}</button>
              ))}
            </div>

            {badDepts.length > 0 && (
              <button onClick={() => setShowBad(v => !v)} style={{
                padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                background: showBad ? `${alpha(theme.danger,'22')}` : 'transparent',
                color: showBad ? theme.danger : theme.textMuted,
                border: `1.5px solid ${showBad ? theme.danger : theme.border}`,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                ⚠ Contrib ≠ 100%
                <span style={{ fontSize: 10, background: theme.danger, color: '#fff', borderRadius: 10, padding: '1px 6px', fontWeight: 700 }}>{badDepts.length}</span>
              </button>
            )}

            <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 4 }}>
              {visibleDepts.length} of {allDepts.length} depts · {monthGroups.length} months × P1/P2
            </span>
          </div>

          {/* Matrix table */}
          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%', tableLayout: 'auto' }}>
                <thead>
                  {/* Month group header */}
                  <tr style={{ background: theme.surfaceAlt, borderBottom: `1px solid ${theme.border}` }}>
                    <th style={{ ...HDR, textAlign: 'left', padding: '7px 14px', minWidth: 200, borderRight: `2px solid ${theme.border}` }} rowSpan={2}>
                      Department / MRP
                    </th>
                    <th style={{ ...HDR, padding: '7px 10px', minWidth: 70, borderRight: `2px solid ${theme.border}` }} rowSpan={2}>
                      Dept TY (₹L)
                    </th>
                    {monthGroups.map(({ month, periods: mps }) => (
                      <th key={month} colSpan={mps.length} style={{
                        ...HDR, textAlign: 'center', padding: '5px 4px',
                        color: theme.primary, borderRight: `1px solid ${theme.border}`,
                        minWidth: 58 * mps.length,
                      }}>
                        {month}
                      </th>
                    ))}
                    <th style={{ ...HDR, padding: '7px 10px', borderLeft: `2px solid ${theme.border}` }} rowSpan={2}>
                      Band Total (₹L)
                    </th>
                  </tr>
                  {/* P1/P2 sub-header */}
                  <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                    {monthGroups.map(({ periods: mps }) =>
                      mps.map((p, pi) => (
                        <th key={p} style={{
                          ...HDR, textAlign: 'center', padding: '4px 6px', fontSize: 9,
                          color: p.endsWith('P1') ? theme.success : theme.accent,
                          borderRight: pi === mps.length - 1 ? `1px solid ${theme.border}` : `1px dashed ${alpha(theme.border,'22')}`,
                          minWidth: 52,
                        }}>
                          {p.endsWith('P1') ? 'P1' : 'P2'}
                        </th>
                      ))
                    )}
                  </tr>
                </thead>
                <tbody>
                  {visibleDepts.map(dept => {
                    const d = divData[dept]
                    const isExpanded = expandedDept === dept
                    const isBad = !d.all_ok
                    const divColor = DIV_COLOR[activeDiv] || theme.primary

                    return [
                      /* Dept summary row */
                      <tr key={`${dept}-hdr`}
                        onClick={() => setExpandedDept(isExpanded ? null : dept)}
                        style={{
                          borderBottom: isExpanded ? 'none' : `1px solid ${theme.border}`,
                          background: isBad ? `${alpha(theme.danger,'08')}` : `${alpha(divColor,'0a')}`,
                          cursor: 'pointer',
                        }}
                      >
                        <td style={{
                          padding: '6px 14px', fontWeight: 700, fontSize: 12,
                          color: divColor, borderRight: `2px solid ${theme.border}`,
                          display: 'flex', alignItems: 'center', gap: 8,
                        }}>
                          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 400 }}>{isExpanded ? '▾' : '▸'}</span>
                          {dept}
                          {isBad && <span style={{ fontSize: 10, color: theme.danger, fontWeight: 600, background: `${alpha(theme.danger,'18')}`, borderRadius: 4, padding: '1px 5px' }}>⚠</span>}
                          <span style={{ fontSize: 10, color: theme.textMuted, fontWeight: 400, marginLeft: 'auto' }}>{d.bands.length} bands</span>
                        </td>
                        <td style={{ ...CELL, fontWeight: 700, color: theme.primary, borderRight: `2px solid ${theme.border}` }}>
                          {d.dept_total_ty > 0 ? d.dept_total_ty.toFixed(2) : '—'}
                        </td>
                        {periods.map((p, pi) => {
                          const isLastInMonth = monthGroups.find(g => g.periods[g.periods.length - 1] === p)
                          const contribOk = d.contrib_ok[p]
                          const periodTotal = viewMode === 'ty'
                            ? d.bands.reduce((s, b) => s + (b.period_ty[p] || 0), 0)
                            : null
                          return (
                            <td key={p} style={{
                              ...CELL, textAlign: 'center', fontWeight: 600, fontSize: 10,
                              borderRight: isLastInMonth ? `1px solid ${theme.border}` : `1px dashed ${alpha(theme.border,'44')}`,
                              color: viewMode === 'ty'
                                ? (periodTotal > 0 ? theme.textPrimary : theme.textMuted)
                                : (contribOk ? theme.textMuted : theme.danger),
                            }}>
                              {viewMode === 'ty'
                                ? (periodTotal > 0 ? periodTotal.toFixed(1) : '—')
                                : (contribOk ? '✓' : '⚠')
                              }
                            </td>
                          )
                        })}
                        <td style={{ ...CELL, fontWeight: 700, color: theme.accent, borderLeft: `2px solid ${theme.border}` }}>
                          {d.bands.reduce((s, b) => s + b.band_total_ty, 0).toFixed(2)}
                        </td>
                      </tr>,

                      /* Expanded band rows */
                      ...(isExpanded ? d.bands.map((band, bi) => (
                        <tr key={`${dept}-${band.mrp}`} style={{
                          borderBottom: bi === d.bands.length - 1 ? `2px solid ${theme.border}` : `1px solid ${alpha(theme.border,'22')}`,
                          background: bi % 2 === 0 ? `${alpha(divColor,'04')}` : 'transparent',
                        }}>
                          <td style={{
                            padding: '4px 14px 4px 36px', fontSize: 11,
                            color: theme.textPrimary, borderRight: `2px solid ${theme.border}`,
                            fontFamily: theme.fontMono,
                          }}>
                            <span style={{ color: theme.accent }}>₹</span>{band.mrp.toLocaleString()}
                          </td>
                          <td style={{ ...CELL, borderRight: `2px solid ${theme.border}`, color: theme.textMuted, fontSize: 10 }}>—</td>
                          {periods.map((p, pi) => {
                            const isLastInMonth = monthGroups.find(g => g.periods[g.periods.length - 1] === p)
                            const val = viewMode === 'ty' ? band.period_ty[p] : band.period_contrib[p]
                            const isZero = !val || val === 0
                            const isP1 = p.endsWith('P1')
                            return (
                              <td key={p} style={{
                                ...CELL, textAlign: 'center',
                                borderRight: isLastInMonth ? `1px solid ${theme.border}` : `1px dashed ${alpha(theme.border,'44')}`,
                                color: isZero ? theme.textMuted
                                  : viewMode === 'ty'
                                    ? (isP1 ? theme.success : theme.accent)
                                    : theme.textPrimary,
                                fontWeight: isZero ? 400 : 600,
                              }}>
                                {isZero ? '—'
                                  : viewMode === 'ty'
                                    ? val.toFixed(2)
                                    : `${val.toFixed(1)}%`
                                }
                              </td>
                            )
                          })}
                          <td style={{ ...CELL, color: theme.success, fontWeight: 700, borderLeft: `2px solid ${theme.border}` }}>
                            {band.band_total_ty > 0 ? band.band_total_ty.toFixed(2) : '—'}
                          </td>
                        </tr>
                      )) : []),
                    ]
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
