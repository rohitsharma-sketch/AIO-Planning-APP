import { useState, useEffect, useRef } from 'react'
import { theme } from '../theme'

const API = '/api/planning/deviation/sor'

const RULE_BADGE = {
  avg:       { label: 'AVG',       bg: '#0D9488', color: '#fff' },
  plan_only: { label: 'PLAN ONLY', bg: '#F59E0B', color: '#fff' },
  ppo_only:  { label: 'PPO ONLY',  bg: '#8B5CF6', color: '#fff' },
  zero:      { label: 'ZERO',      bg: '#6B7280', color: '#fff' },
}

const ATTR_COLOR = {
  SUMMER:     '#F97316',
  OCCASIONAL: '#8B5CF6',
  REGULAR:    '#0EA5E9',
}

const HDR  = { fontFamily: theme.fontMono, fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4, textAlign: 'right', padding: '6px 10px', whiteSpace: 'nowrap' }
const CELL = { fontFamily: theme.fontMono, fontSize: 12, textAlign: 'right', padding: '5px 10px', whiteSpace: 'nowrap' }

function RuleBadge({ rule }) {
  const b = RULE_BADGE[rule] || RULE_BADGE.zero
  return (
    <span style={{
      display: 'inline-block', fontSize: 9, fontWeight: 700, letterSpacing: 0.4,
      padding: '2px 6px', borderRadius: 4, background: b.bg, color: b.color,
    }}>{b.label}</span>
  )
}

function UploadBox({ label, subtitle, onFile, imported, importedDate, importedRows }) {
  const ref = useRef()
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState(null)

  async function upload(file) {
    setUploading(true); setErr(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch(`${API}/${label === 'Sales Plan Cont%' ? 'import/sales-plan' : 'import/stock-ppo'}`, { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Upload failed') }
      onFile()
    } catch (e) { setErr(e.message) }
    setUploading(false)
  }

  return (
    <div style={{
      border: `2px dashed ${dragging ? theme.accent : imported ? theme.success : theme.border}`,
      borderRadius: 12, padding: 24, background: imported ? `${theme.success}0a` : theme.surface,
      cursor: 'pointer', transition: 'border 0.2s', flex: 1,
    }}
      onClick={() => ref.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) upload(f) }}
    >
      <input ref={ref} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }}
        onChange={e => { const f = e.target.files[0]; if (f) upload(f) }} />

      <div style={{ fontSize: 22, marginBottom: 8 }}>{imported ? '✅' : '📂'}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 12 }}>{subtitle}</div>

      {uploading && <div style={{ fontSize: 12, color: theme.accent }}>Uploading…</div>}
      {err && <div style={{ fontSize: 12, color: theme.danger, marginTop: 6 }}>{err}</div>}
      {imported && !uploading && (
        <div style={{ fontSize: 11, color: theme.success, marginTop: 4 }}>
          ✓ {importedRows} rows imported · {importedDate}
        </div>
      )}
      {!imported && !uploading && (
        <div style={{ fontSize: 11, color: theme.textMuted }}>Drop file here or click to browse</div>
      )}
    </div>
  )
}

