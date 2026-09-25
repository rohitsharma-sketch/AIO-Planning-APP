import { useState, useEffect, useCallback } from 'react'
import { theme } from '../theme'

const API = '/api/planning/sync'

function StatusDot({ ok, syncing }) {
  const color = syncing ? '#B45309' : ok ? '#10B981' : '#6B7280'
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: color, flexShrink: 0,
      boxShadow: syncing ? `0 0 8px ${color}` : 'none',
      transition: 'background 0.3s, box-shadow 0.3s',
    }} />
  )
}

function Card({ children, style }) {
  return (
    <div style={{
      background: theme.surface,
      border: `1px solid ${theme.border}`,
      borderRadius: 10,
      padding: 22,
      ...style,
    }}>
      {children}
    </div>
  )
}

function StatusCard({ title, subtitle, summary, syncing, onView, viewDisabled }) {
  const ok = !!summary?.synced
  return (
    <Card style={{ borderColor: ok ? '#3B82F644' : theme.border }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <StatusDot ok={ok} syncing={syncing} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary }}>{title}</div>
          <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 1 }}>{subtitle}</div>
          {ok ? (
            <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 6 }}>
              {summary.rowCount?.toLocaleString()} rows · {summary.columnCount} period(s)
              {summary.dateRange && <> · {summary.dateRange.min} → {summary.dateRange.max}</>}
              <br />computed {new Date(summary.computedAt).toLocaleString()}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 6 }}>Not synced yet</div>
          )}
        </div>
        {ok && (
          <button onClick={onView} disabled={viewDisabled} style={{
            padding: '6px 14px', borderRadius: 6, border: `1px solid #3B82F644`,
            background: '#3B82F611', color: '#3B82F6', fontSize: 12, fontWeight: 600,
            cursor: viewDisabled ? 'default' : 'pointer', opacity: viewDisabled ? 0.5 : 1,
          }}>
            View Data
          </button>
        )}
      </div>
    </Card>
  )
}

