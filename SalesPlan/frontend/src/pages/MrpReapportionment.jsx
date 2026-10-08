import { useState, useEffect, useCallback, useMemo } from 'react'
import { theme, alpha } from '../theme'

const mono = { fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }

// ── Small helpers ──────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }) {
  return (
    <div style={{
      background: theme.surface, border: `1px solid ${color ? color + '44' : theme.border}`,
      borderRadius: 10, padding: '14px 18px', flex: 1, minWidth: 120,
    }}>
      <div style={{ fontSize: 10, color: theme.textMuted, fontWeight: 600, letterSpacing: 0.4, marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color || theme.textPrimary, ...mono }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

// ── Group row: where each discontinued MRP goes (the master's rule, read-only since 2026-10-08) ────────────

function Target({ below, above }) {
  if (!below && !above) return <span style={{ color: '#B45309' }}>unmapped</span>
  if (!below || !above) return <span>₹{below || above} <span style={{ color: theme.textMuted }}>100%</span></span>
  return <span>₹{below} <span style={{ color: theme.textMuted }}>↓</span> · ₹{above} <span style={{ color: theme.textMuted }}>↑</span></span>
}

function GroupRow({ group }) {
  const { dept, display, listed, disc, disc_rows_in_sales } = group

  if (!disc.length) return null

  return (
    <div style={{
      border: `1px solid ${theme.border}`, borderRadius: 9,
      background: theme.surfaceAlt, overflow: 'hidden',
      flexShrink: 0,   // in the 520px scrolling list, 284 cards were squeezed to bare borders (2026-10-08)
    }}>
      {/* Group header */}
      <div style={{
        padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 10,
        background: theme.surface, borderBottom: `1px solid ${theme.border}`,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: theme.textPrimary }}>
            {dept}
            <span style={{ color: theme.textMuted, margin: '0 6px' }}>·</span>
            <span style={{ color: theme.textMuted }}>{display}</span>
          </div>
          <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2 }}>
            {disc.length} discontinued · {listed.length} listed MRP{listed.length !== 1 ? 's' : ''}
            {disc_rows_in_sales > 0 && ` · ${disc_rows_in_sales} rows in sales`}
            {!listed.length && <span style={{ color: '#B45309' }}> · nothing listed - sales go to Unmapped</span>}
          </div>
        </div>
      </div>

      {/* Discontinued MRPs -> nearest listed below / above */}
      <div style={{ padding: '8px 16px 6px', borderBottom: `1px solid ${alpha(theme.border,'22')}` }}>
        <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 4, fontWeight: 600, letterSpacing: 0.3 }}>
          DISCONTINUED → NEAREST LISTED
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {disc.map(d => (
            <span key={d.mrp} style={{
              padding: '2px 8px', borderRadius: 4, fontSize: 11, ...mono,
              background: `${alpha(theme.danger,'0d')}`, border: `1px solid ${alpha(theme.danger,'30')}`,
            }}><span style={{ color: theme.danger }}>₹{d.mrp}</span> → <Target below={d.below} above={d.above} /></span>
          ))}
        </div>
      </div>

      {/* Listed MRPs (old -> new) */}
      {listed.length > 0 && (
        <div style={{ padding: '8px 16px 10px' }}>
          <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 4, fontWeight: 600, letterSpacing: 0.3 }}>
            LISTED
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {listed.map(l => (
              <span key={l.mrp} style={{
                padding: '2px 8px', borderRadius: 4, fontSize: 11, ...mono, color: theme.accent,
                background: `${alpha(theme.accent,'0d')}`, border: `1px solid ${alpha(theme.accent,'30')}`,
              }}>₹{l.mrp}{l.listed !== l.mrp && ` → ₹${l.listed}`}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Preview table ──────────────────────────────────────────────────────────────

function PreviewTable({ rows, monthCols }) {
  if (!rows || rows.length === 0) return null
  const allCols = Object.keys(rows[0])
  const numCols = new Set(allCols.filter(c => typeof rows[0][c] === 'number'))

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
        <thead>
          <tr style={{ background: theme.surfaceUp }}>
            {allCols.map(c => (
              <th key={c} style={{
                padding: '7px 10px', textAlign: numCols.has(c) ? 'right' : 'left',
                color: theme.textMuted, fontWeight: 600, fontSize: 10,
                textTransform: 'uppercase', borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap',
              }}>
                {c.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{
              background: ri % 2 === 0 ? 'transparent' : 'rgba(var(--st-ink-rgb,30,39,35),0.025)',
              borderBottom: `1px solid ${theme.border}`,
            }}>
              {allCols.map(c => (
                <td key={c} style={{
                  padding: '5px 10px',
                  textAlign: numCols.has(c) ? 'right' : 'left',
                  color: c === 'LISTED_MRP'    ? theme.accent
                       : c === 'MRP_CURRENT'   ? theme.danger
                       : (monthCols || []).includes(c) ? theme.primary
                       : theme.textPrimary,
                  fontFamily: numCols.has(c) ? "'JetBrains Mono', monospace" : 'inherit',
                  fontSize: 11, whiteSpace: 'nowrap',
                }}>
                  {typeof row[c] === 'number'
                    ? row[c].toLocaleString('en-IN', { maximumFractionDigits: 2 })
                    : row[c]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Log viewer ─────────────────────────────────────────────────────────────────

function LogPanel({ lines }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? lines : lines.slice(0, 8)
  return (
    <div style={{
      background: theme.surfaceAlt, borderRadius: 8, border: `1px solid ${theme.border}`,
      padding: '10px 14px', ...mono,
    }}>
      {visible.map((l, i) => (
        <div key={i} style={{
          color: l.includes('FAIL') || l.includes('ERROR') ? theme.danger
               : l.includes('PASS') ? theme.accent
               : l.includes('WARN') ? '#B45309'
               : theme.textMuted,
          lineHeight: 1.7,
        }}>{l || ' '}</div>
      ))}
      {lines.length > 8 && (
        <button onClick={() => setExpanded(e => !e)} style={{
          marginTop: 6, background: 'none', border: 'none', color: theme.primary, cursor: 'pointer', fontSize: 11,
        }}>
          {expanded ? '▲ Show less' : `▼ +${lines.length - 8} more lines`}
        </button>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function MrpReapportionment() {
  const [status, setStatus]       = useState(null)
  const [salesInfo, setSalesInfo] = useState(null)
  const [groups, setGroups]       = useState(null)
  const [groupsErr, setGroupsErr] = useState('')
  const [activeTab, setActiveTab] = useState('groups')
  const [filter, setFilter]       = useState('')

  const [running, setRunning]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState('')
  const [resultTab, setResultTab] = useState('preview')
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState(null)   // {ok, text}
  // admin-switchable right (Users & access): null = not known yet, Landing refuses the upload either way
  const [canImport, setCanImport] = useState(null)
  useEffect(() => {
    fetch('/api/auth/rights', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setCanImport(d.rights.includes('mrp_master')) })
      .catch(() => {})
  }, [])

  // a new version of the MRP master: checked by the server before it goes live; the old one moves to Archive (2026-10-08)
  const importMaster = async (file) => {
    if (!file) return
    if (status?.mapping_file_found && !window.confirm(`Make "${file.name}" the MRP master? The current one (${status.mapping_file}) moves to MRP Mapping\\Archive.`)) return
    setImporting(true); setImportMsg(null)
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await fetch('/api/planning/mrp-reapportionment/mapping/upload', { method: 'POST', body: fd })
      const d = await r.json()
      if (!r.ok) { setImportMsg({ ok: false, text: d.detail || 'Import failed' }); return }
      const c = d.changes
      setImportMsg({ ok: true, text: `${d.file}: ${d.rows.toLocaleString('en-IN')} old MRPs in ${d.groups} Dept · Display (${d.listed} listed, ${d.discontinued} discontinued`
        + `${d.no_listed_groups ? `, ${d.no_listed_groups} with nothing listed` : ''}). vs previous: ${c.added} added, ${c.removed} removed, ${c.changed} changed.` })
      setGroups(null); setResult(null)
      reload()
    } catch (e) { setImportMsg({ ok: false, text: String(e) }) }
    finally { setImporting(false) }
  }

  const reload = useCallback(() => {
    fetch('/api/planning/mrp-reapportionment/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStatus(d) })
    fetch('/api/planning/mrp-reapportionment/sales-status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSalesInfo(d) })
  }, [])

  const loadGroups = useCallback(() => {
    setGroupsErr('')
    fetch('/api/planning/mrp-reapportionment/mrp-groups')
      .then(r => r.json())
      .then(d => {
        if (d.detail) { setGroupsErr(d.detail); return }
        setGroups(d)
      })
      .catch(e => setGroupsErr(String(e)))
  }, [])

  useEffect(() => { reload() }, [reload])

  const handleRun = async () => {
    setRunning(true); setError(''); setResult(null)
    try {
      const body = {}   // the split comes from the master's rule
      const r = await fetch('/api/planning/mrp-reapportionment/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) { setError(d.detail || 'Engine error'); return }
      setResult(d); setResultTab('preview'); setActiveTab('results')
      reload()
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  const filteredGroups = useMemo(() => {
    if (!groups?.groups) return []
    if (!filter.trim()) return groups.groups
    const q = filter.trim().toUpperCase()
    return groups.groups.filter(g =>
      g.dept.includes(q) || g.display.includes(q)
    )
  }, [groups, filter])

  const salesOk = !!(salesInfo?.file_found && salesInfo.check?.pass)
  const canRun = salesOk && status?.mapping_file_found && !running
  const lastRun = status?.last_run

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      {/* Heading */}
      <div className="sp-sub" style={{ marginBottom: 8 }}>
        Moves LY sales onto the new MRP structure: a discontinued MRP goes to the nearest listed MRP below and above (40/60, Summer 60/40).
      </div>

      {/* Info panel (was a right-hand column) - collapsed by default so the main panel gets the full width */}
      <details className="sp-fold" style={{ marginBottom: 16 }}>
        <summary>ⓘ How it works · where the file goes · constraints</summary>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14, marginTop: 8, alignItems: 'start' }}>

          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '18px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 12 }}>
              MRP MASTER · IMPORT A NEW VERSION (OLD ONES MOVE TO ARCHIVE)
            </div>
            {[
              { label: 'MRP Mapping Master (.xlsx)',   path: 'Sales Reapportionment\\MRP Mapping\\' },
            ].map(({ label, path }) => (
              <div key={label} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: theme.textPrimary, marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 10, color: theme.textMuted, ...mono }}>…{path}</div>
              </div>
            ))}
          </div>

          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '18px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 12 }}>
              HOW IT WORKS
            </div>
            {[
              { icon: '📂', t: '1. Load groups',  b: 'The MRP master (sheet "MRP Adj") lists every old MRP per Department · Display and its new MRP (0 = discontinued).' },
              { icon: '⚙',  t: '2. Rule',          b: 'Listed MRPs move to their new MRP. A discontinued MRP splits to the nearest listed MRP below / above: 40% / 60% (Regular, Occasional, Winter), 60% / 40% (Summer); only one side listed → 100% there.' },
              { icon: '▶',  t: '3. Run',           b: 'Applied to LY Mar–Jun 2026 sales from the sales engine, store by store, month by month.' },
              { icon: '✓',  t: '4. Validate',      b: 'Store × Dept totals before = after + Unmapped, to 8 decimals. A Department · Display with nothing listed goes to Unmapped.' },
            ].map(({ icon, t, b }) => (
              <div key={t} style={{ display: 'flex', gap: 10, marginBottom: 12, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>{icon}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: theme.textPrimary, marginBottom: 2 }}>{t}</div>
                  <div style={{ fontSize: 11, color: theme.textMuted, lineHeight: 1.6 }}>{b}</div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '18px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 10 }}>
              CONSTRAINTS
            </div>
            {[
              'Sales never cross Stores',
              'Sales never cross Departments',
              'Sales never cross Display types',
              'Sales never cross Attributes',
              'All month totals preserved exactly',
              'Nothing listed in Dept · Display → Unmapped',
            ].map(c => (
              <div key={c} style={{ display: 'flex', gap: 7, marginBottom: 6, fontSize: 11, color: theme.textMuted }}>
                <span style={{ color: theme.accent, flexShrink: 0 }}>✓</span>
                <span>{c}</span>
              </div>
            ))}
          </div>
        </div>
      </details>

      {/* Last-run banner */}
      {lastRun && !result && (
        <div style={{
          marginBottom: 18, padding: '10px 18px', borderRadius: 10,
          background: lastRun.val_pass ? `${alpha(theme.accent,'10')}` : `${alpha(theme.danger,'10')}`,
          border: `1px solid ${alpha(lastRun.val_pass ? theme.accent : theme.danger,'33')}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
        }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: lastRun.val_pass ? theme.accent : theme.danger }}>
              {lastRun.val_pass ? '✓' : '⚠'} Last run: {new Date(lastRun.run_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
            </div>
            <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>
              {lastRun.input_rows?.toLocaleString()} in → {lastRun.output_rows?.toLocaleString()} out
              &ensp;·&ensp;{lastRun.stores} stores, {lastRun.departments} depts
              &ensp;·&ensp;Validation: <strong style={{ color: lastRun.val_pass ? theme.accent : theme.danger }}>
                {lastRun.val_pass ? 'PASSED' : 'FAILED'}
              </strong>
            </div>
          </div>
          <a href="/api/planning/mrp-reapportionment/download" style={{
            padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
            background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)', textDecoration: 'none', flexShrink: 0,
          }}>↓ Download</a>
        </div>
      )}

      {/* Two-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 18, alignItems: 'start' }}>

        {/* ── Left ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* File status */}
          <div style={{
            background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`,
            padding: '18px 22px',
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 12 }}>
              INPUT FILES
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
              <div style={{
                padding: '12px 14px', borderRadius: 8,
                background: salesOk ? `${alpha(theme.accent,'0d')}` : `${alpha(salesInfo ? theme.danger : theme.border,'0d')}`,
                border: `1px solid ${alpha(salesOk ? theme.accent : salesInfo ? theme.danger : theme.border,'33')}`,
              }}>
                {/* LY actual sales come from the suite's sales engine, never an upload (user, 2026-09-29) */}
                <div style={{ fontSize: 11, fontWeight: 700, color: salesOk ? theme.accent : salesInfo ? theme.danger : theme.textMuted, marginBottom: 3 }}>
                  {!salesInfo ? '⟳' : salesOk ? '✓' : '✗'} LY Actual Sales · sales engine
                </div>
                {!salesInfo && <div style={{ fontSize: 11, color: theme.textMuted }}>Reading Mar–Jun 2026 from the data lake…</div>}
                {salesInfo?.file_found && <>
                  <div style={{ fontSize: 11, color: theme.textPrimary }}>
                    {salesInfo.months?.join(' · ')} · ₹{(salesInfo.check?.total_lakh ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L
                  </div>
                  <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2 }}>
                    {salesOk
                      ? `Ties to the Calendar department sales: ${salesInfo.check.cells.toLocaleString('en-IN')} store × dept × month cells, max diff ${salesInfo.check.max_diff_lakh} L`
                      : `Does NOT tie to the Calendar department sales (max diff ${salesInfo.check?.max_diff_lakh} L) — run blocked`}
                  </div>
                  <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2, wordBreak: 'break-all', ...mono }}>{salesInfo.filename} · {salesInfo.modified}</div>
                </>}
                {salesInfo && !salesInfo.file_found && <div style={{ fontSize: 11, color: theme.danger }}>{salesInfo.error}</div>}
              </div>
              <div style={{
                padding: '12px 14px', borderRadius: 8,
                background: status?.mapping_file_found ? `${alpha(theme.accent,'0d')}` : `${alpha(theme.danger,'0d')}`,
                border: `1px solid ${alpha(status?.mapping_file_found ? theme.accent : theme.danger,'33')}`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: status?.mapping_file_found ? theme.accent : theme.danger, marginBottom: 3 }}>
                  {status?.mapping_file_found ? '✓' : '✗'} MRP Mapping Master
                </div>
                {status?.mapping_file_found
                  ? <div style={{ fontSize: 11, color: theme.textPrimary, ...mono }}>{status.mapping_file}</div>
                  : <div style={{ fontSize: 11, color: theme.textMuted }}>No master yet - import one</div>
                }
                <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                  <label title={canImport === false ? 'An admin has switched off your access to: Import a new MRP master' : undefined} style={{
                    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                    cursor: canImport === false ? 'not-allowed' : importing ? 'wait' : 'pointer', opacity: canImport === false ? 0.5 : 1,
                    background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)',
                  }}>
                    {importing ? '⟳ Checking…' : '⇪ Import new version'}
                    <input type="file" accept=".xlsx" hidden disabled={importing || canImport === false}
                      onChange={e => { importMaster(e.target.files[0]); e.target.value = '' }} />
                  </label>
                  {status?.mapping_file_found && (
                    <a href="/api/planning/mrp-reapportionment/mapping/download" style={{
                      padding: '4px 10px', borderRadius: 6, fontSize: 11, textDecoration: 'none',
                      border: `1px solid ${theme.border}`, color: theme.textMuted,
                    }}>↓ Export current</a>
                  )}
                </div>
              </div>
            </div>
            {importMsg && (
              <div style={{
                marginBottom: 10, padding: '8px 12px', borderRadius: 8, fontSize: 11,
                background: alpha(importMsg.ok ? theme.accent : theme.danger, '10'),
                border: `1px solid ${alpha(importMsg.ok ? theme.accent : theme.danger, '33')}`,
                color: importMsg.ok ? theme.textPrimary : theme.danger,
              }}>{importMsg.ok ? '✓ ' : '✗ '}{importMsg.text}</div>
            )}
            <button onClick={reload} style={{
              padding: '5px 12px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
              background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textMuted,
            }}>↺ Refresh</button>
          </div>

          {/* Groups editor + results tabs */}
          <div style={{
            background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden',
          }}>
            <div style={{
              padding: '0 22px', borderBottom: `1px solid ${theme.border}`,
              background: theme.surfaceAlt, display: 'flex', alignItems: 'center',
            }}>
              {['groups', ...(result ? ['results'] : [])].map(tab => (
                <button key={tab} onClick={() => setActiveTab(tab)} style={{
                  padding: '12px 16px', fontSize: 12, fontWeight: activeTab === tab ? 700 : 400,
                  color: activeTab === tab ? theme.primary : theme.textMuted,
                  background: 'none', border: 'none', cursor: 'pointer',
                  borderBottom: activeTab === tab ? `2px solid ${theme.primary}` : '2px solid transparent',
                }}>
                  {tab === 'groups' && `MRP Groups${groups ? ` (${groups.total_groups})` : ''}`}
                  {tab === 'results' && 'Run Results'}
                </button>
              ))}
              <div style={{ flex: 1 }} />
              <button onClick={loadGroups} style={{
                padding: '7px 14px', borderRadius: 7, fontSize: 11, cursor: 'pointer',
                background: 'var(--st-btn,#A8CBB7)', border: 'none', color: 'var(--st-btn-text,#1F4D3A)', fontWeight: 600,
              }}>
                ↻ Load Groups
              </button>
            </div>

            {/* Groups tab */}
            {activeTab === 'groups' && (
              <div style={{ padding: '18px 22px' }}>
                {!groups && !groupsErr && (
                  <div style={{ padding: '32px 0', textAlign: 'center', color: theme.textMuted, fontSize: 13 }}>
                    Click <strong style={{ color: theme.primary }}>Load Groups</strong> to load MRP groups from the mapping master.
                    <div style={{ fontSize: 11, marginTop: 6 }}>
                      Each group shows where every discontinued MRP's sales go.
                    </div>
                  </div>
                )}
                {groupsErr && (
                  <div style={{
                    padding: '10px 14px', borderRadius: 8, fontSize: 12,
                    background: `${alpha(theme.danger,'12')}`, border: `1px solid ${alpha(theme.danger,'44')}`, color: theme.danger,
                  }}>✗ {groupsErr}</div>
                )}
                {groups && (
                  <>
                    <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center' }}>
                      <input
                        placeholder="Filter by dept / display…"
                        value={filter}
                        onChange={e => setFilter(e.target.value)}
                        style={{
                          flex: 1, padding: '7px 12px', borderRadius: 7,
                          background: theme.surfaceAlt, border: `1px solid ${theme.border}`,
                          color: theme.textPrimary, fontSize: 12, outline: 'none',
                        }}
                      />
                      <div style={{ fontSize: 11, color: theme.textMuted, whiteSpace: 'nowrap' }}>
                        {filteredGroups.length}/{groups.total_groups}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 520, overflowY: 'auto' }}>
                      {filteredGroups.map(g => (
                        <GroupRow key={g.group_key} group={g} />
                      ))}
                      {filteredGroups.length === 0 && filter && (
                        <div style={{ textAlign: 'center', color: theme.textMuted, fontSize: 12, padding: 20 }}>
                          No groups match "{filter}"
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Results tab */}
            {activeTab === 'results' && result && (
              <div>
                <div style={{ padding: '16px 22px', borderBottom: `1px solid ${theme.border}` }}>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <StatCard label="INPUT ROWS" value={result.input_rows?.toLocaleString()} />
                    <StatCard label="OUTPUT ROWS" value={result.output_rows?.toLocaleString()} color={theme.primary} />
                    <StatCard label="UNMAPPED" value={result.unmapped} color={result.unmapped > 0 ? '#B45309' : theme.textMuted}
                      sub={result.total_unmapped ? '₹' + (result.total_unmapped/100000).toFixed(2) + 'L' : undefined} />
                    <StatCard label="TOTAL BEFORE" value={'₹' + (result.total_before/100000).toFixed(1) + 'L'}
                      sub={result.total_before.toLocaleString('en-IN', { maximumFractionDigits: 0 })} />
                    <StatCard label="TOTAL AFTER" value={'₹' + (result.total_after/100000).toFixed(1) + 'L'}
                      sub={`diff: ${result.diff?.toFixed(6)}`} color={result.diff < 0.01 ? theme.accent : theme.danger} />
                    <StatCard label="VALIDATION" value={result.val_pass ? 'PASSED' : 'FAILED'}
                      color={result.val_pass ? theme.accent : theme.danger} />
                  </div>
                </div>
                <div style={{ padding: '0 22px', borderBottom: `1px solid ${theme.border}`, display: 'flex' }}>
                  {['preview', 'log'].map(t => (
                    <button key={t} onClick={() => setResultTab(t)} style={{
                      padding: '9px 16px', fontSize: 12, fontWeight: resultTab === t ? 700 : 400,
                      color: resultTab === t ? theme.primary : theme.textMuted,
                      background: 'none', border: 'none', cursor: 'pointer',
                      borderBottom: resultTab === t ? `2px solid ${theme.primary}` : '2px solid transparent',
                    }}>
                      {t === 'preview' ? `Preview (${result.preview?.length})` : 'Engine Log'}
                    </button>
                  ))}
                  <div style={{ flex: 1 }} />
                  <a href="/api/planning/mrp-reapportionment/download" style={{
                    display: 'flex', alignItems: 'center', padding: '6px 14px', borderRadius: 7,
                    fontSize: 12, fontWeight: 700, background: 'var(--st-btn,#A8CBB7)', color: 'var(--st-btn-text,#1F4D3A)',
                    textDecoration: 'none', margin: '8px 0',
                  }}>↓ Download Excel</a>
                </div>
                <div style={{ padding: '0 0 8px 0' }}>
                  {resultTab === 'preview' && (
                    <>
                      <PreviewTable rows={result.preview} monthCols={result.month_cols} />
                      {result.output_rows > 50 && (
                        <div style={{ padding: '8px 22px', fontSize: 11, color: theme.textMuted }}>
                          Showing first 50 of {result.output_rows?.toLocaleString()} rows.
                        </div>
                      )}
                    </>
                  )}
                  {resultTab === 'log' && (
                    <div style={{ padding: '12px 22px' }}>
                      <LogPanel lines={result.log || []} />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Run button */}
          <div style={{
            background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '18px 22px',
          }}>
            <div style={{ marginBottom: 10, fontSize: 12, color: theme.textMuted }}>
              Discontinued MRPs → nearest listed MRP below / above · 40 / 60 (Summer 60 / 40) · one side → 100%
            </div>
            <button
              onClick={handleRun}
              disabled={!canRun}
              style={{
                width: '100%', padding: '13px 0', borderRadius: 9,
                fontSize: 14, fontWeight: 700, letterSpacing: 0.3,
                cursor: canRun ? 'pointer' : 'not-allowed',
                background: canRun ? 'var(--st-btn,#A8CBB7)' : theme.surfaceUp,
                color: canRun ? 'var(--st-btn-text,#1F4D3A)' : theme.textMuted, border: canRun ? 'none' : `1px solid ${theme.border}`,
              }}
            >
              {running ? '⟳  Running engine…' : '▶  Run Re-apportionment'}
            </button>
            {error && (
              <div style={{
                marginTop: 10, padding: '10px 14px', borderRadius: 8, fontSize: 12,
                background: `${alpha(theme.danger,'12')}`, border: `1px solid ${alpha(theme.danger,'44')}`, color: theme.danger,
              }}>✗ {error}</div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
