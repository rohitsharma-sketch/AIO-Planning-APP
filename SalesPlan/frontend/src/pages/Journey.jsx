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
  const [openAll, setOpenAll] = useState(false)
  // Company (holistic) | Store - the last choice is this user's default on this browser (user, 2026-10-16)
  const [scope, setScope_] = useState(() => { try { return localStorage.getItem('sp.journey.scope') || 'store' } catch { return 'store' } })
  const setScope = v => { setScope_(v); try { localStorage.setItem('sp.journey.scope', v) } catch { /* private window */ } }
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

  const scopeBar = (
    <div role="radiogroup" aria-label="Show" style={{ display: 'inline-flex', border: `1px solid ${theme.border}`, borderRadius: 8, overflow: 'hidden' }}>
      {[['company', 'Company (holistic)'], ['store', 'Store specific']].map(([k, t]) => (
        <button key={k} type="button" role="radio" aria-checked={scope === k} onClick={() => setScope(k)}
          style={{ padding: '6px 14px', fontSize: 12.5, fontWeight: 700, border: 'none', cursor: 'pointer',
            background: scope === k ? theme.primary : theme.surface, color: scope === k ? '#fff' : theme.textPrimary }}>{t}</button>))}
    </div>)
  if (scope === 'company') return (
    <div style={{ padding: '24px 32px', display: 'grid', gap: 16, alignContent: 'start' }}>
      <CompanyBridge scopeBar={scopeBar} />
    </div>)

  return (
    <div style={{ padding: '24px 32px', display: 'grid', gap: 16, alignContent: 'start' }}>
      <div style={{ ...card, padding: '14px 18px' }}>
        <div style={{ marginBottom: 10 }}>{scopeBar}</div>
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
                  {(opt?.stores || []).filter(s => s.group === g).map(s => <option key={s.store} value={s.store}>{s.store} · {s.group} · {s.cluster}</option>)}
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
          <a href={sel.store && sel.dept && sel.month ? `${API}/journey/export?${new URLSearchParams(sel)}` : undefined}
            style={{ ...btn(true), alignSelf: 'end', height: 18, display: 'inline-flex', alignItems: 'center' }}
            title="This journey in plain words (one row per step, with its calculation) + every MRP of the department to UDF">⬇ Excel (this journey)</a>
        </div>
      </div>

      {err && <div style={{ color: theme.danger, fontSize: 13 }}>{err}</div>}
      {!opt && !err && <div style={{ fontSize: 12.5, color: theme.textMuted }}>Loading the stores and departments… (the first time after the platform restarts it reads the whole plan - up to a minute)</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16, alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: 0, opacity: busy ? 0.6 : 1 }} aria-busy={busy}>
          {/* the deviation journey (user, 2026-10-15: "explain in simplest words what affected to arrive at this number") */}
          {j?.deviation?.length > 0 && (
            <div style={{ ...card, padding: '12px 16px', marginBottom: 14, borderLeft: `4px solid ${theme.navy}` }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <div style={{ flex: 1, fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>What moved this number - in plain words</div>
                <button type="button" onClick={() => setOpenAll(o => !o)} style={{ ...btn(false), padding: '3px 10px', fontSize: 11.5 }}>{openAll ? 'Collapse all' : 'Expand all'}</button>
              </div>
              <div style={{ fontSize: 13.5, color: theme.textPrimary, margin: '6px 0 10px', lineHeight: 1.55 }}>{j.story}</div>
              <div style={{ display: 'grid', gap: 6 }}>
                {j.deviation.map((d, i) => {
                  const up = d.change != null && d.change > 1e-9, down = d.change != null && d.change < -1e-9
                  const tag = d.kind === 'start' ? 'starts at' : d.kind === 'split' ? 'share' : d.kind === 'qty' ? 'pieces' : up ? 'pushed up' : down ? 'pulled down' : 'no change'
                  const col = d.kind === 'change' ? (up ? theme.success || '#15803d' : down ? theme.danger : theme.textMuted) : theme.textMuted
                  const more = (d.detail || []).length > 0 || d.share != null
                  return (
                    <details key={`${i}-${openAll}`} open={openAll} style={{ borderTop: i ? `1px solid ${theme.border}` : 'none' }}>
                      <summary style={{ display: 'grid', gridTemplateColumns: '18px 170px minmax(0, 1fr) 170px', gap: 10, alignItems: 'baseline',
                        padding: '6px 0', cursor: more ? 'pointer' : 'default', listStyle: 'none' }}>
                        <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 11 }}>{more ? '▸' : ''}</span>
                        <div>
                          <b style={{ fontSize: 13, color: theme.textPrimary }}>{d.what}</b>
                          <div style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4, color: col }}>{tag}</div>
                        </div>
                        <div style={{ fontSize: 12.5, color: theme.textSecondary, lineHeight: 1.5 }}>{d.why}</div>
                        <div style={{ textAlign: 'right', fontFamily: theme.fontMono, fontSize: 12.5 }}>
                          {d.kind === 'change' && <div style={{ color: col, fontWeight: 700 }}>{up ? '+' : down ? '−' : ''}{L(Math.abs(d.change))}{d.pct != null ? ` (${d.pct >= 0 ? '+' : ''}${d.pct.toFixed(2)}%)` : ''}</div>}
                          {d.share != null && <div style={{ fontSize: 11, color: theme.textMuted }}>{d.share.toFixed(1)}% of the change</div>}
                          {d.kind === 'qty'
                            ? <b>{d.after != null ? `${Math.round(d.after).toLocaleString('en-IN')} pcs` : '-'}</b>
                            : <b style={{ color: theme.navy }}>{L(d.after)}</b>}
                        </div>
                      </summary>
                      {more && (
                        <div style={{ margin: '0 0 8px 28px', padding: '8px 12px', borderRadius: 8, background: alpha(theme.primary, '0a'), fontSize: 12, color: theme.textSecondary, lineHeight: 1.6 }}>
                          {d.share != null && j.deviation_total && (
                            <div>Of the whole change from {String(j.deviation_total.from).toLowerCase()} ({L(j.deviation_total.start)}) to the plan ({L(j.deviation_total.plan)}) -
                              {' '}{j.deviation_total.change >= 0 ? '+' : '−'}{L(Math.abs(j.deviation_total.change))} - this step is <b>{d.share.toFixed(1)}%</b>.</div>)}
                          {(d.detail || []).map((t, k) => <div key={k} style={{ fontFamily: theme.fontMono, fontSize: 11.5 }}>{t}</div>)}
                        </div>)}
                    </details>)
                })}
              </div>
            </div>
          )}
          {j?.steps?.length > 0 && <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, margin: '0 0 8px' }}>Every step, worked out again</div>}
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
              One row per store × department × MRP × month: store group, reference store, LY, BIS growth, AOP cap, store balance, department plan and share,
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


