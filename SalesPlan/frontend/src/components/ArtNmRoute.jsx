import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import { FiltersRow } from './ExcelFilter'
import RouteBar from './RouteBar'
import { useGrain } from '../grain'

// The MRP stage's Article Name route (user, 2026-10-13): LY Art Nm mix per Cluster / Store x the buyers' Art Nm Cont %
// (deviation capped 50-150%), apportioned to 100% within each department and applied to the department plan (its AOP).
// New and split departments take the buyers' % as it is. Each department shows whether its articles add back to its AOP.
// Article Name Plan · Plan Output - the MRP branch's counterpart; by store or cluster as the header's Plan by (user,
// 2026-10-13: "it should follow the current selected toggle"); the file comes from this branch's Buyer's Input.
const API = '/api/planning/art-nm'
const DIV_COLOR = { KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A' }
const CELL = { fontFamily: theme.fontMono, fontSize: 11, textAlign: 'right', padding: '4px 8px', whiteSpace: 'nowrap' }
const HDR = { ...CELL, fontSize: 10, color: theme.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4, background: theme.surfaceUp }
const TAG = { existing: 'Existing', new: 'New', split: 'Split', inactive: 'In-active MC', none: 'Not in buyer file' }
const ST = { ok: theme.success, warn: theme.warning, fail: theme.danger }
const f2 = v => (v == null ? '—' : Math.abs(v) < 0.005 ? '—' : v.toFixed(2))
const BTN = { padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: `1px solid ${theme.border}`, background: theme.surface, color: theme.textPrimary }
const pc = v => (v == null ? '—' : `${v.toFixed(1)}%`)

async function readErr(r) {
  try { const j = await r.json(); return j.detail || r.statusText } catch { return r.statusText }
}

export default function ArtNmRoute() {
  const [grain] = useGrain()
  const nav = useNavigate()
  // the server keeps the grain last shown, so Reconciliation checks the split the planners look at
  useEffect(() => { fetch(`${API}/settings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ grain }) }).catch(() => {}) }, [grain])
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)
  const [div, setDiv] = useState(null)
  const [af, setAf] = useState({})          // the Filters row: {group | department | tag | method | check: [values]}
  const [open, setOpen] = useState(null)
  const [view, setView] = useState('plan')  // 'plan' (₹ L) | 'pct' (cont %)
  const groups = af.group || []

  const load = () => {
    setLoading(true); setErr('')
    fetch(`${API}/plan?grain=${grain}&g=${encodeURIComponent(groups.join('|'))}`)
      .then(async r => { if (!r.ok) throw new Error(await readErr(r)); return r.json() })
      .then(d => { setData(d); setDiv(v => (v && d.divisions.includes(v) ? v : d.divisions[0] || null)) })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { setAf({}) }, [grain])
  useEffect(load, [grain, groups.join('|')])   // eslint-disable-line react-hooks/exhaustive-deps

  const months = data?.months || []
  const dd = (data && div && data.data[div]) || {}
  const depts = Object.keys(dd).sort()
  const cellVal = (d, k) => (k === 'department' ? d : k === 'tag' ? TAG[dd[d].tag] || dd[d].tag
    : k === 'method' ? dd[d].method : dd[d].ok ? 'OK' : 'Not = AOP')
  const pass = (d, skip) => Object.entries(af).every(([k, v]) => k === skip || k === 'group' || v.includes(cellVal(d, k)))
  const shown = depts.filter(d => pass(d))
  const values = k => (k === 'group' ? data?.groups || [] : [...new Set(depts.filter(d => pass(d, k)).map(d => cellVal(d, k)))].sort())
  const tot = shown.reduce((s, d) => ({ aop: s.aop + dd[d].aop_total, plan: s.plan + dd[d].plan_total }), { aop: 0, plan: 0 })
  const bad = depts.filter(d => !dd[d].ok)
  const color = DIV_COLOR[div] || theme.primary
  const seg = (opts, cur, set) => (
    <div style={{ display: 'flex', borderRadius: 7, overflow: 'hidden', border: `1px solid ${theme.border}` }}>
      {opts.map(([k, label]) => (
        <button key={k} onClick={() => set(k)} style={{ padding: '5px 14px', fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
          background: cur === k ? 'var(--st-btn,#A8CBB7)' : theme.surface, color: cur === k ? 'var(--st-btn-text,#1F4D3A)' : theme.textMuted }}>{label}</button>
      ))}
    </div>
  )

  return (
    <div style={{ padding: '20px 32px 28px', minHeight: '100vh', background: theme.surfaceAlt }}>
      <RouteBar here="article" />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <div className="sp-sub" style={{ margin: 0, flex: 1, minWidth: 280 }}>
          Department plan split by Article Name: LY Art Nm mix of each {grain} × the buyers' Art Nm Cont % (deviation capped
          50–150%), apportioned to 100% within the department. New and split departments take the buyers' % as it is.
        </div>
        <span style={{ fontSize: 11.5, color: theme.textMuted }}>LY mix by <b style={{ color: theme.textPrimary }}>{grain}</b> (header's Plan by)</span>
        <button style={BTN} onClick={() => nav('/art-plan/import')}>Buyer's Input →</button>
        <button style={BTN} disabled={!data} onClick={() => window.open(`${API}/export?grain=${grain}`, '_blank')}>Export Excel ↓</button>
      </div>
      <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 10 }}>
        {data?.cont ? <>Buyer's file <b style={{ color: theme.textPrimary }}>{data.cont.source_file}</b> · block {data.cont.block || '?'} · imported {data.cont.imported_at}</>
          : "No Art Nm Cont % imported yet - every department is on its LY mix until it is (Article Name Plan → Buyer's Input)."}
      </div>

      {loading && !data && <div style={{ color: theme.textMuted, fontSize: 13, padding: 12 }}>Reading LY article sales and the plan… (about 20 s the first time)</div>}
      {err && <div style={{ color: theme.danger, fontSize: 13, padding: 12 }}>{err}</div>}

      {data && (<>
        {/* Checks */}
        <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, padding: '8px 14px', marginBottom: 14 }}>
          {data.checks.map(c => (
            <div key={c.key} style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12, padding: '3px 0' }}>
              <span aria-label={c.status} style={{ width: 9, height: 9, borderRadius: '50%', background: ST[c.status], flexShrink: 0, transform: 'translateY(1px)' }} />
              <b style={{ minWidth: 330 }}>{c.label}</b>
              <span style={{ color: theme.textSecondary }}>{c.detail}{c.fix && <span style={{ color: ST[c.status] }}> - {c.fix}</span>}</span>
            </div>
          ))}
        </div>

        {/* Division tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          {data.divisions.map(v => {
            const t = Object.values(data.data[v]); const on = v === div
            return (
              <button key={v} onClick={() => { setDiv(v); setOpen(null); setAf(f => (f.group ? { group: f.group } : {})) }} style={{
                padding: '8px 18px', borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontSize: 12,
                border: `2px solid ${on ? DIV_COLOR[v] : theme.border}`, background: on ? alpha(DIV_COLOR[v] || theme.primary, '18') : theme.surface,
                color: on ? DIV_COLOR[v] : theme.textMuted }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{v}</div>
                <div style={{ fontSize: 10, opacity: 0.8 }}>{t.length} depts · {t.reduce((s, x) => s + x.aop_total, 0).toFixed(1)} L{t.some(x => !x.ok) ? ' · ⚠' : ''}</div>
              </button>
            )
          })}
        </div>

        <FiltersRow fields={[['group', grain === 'cluster' ? 'Cluster' : 'Store'], ['department', 'Department'], ['tag', 'Tag'], ['method', 'Method'], ['check', 'Check']]}
          filters={af} onChange={setAf} values={values} style={{ marginBottom: 12 }}>
          {seg([['plan', 'Plan (₹L)'], ['pct', 'Cont %']], view, setView)}
          <span style={{ fontSize: 11, color: theme.textMuted }}>{shown.length} of {depts.length} depts{loading ? ' · updating…' : ''}</span>
          {bad.length > 0 && <span style={{ fontSize: 11, color: theme.danger, fontWeight: 600 }}>⚠ {bad.length} not = AOP - pick Check to see them</span>}
        </FiltersRow>

        <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${theme.border}` }}>
                <th style={{ ...HDR, textAlign: 'left', minWidth: 230 }}>Department / Article Name</th>
                <th style={{ ...HDR, textAlign: 'left' }}>Tag · Method</th>
                <th style={HDR} title="The department's plan in the Sales Plan (what Plan Output splits)">Dept AOP</th>
                <th style={HDR}>LY %</th>
                <th style={HDR}>Buyer %</th>
                {data.single_group && <th style={HDR} title="Buyer % ÷ LY % → capped to 50–150%">Deviation → capped</th>}
                {months.map(m => <th key={m} style={{ ...HDR, color: theme.primary }}>{m}</th>)}
                <th style={HDR}>Article plan</th>
                <th style={HDR}>Plan %</th>
                <th style={HDR}>Check</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(d => {
                const x = dd[d]; const isOpen = open === d
                return [
                  <tr key={d} onClick={() => setOpen(isOpen ? null : d)} style={{ cursor: 'pointer', borderBottom: `1px solid ${theme.border}`, background: x.ok ? alpha(color, '0a') : alpha(theme.danger, '08') }}>
                    <td style={{ padding: '6px 10px', fontWeight: 700, color, fontSize: 12 }}>
                      <span style={{ color: theme.textMuted, fontWeight: 400, marginRight: 6 }}>{isOpen ? '▾' : '▸'}</span>{d}
                      <span style={{ fontSize: 10, color: theme.textMuted, fontWeight: 400, marginLeft: 8 }}>{x.articles.length} articles</span>
                    </td>
                    <td style={{ padding: '4px 8px', fontSize: 10, color: theme.textSecondary }} title={Object.entries(x.methods).map(([k, v]) => `${k}: ${v}`).join('\n')}>
                      <b>{TAG[x.tag] || x.tag}</b> · {x.method}{Object.keys(x.methods).length > 1 ? ` +${Object.keys(x.methods).length - 1}` : ''}
                    </td>
                    <td style={{ ...CELL, fontWeight: 700 }}>{f2(x.aop_total)}</td>
                    <td style={CELL} /><td style={CELL} />{data.single_group && <td style={CELL} />}
                    {months.map(m => <td key={m} style={{ ...CELL, fontWeight: 600 }}>{view === 'plan' ? f2(x.plan[m]) : x.aop[m] ? '100%' : '—'}</td>)}
                    <td style={{ ...CELL, fontWeight: 700, color: theme.accent }}>{f2(x.plan_total)}</td>
                    <td style={CELL}>{x.plan_total ? '100%' : '—'}</td>
                    <td style={{ ...CELL, fontWeight: 700, color: x.ok ? theme.success : theme.danger }}
                      title={x.ok ? (x.neg ? `Articles add back to the department AOP; ${x.neg} store-month cell(s) have a negative department plan (${x.neg_total.toFixed(4)} L, returns in LY) - their articles are 0` : 'Articles add back to the department AOP') : `Articles ${f2(x.plan_total)} vs AOP ${f2(x.aop_total)}`}>
                      {x.ok ? (x.neg ? '✓ = AOP*' : '✓ = AOP') : `≠ AOP ${x.diff.toFixed(2)}`}
                    </td>
                  </tr>,
                  ...(isOpen ? x.articles.map(a => (
                    <tr key={d + a.article} style={{ borderBottom: `1px solid ${alpha(theme.border, '55')}` }}>
                      <td style={{ padding: '4px 10px 4px 30px', fontFamily: theme.fontMono }}>{a.article}</td>
                      <td /><td style={CELL} />
                      <td style={CELL}>{pc(a.ly_pct)}</td>
                      <td style={CELL}>{pc(a.buyer_pct)}</td>
                      {data.single_group && <td style={CELL}>{a.dev == null ? (a.cap == null ? '—' : `→ ${(a.cap * 100).toFixed(0)}%`) : `${(a.dev * 100).toFixed(0)}% → ${(a.cap * 100).toFixed(0)}%`}</td>}
                      {months.map(m => <td key={m} style={CELL}>{view === 'plan' ? f2(a.plan[m]) : x.plan[m] ? pc(a.plan[m] / x.plan[m] * 100) : '—'}</td>)}
                      <td style={{ ...CELL, color: theme.success, fontWeight: 600 }}>{f2(a.total)}</td>
                      <td style={CELL}>{pc(a.plan_pct)}</td>
                      <td />
                    </tr>
                  )) : []),
                ]
              })}
              <tr style={{ borderTop: `2px solid ${theme.border}`, fontWeight: 700 }}>
                <td style={{ padding: '6px 10px' }}>Total ({shown.length} depts)</td><td />
                <td style={{ ...CELL, fontWeight: 700 }}>{f2(tot.aop)}</td>
                <td style={CELL} /><td style={CELL} />{data.single_group && <td style={CELL} />}
                {months.map(m => <td key={m} style={{ ...CELL, fontWeight: 700 }}>{view === 'plan' ? f2(shown.reduce((s, d) => s + dd[d].plan[m], 0)) : ''}</td>)}
                <td style={{ ...CELL, fontWeight: 700, color: theme.accent }}>{f2(tot.plan)}</td>
                <td style={CELL} />
                <td style={{ ...CELL, color: Math.abs(tot.plan - tot.aop) < 0.005 ? theme.success : theme.danger }}>{(tot.plan - tot.aop).toFixed(2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </>)}
    </div>
  )
}
