import { useEffect, useState } from 'react'
import { theme, alpha } from '../theme'

// Number journey (user, 2026-10-14: "i want a journey mapper in the side tile where i can know about how a number was
// derived till udf. Make sure that each and every contribution towards the numbers are mapped in a plain flow. Also i
// want all the fields availble for export till display type") - GET /display-type/journey (engines/journey.py): one
// store x department x month (x MRP x display type) from its sources to qty, each step re-derived and checked.
const API = '/api/planning/display-type'
const L = v => `₹${(v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} L`
const STAGE_C = { Store: '#475569', Department: '#1F4D3A', MRP: '#7C3AED', 'Display type': '#B45309', Qty: '#0E7490' }

async function get(url) {
  const r = await fetch(url)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`)
  return j
}

export default function Journey() {
  const [opt, setOpt] = useState(null)
  const [sel, setSel] = useState({ store: '', dept: '', month: '', mrp: '', display: '' })
  const [j, setJ] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [ex, setEx] = useState({ division: '', group: '' })
  const set = k => e => setSel(s => ({ ...s, [k]: e.target.value, ...(k === 'store' ? { dept: '', mrp: '' } : k === 'dept' ? { mrp: '' } : {}) }))

  useEffect(() => {
    get(`${API}/journey/options?${new URLSearchParams({ store: sel.store, dept: sel.dept })}`)
      .then(o => {
        setOpt(o)
        setSel(s => ({
          ...s,
          store: s.store || o.stores[0]?.store || '',
          month: s.month || o.months[0] || '',
          dept: s.dept || [...(o.depts || [])].sort((a, b) => b.ty - a.ty)[0]?.dept || '',
        }))
      })
      .catch(e => setErr(e.message))
  }, [sel.store, sel.dept])

  useEffect(() => {
    if (!sel.store || !sel.dept || !sel.month) return
    setBusy(true); setErr('')
    get(`${API}/journey?${new URLSearchParams(sel)}`).then(setJ).catch(e => { setErr(e.message); setJ(null) }).finally(() => setBusy(false))
  }, [sel.store, sel.dept, sel.month, sel.mrp, sel.display])

  const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12 }
  const lab = { fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, display: 'grid', gap: 4 }
  const sel_ = { height: 32, padding: '0 8px', borderRadius: 7, border: `1px solid ${theme.border}`, fontSize: 13, background: theme.surface, color: theme.textPrimary, minWidth: 150 }
  const groups = ['SSG', 'NSO', 'Others']
  const btn = primary => ({ padding: '7px 14px', borderRadius: 7, fontSize: 12.5, fontWeight: 700, cursor: 'pointer', textDecoration: 'none',
    border: `1px solid ${primary ? theme.primary : theme.border}`, background: primary ? theme.primary : theme.surface, color: primary ? '#fff' : theme.textPrimary })
  const exq = fmt => `${API}/export?${new URLSearchParams({ format: fmt, ...(ex.division ? { division: ex.division } : {}), ...(ex.group ? { group: ex.group } : {}) })}`

  return (
    <div style={{ padding: '24px 32px', display: 'grid', gap: 16, alignContent: 'start' }}>
      <div style={{ ...card, padding: '14px 18px' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: theme.navy }}>How a plan number is made - from its sources down to UDF and pieces</div>
        <div style={{ fontSize: 12.5, color: theme.textMuted, marginTop: 4 }}>
          Pick a store, department and month (and an MRP, to go down to display type and qty). Every step is worked out again from its own input
          and the department step is checked against the saved plan.
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
          <label style={lab}>Store
            <select value={sel.store} onChange={set('store')} style={sel_} aria-label="Store">
              {groups.map(g => (
                <optgroup key={g} label={`${g} (${(opt?.stores || []).filter(s => s.group === g).length})`}>
                  {(opt?.stores || []).filter(s => s.group === g).map(s => <option key={s.store} value={s.store}>{s.store} · {s.cluster}</option>)}
                </optgroup>))}
            </select>
          </label>
          <label style={lab}>Department
            <select value={sel.dept} onChange={set('dept')} style={{ ...sel_, minWidth: 230 }} aria-label="Department">
              {['KIDS', 'LADIES', 'MENS'].map(dv => (
                <optgroup key={dv} label={dv}>
                  {(opt?.depts || []).filter(d => d.division === dv).map(d => <option key={d.dept} value={d.dept}>{d.dept}</option>)}
                </optgroup>))}
            </select>
          </label>
          <label style={lab}>Month
            <select value={sel.month} onChange={set('month')} style={sel_} aria-label="Month">
              {(opt?.months || []).map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label style={lab}>MRP
            <select value={sel.mrp} onChange={set('mrp')} style={sel_} aria-label="MRP">
              <option value="">— department only —</option>
              {(j?.mrps || []).map(m => <option key={m.mrp} value={m.mrp}>{m.mrp} · {L(m.ty)}</option>)}
            </select>
          </label>
          <label style={lab}>Display type
            <select value={sel.display} onChange={set('display')} style={sel_} aria-label="Display type" disabled={!sel.mrp}>
              <option value="">Table and Non-Table</option>
              <option value="TABLE">Table</option>
              <option value="NON_TABLE">Non-Table</option>
            </select>
          </label>
        </div>
      </div>

      {err && <div style={{ color: theme.danger, fontSize: 13 }}>{err}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16, alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: 0, opacity: busy ? 0.6 : 1 }} aria-busy={busy}>
          {(j?.steps || []).map((s, i) => (
            <div key={i}>
              {i > 0 && <div aria-hidden="true" style={{ textAlign: 'center', color: theme.textMuted, lineHeight: '18px' }}>↓</div>}
              <div style={{ ...card, padding: '10px 14px', borderLeft: `4px solid ${STAGE_C[s.stage] || theme.border}`,
                background: s.check === false ? alpha(theme.danger, '0c') : theme.surface }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase', color: STAGE_C[s.stage] || theme.textMuted }}>{s.stage}</span>
                  <b style={{ fontSize: 13.5, color: theme.textPrimary, flex: 1 }}>{s.title}{s.check === true ? ' ✓' : s.check === false ? ' ✗' : ''}</b>
                  {s.value != null && (
                    <b style={{ fontFamily: theme.fontMono, fontSize: 14, color: theme.navy }}>
                      {s.unit === 'pieces' ? `${Math.round(s.value).toLocaleString('en-IN')} pcs` : s.unit ? L(s.value) : ''}
                    </b>)}
                </div>
                <div style={{ fontSize: 12.5, color: theme.textSecondary, marginTop: 4, lineHeight: 1.5 }}>{s.text}</div>
                {s.formula && <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 4, fontFamily: theme.fontMono }}>{s.formula}</div>}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          {j?.mrps?.length > 0 && (
            <div style={{ ...card, padding: '12px 14px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>MRP split · {j.month}</div>
              <div style={{ fontSize: 11.5, color: theme.textMuted, margin: '4px 0 8px' }}>From {j.mrp_source}. Click an MRP to follow it.</div>
              <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                {j.mrps.map(m => (
                  <button key={m.mrp} type="button" onClick={() => setSel(s => ({ ...s, mrp: m.mrp }))}
                    style={{ all: 'unset', cursor: 'pointer', display: 'flex', width: '100%', boxSizing: 'border-box', gap: 8, padding: '4px 6px', borderRadius: 6, fontSize: 12.5,
                      background: sel.mrp === m.mrp ? alpha(theme.primary, '14') : undefined }}>
                    <b style={{ width: 60 }}>{m.mrp}</b>
                    <span style={{ flex: 1, color: theme.textMuted, fontFamily: theme.fontMono }}>{m.p1_pct.toFixed(2)}% / {m.p2_pct.toFixed(2)}%</span>
                    <span style={{ fontFamily: theme.fontMono }}>{L(m.ty)}</span>
                  </button>))}
              </div>
            </div>
          )}
          <div style={{ ...card, padding: '12px 14px', display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>Export every field</div>
            <div style={{ fontSize: 11.5, color: theme.textMuted }}>
              One row per store × department × MRP × month: store group, reference store, LY, BIS growth, AOP hold, department plan and share,
              MRP share and plan, Table / Non-Table %, where the mix came from, ASP and qty.
            </div>
            <label style={lab}>Division
              <select value={ex.division} onChange={e => setEx(x => ({ ...x, division: e.target.value }))} style={sel_} aria-label="Export division">
                <option value="">All divisions</option>{['KIDS', 'LADIES', 'MENS'].map(d => <option key={d}>{d}</option>)}
              </select>
            </label>
            <label style={lab}>Store group
              <select value={ex.group} onChange={e => setEx(x => ({ ...x, group: e.target.value }))} style={sel_} aria-label="Export store group">
                <option value="">All stores</option>{groups.map(g => <option key={g}>{g}</option>)}
              </select>
            </label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <a href={exq('csv')} style={btn(true)}>⬇ CSV</a>
              <a href={exq('xlsx')} style={btn(false)} title="Excel takes up to 1,000,000 rows - all stores and divisions together are ~700k">⬇ Excel</a>
            </div>
            <div style={{ fontSize: 11, color: theme.textMuted }}>All stores and divisions: ~700k rows, about a minute to build.</div>
          </div>
        </div>
      </div>
    </div>
  )
}