function DataTable({ data }) {
  const [page, setPage] = useState(0)
  const PAGE = 50

  if (!data?.preview?.length) return (
    <div style={{ textAlign: 'center', padding: 32, color: theme.textMuted, fontSize: 13 }}>
      No data to display
    </div>
  )

  const cols       = data.columns || Object.keys(data.preview[0] || {})
  const rows       = data.preview.slice(page * PAGE, (page + 1) * PAGE)
  const totalPages = Math.ceil(data.preview.length / PAGE)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: theme.textMuted }}>
          Showing {page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.preview.length)} of{' '}
          <strong style={{ color: theme.textPrimary }}>{data.rows?.toLocaleString()}</strong> rows
          {data.rows > data.preview.length && (
            <span style={{ color: theme.textMuted }}> (preview capped at {data.preview.length})</span>
          )}
        </span>
        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} style={{
              padding: '4px 10px', borderRadius: 5, border: `1px solid ${theme.border}`,
              background: 'transparent', cursor: page === 0 ? 'default' : 'pointer',
              color: theme.textSecondary, fontSize: 12, opacity: page === 0 ? 0.4 : 1,
            }}>←</button>
            <span style={{ fontSize: 11, color: theme.textMuted }}>{page + 1} / {totalPages}</span>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} style={{
              padding: '4px 10px', borderRadius: 5, border: `1px solid ${theme.border}`,
              background: 'transparent', cursor: page >= totalPages - 1 ? 'default' : 'pointer',
              color: theme.textSecondary, fontSize: 12, opacity: page >= totalPages - 1 ? 0.4 : 1,
            }}>→</button>
          </div>
        )}
      </div>

      <div style={{ overflowX: 'auto', borderRadius: 8, border: `1px solid ${theme.border}` }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
          <thead>
            <tr style={{ background: theme.surfaceAlt }}>
              {cols.map(c => (
                <th key={c} style={{
                  padding: '8px 12px', textAlign: 'left', fontWeight: 700,
                  color: theme.textMuted, fontSize: 10, letterSpacing: 0.5,
                  whiteSpace: 'nowrap', borderBottom: `1px solid ${theme.border}`,
                }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{
                borderBottom: `1px solid ${theme.border}50`,
                background: i % 2 === 0 ? 'transparent' : `${theme.surfaceAlt}80`,
              }}>
                {cols.map(c => (
                  <td key={c} style={{
                    padding: '6px 12px', color: theme.textPrimary,
                    fontFamily: theme.fontMono, fontSize: 11, whiteSpace: 'nowrap',
                  }}>
                    {row[c] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const SOURCE_LABELS = { mw: 'Month-wise', dw: 'Day-wise' }

export default function SyncEngine() {
  const [status,    setStatus]    = useState(null)
  const [syncing,   setSyncing]   = useState(false)
  const [syncErr,   setSyncErr]   = useState(null)
  const [table,     setTable]     = useState(null) // null | { source, kind }
  const [tableData, setTableData] = useState(null)
  const [tableLoading, setTableLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/status`)
      setStatus(await r.json())
    } catch {}
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  const handleSync = async () => {
    setSyncing(true); setSyncErr(null)
    try {
      const r = await fetch(`${API}/sync`, { method: 'POST' })
      if (!r.ok) { const e = await r.json(); setSyncErr(e.detail || 'Sync failed') }
      await fetchStatus()
      if (table) loadData(table.source, table.kind)
    } catch { setSyncErr('Sync failed') }
    setSyncing(false)
  }

  const loadData = async (source, kind) => {
    setTable({ source, kind }); setTableLoading(true)
    try {
      const r = await fetch(`${API}/data?source=${source}&kind=${kind}&limit=500`)
      setTableData(r.ok ? await r.json() : null)
    } catch { setTableData(null) }
    setTableLoading(false)
  }

  const anySynced = Object.keys(SOURCE_LABELS).some(
    src => status?.[src]?.actual?.synced || status?.[src]?.trendShifted?.synced
  )

  return (
    <div style={{ padding: '28px 36px', maxWidth: 1000, margin: '0 auto' }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: theme.textPrimary }}>Sales Sync</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: theme.textMuted }}>
            Reads the Calendarisation app's own sales link and Run Reindex output — no separate
            server-folder setup needed here, and both stay in step with the same database.
          </p>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing}
          style={{
            padding: '10px 26px', borderRadius: 8, border: 'none', fontSize: 14,
            fontWeight: 700, cursor: syncing ? 'default' : 'pointer',
            background: syncing ? theme.border : '#A8CBB7',
            color: '#1F4D3A', display: 'flex', alignItems: 'center', gap: 8,
          }}
        >
          <span style={syncing ? { animation: 'spin 0.8s linear infinite', display: 'inline-block' } : {}}>↺</span>
          {syncing ? 'Syncing…' : 'Sync Sales'}
        </button>
      </div>

      {syncErr && (
        <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: '#EF444411', color: '#EF4444', fontSize: 13 }}>
          {syncErr}
        </div>
      )}

      {/* ── Status cards, grouped by source ── */}
      {Object.entries(SOURCE_LABELS).map(([source, label]) => (
        <div key={source} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.6, marginBottom: 8 }}>
            {label.toUpperCase()}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <StatusCard
              title="Actual Sales" subtitle="Real sales on their own date, from the same sales link Calendar Engine reads"
              summary={status?.[source]?.actual} syncing={syncing}
              onView={() => loadData(source, 'actual')}
              viewDisabled={tableLoading && table?.source === source && table?.kind === 'actual'}
            />
            <StatusCard
              title="Trend Shifted Sales" subtitle="Same sales, moved onto the calendar-aligned future date"
              summary={status?.[source]?.trendShifted} syncing={syncing}
              onView={() => loadData(source, 'trend_shifted')}
              viewDisabled={tableLoading && table?.source === source && table?.kind === 'trend_shifted'}
            />
          </div>
        </div>
      ))}

      {!anySynced && (
        <Card style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: theme.textMuted }}>
            No calendarised sales yet — run <strong style={{ color: theme.textPrimary }}>Reindex</strong> in the
            Calendarisation app's <strong style={{ color: theme.textPrimary }}>Calendarised Sales</strong> tab first,
            then click Sync Sales here.
          </div>
        </Card>
      )}

      {/* ── Data preview ── */}
      {(tableData || tableLoading) && (
        <Card>
          <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary, marginBottom: 16 }}>
            Data Preview — {SOURCE_LABELS[table?.source]} {table?.kind === 'actual' ? 'Actual Sales' : 'Trend Shifted Sales'}
          </div>
          {tableLoading
            ? <div style={{ textAlign: 'center', padding: 40, color: theme.textMuted, fontSize: 13 }}>Loading…</div>
            : <DataTable data={tableData} />
          }
        </Card>
      )}
    </div>
  )
}
