import { useState, useEffect, useCallback } from 'react'
import { theme } from '../theme'

const DIVISIONS = ['KIDS', 'LADIES', 'MENS', 'GM', 'RETAIL']

const DIV_COLOR = {
  KIDS:   '#C85A12',
  LADIES: '#7420B8',
  MENS:   '#077A4A',
  GM:     '#1E54C0',
  RETAIL: '#B22620',
}

const ATTR_STYLE = {
  'REGULAR':    { bg: '#1E2540', color: '#818CF8' },
  'SUMMER':     { bg: '#2A1C10', color: '#FB923C' },
  'PREWINTER':  { bg: '#112318', color: '#4ADE80' },
  'LT WINTER':  { bg: '#0F1E30', color: '#60A5FA' },
  'HVY WINTER': { bg: '#0B1524', color: '#93C5FD' },
  'OCCASIONAL': { bg: '#21102E', color: '#C084FC' },
}

function AttrBadge({ attr }) {
  const s = ATTR_STYLE[attr] || { bg: '#F3F4F6', color: '#374151' }
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, letterSpacing: 0.5,
      padding: '2px 7px', borderRadius: 4,
      background: s.bg, color: s.color,
      whiteSpace: 'nowrap',
    }}>{attr}</span>
  )
}

function ContribBar({ value, max = 100 }) {
  const pct = Math.min((value / max) * 100, 100)
  const color = value > 100.05 ? '#D94F3D' : value >= 99.9 ? '#00A86B' : '#F59E0B'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: '#E5E7EB', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.2s' }} />
      </div>
      <span style={{
        fontSize: 12, fontWeight: 700, minWidth: 46, textAlign: 'right',
        color, fontVariantNumeric: 'tabular-nums',
      }}>{value.toFixed(2)}%</span>
    </div>
  )
}

