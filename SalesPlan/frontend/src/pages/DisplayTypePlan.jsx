import { useState, useEffect, useRef } from 'react'
import { theme, alpha } from '../theme'
import HierarchyView from '../components/HierarchyView'
import ExcelFilter from '../components/ExcelFilter'
import { useRoute } from '../components/RouteBar'

const API = '/api/planning/display-type'
// the MRP plan broken into display types, as the department plan's tree (user, 2026-10-14: "the MRP plan should break
// and it should be highlighted as per that only") - GET /api/planning/grain/display-view/*
const DT_FIELDS = {
  cluster: 'Cluster', store: 'Store', stype: 'Store type', division: 'Division', attribute: 'Attribute',
  department: 'Department', mrp: 'MRP', display: 'Display type', month: 'Month',
}

// ── shared styles ──────────────────────────────────────────────────────────────
const MONO = theme.fontMono
const HDR  = { fontFamily: MONO, fontSize: 11, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4, padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }
const CELL = { fontFamily: MONO, fontSize: 12, padding: '5px 10px', textAlign: 'right', whiteSpace: 'nowrap' }

const SEV_STYLE = {
  error:   { bg: '#FEE2E2', color: '#DC2626', label: 'ERROR' },
  warning: { bg: '#FEF3C7', color: '#D97706', label: 'WARN'  },
  info:    { bg: '#EEF2FF', color: '#4F46E5', label: 'INFO'  },
}

function SevChip({ sev }) {
  const s = SEV_STYLE[sev] || SEV_STYLE.info
  return (
    <span style={{
      fontSize: 9, fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase',
      padding: '2px 7px', borderRadius: 4, background: s.bg, color: s.color,
    }}>{s.label}</span>
  )
}

function UploadBox({ label, subtitle, endpoint, onDone, imported, rows, date, color }) {
  const ref = useRef()
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)
  const c = color || theme.primary

  async function upload(file) {
    setBusy(true); setErr(null)
    const fd = new FormData(); fd.append('file', file)
    try {
      const r = await fetch(`${API}/${endpoint}`, { method: 'POST', body: fd })
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Upload failed') }
      onDone()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <div style={{
      flex: 1, border: `2px dashed ${drag ? c : imported ? theme.success : theme.border}`,
      borderRadius: 10, padding: '20px 22px',
      background: imported ? `${alpha(theme.success,'08')}` : theme.surface,
      cursor: 'pointer', transition: 'border 0.15s',
    }}
      onClick={() => ref.current?.click()}
      onDragOver={e => { e.preventDefault(); setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f) }}
    >
      <input ref={ref} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }}
        onChange={e => { const f = e.target.files[0]; if (f) upload(f) }} />
      <div style={{ fontSize: 20, marginBottom: 6 }}>{imported ? '✅' : '📂'}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 10 }}>{subtitle}</div>
      {busy && <div style={{ fontSize: 11, color: c }}>Uploading…</div>}
      {err  && <div style={{ fontSize: 11, color: theme.danger, marginTop: 4 }}>{err}</div>}
      {imported && !busy && <div style={{ fontSize: 11, color: theme.success }}>{rows} rows · {date}</div>}
      {!imported && !busy && <div style={{ fontSize: 11, color: theme.textMuted }}>Drop file or click to browse</div>}
    </div>
  )
}

