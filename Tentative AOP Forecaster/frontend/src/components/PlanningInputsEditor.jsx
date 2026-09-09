import { useState, useEffect, useMemo, useRef } from 'react'
import { fetchJson } from './DbSyncPanel'
import * as XLSX from 'xlsx'
import './PlanningInputsEditor.css'

const DIVS = ['GM', 'KIDS', 'LADIES', 'MENS', 'RETAIL']
const ROW_KEYS = ['OVERALL', ...DIVS]
const MONTHS = ["Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"]
const AOP_MONTHS = ["Mar'27", ...MONTHS]

const TABS = [
  { key: 'growth',  label: 'Growth %' },
  { key: 'nso',    label: 'NSO Opening Months' },
  { key: 'aop',    label: 'AOP Overrides' },
  { key: 'stores', label: 'Store Master' },
]

// Valid tag values — vintage-based (DB / engine) + simple aliases (CSV imports)
const STORE_TAGS = [
  '032 - Stores','080 - Stores','095 - Stores','125 - Stores','3 - Stores',
  'FY26 - Q1','FY26 - Q2','FY26 - Q3',
  'FY26 - Q4','FY27 - Q1','FY27 - Q2',
  'NSO','MAMJ-NSO',
  'LFL','Ramp',
]

// Tag → colour sets covering both vintage DB values and simple CSV labels
const LFL_TAG_SET  = new Set(['LFL','032 - Stores','080 - Stores','095 - Stores','125 - Stores','3 - Stores','FY26 - Q1','FY26 - Q2','FY26 - Q3'])
const RAMP_TAG_SET = new Set(['Ramp','RAMP','ramp','FY26 - Q4','FY27 - Q1','FY27 - Q2'])
const NSO_TAG_SET  = new Set(['NSO','MAMJ-NSO'])

const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`

function parseCSVRow(line) {
  const fields = []; let cur = ''; let inQ = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (inQ) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++ }
      else if (ch === '"') { inQ = false }
      else { cur += ch }
    } else {
      if (ch === '"') { inQ = true }
      else if (ch === ',') { fields.push(cur.trim()); cur = '' }
      else { cur += ch }
    }
  }
  fields.push(cur.trim())
  return fields
}

function downloadAopTemplate() {
  const text = [
    ['Store', 'Division', 'Month', 'Value'],
    ['EXAMPLE', DIVS[0], AOP_MONTHS[0], '12.5'],
  ].map(row => row.map(csvField).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a'); a.href = url; a.download = 'aop_overrides_template.csv'; a.click()
  URL.revokeObjectURL(url)
}

export default function PlanningInputsEditor({ onBack, onContinue }) {
  const [tab, setTab] = useState('growth')
  const [continuing, setContinuing] = useState(false)
  const [continueErr, setContinueErr] = useState(null)

  // Store master data is pre-fetched in the parent so switching to the tab
  // is instant — no re-fetch on every tab click.
  const [stores, setStores] = useState(null)
  const [storeLoadErr, setStoreLoadErr] = useState(null)
  useEffect(() => {
    fetchJson('/api/config/store-master')
      .then(d => setStores(d))
      .catch(e => setStoreLoadErr(e.message))
  }, [])

  async function handleContinue() {
    setContinuing(true); setContinueErr(null)
    try { await onContinue() } catch (e) { setContinueErr(e.message) } finally { setContinuing(false) }
  }

  return (
    <div className="pie-wrap">
      {/* ── Page header ─────────────────────────────────── */}
      <div className="pie-head">
        <div className="pie-head-left">
          <div className="pie-head-eyebrow">Configuration</div>
          <h1 className="pie-title">Planning Inputs</h1>
          <p className="pie-sub">Growth %, NSO openings, AOP overrides, and Store Master — all written to Postgres and read by every forecast session.</p>
        </div>
        <div className="pie-head-actions">
          {continueErr && <span className="pie-status err" style={{ maxWidth: 240 }}>{continueErr}</span>}
          <button className="btn-primary" onClick={handleContinue} disabled={continuing}>
            {continuing ? 'Building…' : 'Continue to Review →'}
          </button>
          <button className="btn-outline" onClick={onBack}>← Back</button>
        </div>
      </div>

      {/* ── Tabs ──────────────────────────────────────── */}
      <div className="pie-tabs">
        {TABS.map(t => (
          <button key={t.key} className={`pie-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'growth'  && <GrowthTab />}
      {tab === 'nso'     && <NsoTab />}
      {tab === 'aop'     && <AopTab />}
      {tab === 'stores'  && (
        <StoreMasterTab
          stores={stores}
          setStores={setStores}
          loadErr={storeLoadErr}
          reload={() => {
            setStores(null); setStoreLoadErr(null)
            fetchJson('/api/config/store-master').then(setStores).catch(e => setStoreLoadErr(e.message))
          }}
        />
      )}
    </div>
  )
}

