import { useState, useEffect, useCallback, useRef } from 'react'
import { theme, alpha } from '../theme'

// ── Block search combobox ──────────────────────────────────────────────────────
function BlockSearch({ blocks, value, onChange }) {
  const [query,  setQuery]  = useState('')
  const [open,   setOpen]   = useState(false)
  const ref = useRef(null)

  const selected = blocks.find(b => b.key === value)

  const filtered = query.trim()
    ? blocks.filter(b =>
        b.key.includes(query.toUpperCase()) ||
        b.label.toUpperCase().includes(query.toUpperCase()) ||
        b.ly_months.some(m => m.toUpperCase().includes(query.toUpperCase()))
      )
    : blocks

  useEffect(() => {
    const handle = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: theme.surfaceUp, border: `1px solid ${open ? theme.primary : theme.border}`,
          borderRadius: 7, padding: '5px 12px', cursor: 'pointer', minWidth: 200,
          transition: 'border-color 0.15s',
        }}
      >
        <span style={{ fontFamily: theme.fontMono, fontSize: 13, fontWeight: 700, color: theme.primary }}>
          {selected?.key || value}
        </span>
        <span style={{ fontSize: 11, color: theme.textSecondary, flex: 1 }}>
          {selected ? selected.ly_months.join(' · ') : ''}
        </span>
        <span style={{ fontSize: 10, color: theme.textMuted }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 500,
          background: theme.surface, border: `1px solid ${theme.border}`,
          borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          width: 340, maxHeight: 320, display: 'flex', flexDirection: 'column',
        }}>
          <div style={{ padding: '8px 10px', borderBottom: `1px solid ${theme.border}` }}>
            <input
              autoFocus
              placeholder="Search block… e.g. SOND, Mar, OND"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{
                width: '100%', background: theme.surfaceUp, color: theme.textPrimary,
                border: `1px solid ${theme.border}`, borderRadius: 5,
                padding: '5px 10px', fontSize: 12, fontFamily: theme.fontMono, outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.length === 0 && (
              <div style={{ padding: '12px 14px', fontSize: 12, color: theme.textMuted }}>No match</div>
            )}
            {filtered.map(b => {
              const active = b.key === value
              return (
                <div
                  key={b.key}
                  onClick={() => { onChange(b.key); setOpen(false); setQuery('') }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '7px 14px', cursor: 'pointer',
                    background: active ? `${alpha(theme.primary,'22')}` : 'transparent',
                    borderLeft: `3px solid ${active ? theme.primary : 'transparent'}`,
                  }}
                >
                  <span style={{ fontFamily: theme.fontMono, fontSize: 12, fontWeight: 700, color: active ? theme.primary : theme.textPrimary, minWidth: 70 }}>
                    {b.key}
                  </span>
                  <span style={{ fontSize: 11, color: theme.textSecondary }}>
                    {b.ly_months.join(' · ')}
                  </span>
                  <span style={{
                    marginLeft: 'auto', fontSize: 10, color: theme.textMuted,
                    background: theme.surfaceUp, borderRadius: 4, padding: '1px 5px',
                  }}>{b.months_count}m</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

const CELL  = { fontFamily: theme.fontMono, fontSize: 12, padding: '5px 10px', whiteSpace: 'nowrap' }
const CELL2 = { fontFamily: theme.fontMono, fontSize: 11, padding: '4px 8px', whiteSpace: 'nowrap' }
const fmt   = n => n == null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
const fmtP  = n => n == null ? '—' : n.toFixed(4) + '%'
const fmtP2 = n => n == null ? '—' : n.toFixed(2) + '%'

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620', UNKNOWN: '#555',
}

const RULE_META = {
  ppo:                    { label: 'PPO',          color: '#3B82F6' },
  ppo_below_threshold:    { label: 'PPO (thr)',     color: '#3B82F6' },
  ppo_no_plan:            { label: 'PPO (no plan)', color: '#6B7280' },
  floor_50:               { label: '50% Floor',     color: '#B45309' },
  cap_150:                { label: '150% Cap',      color: '#B45309' },
  adjusted:               { label: 'Adjusted',      color: '#0EA5E9' },
}

function RuleBadge({ rule }) {
  const meta = RULE_META[rule] || { label: rule, color: theme.textMuted }
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, borderRadius: 4, padding: '1px 6px',
      background: meta.color + '22', color: meta.color, letterSpacing: 0.3,
    }}>{meta.label}</span>
  )
}