// Company (holistic) deviation bridge (user, 2026-10-16: "How much of deviation is taken for this so that it gets recorded
// on holistic level too") - GET /display-type/journey/holistic: last year -> each effect -> the plan, every effect's share
// of the change, by division / month / store group / cluster / department; the same effects as the store journey, added up.
function CompanyBridge({ scopeBar }) {
  const [f, setF] = useState({ group: '', division: '', month: '' })
  const [h, setH] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    setBusy(true); setErr('')
    get(`${API}/journey/holistic?${new URLSearchParams(f)}`).then(setH).catch(e => setErr(e.message)).finally(() => setBusy(false))
  }, [f.group, f.division, f.month])
  const card = { background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12 }
  const lab = { fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, display: 'grid', gap: 4 }
  const sel_ = { height: 32, padding: '0 8px', borderRadius: 7, border: `1px solid ${theme.border}`, fontSize: 13, background: theme.surface, color: theme.textPrimary, minWidth: 150 }
  const sgn = v => `${v >= 0 ? '+' : '−'}${L(Math.abs(v))}`
  const col = v => v > 1e-9 ? (theme.success || '#15803d') : v < -1e-9 ? theme.danger : theme.textMuted
  const keys = (h?.bridge || []).map(b => b.key)
  const maxAbs = Math.max(1e-9, ...(h?.bridge || []).map(b => Math.abs(b.change)))
  const table = (title, rows, open) => (
    <details open={open} style={{ ...card, padding: '10px 14px' }}>
      <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>{title}</summary>
      <div style={{ overflowX: 'auto', marginTop: 8 }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
          <thead><tr>{['', 'Last year', 'Plan', 'Change', '%', ...keys.map(k => h.names[k])].map((t, i) => (
            <th key={i} style={{ textAlign: i ? 'right' : 'left', padding: '4px 8px', borderBottom: `1px solid ${theme.border}`, color: theme.textMuted, fontWeight: 700, whiteSpace: i > 4 ? 'normal' : 'nowrap', minWidth: i > 4 ? 90 : undefined }}>{t}</th>))}</tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.key}>
              <td style={{ padding: '4px 8px', fontWeight: 700 }}>{r.key || '-'}</td>
              <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(r.ly)}</td>
              <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(r.plan)}</td>
              <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono, color: col(r.change), fontWeight: 700 }}>{sgn(r.change)}</td>
              <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{r.pct != null ? `${r.pct >= 0 ? '+' : ''}${r.pct.toFixed(1)}%` : '-'}</td>
              {keys.map(k => <td key={k} style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono, color: col(r[k]) }}>{Math.abs(r[k]) > 1e-9 ? sgn(r[k]) : '-'}</td>)}
            </tr>))}</tbody>
        </table>
      </div>
    </details>)
  return (
    <>
      <div style={{ ...card, padding: '14px 18px' }}>
        <div style={{ marginBottom: 10 }}>{scopeBar}</div>
        <div style={{ fontSize: 15, fontWeight: 700, color: theme.navy }}>What moved the plan - the whole company, from last year to the plan</div>
        <div style={{ fontSize: 12.5, color: theme.textMuted, marginTop: 4 }}>
          The same steps as a single store's journey, added up over every store, department and month: how much each one moved the plan and what share of the
          whole change it is. Narrow it to a store group, a division or a month.
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12, alignItems: 'end' }}>
          <label style={lab}>Store group
            <select value={f.group} onChange={e => setF(x => ({ ...x, group: e.target.value }))} style={sel_} aria-label="Store group">
              <option value="">All stores</option><option value="SSG">Like-for-like (SSG)</option><option value="NSO">New stores (NSO)</option><option value="Others">Others</option>
            </select>
          </label>
          <label style={lab}>Division
            <select value={f.division} onChange={e => setF(x => ({ ...x, division: e.target.value }))} style={sel_} aria-label="Division">
              <option value="">All divisions</option>{['KIDS', 'LADIES', 'MENS'].map(d => <option key={d}>{d}</option>)}
            </select>
          </label>
          <label style={lab}>Month
            <select value={f.month} onChange={e => setF(x => ({ ...x, month: e.target.value }))} style={sel_} aria-label="Month">
              <option value="">All months</option>{(h?.by?.Month || []).map(m => <option key={m.key}>{m.key}</option>)}
            </select>
          </label>
          <a href={`${API}/journey/holistic/export?${new URLSearchParams(f)}`}
            style={{ padding: '7px 14px', borderRadius: 7, fontSize: 12.5, fontWeight: 700, textDecoration: 'none', background: theme.primary, color: '#fff', border: `1px solid ${theme.primary}` }}
            title="The bridge + the effects by division, month, store group, cluster, department and store">⬇ Excel (deviation bridge)</a>
        </div>
      </div>
      {err && <div style={{ color: theme.danger, fontSize: 13 }}>{err}</div>}
      {!h && !err && <div style={{ fontSize: 12.5, color: theme.textMuted }}>Adding up every store, department and month…</div>}
      {h && (
        <div style={{ display: 'grid', gap: 14, opacity: busy ? 0.6 : 1 }} aria-busy={busy}>
          <div style={{ ...card, padding: '12px 16px', borderLeft: `4px solid ${theme.navy}` }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>What moved the plan - in plain words</div>
            <div style={{ fontSize: 13.5, color: theme.textPrimary, margin: '6px 0 10px', lineHeight: 1.55 }}>{h.story}</div>
            <div style={{ display: 'grid', gap: 6, fontSize: 12.5 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr) 150px 130px', gap: 12 }}>
                <b>Last year</b><span /><b style={{ textAlign: 'right', fontFamily: theme.fontMono }}>{L(h.ly)}</b><span />
              </div>
              {h.bridge.map(b => (
                <details key={b.key} style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 6 }}>
                  <summary style={{ display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr) 150px 130px', gap: 12, alignItems: 'center', cursor: 'pointer', listStyle: 'none' }}>
                    <span><span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 11 }}>▸ </span><b>{b.what}</b></span>
                    <span aria-hidden="true" style={{ height: 10, background: theme.border, borderRadius: 5, position: 'relative' }}>
                      <span style={{ position: 'absolute', top: 0, bottom: 0, left: b.change >= 0 ? '50%' : `${50 - Math.abs(b.change) / maxAbs * 50}%`,
                        width: `${Math.abs(b.change) / maxAbs * 50}%`, background: col(b.change), borderRadius: 5 }} />
                    </span>
                    <b style={{ textAlign: 'right', fontFamily: theme.fontMono, color: col(b.change) }}>{sgn(b.change)}</b>
                    <span style={{ textAlign: 'right', color: theme.textMuted }}>{b.share != null ? `${b.share.toFixed(1)}% of the change` : ''}</span>
                  </summary>
                  <div style={{ margin: '6px 0 8px 14px', padding: '8px 12px', borderRadius: 8, background: alpha(theme.primary, '0a'), lineHeight: 1.6, color: theme.textSecondary }}>
                    <div>{b.why}{b.pct_of_ly != null ? ` ${b.pct_of_ly >= 0 ? '+' : ''}${b.pct_of_ly.toFixed(2)}% of last year.` : ''}</div>
                    {['Division', 'Month', 'Group'].map(dim => (
                      <div key={dim} style={{ marginTop: 4 }}><b>By {dim === 'Group' ? 'store group' : dim.toLowerCase()}:</b>{' '}
                        {(h.by[dim] || []).filter(r => Math.abs(r[b.key]) > 1e-9).map(r => `${r.key} ${sgn(r[b.key])}`).join(' · ') || '-'}</div>))}
                  </div>
                </details>))}
              <div style={{ display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr) 150px 130px', gap: 12, borderTop: `2px solid ${theme.navy}`, paddingTop: 6 }}>
                <b>= Plan</b><span />
                <b style={{ textAlign: 'right', fontFamily: theme.fontMono, color: theme.navy }}>{L(h.plan)}</b>
                <span style={{ textAlign: 'right', color: theme.textMuted }}>{h.pct != null ? `${h.pct >= 0 ? '+' : ''}${h.pct.toFixed(2)}% on last year` : ''}</span>
              </div>
            </div>
          </div>
          {table('By division', h.by.Division, true)}
          {table('By month', h.by.Month, true)}
          {table('By store group', h.by.Group, false)}
          {table('By cluster', h.by.Cluster, false)}
          {table('Departments that moved most (top 25)', h.by.Department, false)}
        </div>)}
    </>)
}