// ── ASP: import, export (the template) and a company-level preview (user, 2026-10-14: "calculate the ASP for P1 P2 and
// month wise ASPs too ... remove the extras like sales and qty ... so that the preview is all about ASP on Company level.
// Make the template default and start the import and export functionality") ─────────────────────────────────────
const ASP_FIELDS = [['division', 'Division'], ['dept', 'Department'], ['mrp', 'MRP'], ['display_type', 'Display type']]
function AspCard({ status, onDone }) {
  const ref = useRef()
  const mode = useRef('replace')   // 'fill' = only what the ASP in use lacks (user, 2026-10-14: "add the ASPs from this file for missing entries")
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [d, setD] = useState(null)
  const [f, setF] = useState({})
  const [edit, setEdit] = useState(null)
  const load = () => fetch(`${API}/asp`).then(r => (r.ok ? r.json() : null)).then(setD).catch(() => setD(null))
  useEffect(() => { if (status?.asp_imported) load() }, [status?.asp_imported, status?.asp_date])   // eslint-disable-line react-hooks/exhaustive-deps
  const upload = async file => {
    setBusy(true); setErr(''); setMsg('')
    const fd = new FormData(); fd.append('file', file)
    try {
      const r = await fetch(`${API}/import/asp?mode=${mode.current}`, { method: 'POST', body: fd })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`)
      if (j.added != null) setMsg(`${file.name}: ${j.added} rows added, ${j.filled} empty periods filled - nothing in use was overwritten`)
      onDone(); load()
    } catch (e) { setErr(e.message) } finally { setBusy(false); if (ref.current) ref.current.value = '' }
  }
  const rows = d?.rows || []
  const val = (r, c) => String(r[c] ?? '')
  const pass = (r, skip) => Object.entries(f).every(([c, v]) => c === skip || v.includes(val(r, c)))
  const shown = rows.filter(r => pass(r))
  const opts = c => [...new Set(rows.filter(r => pass(r, c)).map(r => val(r, c)))].sort((a, b) => (c === 'mrp' ? a - b : a.localeCompare(b)))
  const cap = c => (!f[c] ? '(All)' : f[c].length === 1 ? f[c][0] : `(Multiple Items) ${f[c].length}`)
  const per = d?.periods || []
  const fmt = v => (v == null ? '–' : v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
  const btn = { padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: `1px solid ${theme.border}`, background: theme.surface, color: theme.textPrimary }
  return (
    <div style={{ background: theme.surface, border: `1px solid ${status?.asp_imported ? theme.success : theme.border}`, borderRadius: 10, padding: '16px 18px', marginBottom: 22 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>ASP · company level</div>
        <span style={{ fontSize: 11.5, color: status?.asp_imported ? theme.success : theme.textMuted }}>
          {status?.asp_imported ? `${status.asp_rows} rows · ${d?.source || ''} · ${status.asp_date}` : 'Not imported yet'}
        </span>
        <span style={{ flex: 1 }} />
        <input ref={ref} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }} onChange={e => { const x = e.target.files[0]; if (x) upload(x) }} />
        <button type="button" style={{ ...btn, background: 'var(--st-btn,#A8CBB7)', border: 'none', color: 'var(--st-btn-text,#1F4D3A)' }} disabled={busy} onClick={() => { mode.current = 'replace'; ref.current?.click() }}>{busy ? 'Importing…' : 'Import ↑'}</button>
        {status?.asp_imported && <button type="button" style={btn} disabled={busy} onClick={() => { mode.current = 'fill'; ref.current?.click() }}
          title="Take ASPs from another file only where the ASP in use has none (new Department × MRP × Display Type rows, empty periods)">Add missing ↑</button>}
        <button type="button" style={btn} onClick={() => window.open(`${API}/export/asp`, '_blank')} title={status?.asp_imported ? 'The ASP in use, in the template' : 'A blank template on the plan’s Department × MRP × Display Type'}>
          {status?.asp_imported ? 'Export ↓' : 'Template ↓'}
        </button>
      </div>
      <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 6, lineHeight: 1.6 }}>
        Template: Division | Department | MRP | Display Type | Mar'27 P1 | Mar'27 P2 | Mar'27 | … (₹ per piece). The planners' file with P1 / P2 VAL and QTY
        by cluster and article is converted on import: carried onto the new MRPs through the MRP master (the re-apportionment's rule - listed MRPs move whole, discontinued ones split to the nearest listed below / above), added up per Department × MRP × Display Type, ASP = value ÷ pieces, the month weighted by pieces.
      </div>
      {err && <div style={{ fontSize: 12, color: theme.danger, marginTop: 6 }}>{err}</div>}
      {msg && <div style={{ fontSize: 12, color: theme.success, marginTop: 6 }}>{msg}</div>}
      {d && (
        <>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', margin: '12px 0 8px' }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>Filters</span>
            {ASP_FIELDS.map(([c, t]) => (
              <button key={c} type="button" data-no-undo onClick={e => { const el = e.currentTarget; setEdit(x => (x && x.c === c ? null : { c, t, el })) }}
                style={{ display: 'inline-flex', gap: 6, padding: '3px 8px', borderRadius: 4, fontSize: 12, cursor: 'pointer', border: `1px solid ${f[c] ? theme.primary : theme.border}`, background: f[c] ? alpha(theme.primary, '12') : theme.surface, color: theme.textPrimary }}>
                <span style={{ color: theme.textMuted }}>{t}</span><b style={{ fontWeight: f[c] ? 700 : 500 }}>{cap(c)}</b><span style={{ color: theme.textMuted, fontSize: 10 }}>▾</span>
              </button>
            ))}
            {Object.keys(f).length > 0 && <button type="button" onClick={() => setF({})} style={{ all: 'unset', cursor: 'pointer', fontSize: 12, color: theme.textMuted, textDecoration: 'underline' }}>Clear all</button>}
            <span style={{ fontSize: 11.5, color: theme.textMuted, marginLeft: 6 }}>{shown.length} of {rows.length} rows · ₹ per piece · {d.level}</span>
            {edit && <ExcelFilter key={edit.c + JSON.stringify(f)} title={edit.t} anchor={edit.el} picked={f[edit.c]} load={() => opts(edit.c)}
              onDone={v => { if (v !== undefined) setF(x => { const n = { ...x }; if (v.length) n[edit.c] = v; else delete n[edit.c]; return n }); setEdit(null) }} />}
          </div>
          <div style={{ overflow: 'auto', maxHeight: 420, border: `1px solid ${theme.border}`, borderRadius: 8 }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
              <thead style={{ position: 'sticky', top: 0, background: theme.surfaceAlt }}>
                <tr>{['Division', 'Department', 'MRP', 'Display type', ...per].map((h, i) => (
                  <th key={h} style={{ ...HDR, textAlign: i < 2 || i === 3 ? 'left' : 'right', background: i > 3 && !h.includes(' P') ? alpha(theme.primary, '14') : undefined }}>{h}</th>))}</tr>
              </thead>
              <tbody>{shown.map(r => (
                <tr key={`${r.dept}|${r.mrp}|${r.display_type}`} style={{ borderBottom: `1px solid ${theme.border}` }}>
                  <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted }}>{r.division}</td>
                  <td style={{ ...CELL, textAlign: 'left' }}>{r.dept}</td>
                  <td style={CELL}>{r.mrp}</td>
                  <td style={{ ...CELL, textAlign: 'left' }}>{r.display_type}</td>
                  {per.map(pp => <td key={pp} style={{ ...CELL, fontWeight: pp.includes(' P') ? 400 : 700, background: pp.includes(' P') ? undefined : alpha(theme.primary, '08') }}>{fmt(r.months[pp])}</td>)}
                </tr>))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── main page ──────────────────────────────────────────────────────────────────
export default function DisplayTypePlan() {
  const [route] = useRoute()   // Display Type splits MRP bands - say whose when the Sales Plan runs on Article Name
  const [prom, setProm] = useState(null)
  useEffect(() => { fetch('/api/planning/art-nm/promote').then(r => (r.ok ? r.json() : null)).then(setProm).catch(() => {}) }, [])
  const [status,   setStatus]   = useState(null)
  const [tab,      setTab]      = useState('plan')   // plan | validate | qty | export
  const [running,  setRunning]  = useState(false)
  const [validating, setValid]  = useState(false)
  const [qtyRun,   setQtyRun]  = useState(false)

  // the run files are ~150-200 MB: the page never downloads them - the Qty tab asks for one filtered slice
  // (GET /qty-view, user 2026-10-14: "fix the display type page latency too"); the ₹L Plan tab is the display tree
  const [valResult,  setValResult]  = useState(null)
  const [qtyView,    setQtyView]    = useState(null)
  const [qtyErr,     setQtyErr]     = useState('')

  // filters
  const [fStore,  setFStore]  = useState('ALL')
  const [fDiv,    setFDiv]    = useState('ALL')
  const [fDept,   setFDept]   = useState('ALL')
  const [fMonth,  setFMonth]  = useState(null)
  const [fSev,    setFSev]    = useState('ALL')

  async function loadStatus() {
    const r = await fetch(`${API}/status`)
    const d = await r.json()
    setStatus(d)
  }

  useEffect(() => {
    loadStatus()
  }, [])

  // the Qty tab's slice - fetched only while that tab is open, again when a filter or the run changes
  useEffect(() => {
    if (tab !== 'qty' || !status?.qty_run) return
    const qs = new URLSearchParams({ month: fMonth || '', store: fStore, division: fDiv, dept: fDept })
    setQtyErr('')
    fetch(`${API}/qty-view?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(d => { setQtyView(d); if (!fMonth) setFMonth(d.month) })
      .catch(e => setQtyErr(e.message))
  }, [tab, status?.qty_date, fMonth, fStore, fDiv, fDept])   // eslint-disable-line react-hooks/exhaustive-deps

  async function runPlan() {
    setRunning(true)
    try {
      const r = await fetch(`${API}/run-plan`)
      if (!r.ok) { const e = await r.json(); alert(e.detail); return }
      await loadStatus()
      setTab('plan')
    } finally { setRunning(false) }
  }

  async function runValidate() {
    setValid(true)
    try {
      const r = await fetch(`${API}/validate`)
      if (r.ok) { setValResult(await r.json()); setTab('validate') }
    } finally { setValid(false) }
  }

  async function runQty() {
    setQtyRun(true)
    try {
      const r = await fetch(`${API}/run-qty`)
      if (!r.ok) { const e = await r.json(); alert(e.detail); return }
      await loadStatus()
      setTab('qty')
    } finally { setQtyRun(false) }
  }

  // the Qty tab's filter choices come with its slice
  const months  = qtyView?.months || []
  const curMonth = fMonth || qtyView?.month
  const stores  = ['ALL', ...(qtyView?.stores || [])]
  const divs    = ['ALL', ...(qtyView?.divisions || [])]
  const depts   = ['ALL', ...(qtyView?.depts || [])]

  const canRun      = status?.contrib_ok && status?.dept_plan_ok && status?.mrp_plan_ok && !running
  const canValidate = status?.plan_run && !validating
  const canQty      = valResult?.gate_open && status?.asp_imported && !qtyRun

  // anomaly filter
  const allAnoms = valResult?.anomalies || []
  const filtAnoms = fSev === 'ALL' ? allAnoms : allAnoms.filter(a => a.severity === fSev)

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.bg }}>
      {route?.route === 'article' && (
        <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 8, fontSize: 12.5, border: `1px solid ${alpha(theme.warning, '55')}`, background: alpha(theme.warning, '10'), color: theme.textPrimary }}>
          The Sales Plan runs on the <b>Article Name</b> branch. {prom?.promoted
            ? <>Display Type splits the MRP bands <b>promoted from the Article Name plan</b> ({prom.promoted_at}) - Run plan again after each promote. Their Table / Non-Table % come from the LY sales on each band.</>
            : <>It is not promoted to the MRP stage yet (Article Name Plan → Plan Output → Promote to MRP stage), so Display Type still splits the buyers' MRP bands.</>}
        </div>
      )}
      {/* Header */}
      <div className="sp-sub">
        Store × Dept × MRP × <strong>Table / Non-Table</strong> → ₹L plan and unit quantity
      </div>

      {/* System status strip */}
      {status && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
          {[
            { label: 'Dept Plan',   ok: status.dept_plan_ok },
            { label: 'MRP Plan',    ok: status.mrp_plan_ok  },
            { label: 'Table / Non-Table %', ok: status.contrib_ok, sub: status.contrib_ok ? 'from LY' : null },
            { label: 'ASP',         ok: status.asp_imported, sub: status.asp_rows ? `${status.asp_rows} rows` : null },
            { label: 'Plan Run',    ok: status.plan_run,   sub: status.plan_date || null },
            { label: 'Qty Run',     ok: status.qty_run,    sub: status.qty_date  || null },
          ].map(({ label, ok, sub }) => (
            <div key={label} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '6px 12px', borderRadius: 7,
              background: ok ? `${alpha(theme.success,'14')}` : theme.surface,
              border: `1px solid ${ok ? theme.success : theme.border}`,
              fontSize: 11,
            }}>
              <span style={{ color: ok ? theme.success : theme.textMuted, fontWeight: 700 }}>
                {ok ? '✓' : '○'}
              </span>
              <span style={{ color: ok ? theme.textPrimary : theme.textMuted, fontWeight: ok ? 600 : 400 }}>
                {label}
              </span>
              {sub && <span style={{ color: theme.textMuted, fontFamily: MONO, fontSize: 10 }}>{sub}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Uploads */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 22 }}>
        {/* Table / Non-Table % are no longer uploaded (user, 2026-10-14: "Cont % should be according the Re-apportioned
            MRPs and their respective Display types % as per LY sales") */}
        <div style={{ flex: 1, border: `1px solid ${status?.contrib_ok ? theme.success : theme.border}`, borderRadius: 10, padding: '20px 22px',
          background: status?.contrib_ok ? alpha(theme.success, '08') : theme.surface }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPrimary, marginBottom: 3 }}>Table / Non-Table %</div>
          <div style={{ fontSize: 11.5, color: theme.textMuted, lineHeight: 1.6 }}>
            No upload: each store × department × new MRP × month splits by its own LY sales on that MRP by display type
            (MRP Re-apportionment). A store that didn't sell the MRP that month takes its own mix over the months, then the chain's.
          </div>
          <div style={{ fontSize: 11, marginTop: 8, color: status?.contrib_ok ? theme.success : theme.danger }}>
            {status ? (status.contrib_ok ? `From the ${status.contrib_from}` : `Not available: ${status.contrib_from}`) : ''}
          </div>
        </div>
      </div>

      <AspCard status={status} onDone={loadStatus} />

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 28, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={runPlan} disabled={!canRun} style={btnStyle(canRun, theme.primary)}>
          {running ? 'Computing…' : status?.plan_run ? '↻ Re-run Plan' : '▶ Run Plan'}
        </button>

        {status?.plan_run && (
          <button onClick={runValidate} disabled={!canValidate} style={btnStyle(canValidate, '#D97706')}>
            {validating ? 'Validating…' : '✓ Validate'}
          </button>
        )}

        {valResult && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', borderRadius: 8, background: valResult.gate_open ? `${alpha(theme.success,'14')}` : `${alpha(theme.danger,'14')}`, border: `1px solid ${valResult.gate_open ? theme.success : theme.danger}` }}>
            <span style={{ fontSize: 13 }}>{valResult.gate_open ? '🟢' : '🔴'}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: valResult.gate_open ? theme.success : theme.danger }}>
              {valResult.gate_open ? 'Gate Open' : 'Gate Blocked'}
            </span>
            <span style={{ fontSize: 11, color: theme.textMuted }}>
              {valResult.errors}E / {valResult.warnings}W
            </span>
          </div>
        )}

        {valResult?.gate_open && (
          <button onClick={runQty} disabled={!canQty} style={btnStyle(canQty, '#4F46E5')}>
            {qtyRun ? 'Computing Qty…' : status?.qty_run ? '↻ Re-run Qty' : '📦 Run Qty'}
          </button>
        )}

        {status?.qty_run && (
          <a href={`${API}/export`} style={btnStyle(true, 'var(--st-accent,#4F7A66)', true)}
            title="Every field from store to display type and qty (CSV, all stores). Filtered / Excel exports: Number journey page">↓ Export all fields (CSV)</a>
        )}
      </div>

      {/* Tab bar */}
      {(
        <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: `1px solid ${theme.border}`, paddingBottom: 0 }}>
          {[
            ['plan',     '₹L Plan',    true],
            ['validate', 'Validation', !!valResult,  valResult?.errors > 0 ? theme.danger : valResult?.warnings > 0 ? '#D97706' : theme.success],
            ['qty',      'Qty Plan',   !!status?.qty_run],
          ].map(([k, lbl, enabled, accentC]) => (
            <button key={k} onClick={() => enabled && setTab(k)} disabled={!enabled} style={{
              padding: '9px 18px', border: 'none',
              borderBottom: tab === k ? `3px solid ${accentC || theme.primary}` : '3px solid transparent',
              background: 'transparent', cursor: enabled ? 'pointer' : 'not-allowed',
              fontWeight: tab === k ? 700 : 400, fontSize: 13,
              color: !enabled ? theme.textMuted : tab === k ? (accentC || theme.primary) : theme.textSecondary,
            }}>
              {lbl}
              {k === 'validate' && valResult && (
                <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 800,
                  color: valResult.errors > 0 ? theme.danger : valResult.warnings > 0 ? '#D97706' : theme.success }}>
                  {valResult.errors > 0 ? `${valResult.errors} ERR` : valResult.warnings > 0 ? `${valResult.warnings} WARN` : '✓'}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* ── PLAN TAB ── */}
      {tab === 'plan' && (
        <HierarchyView api="/api/planning/grain/display-view" levels={DT_FIELDS} defaults={['division', 'department', 'mrp', 'display']}
          store="sp.dt" versions={false} halves />
      )}

      {/* ── VALIDATE TAB ── */}
      {tab === 'validate' && valResult && (
        <ValidateView anoms={filtAnoms} all={allAnoms} fSev={fSev} setFSev={setFSev} summary={valResult} />
      )}

      {/* ── QTY TAB ── */}
      {tab === 'qty' && qtyErr && <div style={{ fontSize: 12.5, color: theme.danger }}>{qtyErr}</div>}
      {tab === 'qty' && !qtyView && !qtyErr && <div style={{ fontSize: 12.5, color: theme.textMuted }}>Loading the Qty run…</div>}
      {tab === 'qty' && qtyView && (
        <PlanView rows={qtyView.rows} months={months} curMonth={curMonth} setFMonth={setFMonth}
          stores={stores} fStore={fStore} setFStore={setFStore}
          divs={divs} fDiv={fDiv} setFDiv={v => { setFDiv(v); setFDept('ALL') }}
          depts={depts} fDept={fDept} setFDept={setFDept}
          showQty={true} missingAsp={qtyView.missing_asp || 0} totals={qtyView.totals} totalRows={qtyView.total_rows}
        />
      )}

    </div>
  )
}

