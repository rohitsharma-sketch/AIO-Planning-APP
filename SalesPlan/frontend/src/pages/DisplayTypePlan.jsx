import { useState, useEffect, useRef } from 'react'
import { theme } from '../theme'

const API = '/api/planning/display-type'

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
      background: imported ? `${theme.success}08` : theme.surface,
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

// ── main page ──────────────────────────────────────────────────────────────────
export default function DisplayTypePlan() {
  const [status,   setStatus]   = useState(null)
  const [tab,      setTab]      = useState('plan')   // plan | validate | qty | export
  const [running,  setRunning]  = useState(false)
  const [validating, setValid]  = useState(false)
  const [qtyRun,   setQtyRun]  = useState(false)

  // plan result
  const [planResult, setPlanResult] = useState(null)
  const [valResult,  setValResult]  = useState(null)
  const [qtyResult,  setQtyResult]  = useState(null)

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

  async function loadPlan() {
    const r = await fetch(`${API}/result`)
    if (r.ok) {
      const d = await r.json()
      setPlanResult(d)
      if (!fMonth && d.months?.length) setFMonth(d.months[0])
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  useEffect(() => {
    if (status?.plan_run && !planResult) loadPlan()
    if (status?.qty_run && !qtyResult) {
      fetch(`${API}/qty-result`).then(r => r.json()).then(d => setQtyResult(d))
    }
  }, [status])

  async function runPlan() {
    setRunning(true)
    try {
      const r = await fetch(`${API}/run-plan`)
      if (!r.ok) { const e = await r.json(); alert(e.detail); return }
      await loadPlan()
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
      const d = await fetch(`${API}/qty-result`).then(x => x.json())
      setQtyResult(d)
      await loadStatus()
      setTab('qty')
    } finally { setQtyRun(false) }
  }

  // derive filter options
  const activeData = tab === 'qty' && qtyResult ? qtyResult : planResult
  const rows = activeData?.rows || []
  const months  = activeData?.months || []
  const curMonth = fMonth || months[0]

  const stores  = ['ALL', ...new Set(rows.map(r => r.store))]
  const divs    = ['ALL', ...new Set(rows.map(r => r.division))]
  const depts   = ['ALL', ...new Set(rows.map(r => r.dept))]

  const filtered = rows.filter(r =>
    r.month === curMonth &&
    (fStore === 'ALL' || r.store === fStore) &&
    (fDiv   === 'ALL' || r.division === fDiv) &&
    (fDept  === 'ALL' || r.dept === fDept)
  )

  const canRun      = status?.contrib_imported && status?.dept_plan_ok && status?.mrp_plan_ok && !running
  const canValidate = status?.plan_run && !validating
  const canQty      = valResult?.gate_open && status?.asp_imported && !qtyRun

  // anomaly filter
  const allAnoms = valResult?.anomalies || []
  const filtAnoms = fSev === 'ALL' ? allAnoms : allAnoms.filter(a => a.severity === fSev)

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.bg }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: theme.textPrimary, margin: 0 }}>Display Type Plan</h1>
        <p style={{ fontSize: 13, color: theme.textMuted, margin: '6px 0 0 0' }}>
          Store × Dept × MRP × <strong>Table / Non-Table</strong> → ₹L plan and unit quantity
        </p>
      </div>

      {/* System status strip */}
      {status && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
          {[
            { label: 'Dept Plan',   ok: status.dept_plan_ok },
            { label: 'MRP Plan',    ok: status.mrp_plan_ok  },
            { label: 'Contributions', ok: status.contrib_imported, sub: status.contrib_rows ? `${status.contrib_rows} rows` : null },
            { label: 'ASP',         ok: status.asp_imported, sub: status.asp_rows ? `${status.asp_rows} rows` : null },
            { label: 'Plan Run',    ok: status.plan_run,   sub: status.plan_date || null },
            { label: 'Qty Run',     ok: status.qty_run,    sub: status.qty_date  || null },
          ].map(({ label, ok, sub }) => (
            <div key={label} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '6px 12px', borderRadius: 7,
              background: ok ? `${theme.success}14` : theme.surface,
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
        <UploadBox
          label="Display Type Contributions"
          subtitle="Store | Division | Department | MRP | Table% | Non-Table%"
          endpoint="import/contributions"
          onDone={loadStatus}
          imported={status?.contrib_imported}
          rows={status?.contrib_rows}
          date={status?.contrib_date}
          color={theme.primary}
        />
        <UploadBox
          label="Month-wise ASP"
          subtitle="Division | Department | MRP | Display Type | Mar'27 | Apr'27 | …"
          endpoint="import/asp"
          onDone={loadStatus}
          imported={status?.asp_imported}
          rows={status?.asp_rows}
          date={status?.asp_date}
          color="#4F46E5"
        />
      </div>

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', borderRadius: 8, background: valResult.gate_open ? `${theme.success}14` : `${theme.danger}14`, border: `1px solid ${valResult.gate_open ? theme.success : theme.danger}` }}>
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
          <a href={`${API}/export`} style={btnStyle(true, '#0D9488', true)}>↓ Export Excel</a>
        )}
      </div>

      {/* Tab bar */}
      {(planResult || valResult) && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: `1px solid ${theme.border}`, paddingBottom: 0 }}>
          {[
            ['plan',     '₹L Plan',    !!planResult],
            ['validate', 'Validation', !!valResult,  valResult?.errors > 0 ? theme.danger : valResult?.warnings > 0 ? '#D97706' : theme.success],
            ['qty',      'Qty Plan',   !!qtyResult],
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
      {tab === 'plan' && planResult && (
        <PlanView rows={filtered} months={months} curMonth={curMonth} setFMonth={setFMonth}
          stores={stores} fStore={fStore} setFStore={setFStore}
          divs={divs} fDiv={fDiv} setFDiv={setFDiv}
          depts={depts} fDept={fDept} setFDept={setFDept}
          showQty={false}
        />
      )}

      {/* ── VALIDATE TAB ── */}
      {tab === 'validate' && valResult && (
        <ValidateView anoms={filtAnoms} all={allAnoms} fSev={fSev} setFSev={setFSev} summary={valResult} />
      )}

      {/* ── QTY TAB ── */}
      {tab === 'qty' && qtyResult && (
        <PlanView rows={filtered} months={months} curMonth={curMonth} setFMonth={setFMonth}
          stores={stores} fStore={fStore} setFStore={setFStore}
          divs={divs} fDiv={fDiv} setFDiv={setFDiv}
          depts={depts} fDept={fDept} setFDept={setFDept}
          showQty={true} missingAsp={qtyResult.missing_asp?.length || 0}
        />
      )}

      {!planResult && !running && (
        <div style={{ textAlign: 'center', padding: 60, color: theme.textMuted, fontSize: 13 }}>
          {canRun ? 'Click "Run Plan" to compute Display Type plan.' : 'Import contributions above, then run plan.'}
        </div>
      )}
    </div>
  )
}

// ── Plan / Qty view ────────────────────────────────────────────────────────────
function PlanView({ rows, months, curMonth, setFMonth, stores, fStore, setFStore, divs, fDiv, setFDiv, depts, fDept, setFDept, showQty, missingAsp }) {
  const totalMrp   = rows.reduce((s, r) => s + (r.mrp_plan || 0), 0)
  const totalTable = rows.reduce((s, r) => s + (r.table_plan || 0), 0)
  const totalNonT  = rows.reduce((s, r) => s + (r.nontable_plan || 0), 0)

  return (
    <>
      {/* Month tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        {months.map(m => (
          <button key={m} onClick={() => setFMonth(m)} style={{
            padding: '5px 14px', borderRadius: 7, fontSize: 11, cursor: 'pointer',
            fontWeight: curMonth === m ? 700 : 400,
            border: `1.5px solid ${curMonth === m ? theme.primary : theme.border}`,
            background: curMonth === m ? `${theme.primary}22` : theme.surface,
            color: curMonth === m ? theme.primaryLight : theme.textSecondary,
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
            ⚠ {missingAsp} rows missing ASP
          </span>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        {[
          { label: 'Rows', val: rows.length, c: theme.textPrimary },
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
                  background: !r.has_contrib ? `${theme.danger}0a` : i % 2 === 0 ? 'transparent' : theme.surfaceAlt,
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