/* ── Count tile component ───────────────────────────────────────── */
function CountTile({ label, value, variant, onClick, active }) {
  return (
    <div
      className={`sm-tile sm-tile-${variant}${onClick ? ' sm-tile-clickable' : ''}${active ? ' sm-tile-active' : ''}`}
      onClick={onClick}
      title={onClick ? (active ? `Clear filter` : `Filter by ${label}`) : undefined}
    >
      <span className="sm-tile-val">{value ?? '—'}</span>
      <span className="sm-tile-lbl">{label}</span>
    </div>
  )
}

/* ── Multi-select filter dropdown ────────────────────────────────── */
function MultiSelect({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function onClickOutside(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function toggle(v) {
    onChange(selected.includes(v) ? selected.filter(x => x !== v) : [...selected, v])
  }

  const displayLabel = selected.length === 0
    ? label
    : selected.length === 1 ? `${label}: ${selected[0]}` : `${label}: ${selected.length} selected`

  return (
    <div className="ms-root" ref={ref}>
      <button className={`ms-btn ${selected.length ? 'ms-btn-active' : ''}`} onClick={() => setOpen(o => !o)}>
        {displayLabel}
        <svg className="ms-caret" width="10" height="6" viewBox="0 0 10 6" fill="currentColor">
          <path d="M0 0l5 6 5-6z"/>
        </svg>
      </button>
      {open && (
        <div className="ms-panel">
          {options.length === 0
            ? <div className="ms-empty">No options</div>
            : options.map(v => (
              <label key={v} className="ms-item">
                <input type="checkbox" checked={selected.includes(v)} onChange={() => toggle(v)} />
                <span>{v}</span>
              </label>
            ))
          }
          {selected.length > 0 && (
            <button className="ms-clear" onClick={() => onChange([])}>Clear all</button>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Store Master XLSX template ──────────────────────────────────── */
function downloadStoreMasterTemplate() {
  const HEADERS  = ['store_code','store_name','tag','cluster_key','ref_store','region_type','store_grade','erp_cluster_type','festival_grouping']
  const EXAMPLE1 = ['STORE001','Example LFL Store','LFL','NORTH-1','REF001','North','A','','']
  const EXAMPLE2 = ['STORE002','Example Ramp Store','Ramp','SOUTH-2','','South','B','','']
  const EXAMPLE3 = ['STORE003','Example NSO Store','NSO','EAST-3','','East','C','','']
  const ws = XLSX.utils.aoa_to_sheet([HEADERS, EXAMPLE1, EXAMPLE2, EXAMPLE3])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Store Master')
  XLSX.writeFile(wb, 'store_master_template.xlsx')
}

const SM_CACHE_KEY = 'aop-store-master-cache'

/* ── Store Master Tab ────────────────────────────────────────────── */
function StoreMasterTab({ stores, setStores, loadErr, reload }) {
  const [edits, setEdits] = useState(() => {
    try { return JSON.parse(localStorage.getItem(SM_CACHE_KEY) || '{}') } catch { return {} }
  })
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ tag: [], cluster: [], region: [], grade: [] })
  const [status, setStatus] = useState(null)
  const [busy, setBusy]     = useState(false)
  const [importing, setImporting] = useState(false)
  // Use empty array when DB load failed so import tools still render
  const safeStores = stores || []

  // Persist imports in localStorage so they survive page reloads
  useEffect(() => {
    try { localStorage.setItem(SM_CACHE_KEY, JSON.stringify(edits)) } catch {}
  }, [edits])

  async function importFile(e) {
    const file = e.target.files?.[0]; e.target.value = ''
    if (!file) return
    setImporting(true); setStatus(null)
    try {
      // Parse rows — XLSX/XLS via SheetJS, CSV via RFC 4180 parser
      let allRows = []
      const ext = file.name.split('.').pop().toLowerCase()
      if (ext === 'xlsx' || ext === 'xls') {
        const buf = await file.arrayBuffer()
        const wb  = XLSX.read(buf, { type: 'array' })
        const ws  = wb.Sheets[wb.SheetNames[0]]
        allRows   = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' })
      } else {
        const text = await file.text()
        allRows = text.split(/\r?\n/).filter(l => l.trim()).map(parseCSVRow)
      }
      if (!allRows.length) throw new Error('Empty file')
      // Auto-detect header
      const raw = allRows[0].map(h => String(h).toLowerCase().replace(/\s+/g,'_'))
      const colIdx = {
        store:    raw.findIndex(h => ['store_code','store_id','store','storeid','code'].includes(h)),
        name:     raw.findIndex(h => ['store_name','storename','name','store name'].includes(h)),
        tag:      raw.findIndex(h => ['tag','store_tag','storetag','store_type','storetype'].includes(h)),
        cluster:  raw.findIndex(h => ['cluster_key','cluster','clusterkey'].includes(h)),
        ref:      raw.findIndex(h => ['ref_store','ref','refstore','reference_store'].includes(h)),
        region:   raw.findIndex(h => ['region_type','region','regiontype'].includes(h)),
        grade:    raw.findIndex(h => ['store_grade','grade','storegrade'].includes(h)),
        erp:      raw.findIndex(h => ['erp_cluster_type','erp_cluster','erp','erpcluster'].includes(h)),
        festival: raw.findIndex(h => ['festival_grouping','festival','festival_group'].includes(h)),
      }
      if (colIdx.store === -1) throw new Error('Column "store_code" not found in file')
      let staged = 0, skipped = 0
      const next = {}
      for (let i = 1; i < allRows.length; i++) {
        const cols = allRows[i].map(c => String(c ?? '').trim())
        const sid = cols[colIdx.store]?.toUpperCase()
        if (!sid) { skipped++; continue }
        const patch = {}
        if (colIdx.name     >= 0) patch.store_name        = cols[colIdx.name]     ?? ''
        if (colIdx.tag      >= 0) patch.tag               = cols[colIdx.tag]      ?? ''
        if (colIdx.cluster  >= 0) patch.cluster_key       = cols[colIdx.cluster]  ?? ''
        if (colIdx.ref      >= 0) patch.ref_store         = cols[colIdx.ref]      ?? ''
        if (colIdx.region   >= 0) patch.region_type       = cols[colIdx.region]   ?? ''
        if (colIdx.grade    >= 0) patch.store_grade       = cols[colIdx.grade]    ?? ''
        if (colIdx.erp      >= 0) patch.erp_cluster_type  = cols[colIdx.erp]      ?? ''
        if (colIdx.festival >= 0) patch.festival_grouping = cols[colIdx.festival] ?? ''
        if (Object.keys(patch).length) { next[sid] = { ...(next[sid] || {}), ...patch }; staged++ }
        else skipped++
      }
      setEdits(prev => {
        const merged = { ...prev }
        for (const [sid, patch] of Object.entries(next)) merged[sid] = { ...(merged[sid] || {}), ...patch }
        return merged
      })
      setStatus({ err: false, msg: `Staged ${staged} store(s) from import${skipped ? ` · ${skipped} row(s) skipped` : ''}. Review and Save changes.` })
    } catch (err) { setStatus({ err: true, msg: `Import failed: ${err.message}` }) }
    finally { setImporting(false) }
  }

  function tileVariant(tag) {
    const t = (tag || '').trim()
    if (LFL_TAG_SET.has(t))  return 'lfl'
    if (RAMP_TAG_SET.has(t)) return 'ramp'
    if (NSO_TAG_SET.has(t))  return 'nso'
    return 'other'
  }

  // Full merged view: DB stores with edits overlaid + CSV-import-only rows
  const mergedStores = useMemo(() => {
    const inDb = new Set(safeStores.map(s => s.store_id))
    const dbRows = safeStores.map(s => ({ ...s, ...(edits[s.store_id] || {}) }))
    const importOnly = Object.entries(edits)
      .filter(([id]) => !inDb.has(id))
      .map(([id, edit]) => ({ store_id: id, ...edit }))
    return [...dbRows, ...importOnly]
  }, [safeStores, edits])

  // Unique filter options derived from full merged view
  const opts = useMemo(() => {
    const uniq = (arr) => [...new Set(arr.filter(Boolean))].sort()
    return {
      tag:     uniq(mergedStores.map(s => s.tag)),
      cluster: uniq(mergedStores.map(s => s.cluster_key)),
      region:  uniq(mergedStores.map(s => s.region_type)),
      grade:   uniq(mergedStores.map(s => s.store_grade)),
    }
  }, [mergedStores])

  // Apply filters + search over the full merged view
  const filtered = useMemo(() => {
    return mergedStores.filter(s => {
      if (search) {
        const q = search.toLowerCase()
        if (!(s.store_id || '').toLowerCase().includes(q) && !(s.store_name || '').toLowerCase().includes(q)) return false
      }
      if (filters.tag.length     && !filters.tag.includes(s.tag))             return false
      if (filters.cluster.length && !filters.cluster.includes(s.cluster_key)) return false
      if (filters.region.length  && !filters.region.includes(s.region_type))  return false
      if (filters.grade.length   && !filters.grade.includes(s.store_grade))   return false
      return true
    })
  }, [mergedStores, filters, search])

  // Tag groups always from the FULL merged view so tile counts stay stable
  // while the table below is filtered. Untagged sorted last.
  const tagGroups = useMemo(() => {
    const groups = {}
    mergedStores.forEach(s => {
      const t = (s.tag || '').trim() || '(untagged)'
      groups[t] = (groups[t] || 0) + 1
    })
    return Object.entries(groups).sort(([a], [b]) => {
      if (a === '(untagged)') return 1
      if (b === '(untagged)') return -1
      return a.localeCompare(b)
    })
  }, [mergedStores])

  // Total for the TOTAL tile = tagged stores only (the active planning universe)
  const taggedTotal = useMemo(() =>
    mergedStores.filter(s => (s.tag || '').trim()).length
  , [mergedStores])

  // Tile click: toggle tag filter on the table. Clicking TOTAL clears tag filter.
  function handleTileClick(tag) {
    if (tag === null) {
      setFilters(f => ({ ...f, tag: [] }))
    } else {
      const filterVal = tag === '(untagged)' ? '' : tag
      setFilters(f => {
        const already = f.tag.length === 1 && f.tag[0] === filterVal
        return { ...f, tag: already ? [] : [filterVal] }
      })
    }
  }

  // Whether a tile is currently the active filter
  function tileActive(tag) {
    if (tag === null) return filters.tag.length === 0
    const filterVal = tag === '(untagged)' ? '' : tag
    return filters.tag.length === 1 && filters.tag[0] === filterVal
  }

  function setField(store_id, field, value) {
    setEdits(e => ({ ...e, [store_id]: { ...(e[store_id] || {}), [field]: value } }))
  }

  async function save() {
    const rows = Object.entries(edits).map(([store_id, fields]) => ({ store_id, ...fields }))
    if (!rows.length) { setStatus({ err: false, msg: 'No changes to save.' }); return }
    setBusy(true); setStatus(null)
    try {
      const r = await fetchJson('/api/config/store-master', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      })
      setStatus({ err: false, msg: `Saved ${r.updated} store(s).` })
      setEdits({})
      reload()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  const unsavedCount = Object.keys(edits).length

  if (!stores && !loadErr) return <div className="card pie-card pie-loading">Loading store master…</div>

  return (
    <div className="card pie-card">
      {loadErr && (
        <div className="pie-import-skipped" style={{marginBottom:14}}>
          <div className="pie-import-skipped-head">
            <span>Could not load store data from database — {loadErr}</span>
          </div>
          <p style={{marginTop:6,fontSize:12,color:'var(--char)'}}>
            You can still import from a file. Download the template (XLSX), fill in store codes with tag / cluster / ref-store, and use Import below.
          </p>
        </div>
      )}
      {/* Count tiles — click any tile to filter the table; click again to clear.
          TOTAL shows tagged stores only. Untagged DB records appear last in grey. */}
      <div className="sm-tiles">
        <CountTile
          label="TOTAL STORES"
          value={taggedTotal}
          variant="total"
          onClick={() => handleTileClick(null)}
          active={tileActive(null)}
        />
        {tagGroups.filter(([tag]) => tag !== '(untagged)').map(([tag, count]) => (
          <CountTile
            key={tag}
            label={tag}
            value={count}
            variant={tileVariant(tag)}
            onClick={() => handleTileClick(tag)}
            active={tileActive(tag)}
          />
        ))}
      </div>

      {/* Toolbar */}
      <div className="pie-toolbar">
        <input
          className="pie-search"
          placeholder="Search store code or name…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <MultiSelect label="Tag"     options={opts.tag}     selected={filters.tag}     onChange={v => setFilters(f => ({ ...f, tag: v }))} />
        <MultiSelect label="Cluster" options={opts.cluster} selected={filters.cluster} onChange={v => setFilters(f => ({ ...f, cluster: v }))} />
        <MultiSelect label="Region"  options={opts.region}  selected={filters.region}  onChange={v => setFilters(f => ({ ...f, region: v }))} />
        <MultiSelect label="Grade"   options={opts.grade}   selected={filters.grade}   onChange={v => setFilters(f => ({ ...f, grade: v }))} />
        <span className="pie-count-label">{filtered.length} stores{unsavedCount > 0 ? ` · ${unsavedCount} unsaved` : ''}</span>
        <button className="btn-outline" onClick={downloadStoreMasterTemplate}>Template</button>
        <label className="btn-outline pie-import-btn">
          {importing ? 'Importing…' : 'Import'}
          <input type="file" accept=".xlsx,.xls,.csv" onChange={importFile} disabled={importing} style={{ display: 'none' }} />
        </label>
        <button className="btn-primary pie-save" onClick={save} disabled={busy || !unsavedCount}>
          {busy ? 'Saving…' : 'Save changes'}
        </button>
      </div>

      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}

      {/* Table */}
      <div className="pie-scroll">
        <table className="pie-row-table sm-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Name</th>
              <th>Tag</th>
              <th>Cluster</th>
              <th>Ref Store</th>
              <th>Region</th>
              <th>Grade</th>
              <th>ERP Cluster</th>
              <th>Festival Group</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(s => {
              const edited = edits[s.store_id] || {}
              return (
                <tr key={s.store_id} className={Object.keys(edited).length ? 'sm-row-edited' : ''}>
                  <td className="sm-code">{s.store_id}</td>
                  <td className="sm-name">{s.store_name || <span className="sm-null">—</span>}</td>
                  <td>
                    <select
                      className="sm-select"
                      value={edited.tag !== undefined ? edited.tag : (s.tag || '')}
                      onChange={e => setField(s.store_id, 'tag', e.target.value)}
                    >
                      <option value="">—</option>
                      {STORE_TAGS.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </td>
                  <td>
                    <input
                      className="sm-input"
                      type="text"
                      value={edited.cluster_key !== undefined ? edited.cluster_key : (s.cluster_key || '')}
                      onChange={e => setField(s.store_id, 'cluster_key', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="sm-input sm-input-sm"
                      type="text"
                      value={edited.ref_store !== undefined ? edited.ref_store : (s.ref_store || '')}
                      onChange={e => setField(s.store_id, 'ref_store', e.target.value)}
                    />
                  </td>
                  <td>{s.region_type || <span className="sm-null">—</span>}</td>
                  <td>
                    <span className={`sm-grade sm-grade-${(s.store_grade || '').toLowerCase()}`}>
                      {s.store_grade || '—'}
                    </span>
                  </td>
                  <td className="sm-muted">{s.erp_cluster_type || '—'}</td>
                  <td className="sm-muted">{s.festival_grouping || '—'}</td>
                </tr>
              )
            })}
            {!filtered.length && (
              <tr><td colSpan={9} className="sm-empty-row">No stores match the current filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── Growth % Tab ───────────────────────────────────────────────── */
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

  if (!rows) return <div className="card pie-card pie-loading">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <span className="pie-hint">OVERALL is the fallback for any division cell left blank.</span>
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
                <tr key={rk} className={rk === 'OVERALL' ? 'pie-row-overall' : ''}>
                  <td className="pie-row-label">{rk}</td>
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

/* ── NSO Opening Months Tab ──────────────────────────────────────── */
function NsoTab() {
  const [rows, setRows]     = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy]     = useState(false)
  const [draft, setDraft]   = useState({ store_id: '', opening_month: '', is_named: false })

  const load = () => fetchJson('/api/config/nso').then(setRows).catch(e => setStatus({ err: true, msg: e.message }))
  useEffect(() => { load() }, [])

  function updateRow(i, patch) { setRows(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r)) }
  function removeRow(i)        { setRows(rs => rs.filter((_, idx) => idx !== i)) }
  function addRow() {
    if (!draft.store_id.trim() || !/^[A-Za-z]{3}'\d{2}$/.test(draft.opening_month)) {
      setStatus({ err: true, msg: "Store and Opening Month (e.g. Apr'27) are required." }); return
    }
    setRows(rs => [...rs, { ...draft, store_id: draft.store_id.trim().toUpperCase() }])
    setDraft({ store_id: '', opening_month: '', is_named: false }); setStatus(null)
  }

  async function save() {
    setBusy(true); setStatus(null)
    try {
      await fetchJson('/api/config/nso', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows }) })
      setStatus({ err: false, msg: 'Saved.' }); load()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  if (!rows) return <div className="card pie-card pie-loading">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <span className="pie-hint">{rows.length} stores — removing a row here deletes it on Save.</span>
        <button className="btn-primary pie-save" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save NSO openings'}</button>
      </div>
      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}
      <div className="pie-scroll">
        <table className="pie-row-table">
          <thead><tr><th>Store</th><th>Opening Month</th><th>Named</th><th></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.store_id}>
                <td className="pie-row-label">{r.store_id}</td>
                <td><input type="text" value={r.opening_month} placeholder="Apr'27"
                  onChange={e => updateRow(i, { opening_month: e.target.value })} /></td>
                <td style={{ textAlign: 'center' }}>
                  <input type="checkbox" checked={r.is_named} onChange={e => updateRow(i, { is_named: e.target.checked })} />
                </td>
                <td><button className="pie-del" onClick={() => removeRow(i)}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pie-add-row">
        <input type="text" placeholder="Store code" value={draft.store_id} onChange={e => setDraft(d => ({ ...d, store_id: e.target.value }))} />
        <input type="text" placeholder="Opening month, e.g. Apr'27" value={draft.opening_month} onChange={e => setDraft(d => ({ ...d, opening_month: e.target.value }))} />
        <label className="pie-check-label">
          <input type="checkbox" checked={draft.is_named} onChange={e => setDraft(d => ({ ...d, is_named: e.target.checked }))} /> Named
        </label>
        <button className="btn-outline" onClick={addRow}>+ Add store</button>
      </div>
    </div>
  )
}

/* ── AOP Overrides Tab ───────────────────────────────────────────── */
function AopTab() {
  const [rows, setRows]           = useState(null)
  const [edits, setEdits]         = useState({})
  const [search, setSearch]       = useState('')
  const [status, setStatus]       = useState(null)
  const [busy, setBusy]           = useState(false)
  const [draft, setDraft]         = useState({ store_id: '', division: DIVS[0], month: AOP_MONTHS[0], value: '' })
  const [importing, setImporting] = useState(false)
  const [importSkipped, setImportSkipped] = useState(null)

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

  const filtered = search ? merged.filter(r => r.store_id.toLowerCase().includes(search.toLowerCase())) : merged

  function setValue(r, val) { setEdits(e => ({ ...e, [key(r)]: val })) }
  function deleteRow(r)     { setEdits(e => ({ ...e, [key(r)]: '' })) }
  function addDraft() {
    if (!draft.store_id.trim() || draft.value === '') { setStatus({ err: true, msg: 'Store and Value are required.' }); return }
    setEdits(e => ({ ...e, [`${draft.store_id.trim().toUpperCase()}|${draft.division}|${draft.month}`]: draft.value }))
    setDraft({ store_id: '', division: DIVS[0], month: AOP_MONTHS[0], value: '' }); setStatus(null)
  }

  async function importFile(e) {
    const file = e.target.files?.[0]; e.target.value = ''
    if (!file) return
    setImporting(true); setStatus(null); setImportSkipped(null)
    try {
      const form = new FormData(); form.append('file', file)
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
      if (result.skipped.length) parts.push(`${result.skipped.length} row(s) skipped`)
      setStatus({ err: !result.rows.length && !!result.skipped.length, msg: parts.join(' · ') + '. Review below, then Save changes.' })
    } catch (err) { setStatus({ err: true, msg: `Import failed: ${err.message}` }) }
    finally { setImporting(false) }
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
      setStatus({ err: false, msg: `Saved ${payload.length} change(s).` }); load()
    } catch (e) { setStatus({ err: true, msg: e.message }) }
    finally { setBusy(false) }
  }

  if (!rows) return <div className="card pie-card pie-loading">Loading…</div>

  return (
    <div className="card pie-card">
      <div className="pie-toolbar">
        <input className="pie-search" placeholder="Search by store code…" value={search} onChange={e => setSearch(e.target.value)} />
        <span className="pie-count-label">{rows.length} overrides · {Object.keys(edits).length} unsaved change(s)</span>
        <button className="btn-outline" onClick={downloadAopTemplate}>Download Template</button>
        <label className="btn-outline pie-import-btn">
          {importing ? 'Importing…' : 'Import'}
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={importFile} disabled={importing} style={{ display: 'none' }} />
        </label>
        <button className="btn-primary pie-save" onClick={save} disabled={busy || !Object.keys(edits).length}>
          {busy ? 'Saving…' : 'Save changes'}
        </button>
      </div>
      {status && <p className={`pie-status ${status.err ? 'err' : ''}`}>{status.msg}</p>}
      {importSkipped && importSkipped.length > 0 && (
        <div className="pie-import-skipped">
          <div className="pie-import-skipped-head">
            {importSkipped.length} row{importSkipped.length === 1 ? '' : 's'} skipped on import
            <button className="pie-del" onClick={() => setImportSkipped(null)}>Dismiss</button>
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
              <tr key={r._key} className={r._new ? 'pie-row-new' : ''}>
                <td className="pie-row-label">{r.store_id}</td>
                <td>{r.division}</td>
                <td>{r.month}</td>
                <td><input type="number" step="0.01" value={edits[r._key] ?? r.value} onChange={e => setValue(r, e.target.value)} /></td>
                <td><button className="pie-del" onClick={() => deleteRow(r)}>Remove</button></td>
              </tr>
            ))}
            {!filtered.length && <tr><td colSpan={5} className="sm-empty-row">No overrides match.</td></tr>}
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