// ── Plan / Qty view ────────────────────────────────────────────────────────────
function PlanView({ rows, months, curMonth, setFMonth, stores, fStore, setFStore, divs, fDiv, setFDiv, depts, fDept, setFDept, showQty, missingAsp, totals, totalRows }) {
  // totals of every row inside the filters (the server's), not only of the rows listed
  const totalMrp   = totals?.mrp_plan ?? rows.reduce((s, r) => s + (r.mrp_plan || 0), 0)
  const totalTable = totals?.table_plan ?? rows.reduce((s, r) => s + (r.table_plan || 0), 0)
  const totalNonT  = totals?.nontable_plan ?? rows.reduce((s, r) => s + (r.nontable_plan || 0), 0)

  return (
    <>
      {/* Month tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        {months.map(m => (
          <button key={m} onClick={() => setFMonth(m)} style={{
            padding: '5px 14px', borderRadius: 7, fontSize: 11, cursor: 'pointer',
            fontWeight: curMonth === m ? 700 : 400,
            border: `1.5px solid ${curMonth === m ? theme.primary : theme.border}`,
            background: curMonth === m ? `${alpha(theme.primary,'22')}` : theme.surface,
            color: curMonth === m ? theme.primary : theme.textSecondary,
          }}>{m}</button>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        {[
          ['Store', stores, fStore, setFStore],
          ['Division', divs, fDiv, setFDiv],
          ['Department', depts, fDept, setFDept],
        ].map(([lbl, opts, val, setVal]) => (
          <div key={lbl} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600 }}>{lbl.toUpperCase()}</span>
            <select value={val} onChange={e => setVal(e.target.value)} style={{
              background: theme.surface, color: theme.textPrimary,
              border: `1px solid ${theme.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 12,
            }}>
              {opts.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        ))}
        {showQty && missingAsp > 0 && (
          <span style={{ fontSize: 11, color: '#D97706', fontWeight: 600, marginLeft: 'auto' }}>
            ⚠ {Number(missingAsp).toLocaleString('en-IN')} projected values with no ASP (all months)
          </span>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        {[
          { label: 'Rows', val: totalRows != null && totalRows > rows.length ? `${rows.length.toLocaleString('en-IN')} of ${totalRows.toLocaleString('en-IN')} (largest first)` : (totalRows ?? rows.length).toLocaleString('en-IN'), c: theme.textPrimary },
          ...(totals ? [{ label: 'Table Qty', val: Math.round(totals.table_qty).toLocaleString('en-IN'), c: theme.primary },
                        { label: 'Non-Table Qty', val: Math.round(totals.nontable_qty).toLocaleString('en-IN'), c: '#D97706' }] : []),
          { label: 'MRP Plan (₹L)', val: totalMrp.toFixed(2), c: theme.accent },
          { label: 'Table Plan (₹L)', val: totalTable.toFixed(2), c: theme.primary },
          { label: 'Non-Table Plan (₹L)', val: totalNonT.toFixed(2), c: '#D97706' },
        ].map(({ label, val, c }) => (
          <div key={label} style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '10px 16px', flex: 1 }}>
            <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>{label}</div>
            <div style={{ fontSize: 15, fontWeight: 700, fontFamily: MONO, color: c, marginTop: 3 }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div style={{ background: theme.surface, borderRadius: 10, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
            <thead>
              <tr style={{ background: theme.surfaceAlt, borderBottom: `2px solid ${theme.border}` }}>
                <th style={{ ...HDR, textAlign: 'left', paddingLeft: 14 }}>Store</th>
                <th style={{ ...HDR, textAlign: 'left' }}>Division</th>
                <th style={{ ...HDR, textAlign: 'left' }}>Department</th>
                <th style={{ ...HDR }}>MRP</th>
                <th style={{ ...HDR }}>Table%</th>
                <th style={{ ...HDR }}>Non-Table%</th>
                <th style={{ ...HDR, color: theme.accent }}>MRP Plan ₹L</th>
                <th style={{ ...HDR, color: theme.primary }}>Table ₹L</th>
                <th style={{ ...HDR, color: '#D97706' }}>Non-Table ₹L</th>
                {showQty && <th style={{ ...HDR, color: theme.primary }}>Table Qty</th>}
                {showQty && <th style={{ ...HDR, color: '#D97706' }}>Non-Table Qty</th>}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={showQty ? 11 : 9} style={{ padding: 24, textAlign: 'center', color: theme.textMuted }}>No data for this filter.</td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={`${r.store}-${r.dept}-${r.mrp}-${i}`} style={{
                  borderBottom: `1px solid ${theme.border}`,
                  background: !r.has_contrib ? `${alpha(theme.danger,'0a')}` : i % 2 === 0 ? 'transparent' : theme.surfaceAlt,
                }}>
                  <td style={{ ...CELL, textAlign: 'left', paddingLeft: 14, fontWeight: 600 }}>{r.store}</td>
                  <td style={{ ...CELL, textAlign: 'left', color: theme.textMuted }}>{r.division}</td>
                  <td style={{ ...CELL, textAlign: 'left', color: theme.textPrimary }}>{r.dept}</td>
                  <td style={{ ...CELL }}>₹{r.mrp}</td>
                  <td style={{ ...CELL, color: theme.primary }}>{r.table_contrib?.toFixed(1)}%</td>
                  <td style={{ ...CELL, color: '#D97706' }}>{r.nontable_contrib?.toFixed(1)}%</td>
                  <td style={{ ...CELL, fontWeight: 600, color: theme.accent }}>{r.mrp_plan?.toFixed(4)}</td>
                  <td style={{ ...CELL, color: theme.primary }}>{r.table_plan?.toFixed(4)}</td>
                  <td style={{ ...CELL, color: '#D97706' }}>{r.nontable_plan?.toFixed(4)}</td>
                  {showQty && <td style={{ ...CELL, color: theme.primary }}>
                    {r.table_qty != null ? Number(r.table_qty).toLocaleString() : <span style={{ color: theme.textMuted }}>—</span>}
                  </td>}
                  {showQty && <td style={{ ...CELL, color: '#D97706' }}>
                    {r.nontable_qty != null ? Number(r.nontable_qty).toLocaleString() : <span style={{ color: theme.textMuted }}>—</span>}
                  </td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

// ── Validate view ──────────────────────────────────────────────────────────────
function ValidateView({ anoms, all, fSev, setFSev, summary }) {
  const byLevel = {}
  all.forEach(a => {
    if (!byLevel[a.level]) byLevel[a.level] = { error: 0, warning: 0, info: 0 }
    byLevel[a.level][a.severity] = (byLevel[a.level][a.severity] || 0) + 1
  })

  return (
    <>
      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {[
          { label: 'Total Anomalies', val: summary.total,    c: theme.textPrimary },
          { label: 'Errors (Gate)',   val: summary.errors,   c: theme.danger },
          { label: 'Warnings',        val: summary.warnings, c: '#D97706' },
          { label: 'Gate Status',     val: summary.gate_open ? 'OPEN' : 'BLOCKED', c: summary.gate_open ? theme.success : theme.danger },
        ].map(({ label, val, c }) => (
          <div key={label} style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '10px 16px', flex: 1 }}>
            <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 600 }}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 800, fontFamily: MONO, color: c, marginTop: 3 }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Level breakdown */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {Object.entries(byLevel).map(([level, counts]) => (
          <div key={level} style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '8px 14px', fontSize: 12 }}>
            <div style={{ fontWeight: 700, color: theme.textPrimary, marginBottom: 4 }}>{level}</div>
            {counts.error > 0   && <span style={{ color: theme.danger, marginRight: 8 }}>{counts.error} error{counts.error > 1 ? 's' : ''}</span>}
            {counts.warning > 0 && <span style={{ color: '#D97706',   marginRight: 8 }}>{counts.warning} warn{counts.warning > 1 ? 's' : ''}</span>}
          </div>
        ))}
      </div>

      {/* Severity filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: theme.textMuted, fontWeight: 600 }}>SHOW</span>
        {['ALL', 'error', 'warning'].map(s => (
          <button key={s} onClick={() => setFSev(s)} style={{
            padding: '4px 12px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
            fontWeight: fSev === s ? 700 : 400,
            border: `1.5px solid ${fSev === s ? (SEV_STYLE[s]?.color || theme.primary) : theme.border}`,
            background: fSev === s ? `${SEV_STYLE[s]?.bg || theme.primary}` : theme.surface,
            color: fSev === s ? (SEV_STYLE[s]?.color || theme.primary) : theme.textSecondary,
          }}>{s === 'ALL' ? 'All' : s === 'error' ? '🔴 Errors' : '🟡 Warnings'}</button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: theme.textMuted }}>{anoms.length} shown</span>
      </div>

      {anoms.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: theme.success, fontSize: 14, fontWeight: 600 }}>
          ✓ No anomalies found for this filter
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {anoms.map((a, i) => (
          <div key={i} style={{
            background: theme.surface, border: `1px solid ${a.severity === 'error' ? theme.danger : a.severity === 'warning' ? '#D97706' : theme.border}`,
            borderLeft: `4px solid ${a.severity === 'error' ? theme.danger : '#D97706'}`,
            borderRadius: 8, padding: '14px 16px',
          }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <SevChip sev={a.severity} />
              <span style={{ fontWeight: 700, fontSize: 12, color: theme.textPrimary }}>{a.level}</span>
              <span style={{ fontFamily: MONO, fontSize: 11, color: theme.textMuted }}>
                {[a.store, a.dept, a.mrp !== 'ALL' && `₹${a.mrp}`, a.month].filter(Boolean).join(' · ')}
              </span>
              {a.expected != null && (
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 11, color: theme.textMuted }}>
                  expected: {a.expected} · actual: {a.actual} · gap: <span style={{ color: theme.danger, fontWeight: 700 }}>{a.gap > 0 ? '+' : ''}{a.gap}</span>
                </span>
              )}
            </div>
            <div style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.6 }}>{a.message}</div>
          </div>
        ))}
      </div>
    </>
  )
}

// ── button style helper ────────────────────────────────────────────────────────
function btnStyle(enabled, color, isLink) {
  const base = {
    padding: '10px 22px', borderRadius: 8, fontWeight: 700, fontSize: 13,
    border: 'none', cursor: enabled ? 'pointer' : 'not-allowed',
    background: enabled ? color : theme.surfaceAlt,
    color: enabled ? '#fff' : theme.textMuted,
    textDecoration: 'none', display: 'inline-block',
  }
  return base
}