export default function SorDeviation() {
  const [status, setStatus]         = useState(null)
  const [running, setRunning]       = useState(false)
  const [reapping, setReapping]     = useState(false)
  const [viewMode, setViewMode]     = useState('avg')   // 'avg' | 'reapp'
  const [avgResult, setAvgResult]   = useState(null)
  const [reappResult, setReappResult] = useState(null)

  // filters
  const [selMonth, setSelMonth]     = useState(null)
  const [selAttr, setSelAttr]       = useState('ALL')
  const [selDept, setSelDept]       = useState('ALL')
  const [expandedRows, setExpandedRows] = useState(new Set())

  async function loadStatus() {
    const r = await fetch(`${API}/status`)
    const d = await r.json()
    setStatus(d)
    if (d.avg_run && !avgResult) {
      const r2 = await fetch(`${API}/avg-result`)
      const d2 = await r2.json()
      setAvgResult(d2)
      if (!selMonth && d2.months?.length) setSelMonth(d2.months[0])
    }
    if (d.reapp_run && !reappResult) {
      const r3 = await fetch(`${API}/reapp-result`)
      const d3 = await r3.json()
      setReappResult(d3)
    }
  }

  useEffect(() => { loadStatus() }, [])

  async function runAvg() {
    setRunning(true)
    const r = await fetch(`${API}/run-avg`)
    if (r.ok) {
      const d = await fetch(`${API}/avg-result`).then(x => x.json())
      setAvgResult(d)
      if (!selMonth && d.months?.length) setSelMonth(d.months[0])
    }
    setRunning(false)
    loadStatus()
  }

  async function runReapp() {
    setReapping(true)
    const r = await fetch(`${API}/reapportion`)
    if (r.ok) {
      const d = await fetch(`${API}/reapp-result`).then(x => x.json())
      setReappResult(d)
      setViewMode('reapp')
    }
    setReapping(false)
    loadStatus()
  }

  // derive display data
  const activeData = viewMode === 'reapp' ? reappResult : avgResult
  const months  = activeData?.months || []
  const curMonth = selMonth || months[0]

  const allRows = activeData?.rows || []
  const attrs   = ['ALL', ...new Set(allRows.map(r => r.attr).filter(Boolean).map(a => a.toUpperCase()))]
  // Same field, normalized the same way everywhere it's compared/keyed below —
  // a blank/missing dept would otherwise collide with every other blank-dept
  // row under one bucket (JS object keys coerce undefined/'' to equal strings).
  const deptKey = r => r.dept || '—'
  const depts   = ['ALL', ...new Set(allRows.map(deptKey))]

  const filtered = allRows.filter(r => {
    if (selAttr !== 'ALL' && r.attr?.toUpperCase() !== selAttr) return false
    if (selDept !== 'ALL' && deptKey(r) !== selDept) return false
    return true
  })

  // group by dept for display
  const byDept = {}
  filtered.forEach(r => {
    const k = deptKey(r)
    if (!byDept[k]) byDept[k] = []
    byDept[k].push(r)
  })

  // dept-level totals for current month
  function deptTotal(rows, month) {
    return rows.reduce((s, r) => {
      const md = r.months[month] || {}
      return s + (md.avg_cont || 0)
    }, 0)
  }
  function deptReappCheck(rows, month) {
    return rows.reduce((s, r) => {
      const md = r.months[month] || {}
      return s + (md.reapp_cont || 0)
    }, 0)
  }

  const canRunAvg   = status?.plan_imported && status?.ppo_imported && !running
  const canReapp    = status?.avg_run && !reapping

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.bg }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary, margin: 0 }}>SOR Deviation</h1>
        <p style={{ fontSize: 13, color: theme.textMuted, margin: '6px 0 0 0' }}>
          Summer · Occasional · Regular — Sales Plan × Stock PPO averaging &amp; reapportionment
        </p>
      </div>

      {/* Upload row */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        <UploadBox
          label="Sales Plan Cont%"
          subtitle="Wide format: ATTRIBUTE-1 | DEPT | ARTICLE NAME | FINAL MRP | Month cols"
          onFile={loadStatus}
          imported={status?.plan_imported}
          importedDate={status?.plan_date}
          importedRows={status?.plan_rows}
        />
        <UploadBox
          label="Stock PPO Cont%"
          subtitle="Same template as Sales Plan — month columns are cont%"
          onFile={loadStatus}
          imported={status?.ppo_imported}
          importedDate={status?.ppo_date}
          importedRows={status?.ppo_rows}
        />
      </div>

      {/* Run buttons */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 28, alignItems: 'center' }}>
        <button
          onClick={runAvg}
          disabled={!canRunAvg}
          style={{
            padding: '10px 24px', borderRadius: 8, border: 'none', cursor: canRunAvg ? 'pointer' : 'not-allowed',
            background: canRunAvg ? theme.primary : theme.surfaceAlt,
            color: canRunAvg ? '#fff' : theme.textMuted, fontWeight: 700, fontSize: 13,
          }}
        >
          {running ? 'Computing…' : status?.avg_run ? '↻ Re-run Average' : '▶ Run Average'}
        </button>

        {status?.avg_run && (
          <button
            onClick={runReapp}
            disabled={!canReapp}
            style={{
              padding: '10px 24px', borderRadius: 8, border: 'none', cursor: canReapp ? 'pointer' : 'not-allowed',
              background: canReapp ? '#0D9488' : theme.surfaceAlt,
              color: canReapp ? '#fff' : theme.textMuted, fontWeight: 700, fontSize: 13,
            }}
          >
            {reapping ? 'Reapportioning…' : status?.reapp_run ? '↻ Re-reapportion' : '⇄ Reapportion'}
          </button>
        )}

        {status?.reapp_run && (
          <a
            href={`${API}/export`}
            style={{
              padding: '10px 20px', borderRadius: 8, textDecoration: 'none', fontWeight: 700, fontSize: 13,
              background: '#0EA5E9', color: '#fff', display: 'inline-block',
            }}
          >↓ Export Excel</a>
        )}

        <div style={{ marginLeft: 'auto', fontSize: 11, color: theme.textMuted }}>
          {status?.avg_run && <span>Avg: {status.avg_date}</span>}
          {status?.reapp_run && <span style={{ marginLeft: 12 }}>Reapp: {status.reapp_date}</span>}
        </div>
      </div>

      {/* Results */}
      {activeData && (
        <>
          {/* View toggle */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 18, alignItems: 'center' }}>
            {[['avg','Average View'], ['reapp','Reapportioned View']].map(([k, lbl]) => (
              <button key={k} onClick={() => setViewMode(k)}
                disabled={k === 'reapp' && !reappResult}
                style={{
                  padding: '7px 18px', borderRadius: 8, border: `1.5px solid ${viewMode === k ? theme.primary : theme.border}`,
                  background: viewMode === k ? `${theme.primary}22` : theme.surface,
                  color: viewMode === k ? theme.primaryLight : theme.textSecondary,
                  fontWeight: viewMode === k ? 700 : 400, fontSize: 12, cursor: 'pointer',
                }}>{lbl}</button>
            ))}
          </div>

          {/* Filters row */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            {/* Attribute pills */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600 }}>ATTRIBUTE</span>
              {attrs.map(a => {
                const c = ATTR_COLOR[a] || theme.accent
                const active = selAttr === a
                return (
                  <button key={a} onClick={() => setSelAttr(a)} style={{
                    padding: '4px 12px', borderRadius: 6, fontSize: 11, fontWeight: active ? 700 : 400,
                    border: `1.5px solid ${active ? c : theme.border}`,
                    background: active ? `${c}22` : theme.surface,
                    color: active ? c : theme.textSecondary, cursor: 'pointer',
                  }}>{a}</button>
                )
              })}
            </div>

            {/* Dept dropdown */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 12 }}>
              <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600 }}>DEPT</span>
              <select value={selDept} onChange={e => setSelDept(e.target.value)} style={{
                background: theme.surface, color: theme.textPrimary, border: `1px solid ${theme.border}`,
                borderRadius: 6, padding: '4px 10px', fontSize: 12,
              }}>
                {depts.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          </div>

          {/* Month tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
            {months.map(m => (
              <button key={m} onClick={() => setSelMonth(m)} style={{
                padding: '5px 14px', borderRadius: 7, fontSize: 11, fontWeight: curMonth === m ? 700 : 400,
                border: `1.5px solid ${curMonth === m ? theme.primary : theme.border}`,
                background: curMonth === m ? `${theme.primary}22` : theme.surface,
                color: curMonth === m ? theme.primaryLight : theme.textSecondary, cursor: 'pointer',
              }}>{m}</button>
            ))}
          </div>

          {/* Table grouped by dept */}
          {Object.entries(byDept).map(([dept, rows]) => {
            const isExpanded = expandedRows.has(dept)
            const total = deptTotal(rows, curMonth)
            const reappSum = viewMode === 'reapp' ? deptReappCheck(rows, curMonth) : null

            return (
              <div key={dept} style={{ marginBottom: 12, background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
                {/* Dept header row */}
                <div
                  onClick={() => setExpandedRows(prev => {
                    const n = new Set(prev)
                    n.has(dept) ? n.delete(dept) : n.add(dept)
                    return n
                  })}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 16px', cursor: 'pointer',
                    background: isExpanded ? `${theme.primary}12` : theme.surfaceAlt,
                    borderBottom: isExpanded ? `1px solid ${theme.border}` : 'none',
                  }}
                >
                  <span style={{ fontSize: 11, color: theme.textMuted }}>{isExpanded ? '▾' : '▸'}</span>
                  <span style={{ fontWeight: 700, fontSize: 13, color: theme.textPrimary, flex: 1 }}>{dept}</span>
                  <span style={{ fontSize: 11, color: theme.textMuted }}>{rows.length} articles</span>
                  <span style={{ fontFamily: theme.fontMono, fontSize: 12, color: theme.accent, minWidth: 80, textAlign: 'right' }}>
                    Avg total: {total.toFixed(2)}%
                  </span>
                  {reappSum !== null && (
                    <span style={{ fontFamily: theme.fontMono, fontSize: 12, color: '#0D9488', minWidth: 90, textAlign: 'right' }}>
                      Reapp Σ: {reappSum.toFixed(1)}%
                    </span>
                  )}
                </div>

                {/* Article rows */}
                {isExpanded && (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                          <th style={{ ...HDR, textAlign: 'left', paddingLeft: 16 }}>Attribute</th>
                          <th style={{ ...HDR, textAlign: 'left' }}>Article</th>
                          <th style={{ ...HDR }}>MRP</th>
                          <th style={{ ...HDR }}>Plan %</th>
                          <th style={{ ...HDR }}>PPO %</th>
                          <th style={{ ...HDR }}>Avg %</th>
                          {viewMode === 'reapp' && <th style={{ ...HDR, color: '#0D9488' }}>Reapp %</th>}
                          <th style={{ ...HDR, textAlign: 'center' }}>Rule</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => {
                          const md = row.months[curMonth] || {}
                          const ac = ATTR_COLOR[row.attr?.toUpperCase()] || theme.accent
                          return (
                            <tr key={`${row.article}-${row.mrp}`} style={{
                              borderBottom: `1px solid ${theme.border}`,
                              background: i % 2 === 0 ? 'transparent' : theme.surfaceAlt,
                            }}>
                              <td style={{ ...CELL, textAlign: 'left', paddingLeft: 16 }}>
                                <span style={{ fontSize: 10, fontWeight: 700, color: ac, background: `${ac}18`, padding: '2px 7px', borderRadius: 5 }}>
                                  {row.attr || '—'}
                                </span>
                              </td>
                              <td style={{ ...CELL, textAlign: 'left', color: theme.textPrimary, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.article}</td>
                              <td style={{ ...CELL, color: theme.textMuted }}>₹{row.mrp}</td>
                              <td style={{ ...CELL }}>{md.plan_cont?.toFixed(2) ?? '—'}</td>
                              <td style={{ ...CELL }}>{md.ppo_cont?.toFixed(2) ?? '—'}</td>
                              <td style={{ ...CELL, fontWeight: 700, color: theme.textPrimary }}>{md.avg_cont?.toFixed(4) ?? '—'}</td>
                              {viewMode === 'reapp' && (
                                <td style={{ ...CELL, fontWeight: 700, color: '#0D9488' }}>{md.reapp_cont?.toFixed(4) ?? '—'}</td>
                              )}
                              <td style={{ ...CELL, textAlign: 'center' }}><RuleBadge rule={md.rule} /></td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}

          {Object.keys(byDept).length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: theme.textMuted, fontSize: 13 }}>
              No data for this filter.
            </div>
          )}
        </>
      )}

      {!activeData && !running && (
        <div style={{ textAlign: 'center', padding: 60, color: theme.textMuted, fontSize: 13 }}>
          {status?.plan_imported && status?.ppo_imported
            ? 'Both files imported — click "Run Average" to compute.'
            : 'Import both files above to get started.'}
        </div>
      )}
    </div>
  )
}
