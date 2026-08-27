import { useState, useEffect, useMemo } from 'react'
import { fetchJson } from './DbSyncPanel'
import './PlanningInputsEditor.css'

const DIVS = ['GM', 'KIDS', 'LADIES', 'MENS', 'RETAIL']
const ROW_KEYS = ['OVERALL', ...DIVS]
const MONTHS = ["Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"]
const AOP_MONTHS = ["Mar'27", ...MONTHS]

const TABS = [
  { key: 'growth', label: 'Growth %' },
  { key: 'nso', label: 'NSO Opening Months' },
  { key: 'aop', label: 'AOP Overrides' },
]

export default function PlanningInputsEditor({ onBack }) {
  const [tab, setTab] = useState('growth')
  return (
    <div className="pie-wrap">
      <div className="pie-head">
        <div>
          <h1 className="pie-title">Planning Inputs</h1>
          <p className="pie-sub">Growth %, NSO openings, and AOP overrides — writes directly to Postgres (rs_planning), read by every "Continue from database" session.</p>
        </div>
        <button className="btn-outline" onClick={onBack}>← Back</button>
      </div>
      <div className="pie-tabs">
        {TABS.map(t => (
          <button key={t.key} className={`pie-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      {tab === 'growth' && <GrowthTab />}
      {tab === 'nso' && <NsoTab />}
      {tab === 'aop' && <AopTab />}
    </div>
  )
}

// ── Growth % — small, dense grid, save-all ──────────────────────────────────
function GrowthTab() {
  const [rows, setRows]     = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy]     = useState(false)

  const load = () => fetchJson('/api/config/growth').then(d => setRows(d.rows)).catch(e => setStatus({ err: true, msg: e.message }))
  useEffect(() => { load() }, [])

  function setCell(rowKey, month, val) {
    setRows(rs => rs.map(r => r.row_key === rowKey ? { ...r, values: { ...r.values, [month]: val } } : r))
  }

  async function save() {
    setBusy(true); setStatus(null)
    try {
      const payload = rows.map(r => ({
        row_key: r.row_key,
        values: Object.fromEntries(MONTHS.map(m => [m, r.values[m] === '' || r.values[m] == null ? null : Number(r.values[m])])),
      }))
      await fetchJson('/api/config/growth', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows: payload }) })
      setStatus({ err: false, msg: 'Saved.' })
      load()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  if (!rows) return <div className="card pie-card">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>OVERALL is the fallback for any division cell left blank. Blank a division cell to inherit OVERALL for that month.</span>
        <button className="btn-primary pie-save" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save growth rates'}</button>
      </div>
      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}
      <div className="pie-scroll">
        <table className="pie-grid-table">
          <thead>
            <tr><th>Division</th>{MONTHS.map(m => <th key={m}>{m}</th>)}</tr>
          </thead>
          <tbody>
            {ROW_KEYS.map(rk => {
              const row = rows.find(r => r.row_key === rk) || { row_key: rk, values: {} }
              return (
                <tr key={rk}>
                  <td>{rk}</td>
                  {MONTHS.map(m => (
                    <td key={m}>
                      <input type="number" step="0.1" placeholder={rk === 'OVERALL' ? '' : '—'}
                        value={row.values[m] ?? ''}
                        onChange={e => setCell(rk, m, e.target.value)} />
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── NSO Opening Months — full-table editor (add/edit/delete rows) ──────────
function NsoTab() {
  const [rows, setRows]     = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy]     = useState(false)
  const [draft, setDraft]   = useState({ store_id: '', opening_month: '', is_named: false })

  const load = () => fetchJson('/api/config/nso').then(setRows).catch(e => setStatus({ err: true, msg: e.message }))
  useEffect(() => { load() }, [])

  function updateRow(i, patch) {
    setRows(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r))
  }
  function removeRow(i) {
    setRows(rs => rs.filter((_, idx) => idx !== i))
  }
  function addRow() {
    if (!draft.store_id.trim() || !/^[A-Za-z]{3}'\d{2}$/.test(draft.opening_month)) {
      setStatus({ err: true, msg: "Store and Opening Month (e.g. Apr'27) are required." }); return
    }
    setRows(rs => [...rs, { ...draft, store_id: draft.store_id.trim().toUpperCase() }])
    setDraft({ store_id: '', opening_month: '', is_named: false })
    setStatus(null)
  }

  async function save() {
    setBusy(true); setStatus(null)
    try {
      await fetchJson('/api/config/nso', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows }) })
      setStatus({ err: false, msg: 'Saved.' })
      load()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  if (!rows) return <div className="card pie-card">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>{rows.length} stores. This is the full list — removing a row here deletes it on Save.</span>
        <button className="btn-primary pie-save" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save NSO openings'}</button>
      </div>
      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}
      <div className="pie-scroll">
        <table className="pie-row-table">
          <thead><tr><th>Store</th><th>Opening Month</th><th>Named</th><th></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.store_id}>
                <td>{r.store_id}</td>
                <td><input type="text" value={r.opening_month} placeholder="Apr'27"
                  onChange={e => updateRow(i, { opening_month: e.target.value })} /></td>
                <td><input type="checkbox" checked={r.is_named} onChange={e => updateRow(i, { is_named: e.target.checked })} /></td>
                <td><button className="pie-del" onClick={() => removeRow(i)} title="Remove">✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pie-add-row">
        <input type="text" placeholder="Store code" value={draft.store_id} onChange={e => setDraft(d => ({ ...d, store_id: e.target.value }))} />
        <input type="text" placeholder="Opening month, e.g. Apr'27" value={draft.opening_month} onChange={e => setDraft(d => ({ ...d, opening_month: e.target.value }))} />
        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
          <input type="checkbox" checked={draft.is_named} onChange={e => setDraft(d => ({ ...d, is_named: e.target.checked }))} /> Named
        </label>
        <button className="btn-outline" onClick={addRow}>+ Add store</button>
      </div>
    </div>
  )
}

// ── AOP Overrides — sparse delta editor, searchable ─────────────────────────
function AopTab() {
  const [rows, setRows]       = useState(null)      // as loaded from the server
  const [edits, setEdits]     = useState({})        // key -> value ('' meaning delete) for edited/new rows
  const [search, setSearch]   = useState('')
  const [status, setStatus]   = useState(null)
  const [busy, setBusy]       = useState(false)
  const [draft, setDraft]     = useState({ store_id: '', division: DIVS[0], month: AOP_MONTHS[0], value: '' })
  const [importing, setImporting] = useState(false)
  const [importSkipped, setImportSkipped] = useState(null) // [{row, reason}] from the last import, or null

  const load = () => fetchJson('/api/config/aop-overrides').then(d => { setRows(d); setEdits({}) }).catch(e => setStatus({ err: true, msg: e.message }))
  useEffect(() => { load() }, [])

  const key = r => `${r.store_id}|${r.division}|${r.month}`

  const merged = useMemo(() => {
    if (!rows) return []
    const out = rows.map(r => ({ ...r, _key: key(r), _deleted: edits[key(r)] === '' }))
    for (const [k, v] of Object.entries(edits)) {
      if (!out.some(r => r._key === k) && v !== '') {
        const [store_id, division, month] = k.split('|')
        out.push({ store_id, division, month, value: Number(v), _key: k, _new: true })
      }
    }
    return out.filter(r => !r._deleted).sort((a, b) => a.store_id.localeCompare(b.store_id) || a.division.localeCompare(b.division))
  }, [rows, edits])

  const filtered = search
    ? merged.filter(r => r.store_id.toLowerCase().includes(search.toLowerCase()))
    : merged

  function setValue(r, val) { setEdits(e => ({ ...e, [key(r)]: val })) }
  function deleteRow(r) { setEdits(e => ({ ...e, [key(r)]: '' })) }
  function addDraft() {
    if (!draft.store_id.trim() || draft.value === '') { setStatus({ err: true, msg: 'Store and Value are required.' }); return }
    setEdits(e => ({ ...e, [`${draft.store_id.trim().toUpperCase()}|${draft.division}|${draft.month}`]: draft.value }))
    setDraft({ store_id: '', division: DIVS[0], month: AOP_MONTHS[0], value: '' })
    setStatus(null)
  }

  // Import from CSV/XLSX (Store, Division, Month, Value columns) — parse-only
  // on the server (see db/editor.py's parse_aop_overrides_import), so this
  // only stages rows into `edits` the same way a manual edit does. Nothing
  // reaches Postgres until the user reviews the grid below and clicks
  // "Save changes" — a bulk import silently overwriting 1000+ live overrides
  // with no review step is exactly what every other editor in this tab
  // already avoids.
  async function importFile(e) {
    const file = e.target.files?.[0]
    e.target.value = '' // so picking the same file again still fires onChange
    if (!file) return
    setImporting(true); setStatus(null); setImportSkipped(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await fetchJson('/api/config/aop-overrides/import', { method: 'POST', body: form })
      if (result.rows.length) {
        setEdits(prev => {
          const next = { ...prev }
          for (const r of result.rows) next[`${r.store_id}|${r.division}|${r.month}`] = String(r.value)
          return next
        })
      }
      setImportSkipped(result.skipped)
      const parts = [`Staged ${result.rows.length} row(s) as pending changes`]
      if (result.skipped.length) parts.push(`${result.skipped.length} row(s) skipped — see below`)
      setStatus({ err: !result.rows.length && !!result.skipped.length, msg: parts.join(' · ') + '. Review below, then Save changes.' })
    } catch (err) {
      setStatus({ err: true, msg: `Import failed: ${err.message}` })
    } finally {
      setImporting(false)
    }
  }

  async function save() {
    const changed = Object.entries(edits)
    if (!changed.length) { setStatus({ err: false, msg: 'Nothing to save.' }); return }
    setBusy(true); setStatus(null)
    try {
      const payload = changed.map(([k, v]) => {
        const [store_id, division, month] = k.split('|')
        return { store_id, division, month, value: v === '' ? null : Number(v) }
      })
      await fetchJson('/api/config/aop-overrides', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows: payload }) })
      setStatus({ err: false, msg: `Saved ${payload.length} change(s).` })
      load()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  if (!rows) return <div className="card pie-card">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <input className="pie-search" placeholder="Search by store code…" value={search} onChange={e => setSearch(e.target.value)} />
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>{rows.length} overrides · {Object.keys(edits).length} unsaved change(s)</span>
        <label className="btn-outline pie-import-btn" title="Import Store, Division, Month, Value from a .csv or .xlsx">
          {importing ? 'Importing…' : '⇪ Import'}
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={importFile} disabled={importing} style={{ display: 'none' }} />
        </label>
        <button className="btn-primary pie-save" onClick={save} disabled={busy || !Object.keys(edits).length}>{busy ? 'Saving…' : 'Save changes'}</button>
      </div>
      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}
      {importSkipped && importSkipped.length > 0 && (
        <div className="pie-import-skipped">
          <div className="pie-import-skipped-head">
            {importSkipped.length} row{importSkipped.length === 1 ? '' : 's'} skipped on import
            <button className="pie-del" onClick={() => setImportSkipped(null)} title="Dismiss">✕</button>
          </div>
          <ul>
            {importSkipped.slice(0, 20).map((s, i) => <li key={i}>Row {s.row}: {s.reason}</li>)}
          </ul>
          {importSkipped.length > 20 && <div className="pie-import-skipped-more">…and {importSkipped.length - 20} more</div>}
        </div>
      )}
      <div className="pie-scroll">
        <table className="pie-row-table">
          <thead><tr><th>Store</th><th>Division</th><th>Month</th><th>Value (₹ L)</th><th></th></tr></thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r._key}>
                <td>{r.store_id}</td>
                <td>{r.division}</td>
                <td>{r.month}</td>
                <td><input type="number" step="0.01" value={edits[r._key] ?? r.value} onChange={e => setValue(r, e.target.value)} /></td>
                <td><button className="pie-del" onClick={() => deleteRow(r)} title="Remove">✕</button></td>
              </tr>
            ))}
            {!filtered.length && <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted)', padding: 16 }}>No overrides match.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="pie-add-row">
        <input type="text" placeholder="Store code" value={draft.store_id} onChange={e => setDraft(d => ({ ...d, store_id: e.target.value }))} />
        <select value={draft.division} onChange={e => setDraft(d => ({ ...d, division: e.target.value }))}>
          {DIVS.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={draft.month} onChange={e => setDraft(d => ({ ...d, month: e.target.value }))}>
          {AOP_MONTHS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <input type="number" step="0.01" placeholder="Value (₹ L)" value={draft.value} onChange={e => setDraft(d => ({ ...d, value: e.target.value }))} />
        <button className="btn-outline" onClick={addDraft}>+ Add override</button>
      </div>
    </div>
  )
}
