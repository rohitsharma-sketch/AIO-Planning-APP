import { useState, useEffect, useCallback, useMemo } from 'react'
import { theme } from '../theme'

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

// ── Contribution % editor row ─────────────────────────────────────────────────

function GroupRow({ group, overrides, onChange }) {
  const { dept, display, attr, valid_mrps, disc_mrps, disc_rows_in_sales, default_pcts, group_key } = group

  const initPcts = overrides
    ? overrides.map(s => s.pct)
    : (default_pcts.length ? default_pcts : valid_mrps.map(() => parseFloat((100 / valid_mrps.length).toFixed(4))))

  const [pcts, setPcts] = useState(initPcts)

  const total = pcts.reduce((a, b) => a + (parseFloat(b) || 0), 0)
  const balanced = Math.abs(total - 100) < 0.05

  const update = (idx, val) => {
    const next = [...pcts]
    next[idx] = val
    setPcts(next)
    onChange(group_key, valid_mrps.map((mrp, i) => ({ mrp, pct: parseFloat(next[i]) || 0 })))
  }

  const autoBalance = () => {
    const eq = default_pcts.length ? default_pcts : valid_mrps.map(() => parseFloat((100 / valid_mrps.length).toFixed(4)))
    setPcts(eq)
    onChange(group_key, valid_mrps.map((mrp, i) => ({ mrp, pct: eq[i] })))
  }

  if (!disc_mrps.length) return null

  return (
    <div style={{
      border: `1px solid ${theme.border}`, borderRadius: 9,
      background: theme.surfaceAlt, overflow: 'hidden',
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
            <span style={{ color: theme.textMuted, margin: '0 6px' }}>·</span>
            <span style={{ color: theme.primary }}>{attr}</span>
          </div>
          <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2 }}>
            {disc_mrps.length} discontinued → {valid_mrps.length} valid MRP{valid_mrps.length !== 1 ? 's' : ''}
            {disc_rows_in_sales > 0 && ` · ${disc_rows_in_sales} rows in sales`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {!balanced && (
            <span style={{ fontSize: 10, color: '#FBBF24' }}>Sum={total.toFixed(1)}%</span>
          )}
          <button onClick={autoBalance} style={{
            padding: '3px 10px', fontSize: 10, borderRadius: 5,
            background: 'transparent', border: `1px solid ${theme.border}`,
            color: theme.textMuted, cursor: 'pointer',
          }}>= Equal</button>
        </div>
      </div>

      {/* Discontinued MRPs */}
      <div style={{ padding: '8px 16px 6px', borderBottom: `1px solid ${theme.border}22` }}>
        <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 4, fontWeight: 600, letterSpacing: 0.3 }}>
          DISCONTINUED (redistributed away)
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {disc_mrps.map(m => (
            <span key={m} style={{
              padding: '2px 8px', borderRadius: 4, fontSize: 11, ...mono,
              background: `${theme.danger}15`, color: theme.danger, border: `1px solid ${theme.danger}30`,
            }}>₹{m}</span>
          ))}
        </div>
      </div>

      {/* Valid MRPs with % inputs */}
      <div style={{ padding: '10px 16px' }}>
        <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 8, fontWeight: 600, letterSpacing: 0.3 }}>
          SPLIT ACROSS VALID MRPs
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {valid_mrps.map((mrp, idx) => (
            <div key={mrp} style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px',
              borderRadius: 7, background: `${theme.accent}0d`, border: `1px solid ${theme.accent}30`,
            }}>
              <span style={{ fontSize: 11, color: theme.accent, ...mono, minWidth: 36 }}>₹{mrp}</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={pcts[idx] ?? ''}
                onChange={e => update(idx, e.target.value)}
                style={{
                  width: 54, padding: '3px 6px', borderRadius: 5,
                  background: theme.surfaceAlt, border: `1px solid ${balanced ? theme.border : '#FBBF2444'}`,
                  color: theme.textPrimary, fontSize: 11, textAlign: 'right', ...mono, outline: 'none',
                }}
              />
              <span style={{ fontSize: 10, color: theme.textMuted }}>%</span>
            </div>
          ))}
        </div>
      </div>
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
              background: ri % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
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
               : l.includes('WARN') ? '#FBBF24'
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
  const [overrides, setOverrides] = useState({})
  const [activeTab, setActiveTab] = useState('groups')
  const [filter, setFilter]       = useState('')

  const [running, setRunning]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState('')
  const [resultTab, setResultTab] = useState('preview')

  const reload = useCallback(() => {
    fetch('/api/mrp-reapportionment/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStatus(d) })
    fetch('/api/mrp-reapportionment/sales-status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSalesInfo(d) })
  }, [])

  const loadGroups = useCallback(() => {
    setGroupsErr('')
    fetch('/api/mrp-reapportionment/mrp-groups')
      .then(r => r.json())
      .then(d => {
        if (d.detail) { setGroupsErr(d.detail); return }
        setGroups(d)
      })
      .catch(e => setGroupsErr(String(e)))
  }, [])

  useEffect(() => { reload() }, [reload])

  const handleGroupChange = useCallback((group_key, splits) => {
    setOverrides(prev => ({ ...prev, [group_key]: splits }))
  }, [])

  const handleRun = async () => {
    setRunning(true); setError(''); setResult(null)
    try {
      const body = { cont_pcts: Object.keys(overrides).length ? overrides : null }
      const r = await fetch('/api/mrp-reapportionment/run', {
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
      g.dept.includes(q) || g.display.includes(q) || g.attr.includes(q)
    )
  }, [groups, filter])

  const overrideCount = Object.keys(overrides).length
  const canRun = salesInfo?.file_found && status?.mapping_file_found && !running
  const lastRun = status?.last_run

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      {/* Heading */}
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: theme.textPrimary }}>
          MRP Re-apportionment
        </h1>
        <p style={{ margin: '5px 0 0', fontSize: 13, color: theme.textMuted }}>
          Redistribute sales from discontinued MRP slabs to valid listed MRPs. Configure split % per group.
        </p>
      </div>

      {/* Last-run banner */}
      {lastRun && !result && (
        <div style={{
          marginBottom: 18, padding: '10px 18px', borderRadius: 10,
          background: lastRun.val_pass ? `${theme.accent}10` : `${theme.danger}10`,
          border: `1px solid ${lastRun.val_pass ? theme.accent : theme.danger}33`,
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
          <a href="/api/mrp-reapportionment/download" style={{
            padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
            background: theme.primary, color: '#fff', textDecoration: 'none', flexShrink: 0,
          }}>↓ Download</a>
        </div>
      )}

      {/* Two-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 18, alignItems: 'start' }}>

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
                background: salesInfo?.file_found ? `${theme.accent}0d` : `${theme.danger}0d`,
                border: `1px solid ${salesInfo?.file_found ? theme.accent : theme.danger}33`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: salesInfo?.file_found ? theme.accent : theme.danger, marginBottom: 3 }}>
                  {salesInfo?.file_found ? '✓' : '✗'} Actual Sales
                </div>
                {salesInfo?.file_found
                  ? <>
                      <div style={{ fontSize: 11, color: theme.textPrimary, ...mono }}>{salesInfo.filename}</div>
                      <div style={{ fontSize: 10, color: theme.textMuted, marginTop: 2 }}>{salesInfo.size_kb} KB · {salesInfo.modified}</div>
                    </>
                  : <div style={{ fontSize: 11, color: theme.textMuted }}>Drop .xlsb/.xlsx in Historical Sales\</div>
                }
              </div>
              <div style={{
                padding: '12px 14px', borderRadius: 8,
                background: status?.mapping_file_found ? `${theme.accent}0d` : `${theme.danger}0d`,
                border: `1px solid ${status?.mapping_file_found ? theme.accent : theme.danger}33`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: status?.mapping_file_found ? theme.accent : theme.danger, marginBottom: 3 }}>
                  {status?.mapping_file_found ? '✓' : '✗'} MRP Mapping Master
                </div>
                {status?.mapping_file_found
                  ? <div style={{ fontSize: 11, color: theme.textPrimary, ...mono }}>{status.mapping_file}</div>
                  : <div style={{ fontSize: 11, color: theme.textMuted }}>Drop .xlsx in MRP Mapping\</div>
                }
              </div>
            </div>
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
                background: theme.primary, border: 'none', color: '#fff', fontWeight: 600,
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
                      Each group shows discontinued MRPs and lets you set the split % across valid MRPs.
                    </div>
                  </div>
                )}
                {groupsErr && (
                  <div style={{
                    padding: '10px 14px', borderRadius: 8, fontSize: 12,
                    background: `${theme.danger}12`, border: `1px solid ${theme.danger}44`, color: theme.danger,
                  }}>✗ {groupsErr}</div>
                )}
                {groups && (
                  <>
                    <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center' }}>
                      <input
                        placeholder="Filter by dept / display / attribute…"
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
                        {overrideCount > 0 && (
                          <span style={{ marginLeft: 8, color: theme.accent }}>· {overrideCount} custom</span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 520, overflowY: 'auto' }}>
                      {filteredGroups.map(g => (
                        <GroupRow
                          key={g.group_key}
                          group={g}
                          overrides={overrides[g.group_key] || null}
                          onChange={handleGroupChange}
                        />
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
                    <StatCard label="UNMAPPED" value={result.unmapped} color={result.unmapped > 0 ? '#FBBF24' : theme.textMuted} />
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
                  <a href="/api/mrp-reapportionment/download" style={{
                    display: 'flex', alignItems: 'center', padding: '6px 14px', borderRadius: 7,
                    fontSize: 12, fontWeight: 700, background: theme.primary, color: '#fff',
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
            {groups && (
              <div style={{ marginBottom: 10, fontSize: 12, color: theme.textMuted }}>
                {overrideCount > 0
                  ? <><span style={{ color: theme.accent, fontWeight: 700 }}>{overrideCount}</span> group{overrideCount !== 1 ? 's' : ''} with custom splits · {groups.total_groups - overrideCount} using equal split</>
                  : <span>All groups using equal split — load groups above to customise</span>
                }
              </div>
            )}
            <button
              onClick={handleRun}
              disabled={!canRun}
              style={{
                width: '100%', padding: '13px 0', borderRadius: 9,
                fontSize: 14, fontWeight: 700, letterSpacing: 0.3,
                cursor: canRun ? 'pointer' : 'not-allowed',
                background: canRun ? theme.primary : theme.border,
                color: '#fff', border: 'none',
              }}
            >
              {running ? '⟳  Running engine…' : '▶  Run Re-apportionment'}
            </button>
            {error && (
              <div style={{
                marginTop: 10, padding: '10px 14px', borderRadius: 8, fontSize: 12,
                background: `${theme.danger}12`, border: `1px solid ${theme.danger}44`, color: theme.danger,
              }}>✗ {error}</div>
            )}
          </div>
        </div>

        {/* ── Right: info panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '18px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 12 }}>
              DROP FILES HERE
            </div>
            {[
              { label: 'Actual Sales (.xlsb / .xlsx)', path: 'Sales Reapportionment\\Historical Sales\\' },
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
              { icon: '📂', t: '1. Load groups',  b: 'Mapping master shows which MRPs are valid vs. discontinued per group (Dept · Display · Attribute).' },
              { icon: '⚙',  t: '2. Set splits',   b: 'For each group with discontinued MRPs, assign % of sales to each valid MRP. Default = equal split.' },
              { icon: '▶',  t: '3. Run',           b: 'Valid MRP rows pass through. Discontinued MRP sales are redistributed per your %s.' },
              { icon: '✓',  t: '4. Validate',      b: 'Totals per Store × Dept verified before and after — diff must be < ₹0.01.' },
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
              'No valid group → Listed MRP 0',
            ].map(c => (
              <div key={c} style={{ display: 'flex', gap: 7, marginBottom: 6, fontSize: 11, color: theme.textMuted }}>
                <span style={{ color: theme.accent, flexShrink: 0 }}>✓</span>
                <span>{c}</span>
              </div>
            ))}
          </div>

          <a href="/api/mrp-reapportionment/template" style={{
            display: 'block', padding: '9px 14px', borderRadius: 8,
            background: 'transparent', border: `1px solid ${theme.border}`,
            color: theme.textMuted, textDecoration: 'none', fontSize: 12, textAlign: 'center',
          }}>↓ Download Sales Template</a>
        </div>
      </div>
    </div>
  )
}
