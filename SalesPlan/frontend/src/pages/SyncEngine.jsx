import { useState, useEffect, useCallback } from 'react'
import { theme } from '../theme'

const API = '/api/sync'

function StatusDot({ ok, error, syncing }) {
  const color = syncing ? '#F59E0B' : error ? '#EF4444' : ok ? '#10B981' : '#6B7280'
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

export default function SyncEngine() {
  const [config,    setConfig]    = useState(null)
  const [status,    setStatus]    = useState(null)
  const [syncing,   setSyncing]   = useState(false)
  const [tableData, setTableData] = useState(null)
  const [tableLoading, setTableLoading] = useState(false)

  // config edit state
  const [folder,    setFolder]    = useState('')
  const [pattern,   setPattern]   = useState('*.parquet')
  const [configDirty, setConfigDirty] = useState(false)

  // folder preview
  const [folderPreview,  setFolderPreview]  = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/status`)
      const d = await r.json()
      setConfig(d.config)
      setStatus(d.status)
      // seed local edit state on first load
      setFolder(f  => f || d.config?.sales_folder  || '')
      setPattern(p => p !== '*.parquet' ? p : (d.config?.sales_pattern || '*.parquet'))
    } catch {}
  }, [])

  useEffect(() => { fetchStatus() }, [])

  const handleSaveConfig = async () => {
    await fetch(`${API}/config`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ sales_folder: folder, sales_pattern: pattern }),
    })
    setConfigDirty(false)
    setFolderPreview(null)
    await fetchStatus()
  }

  const handlePreviewFolder = async () => {
    if (!folder) return
    setPreviewLoading(true)
    try {
      const r = await fetch(`${API}/preview-folder?path=${encodeURIComponent(folder)}&pattern=${encodeURIComponent(pattern)}`)
      setFolderPreview(await r.json())
    } catch { setFolderPreview({ error: 'Request failed', files: [] }) }
    finally  { setPreviewLoading(false) }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const r = await fetch(`${API}/sync`, { method: 'POST' })
      await fetchStatus()
      if (r.ok) loadData()
    } catch {}
    setSyncing(false)
  }

  const loadData = async () => {
    setTableLoading(true)
    try {
      const r = await fetch(`${API}/data?limit=500`)
      if (r.ok) setTableData(await r.json())
    } catch {}
    setTableLoading(false)
  }

  const st      = status?.sales || {}
  const isSynced = !!st.last_sync && !st.error

  return (
    <div style={{ padding: '28px 36px', maxWidth: 1000, margin: '0 auto' }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: theme.textPrimary }}>Sales Sync</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: theme.textMuted }}>
            Parse the latest sales parquet from the server folder on demand
          </p>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing || !config?.sales_folder}
          style={{
            padding: '10px 26px', borderRadius: 8, border: 'none', fontSize: 14,
            fontWeight: 700, cursor: syncing || !config?.sales_folder ? 'default' : 'pointer',
            background: syncing || !config?.sales_folder ? theme.border : theme.primary,
            color: '#fff', display: 'flex', alignItems: 'center', gap: 8,
          }}
        >
          <span style={syncing ? { animation: 'spin 0.8s linear infinite', display: 'inline-block' } : {}}>↺</span>
          {syncing ? 'Syncing…' : 'Sync Sales'}
        </button>
      </div>

      {/* ── Status card ── */}
      <Card style={{ marginBottom: 20, borderColor: isSynced ? '#3B82F644' : theme.border }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <StatusDot ok={isSynced} error={st.error} syncing={syncing} />
          <div style={{ flex: 1 }}>
            {isSynced ? (
              <>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#3B82F6' }}>
                  {st.file}
                </div>
                <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 2 }}>
                  {st.rows?.toLocaleString()} rows · synced {new Date(st.last_sync).toLocaleString()}
                </div>
              </>
            ) : st.error ? (
              <div style={{ color: '#EF4444', fontSize: 13, fontWeight: 600 }}>{st.error}</div>
            ) : (
              <div style={{ fontSize: 13, color: theme.textMuted }}>Not synced yet</div>
            )}
          </div>
          {isSynced && !tableData && (
            <button onClick={loadData} style={{
              padding: '6px 14px', borderRadius: 6, border: `1px solid #3B82F644`,
              background: '#3B82F611', color: '#3B82F6', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}>
              View Data
            </button>
          )}
        </div>

        {/* Column chips */}
        {st.columns?.length > 0 && (
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${theme.border}` }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.8, marginBottom: 8 }}>
              COLUMNS ({st.columns.length})
            </div>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {st.columns.map(c => (
                <span key={c} style={{
                  fontSize: 10, padding: '2px 8px', borderRadius: 4,
                  background: '#3B82F618', color: '#3B82F6', fontFamily: theme.fontMono,
                }}>{c}</span>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* ── Path config ── */}
      <Card style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary, marginBottom: 14 }}>
          Server Folder Path
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, display: 'block', marginBottom: 5 }}>
              FOLDER (UNC or local)
            </label>
            <input
              value={folder}
              onChange={e => { setFolder(e.target.value); setConfigDirty(true); setFolderPreview(null) }}
              placeholder={`\\\\server\\share\\sales`}
              style={{
                width: '100%', padding: '9px 13px', borderRadius: 7,
                border: `1.5px solid ${configDirty ? theme.primary : theme.border}`,
                background: theme.surfaceAlt, color: theme.textPrimary,
                fontSize: 13, fontFamily: theme.fontMono, boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600, display: 'block', marginBottom: 5 }}>
                FILE PATTERN
              </label>
              <input
                value={pattern}
                onChange={e => { setPattern(e.target.value); setConfigDirty(true); setFolderPreview(null) }}
                placeholder="*.parquet"
                style={{
                  width: '100%', padding: '9px 13px', borderRadius: 7,
                  border: `1.5px solid ${configDirty ? theme.primary : theme.border}`,
                  background: theme.surfaceAlt, color: theme.textPrimary,
                  fontSize: 13, fontFamily: theme.fontMono, boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <button onClick={handlePreviewFolder} disabled={!folder || previewLoading} style={{
                padding: '9px 16px', borderRadius: 7, border: `1px solid ${theme.border}`,
                background: 'transparent', color: theme.textSecondary,
                cursor: !folder || previewLoading ? 'default' : 'pointer', fontSize: 13,
                opacity: !folder ? 0.5 : 1,
              }}>
                {previewLoading ? '…' : 'Browse'}
              </button>

              {configDirty && (
                <button onClick={handleSaveConfig} style={{
                  padding: '9px 20px', borderRadius: 7, border: 'none',
                  background: theme.primary, color: '#fff',
                  cursor: 'pointer', fontSize: 13, fontWeight: 700,
                }}>
                  Save
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Folder browse preview */}
        {folderPreview && (
          <div style={{ marginTop: 14 }}>
            {!folderPreview.exists ? (
              <div style={{ color: '#EF4444', fontSize: 12 }}>
                {folderPreview.error || 'Folder not accessible'}
              </div>
            ) : folderPreview.files.length === 0 ? (
              <div style={{ color: theme.textMuted, fontSize: 12 }}>No files matching pattern</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
                  <thead>
                    <tr>
                      {['File', 'Size (KB)', 'Modified'].map(h => (
                        <th key={h} style={{
                          textAlign: 'left', color: theme.textMuted, fontWeight: 700,
                          padding: '4px 10px', borderBottom: `1px solid ${theme.border}`,
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {folderPreview.files.map((f, i) => (
                      <tr key={i} style={{ background: i === 0 ? '#3B82F611' : 'transparent' }}>
                        <td style={{
                          padding: '5px 10px', fontFamily: theme.fontMono,
                          color: i === 0 ? '#3B82F6' : theme.textPrimary,
                          fontWeight: i === 0 ? 700 : 400,
                        }}>
                          {f.name}{i === 0 && <span style={{ fontSize: 9, marginLeft: 6, opacity: 0.7 }}>← latest</span>}
                        </td>
                        <td style={{ padding: '5px 10px', color: theme.textMuted }}>{f.size_kb}</td>
                        <td style={{ padding: '5px 10px', color: theme.textMuted }}>{f.modified}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Data preview ── */}
      {(tableData || tableLoading) && (
        <Card>
          <div style={{ fontWeight: 700, fontSize: 14, color: theme.textPrimary, marginBottom: 16 }}>
            Data Preview
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