export default function DepartmentPlan() {
  const [config, setConfig] = useState(null)
  const [activeDiv, setActiveDiv] = useState('KIDS')
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newDept, setNewDept] = useState({ division: 'KIDS', name: '', attribute: 'REGULAR' })
  const [addError, setAddError] = useState('')
  const [search, setSearch] = useState('')
  const [attrFilter, setAttrFilter] = useState(null) // null = All
  const [aopSyncing, setAopSyncing] = useState(false)
  const [aopSyncResult, setAopSyncResult] = useState(null)
  const [aopDivisionAops, setAopDivisionAops] = useState(null)   // [{division, annual_target}] from AOP Forecaster
  const [aopRunMeta, setAopRunMeta] = useState(null)             // {run_id, computed_at}
  const [calcRunning, setCalcRunning] = useState(false)
  const [calcResults, setCalcResults] = useState(null)           // {results: [{division, annual_target, contrib_sum, dept_breakdown}]}

  const fetchConfig = useCallback(async () => {
    try {
      const r = await fetch('/api/planning/department-plan/config')
      const data = await r.json()
      setConfig(data.divisions)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  // Pick up the last sync-from-aop-forecaster result on load, if any, so a
  // page reload doesn't lose it.
  useEffect(() => {
    fetch('/api/planning/department-plan/aop-forecaster-status')
      .then(r => r.json())
      .then(d => { if (d.synced) { setAopDivisionAops(d.division_aops); setAopRunMeta({ run_id: d.run_id, computed_at: d.computed_at }) } })
      .catch(() => {})
  }, [])

  const syncFromAop = async () => {
    setAopSyncing(true); setAopSyncResult(null)
    try {
      const r = await fetch('/api/planning/department-plan/sync-from-aop-forecaster', { method: 'POST' })
      const d = await r.json()
      if (r.ok) {
        setAopDivisionAops(d.division_aops)
        setAopRunMeta({ run_id: d.run_id, computed_at: d.computed_at })
        setAopSyncResult({ ok: true, msg: `Synced ${d.division_aops.length} divisions from run ${d.run_id.slice(0, 8)}…` })
        setCalcResults(null)
      } else {
        setAopSyncResult({ ok: false, msg: d.detail || 'Error' })
      }
    } catch (e) { setAopSyncResult({ ok: false, msg: String(e) }) }
    finally { setAopSyncing(false) }
  }

  const calculateFromAop = async () => {
    if (!aopDivisionAops) return
    setCalcRunning(true)
    try {
      const r = await fetch('/api/planning/department-plan/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ division_aops: aopDivisionAops }),
      })
      const d = await r.json()
      if (r.ok) setCalcResults(d)
      else setAopSyncResult({ ok: false, msg: d.detail || 'Calculate failed' })
    } catch (e) { setAopSyncResult({ ok: false, msg: String(e) }) }
    finally { setCalcRunning(false) }
  }

  const handleToggle = async (div, name, active) => {
    // Optimistic update
    setConfig(prev => {
      const next = { ...prev }
      next[div] = prev[div].map(r => r.name === name ? { ...r, active } : r)
      return next
    })
    await fetch('/api/planning/department-plan/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ division: div, name, active }),
    })
    fetchConfig()
  }

  const handleAddDept = async () => {
    setAddError('')
    if (!newDept.name.trim()) { setAddError('Department name is required'); return }
    const r = await fetch('/api/planning/department-plan/add-department', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...newDept, name: newDept.name.trim().toUpperCase() }),
    })
    const data = await r.json()
    if (!data.ok) { setAddError(data.error || 'Failed to add'); return }
    setNewDept(prev => ({ ...prev, name: '' }))
    setShowAdd(false)
    await fetchConfig()
  }

  if (loading) return (
    <div style={{ padding: 40, color: theme.textSecondary, fontSize: 14 }}>Loading department master…</div>
  )

  const rows = config?.[activeDiv] || []
  const activeRows = rows.filter(r => r.active)
  const filteredRows = rows.filter(r => {
    const matchSearch = !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.attribute.toLowerCase().includes(search.toLowerCase())
    const matchAttr = !attrFilter || r.attribute === attrFilter
    return matchSearch && matchAttr
  })
  // Count per attribute for the filter chips
  const attrCounts = {}
  rows.forEach(r => { attrCounts[r.attribute] = (attrCounts[r.attribute] || 0) + 1 })

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh' }}>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>Department Master Setup</div>
            <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
              Department hierarchy, active/inactive status &amp; contribution % per division
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
            {/* Sync from AOP Forecaster — real pipeline link, not just navigation */}
            <button
              onClick={syncFromAop}
              disabled={aopSyncing}
              style={{
                padding: '8px 18px', borderRadius: 8, border: `1.5px solid #1488cc`,
                background: aopSyncing ? 'transparent' : '#1488cc12',
                color: '#1488cc', fontWeight: 700, fontSize: 12, cursor: aopSyncing ? 'default' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 7,
              }}
            >
              <span style={aopSyncing ? { animation: 'spin 0.9s linear infinite', display: 'inline-block' } : {}}>↺</span>
              {aopSyncing ? 'Syncing…' : 'Sync from AOP Forecaster'}
            </button>
            {aopSyncResult && (
              <div style={{
                fontSize: 11, padding: '4px 10px', borderRadius: 5,
                background: aopSyncResult.ok ? '#1488cc14' : '#FEE2E2',
                color: aopSyncResult.ok ? '#1488cc' : '#991B1B',
                border: `1px solid ${aopSyncResult.ok ? '#1488cc44' : '#FCA5A5'}`,
              }}>
                {aopSyncResult.msg}
              </div>
            )}
          </div>
        </div>
        <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>

        {/* AOP-synced division targets → Calculate Department Plan */}
        {aopDivisionAops && (
          <div style={{
            marginTop: 14, padding: '14px 18px', borderRadius: 10,
            background: '#1488cc0A', border: '1px solid #1488cc33',
            display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16,
          }}>
            <div style={{ fontSize: 12, color: theme.textSecondary, minWidth: 180 }}>
              <strong style={{ color: theme.textPrimary }}>AOP Forecaster</strong> run {aopRunMeta?.run_id?.slice(0, 8)}…
              <br />computed {aopRunMeta?.computed_at ? new Date(aopRunMeta.computed_at).toLocaleString('en-IN') : '—'}
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {aopDivisionAops.map(d => (
                <div key={d.division} style={{
                  padding: '6px 12px', borderRadius: 7, background: theme.surface,
                  border: `1px solid ${DIV_COLOR[d.division] || theme.border}44`,
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: DIV_COLOR[d.division] || theme.textSecondary }}>{d.division}</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary }}>₹{d.annual_target.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L</div>
                </div>
              ))}
            </div>
            <button
              onClick={calculateFromAop}
              disabled={calcRunning}
              style={{
                marginLeft: 'auto', padding: '9px 20px', borderRadius: 8, border: 'none',
                background: calcRunning ? theme.surfaceAlt : '#1488cc',
                color: '#fff', fontWeight: 700, fontSize: 13, cursor: calcRunning ? 'default' : 'pointer',
              }}
            >
              {calcRunning ? 'Calculating…' : 'Calculate Department Plan →'}
            </button>
          </div>
        )}

        {/* Calculated department breakdown for the active division */}
        {calcResults && (() => {
          const divResult = calcResults.results.find(r => r.division === activeDiv)
          if (!divResult) return null
          return (
            <div style={{ marginTop: 14, border: `1px solid ${theme.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <div style={{
                padding: '10px 18px', background: `${DIV_COLOR[activeDiv]}0F`,
                borderBottom: `1px solid ${theme.border}`, display: 'flex', justifyContent: 'space-between', fontSize: 12,
              }}>
                <strong style={{ color: theme.textPrimary }}>{activeDiv} — calculated department plan</strong>
                <span style={{ color: theme.textSecondary }}>
                  ₹{divResult.annual_target.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L annual · contrib sum {divResult.contrib_sum}% · {divResult.dept_breakdown.length} depts
                </span>
              </div>
              <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ position: 'sticky', top: 0, background: theme.surface }}>
                      <th style={{ textAlign: 'left', padding: '8px 18px', color: theme.textSecondary }}>Department</th>
                      <th style={{ textAlign: 'left', padding: '8px 12px', color: theme.textSecondary }}>Attribute</th>
                      <th style={{ textAlign: 'right', padding: '8px 12px', color: theme.textSecondary }}>Contrib %</th>
                      <th style={{ textAlign: 'right', padding: '8px 18px', color: theme.textSecondary }}>Sales (₹ L)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {divResult.dept_breakdown.map(d => (
                      <tr key={d.name} style={{ borderTop: `1px solid ${theme.border}` }}>
                        <td style={{ padding: '7px 18px', color: theme.textPrimary }}>{d.name}</td>
                        <td style={{ padding: '7px 12px' }}><AttrBadge attr={d.attribute} /></td>
                        <td style={{ padding: '7px 12px', textAlign: 'right', color: theme.textSecondary, fontVariantNumeric: 'tabular-nums' }}>{d.contrib_pct.toFixed(2)}%</td>
                        <td style={{ padding: '7px 18px', textAlign: 'right', color: theme.textPrimary, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{d.sales_lakhs.toLocaleString('en-IN')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })()}
      </div>

      {/* Division tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
        {DIVISIONS.map(div => {
          const divRows = config?.[div] || []
          const activeCount = divRows.filter(r => r.active).length
          return (
            <button key={div} onClick={() => { setActiveDiv(div); setSearch(''); setAttrFilter(null) }} style={{
              padding: '8px 18px', borderRadius: 7, cursor: 'pointer',
              border: activeDiv === div ? `2px solid ${DIV_COLOR[div]}` : '2px solid transparent',
              background: activeDiv === div ? DIV_COLOR[div] : theme.surface,
              color: activeDiv === div ? '#fff' : theme.textPrimary,
              fontWeight: 600, fontSize: 13,
              boxShadow: activeDiv === div ? `0 2px 8px ${DIV_COLOR[div]}44` : 'none',
              outline: 'none',
            }}>
              {div}
              {activeCount > 0 && (
                <span style={{
                  marginLeft: 7, fontSize: 10, fontWeight: 700,
                  background: activeDiv === div ? 'rgba(255,255,255,0.25)' : theme.surfaceAlt,
                  color: activeDiv === div ? '#fff' : theme.textSecondary,
                  borderRadius: 10, padding: '1px 6px',
                }}>
                  {activeCount}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Active division panel */}
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10 }}>

        {/* Panel toolbar */}
        <div style={{
          padding: '14px 20px',
          borderBottom: `1px solid ${theme.border}`,
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: DIV_COLOR[activeDiv], flexShrink: 0,
          }} />
          <span style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary, marginRight: 4 }}>
            {activeDiv}
          </span>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>
            {rows.length} departments · {activeRows.length} active
          </span>

          <div style={{ flex: 1 }} />

          {/* Search */}
          <input
            placeholder="Search departments…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              border: `1px solid ${theme.border}`, outline: 'none',
              color: theme.textPrimary, background: theme.surfaceAlt, width: 180,
            }}
          />

          {/* Export */}
          <a href="/api/planning/department-plan/export" style={{
            padding: '6px 14px', borderRadius: 6, fontSize: 12,
            background: theme.surfaceAlt, border: `1px solid ${theme.border}`,
            color: theme.textSecondary, textDecoration: 'none', fontWeight: 500,
          }}>↓ Export</a>
        </div>

        {/* Attribute filter chips */}
        <div style={{
          padding: '10px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.4, marginRight: 4 }}>FILTER</span>
          {/* All chip */}
          <button onClick={() => setAttrFilter(null)} style={{
            padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
            cursor: 'pointer', border: 'none', outline: 'none',
            background: !attrFilter ? DIV_COLOR[activeDiv] : theme.surfaceAlt,
            color: !attrFilter ? '#fff' : theme.textSecondary,
            transition: 'background 0.15s',
          }}>
            All <span style={{ opacity: 0.7 }}>({rows.length})</span>
          </button>
          {Object.entries(ATTR_STYLE).map(([attr, s]) => {
            const count = attrCounts[attr] || 0
            if (count === 0) return null
            const isActive = attrFilter === attr
            return (
              <button key={attr} onClick={() => setAttrFilter(isActive ? null : attr)} style={{
                padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                cursor: 'pointer', outline: 'none',
                border: isActive ? 'none' : `1px solid ${s.bg === '#1E3A5F' ? '#334155' : theme.border}`,
                background: isActive ? s.color : s.bg,
                color: isActive ? (s.bg === '#1E3A5F' ? '#1E3A5F' : '#fff') : s.color,
                transition: 'all 0.15s',
              }}>
                {attr} <span style={{ opacity: 0.7 }}>({count})</span>
              </button>
            )
          })}
          {attrFilter && (
            <span style={{ fontSize: 11, color: theme.textMuted, marginLeft: 4 }}>
              showing {filteredRows.length} of {rows.length}
            </span>
          )}
        </div>

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: theme.surfaceAlt }}>
                <th style={thStyle('left', 40)}>Status</th>
                <th style={thStyle('left', 260)}>Department</th>
                <th style={thStyle('left', 120)}>Attribute</th>
                <th style={thStyle('left', 80)}>Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ padding: '32px 20px', textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>
                    {rows.length === 0
                      ? `No departments defined for ${activeDiv} yet. Add one below.`
                      : 'No departments match your search.'}
                  </td>
                </tr>
              )}
              {filteredRows.map((row, i) => (
                <tr key={row.name} style={{
                  borderBottom: `1px solid ${theme.border}`,
                  background: row.active ? 'transparent' : 'rgba(0,0,0,0.15)',
                  opacity: row.active ? 1 : 0.55,
                }}>
                  {/* Toggle */}
                  <td style={{ padding: '8px 12px 8px 20px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 6 }}>
                      <div
                        onClick={() => handleToggle(activeDiv, row.name, !row.active)}
                        style={{
                          width: 34, height: 18, borderRadius: 9,
                          background: row.active ? DIV_COLOR[activeDiv] : '#D1D5DB',
                          position: 'relative', cursor: 'pointer', transition: 'background 0.2s',
                          flexShrink: 0,
                        }}
                      >
                        <div style={{
                          position: 'absolute', top: 2,
                          left: row.active ? 18 : 2,
                          width: 14, height: 14, borderRadius: '50%',
                          background: '#fff', transition: 'left 0.2s',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                        }} />
                      </div>
                      <span style={{ fontSize: 10, color: row.active ? DIV_COLOR[activeDiv] : theme.textMuted, fontWeight: 600 }}>
                        {row.active ? 'ON' : 'OFF'}
                      </span>
                    </label>
                  </td>

                  {/* Name */}
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      fontWeight: row.active ? 500 : 400,
                      color: row.active ? theme.textPrimary : theme.textMuted,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: 12,
                    }}>{row.name}</span>
                  </td>

                  {/* Attribute */}
                  <td style={{ padding: '8px 12px' }}>
                    <AttrBadge attr={row.attribute} />
                  </td>

                  {/* Source */}
                  <td style={{ padding: '8px 12px' }}>
                    {row.source === 'custom' ? (
                      <span style={{
                        fontSize: 10, padding: '2px 6px', borderRadius: 4,
                        background: '#21102E', color: '#C084FC', fontWeight: 600,
                      }}>Custom</span>
                    ) : (
                      <span style={{ fontSize: 10, color: theme.textMuted }}>Master</span>
                    )}
                  </td>

                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Optional: Add Department ── */}
        <div style={{ borderTop: `1px solid ${theme.border}` }}>
          <button
            onClick={() => { setShowAdd(v => !v); setAddError('') }}
            style={{
              width: '100%', padding: '12px 20px',
              background: 'transparent', border: 'none',
              color: theme.textSecondary, fontSize: 12, cursor: 'pointer',
              textAlign: 'left', display: 'flex', alignItems: 'center', gap: 8,
            }}
          >
            <span style={{
              width: 18, height: 18, borderRadius: '50%',
              background: theme.surfaceAlt, border: `1px dashed ${theme.border}`,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, color: theme.primary, fontWeight: 700, lineHeight: 1,
            }}>+</span>
            <span style={{ fontWeight: 500 }}>Add department</span>
            <span style={{
              marginLeft: 4, fontSize: 10, padding: '1px 6px', borderRadius: 3,
              background: theme.surfaceAlt, border: `1px solid ${theme.border}`,
              color: theme.textMuted, letterSpacing: 0.3,
            }}>Optional</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: theme.textMuted }}>
              {showAdd ? '▲' : '▼'}
            </span>
          </button>

          {showAdd && (
            <div style={{
              padding: '16px 20px 20px',
              background: theme.surfaceAlt,
              borderTop: `1px solid ${theme.border}`,
            }}>
              <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 14, fontWeight: 500 }}>
                New departments are saved permanently and will appear in future sessions.
              </div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                {/* Division selector */}
                <div>
                  <label style={labelStyle}>Division</label>
                  <select
                    value={newDept.division}
                    onChange={e => setNewDept(p => ({ ...p, division: e.target.value }))}
                    style={inputStyle}
                  >
                    {DIVISIONS.map(d => <option key={d}>{d}</option>)}
                  </select>
                </div>

                {/* Name */}
                <div style={{ flex: 1, minWidth: 200 }}>
                  <label style={labelStyle}>Department Name</label>
                  <input
                    placeholder="e.g. KB_NEW CATEGORY"
                    value={newDept.name}
                    onChange={e => setNewDept(p => ({ ...p, name: e.target.value.toUpperCase() }))}
                    style={{ ...inputStyle, width: '100%' }}
                  />
                </div>

                {/* Attribute */}
                <div>
                  <label style={labelStyle}>Attribute</label>
                  <select
                    value={newDept.attribute}
                    onChange={e => setNewDept(p => ({ ...p, attribute: e.target.value }))}
                    style={inputStyle}
                  >
                    {Object.keys(ATTR_STYLE).map(a => <option key={a}>{a}</option>)}
                  </select>
                </div>

                <button onClick={handleAddDept} style={{
                  padding: '7px 20px', borderRadius: 6, cursor: 'pointer',
                  background: theme.primary, color: '#fff', border: 'none',
                  fontSize: 13, fontWeight: 600,
                }}>
                  Add
                </button>
              </div>
              {addError && (
                <div style={{ marginTop: 10, fontSize: 12, color: '#D94F3D' }}>{addError}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const thStyle = (align, minWidth) => ({
  padding: '9px 12px',
  textAlign: align,
  fontSize: 10.5,
  fontWeight: 600,
  color: theme.textMuted,
  letterSpacing: 0.5,
  borderBottom: `1px solid ${theme.border}`,
  whiteSpace: 'nowrap',
  minWidth,
  ...(align === 'left' && { paddingLeft: align === 'left' ? 20 : 12 }),
})

const labelStyle = {
  display: 'block', fontSize: 11, color: theme.textMuted,
  marginBottom: 4, fontWeight: 600, letterSpacing: 0.3,
}

const inputStyle = {
  padding: '7px 10px', borderRadius: 6, fontSize: 12,
  border: `1px solid ${theme.border}`, outline: 'none',
  color: theme.textPrimary, background: theme.surface,
}