export default function PwwDeviation() {
  const [syncStatus,    setSyncStatus]    = useState(null)
  const [status,        setStatus]        = useState(null)
  const [result,        setResult]        = useState(null)
  const [p2Result,      setP2Result]      = useState(null)
  const [reappResult,   setReappResult]   = useState(null)
  const [blocks,        setBlocks]        = useState([])
  const [activeBlock,   setActiveBlock]   = useState('MAMJ')
  const [syncing,       setSyncing]       = useState(false)
  const [running,       setRunning]       = useState(false)
  const [runningP2,     setRunningP2]     = useState(false)
  const [runningReapp,  setRunningReapp]  = useState(false)
  const [msg,           setMsg]           = useState('')
  const [activeDiv,     setActiveDiv]     = useState(null)
  const [expanded,      setExpanded]      = useState(new Set())

  // Phase 2 view state
  const [activeMonth,   setActiveMonth]   = useState(null)
  const [activeCluster, setActiveCluster] = useState(null)
  const [activeDiv2,    setActiveDiv2]    = useState(null)
  const [expanded2,     setExpanded2]     = useState(new Set())

  // Reapportionment view state
  const [reappCluster,  setReappCluster]  = useState(null)
  const [reappDiv,      setReappDiv]      = useState(null)
  const [expandedReapp, setExpandedReapp] = useState(new Set())

  const flash = (m, ms = 5000) => { setMsg(m); setTimeout(() => setMsg(''), ms) }

  const fetchSyncStatus = useCallback(async () => {
    try { setSyncStatus(await (await fetch('/api/planning/deviation/pww/sync-status')).json()) } catch {}
  }, [])

  const fetchStatus = useCallback(async () => {
    try { setStatus(await (await fetch('/api/planning/deviation/pww/status')).json()) } catch {}
  }, [])

  const fetchBlocks = useCallback(async () => {
    try { setBlocks(await (await fetch('/api/planning/deviation/pww/blocks')).json()) } catch {}
  }, [])

  useEffect(() => {
    fetchSyncStatus()
    fetchStatus()
    fetchBlocks()
  }, [fetchSyncStatus, fetchStatus, fetchBlocks])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const d = await (await fetch('/api/planning/deviation/pww/sync', { method: 'POST' })).json()
      if (d.ok) {
        flash(`Synced — ${d.depts} departments, ${d.rows} MRP rows`)
        fetchStatus()
      } else flash(d.detail || 'Sync failed')
    } catch (e) { flash('Error: ' + e.message) }
    finally { setSyncing(false) }
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      const d = await (await fetch(`/api/planning/deviation/pww/run-phase1?block=${activeBlock}`)).json()
      if (d.divisions) {
        setResult(d)
        setP2Result(null)
        const divs = Object.keys(d.divisions)
        if (divs.length) setActiveDiv(prev => divs.includes(prev) ? prev : divs[0])
        flash(`Block ${d.block} · ${d.total_depts} depts · ${d.ssg_stores?.length} SSG stores · ${d.ly_months_used?.length} months`)
        fetchStatus()
      } else flash(d.detail || 'Run failed')
    } catch (e) { flash('Error: ' + e.message) }
    finally { setRunning(false) }
  }

  const handleRunP2 = async () => {
    setRunningP2(true)
    try {
      const d = await (await fetch(`/api/planning/deviation/pww/run-phase2?block=${result?.block || activeBlock}`)).json()
      if (d.ok) {
        flash(`Phase 2 done — ${d.clusters?.length} clusters · ${d.months?.length} months · ${d.total_depts} depts`)
        const full = await (await fetch('/api/planning/deviation/pww/phase2-result')).json()
        setP2Result(full)
        setReappResult(null)
        const m0 = full.ly_months?.[0]
        if (m0) setActiveMonth(m0)
        const cl0 = full.clusters?.[0]
        if (cl0) setActiveCluster(cl0)
        fetchStatus()
      } else flash(d.detail || 'Phase 2 failed')
    } catch (e) { flash('Error: ' + e.message) }
    finally { setRunningP2(false) }
  }

  const handleReapportion = async () => {
    setRunningReapp(true)
    try {
      const d = await (await fetch('/api/planning/deviation/pww/reapportion')).json()
      if (d.ok) {
        flash(`Reapportionment done — ${d.clusters?.length} clusters · ${d.total_depts} depts/cluster`)
        const full = await (await fetch('/api/planning/deviation/pww/reapportion-result')).json()
        setReappResult(full)
        const cl0 = full.clusters?.[0]
        if (cl0) setReappCluster(cl0)
        fetchStatus()
      } else flash(d.detail || 'Reapportionment failed')
    } catch (e) { flash('Error: ' + e.message) }
    finally { setRunningReapp(false) }
  }

  const toggleExpand = dept => setExpanded(prev => {
    const n = new Set(prev); n.has(dept) ? n.delete(dept) : n.add(dept); return n
  })
  const toggleExpand2 = key => setExpanded2(prev => {
    const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n
  })

  const divData   = result?.divisions?.[activeDiv]
  const depts     = Object.entries(divData?.depts || {})
  const divTotal  = divData?.ly_div_block_total ?? 0
  const divNames  = Object.keys(result?.divisions || {})

  // Phase 2 derived
  const p2MonthData   = p2Result?.result?.[activeMonth] || {}
  const p2ClusterData = p2MonthData[activeCluster] || {}
  const p2Divs        = [...new Set(Object.values(p2ClusterData).map(d => d.div))].sort()
  const p2Depts       = Object.entries(p2ClusterData).filter(([, d]) => !activeDiv2 || d.div === activeDiv2)

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1800 }}>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary, letterSpacing: -0.3 }}>
          PW/W Deviation Engine
        </div>
        <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
          Phase 1: Dept-level deviation · Phase 2: Cluster × Dept × MRP × Month adjusted contribution %
        </div>
      </div>

      {/* ── Sync + Run panel ─────────────────────────────────────────────────── */}
      <div style={{
        background: theme.surface, border: `1px solid ${theme.border}`,
        borderRadius: 10, padding: '16px 20px', marginBottom: 16,
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 260 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, marginBottom: 3 }}>
            PPO Cont % — Sync from Folder
          </div>
          <div style={{ fontSize: 11, color: theme.textMuted, fontFamily: theme.fontMono }}>
            {syncStatus?.path || '…'}
          </div>
          <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 3 }}>
            {syncStatus?.file_found
              ? `File found · ${syncStatus.file_date} · ${syncStatus.size_kb} KB`
              : 'File not found — drop PPO Cont %.xlsx in the PW-W Deviation folder'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={fetchSyncStatus} style={btnStyle('ghost')}>Refresh</button>
          <button onClick={handleSync} disabled={syncing || !syncStatus?.file_found} style={btnStyle('secondary', syncing || !syncStatus?.file_found)}>
            {syncing ? 'Syncing…' : 'Sync File'}
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, whiteSpace: 'nowrap' }}>BLOCK</span>
            <BlockSearch blocks={blocks} value={activeBlock} onChange={setActiveBlock} />
          </div>
          <button onClick={handleRun} disabled={running || !status?.ppo_loaded} style={btnStyle('primary', running || !status?.ppo_loaded)}>
            {running ? 'Running…' : 'Run Phase 1'}
          </button>
          {result && (
            <button onClick={handleRunP2} disabled={runningP2} style={btnStyle('accent', runningP2)}>
              {runningP2 ? 'Running Phase 2…' : 'Run Phase 2'}
            </button>
          )}
          {p2Result && (
            <button onClick={handleReapportion} disabled={runningReapp} style={btnStyle('teal', runningReapp)}>
              {runningReapp ? 'Reapportioning…' : 'Reapportion'}
            </button>
          )}
        </div>
        {msg && <div style={{ width: '100%', fontSize: 12, color: theme.accent, fontWeight: 600 }}>{msg}</div>}
      </div>

      {/* Status bar */}
      {status && (
        <div style={{
          display: 'flex', gap: 24, marginBottom: 20, flexWrap: 'wrap',
          background: theme.surface, border: `1px solid ${theme.border}`,
          borderRadius: 8, padding: '10px 20px',
        }}>
          <Stat label="PPO Depts" value={status.ppo_depts || '—'} />
          {result && <>
            <Stat label="Block"       value={result.block} />
            <Stat label="SSG Stores"  value={result.ssg_stores?.length} />
            <Stat label="Months"      value={result.ly_months_used?.length} />
            <Stat label="Threshold"   value={`< ${result.threshold_pct}%`} />
            {result.unmatched_depts?.length > 0 && (
              <Stat label="No LY Data" value={result.unmatched_depts.length} warn />
            )}
          </>}
          {p2Result && <>
            <div style={{ width: 1, background: theme.border, margin: '0 4px' }} />
            <Stat label="P2 Clusters" value={p2Result.clusters?.length} />
            <Stat label="P2 Months"   value={p2Result.ly_months?.length} />
            <Stat label="P2 Run"      value={p2Result.run_date?.split(' ')[0]} />
          </>}
          {reappResult && <>
            <div style={{ width: 1, background: theme.border, margin: '0 4px' }} />
            <Stat label="Reapp Run" value={reappResult.run_date?.split(' ')[0]} />
          </>}
          {result && (
            <div style={{ marginLeft: 'auto', fontSize: 11, color: theme.textMuted, alignSelf: 'center', textAlign: 'right' }}>
              {result.ly_months_used?.join(' · ')}<br/>P1 run: {result.run_date}
            </div>
          )}
        </div>
      )}

      {/* ── Phase 1 Results ──────────────────────────────────────────────────── */}
      {result && (
        <div style={{ marginBottom: 32 }}>
          <SectionTitle>Phase 1 — Department Deviation</SectionTitle>

          {/* Division tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            {divNames.map(div => {
              const active = div === activeDiv
              const c = DIV_COLOR[div] || theme.primary
              const count = Object.keys(result.divisions[div]?.depts || {}).length
              return (
                <button key={div} onClick={() => setActiveDiv(div)} style={{
                  padding: '7px 18px', borderRadius: 8, cursor: 'pointer',
                  border: `1.5px solid ${active ? c : theme.border}`,
                  background: active ? `${alpha(c,'22')}` : theme.surface,
                  color: active ? c : theme.textSecondary,
                  fontWeight: active ? 700 : 500, fontSize: 13,
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  {div}
                  <span style={{
                    fontSize: 10, fontWeight: 700, borderRadius: 10, padding: '1px 6px',
                    background: active ? c : theme.border,
                    color: active ? '#fff' : theme.textSecondary,
                  }}>{count}</span>
                </button>
              )
            })}
            <div style={{ marginLeft: 'auto', fontSize: 11, color: theme.textMuted }}>
              Div LY SSG Total: <span style={{ color: theme.textPrimary, fontFamily: theme.fontMono }}>₹{fmt(divTotal)}</span>
            </div>
          </div>

          {/* Phase 1 table */}
          <div style={{ background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: theme.surfaceUp }}>
                  <th style={{ ...CELL, textAlign: 'left', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5, paddingLeft: 16 }}>DEPARTMENT</th>
                  <th style={{ ...CELL, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5 }}>LY BLOCK SALES</th>
                  <th style={{ ...CELL, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5 }}>BLOCK CONT%</th>
                  <th style={{ ...CELL, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5 }}>PPO CONT%</th>
                  <th style={{ ...CELL, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5 }}>DEV RATIO</th>
                  <th style={{ ...CELL, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 11, letterSpacing: 0.5 }}>MRP PTS</th>
                  <th style={{ ...CELL, width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {depts.map(([dept, d], i) => {
                  const isExp   = expanded.has(dept)
                  const mrpRows = d.ppo_mrp_breakdown || []
                  return (
                    <>
                      <tr key={dept} style={{
                        background: i % 2 === 0 ? 'transparent' : `${alpha(theme.surfaceUp,'66')}`,
                        borderTop: `1px solid ${theme.border}`,
                        cursor: 'pointer',
                      }} onClick={() => toggleExpand(dept)}>
                        <td style={{ ...CELL, textAlign: 'left', paddingLeft: 16, fontWeight: 600, color: theme.textPrimary }}>{dept}</td>
                        <td style={{ ...CELL, textAlign: 'right', color: d.ly_block_sales > 0 ? theme.textPrimary : theme.textMuted }}>
                          ₹{fmt(d.ly_block_sales)}
                        </td>
                        <td style={{ ...CELL, textAlign: 'right' }}>
                          <span style={{
                            background: d.block_cont_pct < 2.5 ? `${alpha(theme.textMuted,'22')}` : `${alpha('var(--st-btn,#A8CBB7)','22')}`,
                            color: d.block_cont_pct < 2.5 ? theme.textMuted : theme.primary,
                            borderRadius: 4, padding: '1px 6px', fontFamily: theme.fontMono, fontSize: 11,
                          }}>{fmtP(d.block_cont_pct)}</span>
                        </td>
                        <td style={{ ...CELL, textAlign: 'right', color: theme.textSecondary, fontSize: 11 }}>
                          {fmtP(d.ppo_dept_cont_pct)}
                        </td>
                        <td style={{ ...CELL, textAlign: 'right' }}>
                          {d.deviation_flag === 'below_threshold' ? (
                            <span style={{ fontSize: 10, color: theme.textMuted, fontStyle: 'italic' }}>0 (below {result.threshold_pct}%)</span>
                          ) : d.deviation_flag === 'no_plan' ? (
                            <span style={{ fontSize: 10, color: theme.warning }}>no plan</span>
                          ) : (
                            <span style={{
                              background: `${alpha(theme.accent,'18')}`, color: theme.accent,
                              borderRadius: 4, padding: '1px 8px', fontFamily: theme.fontMono, fontSize: 11, fontWeight: 600,
                            }}>{d.deviation_ratio?.toFixed(4)}×</span>
                          )}
                        </td>
                        <td style={{ ...CELL, textAlign: 'right', color: theme.textSecondary }}>{mrpRows.length}</td>
                        <td style={{ ...CELL, textAlign: 'center', color: theme.textMuted, fontSize: 10 }}>{isExp ? '▲' : '▼'}</td>
                      </tr>

                      {isExp && mrpRows.map((r, j) => (
                        <tr key={`${dept}-mrp-${j}`} style={{
                          background: `${alpha(theme.surfaceUp,'44')}`, borderTop: `1px solid ${alpha(theme.border,'22')}`,
                        }}>
                          <td style={{ ...CELL, textAlign: 'left', paddingLeft: 36, color: theme.textSecondary, fontSize: 11 }}>
                            ↳ {r.article_name || 'MRP ' + r.mrp}
                          </td>
                          <td style={{ ...CELL, textAlign: 'right', color: theme.textMuted, fontSize: 11 }}>MRP ₹{fmt(r.mrp)}</td>
                          <td style={{ ...CELL, textAlign: 'right' }}>
                            <span style={{
                              background: `${alpha(theme.accent,'18')}`, color: theme.accent,
                              borderRadius: 4, padding: '1px 6px', fontFamily: theme.fontMono, fontSize: 10,
                            }}>{fmtP(r.ppo_cont_pct)}</span>
                          </td>
                          <td colSpan={3}></td>
                          <td></td>
                        </tr>
                      ))}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>

          {result.unmatched_depts?.length > 0 && (
            <div style={{
              marginTop: 16, padding: '10px 16px', borderRadius: 8,
              background: `${alpha(theme.warning,'18')}`, border: `1px solid ${alpha(theme.warning,'44')}`,
              fontSize: 12, color: theme.warning,
            }}>
              <strong>{result.unmatched_depts.length} dept(s) in PPO file have no LY actuals</strong>:{' '}
              {result.unmatched_depts.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* ── Reapportionment Results ──────────────────────────────────────────── */}
      {reappResult && (
        <div style={{ marginBottom: 32 }}>
          <SectionTitle>Reapportionment — Cluster × Department MRP Mix</SectionTitle>
          <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14 }}>
            Final MRP contribution % per Cluster × Department (summed across {reappResult.ly_months?.join(', ')}, normalised to 100% within each dept).
          </div>

          {/* Cluster selector */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, alignSelf: 'center', marginRight: 4 }}>CLUSTER</span>
            {(reappResult.clusters || []).map(cl => {
              const active = cl === reappCluster
              return (
                <button key={cl} onClick={() => { setReappCluster(cl); setReappDiv(null); setExpandedReapp(new Set()) }} style={{
                  padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: active ? 700 : 400,
                  border: `1.5px solid ${active ? theme.accent : theme.border}`,
                  background: active ? `${alpha(theme.accent,'22')}` : theme.surface,
                  color: active ? theme.accent : theme.textSecondary,
                }}>{cl}</button>
              )
            })}
          </div>

          {/* Division filter */}
          {reappCluster && (() => {
            const clData  = reappResult.result?.[reappCluster] || {}
            const divSet  = [...new Set(Object.values(clData).map(d => d.div))].sort()
            const depts   = Object.entries(clData).filter(([, d]) => !reappDiv || d.div === reappDiv)

            return (
              <>
                <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, alignSelf: 'center', marginRight: 4 }}>DIVISION</span>
                  <button onClick={() => setReappDiv(null)} style={{
                    padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: !reappDiv ? 700 : 400,
                    border: `1.5px solid ${!reappDiv ? theme.primary : theme.border}`,
                    background: !reappDiv ? `${alpha(theme.primary,'22')}` : theme.surface,
                    color: !reappDiv ? theme.primary : theme.textSecondary,
                  }}>All</button>
                  {divSet.map(div => {
                    const active = div === reappDiv
                    const c = DIV_COLOR[div] || theme.primary
                    return (
                      <button key={div} onClick={() => setReappDiv(div)} style={{
                        padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: active ? 700 : 400,
                        border: `1.5px solid ${active ? c : theme.border}`,
                        background: active ? `${alpha(c,'22')}` : theme.surface,
                        color: active ? c : theme.textSecondary,
                      }}>{div}</button>
                    )
                  })}
                </div>

                <div style={{ background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: theme.surfaceUp }}>
                        <th style={{ ...CELL2, textAlign: 'left', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5, paddingLeft: 16 }}>DEPT</th>
                        <th style={{ ...CELL2, textAlign: 'center', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>DIV</th>
                        <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>BLOCK FINAL%</th>
                        <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>DEV RATIO</th>
                        <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>MRP PTS</th>
                        <th style={{ ...CELL2, width: 32 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {depts.map(([dept, dd], i) => {
                        const rowKey = `reapp-${reappCluster}-${dept}`
                        const isExp  = expandedReapp.has(rowKey)
                        const mrpEntries = Object.entries(dd.mrp_rows || {})
                        const c = DIV_COLOR[dd.div] || theme.primary
                        return (
                          <>
                            <tr key={rowKey} style={{
                              background: i % 2 === 0 ? 'transparent' : `${alpha(theme.surfaceUp,'66')}`,
                              borderTop: `1px solid ${theme.border}`,
                              cursor: 'pointer',
                            }} onClick={() => {
                              setExpandedReapp(prev => {
                                const n = new Set(prev); n.has(rowKey) ? n.delete(rowKey) : n.add(rowKey); return n
                              })
                            }}>
                              <td style={{ ...CELL2, textAlign: 'left', paddingLeft: 16, fontWeight: 600, color: theme.textPrimary }}>{dept}</td>
                              <td style={{ ...CELL2, textAlign: 'center' }}>
                                <span style={{ fontSize: 9, background: `${alpha(c,'22')}`, color: c, borderRadius: 4, padding: '1px 5px', fontWeight: 700 }}>{dd.div}</span>
                              </td>
                              <td style={{ ...CELL2, textAlign: 'right' }}>
                                <span style={{
                                  background: dd.dept_block_final_pct > 0 ? `${alpha('var(--st-btn,#A8CBB7)','18')}` : `${alpha(theme.textMuted,'18')}`,
                                  color: dd.dept_block_final_pct > 0 ? theme.primary : theme.textMuted,
                                  borderRadius: 4, padding: '1px 6px', fontFamily: theme.fontMono, fontSize: 10,
                                }}>{fmtP(dd.dept_block_final_pct)}</span>
                              </td>
                              <td style={{ ...CELL2, textAlign: 'right' }}>
                                {dd.deviation_flag === 'below_threshold' ? (
                                  <span style={{ fontSize: 10, color: theme.textMuted, fontStyle: 'italic' }}>thr</span>
                                ) : dd.deviation_flag === 'no_plan' ? (
                                  <span style={{ fontSize: 10, color: theme.warning }}>—</span>
                                ) : (
                                  <span style={{ color: theme.accent, fontFamily: theme.fontMono }}>{dd.deviation_ratio?.toFixed(4)}×</span>
                                )}
                              </td>
                              <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{mrpEntries.length}</td>
                              <td style={{ ...CELL2, textAlign: 'center', color: theme.textMuted, fontSize: 9 }}>{isExp ? '▲' : '▼'}</td>
                            </tr>

                            {isExp && (
                              <>
                                <tr style={{ background: `${alpha(theme.surfaceUp,'99')}` }}>
                                  <td style={{ ...CELL2, paddingLeft: 36, fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>ARTICLE / MRP</td>
                                  <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>PPO MIX%</td>
                                  <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>BLOCK FINAL%</td>
                                  <td colSpan={2} style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: '#0EA5E9', fontWeight: 700, letterSpacing: 0.5 }}>REAPPORTIONED%</td>
                                  <td></td>
                                </tr>
                                {mrpEntries.map(([mrpKey, mr]) => (
                                  <tr key={`${rowKey}-${mrpKey}`} style={{ background: `${alpha(theme.surfaceUp,'44')}`, borderTop: `1px solid ${alpha(theme.border,'22')}` }}>
                                    <td style={{ ...CELL2, paddingLeft: 36, color: theme.textSecondary, fontSize: 11 }}>
                                      ↳ {mr.article_name || 'MRP'} <span style={{ color: theme.textMuted }}>₹{fmt(mr.mrp)}</span>
                                    </td>
                                    <td style={{ ...CELL2, textAlign: 'right', color: theme.textMuted }}>{fmtP(mr.ppo_mrp_pct)}</td>
                                    <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{fmtP(mr.block_final_pct)}</td>
                                    <td colSpan={2} style={{ ...CELL2, textAlign: 'right' }}>
                                      <span style={{
                                        background: '#0EA5E922', color: '#0EA5E9',
                                        borderRadius: 4, padding: '1px 8px', fontFamily: theme.fontMono,
                                        fontSize: 11, fontWeight: 700,
                                      }}>{mr.reapportioned_pct?.toFixed(2)}%</span>
                                    </td>
                                    <td></td>
                                  </tr>
                                ))}
                              </>
                            )}
                          </>
                        )
                      })}
                    </tbody>
                  </table>
                  {depts.length === 0 && (
                    <div style={{ padding: '20px 24px', fontSize: 13, color: theme.textMuted, textAlign: 'center' }}>
                      No data for this cluster/division.
                    </div>
                  )}
                </div>
              </>
            )
          })()}
        </div>
      )}

      {/* ── Phase 2 Results ──────────────────────────────────────────────────── */}
      {p2Result && (
        <div>
          <SectionTitle>Phase 2 — Cluster × Dept × MRP Adjusted Contribution %</SectionTitle>

          {/* Month tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, alignSelf: 'center', marginRight: 4 }}>MONTH</span>
            {(p2Result.ly_months || []).map(m => {
              const active = m === activeMonth
              return (
                <button key={m} onClick={() => setActiveMonth(m)} style={{
                  padding: '5px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 12, fontWeight: active ? 700 : 500,
                  border: `1.5px solid ${active ? theme.primary : theme.border}`,
                  background: active ? `${alpha(theme.primary,'22')}` : theme.surface,
                  color: active ? theme.primary : theme.textSecondary,
                }}>{m}</button>
              )
            })}
          </div>

          {/* Cluster pills */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, alignSelf: 'center', marginRight: 4 }}>CLUSTER</span>
            {(p2Result.clusters || []).map(cl => {
              const active = cl === activeCluster
              return (
                <button key={cl} onClick={() => setActiveCluster(cl)} style={{
                  padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: active ? 700 : 400,
                  border: `1.5px solid ${active ? theme.accent : theme.border}`,
                  background: active ? `${alpha(theme.accent,'22')}` : theme.surface,
                  color: active ? theme.accent : theme.textSecondary,
                }}>{cl}</button>
              )
            })}
          </div>

          {/* Division filter */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, alignSelf: 'center', marginRight: 4 }}>DIVISION</span>
            <button onClick={() => setActiveDiv2(null)} style={{
              padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: !activeDiv2 ? 700 : 400,
              border: `1.5px solid ${!activeDiv2 ? theme.primary : theme.border}`,
              background: !activeDiv2 ? `${alpha(theme.primary,'22')}` : theme.surface,
              color: !activeDiv2 ? theme.primary : theme.textSecondary,
            }}>All</button>
            {p2Divs.map(div => {
              const active = div === activeDiv2
              const c = DIV_COLOR[div] || theme.primary
              return (
                <button key={div} onClick={() => setActiveDiv2(div)} style={{
                  padding: '5px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: active ? 700 : 400,
                  border: `1.5px solid ${active ? c : theme.border}`,
                  background: active ? `${alpha(c,'22')}` : theme.surface,
                  color: active ? c : theme.textSecondary,
                }}>{div}</button>
              )
            })}
          </div>

          {/* Phase 2 table */}
          <div style={{ background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: theme.surfaceUp }}>
                  <th style={{ ...CELL2, textAlign: 'left', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5, paddingLeft: 16 }}>DEPT</th>
                  <th style={{ ...CELL2, textAlign: 'center', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>DIV</th>
                  <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>LY DEPT CONT%</th>
                  <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>DEV RATIO</th>
                  <th style={{ ...CELL2, textAlign: 'right', fontWeight: 600, color: theme.textMuted, fontSize: 10, letterSpacing: 0.5 }}>MRP PTS</th>
                  <th style={{ ...CELL2, width: 32 }}></th>
                </tr>
              </thead>
              <tbody>
                {p2Depts.map(([dept, dd], i) => {
                  const rowKey = `${activeMonth}-${activeCluster}-${dept}`
                  const isExp  = expanded2.has(rowKey)
                  const mrpEntries = Object.entries(dd.mrp_rows || {})
                  const c = DIV_COLOR[dd.div] || theme.primary
                  return (
                    <>
                      <tr key={rowKey} style={{
                        background: i % 2 === 0 ? 'transparent' : `${alpha(theme.surfaceUp,'66')}`,
                        borderTop: `1px solid ${theme.border}`,
                        cursor: 'pointer',
                      }} onClick={() => toggleExpand2(rowKey)}>
                        <td style={{ ...CELL2, textAlign: 'left', paddingLeft: 16, fontWeight: 600, color: theme.textPrimary }}>{dept}</td>
                        <td style={{ ...CELL2, textAlign: 'center' }}>
                          <span style={{ fontSize: 9, background: `${alpha(c,'22')}`, color: c, borderRadius: 4, padding: '1px 5px', fontWeight: 700 }}>{dd.div}</span>
                        </td>
                        <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{fmtP2(dd.ly_dept_cont_pct)}</td>
                        <td style={{ ...CELL2, textAlign: 'right' }}>
                          {dd.deviation_flag === 'below_threshold' ? (
                            <span style={{ fontSize: 10, color: theme.textMuted, fontStyle: 'italic' }}>0 (thr)</span>
                          ) : dd.deviation_flag === 'no_plan' ? (
                            <span style={{ fontSize: 10, color: theme.warning }}>—</span>
                          ) : (
                            <span style={{ color: theme.accent, fontFamily: theme.fontMono }}>{dd.deviation_ratio?.toFixed(4)}×</span>
                          )}
                        </td>
                        <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{mrpEntries.length}</td>
                        <td style={{ ...CELL2, textAlign: 'center', color: theme.textMuted, fontSize: 9 }}>{isExp ? '▲' : '▼'}</td>
                      </tr>

                      {isExp && (
                        <>
                          {/* MRP sub-header */}
                          <tr style={{ background: `${alpha(theme.surfaceUp,'99')}` }}>
                            <td style={{ ...CELL2, paddingLeft: 36, fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>ARTICLE / MRP</td>
                            <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>PPO MIX%</td>
                            <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>LY MRP%</td>
                            <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>ADJUSTED%</td>
                            <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5 }}>PPO DIV%</td>
                            <td style={{ ...CELL2, textAlign: 'right', fontSize: 9, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, paddingRight: 16 }}>
                              FINAL% / RULE
                            </td>
                          </tr>
                          {mrpEntries.map(([mrpKey, mr]) => (
                            <tr key={`${rowKey}-${mrpKey}`} style={{
                              background: `${alpha(theme.surfaceUp,'44')}`, borderTop: `1px solid ${alpha(theme.border,'22')}`,
                            }}>
                              <td style={{ ...CELL2, paddingLeft: 36, color: theme.textSecondary, fontSize: 11 }}>
                                ↳ {mr.article_name || 'MRP'} <span style={{ color: theme.textMuted }}>₹{fmt(mr.mrp)}</span>
                              </td>
                              <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{fmtP(mr.ppo_mrp_pct)}</td>
                              <td style={{ ...CELL2, textAlign: 'right', color: theme.textSecondary }}>{fmtP(mr.ly_mrp_cont_pct)}</td>
                              <td style={{ ...CELL2, textAlign: 'right', color: mr.adjusted_cont_pct > 0 ? theme.textPrimary : theme.textMuted }}>
                                {fmtP(mr.adjusted_cont_pct)}
                              </td>
                              <td style={{ ...CELL2, textAlign: 'right', color: theme.textMuted }}>{fmtP(mr.ppo_div_cont_pct)}</td>
                              <td style={{ ...CELL2, textAlign: 'right', paddingRight: 16 }}>
                                <span style={{ fontFamily: theme.fontMono, fontSize: 11, fontWeight: 700, color: theme.textPrimary, marginRight: 6 }}>
                                  {fmtP(mr.final_cont_pct)}
                                </span>
                                <RuleBadge rule={mr.rule} />
                              </td>
                            </tr>
                          ))}
                        </>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
            {p2Depts.length === 0 && (
              <div style={{ padding: '20px 24px', fontSize: 13, color: theme.textMuted, textAlign: 'center' }}>
                No data for this month/cluster/division combination.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function SectionTitle({ children }) {
  return (
    <div style={{
      fontSize: 14, fontWeight: 700, color: theme.textPrimary, letterSpacing: 0.2,
      marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${theme.border}`,
    }}>{children}</div>
  )
}

function Stat({ label, value, warn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ fontSize: 10, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: warn ? theme.warning : theme.textPrimary, fontFamily: theme.fontMono }}>{value ?? '—'}</div>
    </div>
  )
}

function btnStyle(variant, disabled) {
  const base = {
    padding: '6px 16px', borderRadius: 7, fontSize: 12, fontWeight: 600,
    cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
    border: 'none', transition: 'opacity 0.15s',
  }
  if (variant === 'primary')   return { ...base, background: 'var(--st-btn,#A8CBB7)',  color: 'var(--st-btn-text,#1F4D3A)' }
  if (variant === 'secondary') return { ...base, background: theme.accent,   color: '#fff' }
  if (variant === 'accent')    return { ...base, background: '#0EA5E9',      color: '#fff' }
  if (variant === 'teal')     return { ...base, background: 'var(--st-btn,#A8CBB7)',      color: 'var(--st-btn-text,#1F4D3A)' }
  return { ...base, background: 'none', color: theme.textSecondary, border: `1px solid ${theme.border}` }
}
