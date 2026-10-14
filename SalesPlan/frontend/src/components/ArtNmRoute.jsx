import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'
import RouteBar from './RouteBar'
import HierarchyView from './HierarchyView'
import { useGrain } from '../grain'

// Article Name Plan · Plan Output - the MRP branch's counterpart, by store or cluster as the header's Plan by (user,
// 2026-10-13). The plan engine as set out: pick the departments (the Department filter) -> LY cont % per cluster/store x
// department x article x month against the input Art Nm Cont % -> deviation capped 50-150% -> resultant = LY cont % x
// capped -> apportioned to 100% and x the department AOP. The output is the department plan's Final Results tree ("make
// similar output page as the department with all features similarly"): Rows, a filter per field, Grand Total, Cont %
// and the ⓘ pop-up with each row's working month by month ("Mimic the working pop up for every entry").
const API = '/api/planning/art-nm'
const ST = { ok: theme.success, warn: theme.warning, fail: theme.danger }
const BTN = { padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: `1px solid ${theme.border}`, background: theme.surface, color: theme.textPrimary }
const FIELDS = {   // Department first: the department selection
  department: 'Department', article: 'Article Name', cluster: 'Cluster', store: 'Store', stype: 'Store type',
  division: 'Division', attribute: 'Attribute', month: 'Month',
}
const STEPS = g => [
  ['1', 'Departments', 'pick them in the Department filter (all, if none picked)'],
  ['2', 'LY cont %', `each article's share of its department's LY sales, per ${g} × month`],
  ['3', 'Deviation', 'input Art Nm Cont % ÷ LY cont %, capped 50%–150% (in-active MC = 0%)'],
  ['4', 'Resultant', 'LY cont % × capped deviation'],
  ['5', 'Plan', `resultants apportioned to 100% per ${g} × department × month, × the department AOP`],
]

// The post-generation check (user, 2026-10-13: "make a check where the post generation of the data it should look if the
// department sales plan is matching for all departments x months and AOP is correct for all months"): every division x
// month - like-for-like department plan vs the AOP, the all-store plan and the article plan beside it; every department x
// month - article plan vs department sales plan (only the ones that don't match listed, all on request).
function PostCheck({ grain }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [all, setAll] = useState(false)
  useEffect(() => {
    setD(null); setErr('')
    fetch(`${API}/post-check?grain=${grain}`).then(async r => { if (!r.ok) throw new Error(await readErr(r)); return r.json() }).then(setD).catch(e => setErr(e.message))
  }, [grain])
  const L = v => (v == null ? '–' : v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
  const ok = v => <span style={{ fontWeight: 700, color: v === null ? theme.textMuted : v ? theme.success : theme.danger }}>{v === null ? '–' : v ? '✓' : '✗'}</span>
  const th = { padding: '5px 8px', fontSize: 10.5, color: theme.textMuted, textAlign: 'right', borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }
  const td = { padding: '4px 8px', fontSize: 12, textAlign: 'right', fontFamily: theme.fontMono, borderBottom: `1px solid ${alpha(theme.border, '88')}` }
  const s = d?.summary
  const deps = d ? (all ? d.departments : d.departments.filter(r => !r.ok)) : []
  const good = s && !s.dept_off && !s.aop_off && s.aop_cells
  return (
    <details open={!good} style={{ background: theme.surface, border: `1px solid ${good ? alpha(theme.success, '55') : theme.border}`, borderRadius: 10, padding: '8px 14px', marginBottom: 14 }}>
      <summary style={{ cursor: 'pointer', fontSize: 12.5, fontWeight: 700 }}>
        Post-generation check {s && <span style={{ fontWeight: 600, color: good ? theme.success : theme.danger, marginLeft: 6 }}>
          {s.dept_cells - s.dept_off} of {s.dept_cells} department × month = department sales plan · {s.aop_cells - s.aop_off} of {s.aop_cells} division × month = AOP{s.aop_label ? ` (${s.aop_label})` : ''}</span>}
        {err && <span style={{ color: theme.danger, fontWeight: 400, marginLeft: 6 }}>{err}</span>}
      </summary>
      {!d && !err && <div style={{ fontSize: 12, color: theme.textMuted, padding: 6 }}>Checking…</div>}
      {d && (<>
        <div style={{ fontSize: 11.5, color: theme.textMuted, margin: '8px 0 4px' }}>
          Division × month - the like-for-like stores' department plan against the AOP (the department engine holds them on it), with the all-store plan and the Article Name plan (₹ lakh).
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>{['Division', 'Month', 'AOP', 'LFL dept plan', 'Diff', '= AOP', 'All-store dept plan', 'Article plan', '= dept plan'].map((h, i) => <th key={h} style={{ ...th, textAlign: i < 2 ? 'left' : 'right' }}>{h}</th>)}</tr></thead>
            <tbody>{d.divisions.map(r => {
              const ad = r.articles - r.all_plan
              return (
                <tr key={r.division + r.month}>
                  <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit', fontWeight: 600 }}>{r.division}</td><td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>{r.month}</td>
                  <td style={td}>{L(r.aop)}</td><td style={td}>{L(r.lfl_plan)}</td><td style={td}>{r.diff == null ? '–' : r.diff.toFixed(4)}</td><td style={td}>{ok(r.ok)}</td>
                  <td style={td}>{L(r.all_plan)}</td><td style={td}>{L(r.articles)}</td>
                  <td style={td} title="A negative store-month department plan (returns in LY) keeps its articles at 0">{ok(Math.abs(ad + d.departments.filter(x => x.division === r.division && x.month === r.month).reduce((t, x) => t + x.negative, 0)) < 1e-4)}</td>
                </tr>)
            })}</tbody>
          </table>
        </div>
        <div style={{ fontSize: 11.5, color: theme.textMuted, margin: '10px 0 4px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span>Department × month - Article Name plan against the department sales plan: {s.dept_off ? `${s.dept_off} don't match` : `all ${s.dept_cells} match`}
            {s.dept_neg ? ` (${s.dept_neg} carry a negative store plan, ₹${s.neg_total.toFixed(4)} L, kept at 0)` : ''}.</span>
          <button type="button" onClick={() => setAll(a => !a)} style={{ all: 'unset', cursor: 'pointer', color: theme.primary, textDecoration: 'underline' }}>{all ? 'Show only the ones off' : `Show all ${s.dept_cells}`}</button>
        </div>
        {deps.length > 0 && (
          <div style={{ overflow: 'auto', maxHeight: 320 }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Division', 'Department', 'Month', 'Dept sales plan', 'Article plan', 'Negative store plan', 'Diff', 'Check'].map((h, i) => <th key={h} style={{ ...th, textAlign: i < 3 ? 'left' : 'right', position: 'sticky', top: 0, background: theme.surface }}>{h}</th>)}</tr></thead>
              <tbody>{deps.map(r => (
                <tr key={r.division + r.department + r.month}>
                  <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>{r.division}</td><td style={{ ...td, textAlign: 'left', fontFamily: 'inherit', fontWeight: 600 }}>{r.department}</td>
                  <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>{r.month}</td><td style={td}>{L(r.plan)}</td><td style={td}>{L(r.articles)}</td>
                  <td style={td}>{r.negative ? r.negative.toFixed(4) : '–'}</td><td style={td}>{r.diff.toFixed(6)}</td><td style={td}>{ok(r.ok)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </>)}
    </details>
  )
}

async function readErr(r) {
  if (r.status === 401) return 'Not signed in - sign in again on Landing'
  try { const j = await r.json(); return j.detail || r.statusText } catch { return r.statusText }
}

export default function ArtNmRoute() {
  const [grain] = useGrain()
  const nav = useNavigate()
  // the server keeps the grain last shown, so Reconciliation and Promote work on the split the planners look at
  useEffect(() => { fetch(`${API}/settings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ grain }) }).catch(() => {}) }, [grain])
  const [sum, setSum] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setSum(null); setErr('')
    fetch(`${API}/summary?grain=${grain}`).then(async r => { if (!r.ok) throw new Error(await readErr(r)); return r.json() }).then(setSum).catch(e => setErr(e.message))
  }, [grain])

  // promote to the MRP stage (user, 2026-10-13: "a provision if the art nm plan has to be promoted to mrp planning
  // stage" -> split into MRP bands): the article plan over MRP bands by the LY article x MRP mix becomes the MRP split
  const [prom, setProm] = useState(null)
  const [promBusy, setPromBusy] = useState(false)
  const [promErr, setPromErr] = useState('')
  const loadProm = () => fetch(`${API}/promote`).then(r => (r.ok ? r.json() : null)).then(setProm).catch(() => setProm(null))
  useEffect(() => { loadProm() }, [grain, sum?.cont?.imported_at])   // eslint-disable-line react-hooks/exhaustive-deps
  const promote = async () => {
    if (!window.confirm(`Promote the Article Name plan (by ${grain}) to the MRP stage? Its MRP split replaces the buyers' MRP Cont % split in MRP Plan Output, Display Type and Reconciliation while the route is Article Name. The buyers' file is kept - switching the route to MRP brings it back.`)) return
    setPromBusy(true); setPromErr('')
    try {
      const r = await fetch(`${API}/promote`, { method: 'POST' })
      if (!r.ok) throw new Error(await readErr(r))
      await loadProm()
    } catch (e) { setPromErr(e.message) } finally { setPromBusy(false) }
  }

  const levels = grain === 'store' ? FIELDS : Object.fromEntries(Object.entries(FIELDS).filter(([k]) => k !== 'store' && k !== 'stype'))
  const L = v => (v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

  return (
    <div style={{ padding: '20px 32px 28px', minHeight: '100vh', background: theme.surfaceAlt }}>
      <RouteBar key={prom?.promoted_at || 'route'} here="article" />

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12, padding: '10px 14px', borderRadius: 10,
        border: `1px solid ${prom?.promoted && !prom.stale ? alpha(theme.success, '55') : theme.border}`, background: prom?.promoted && !prom.stale ? alpha(theme.success, '0c') : theme.surface }}>
        <b style={{ fontSize: 12.5 }}>MRP stage</b>
        <span style={{ fontSize: 12, color: theme.textSecondary, flex: 1, minWidth: 260 }}>
          {!prom?.promoted ? "Not promoted - the MRP stage splits the department plan by the buyers' MRP Cont %."
            : <>Promoted {prom.promoted_at}{prom.by ? ` by ${prom.by}` : ''} (by {prom.stamp.grain}): {prom.depts} departments over {prom.bands} MRP bands,
              ₹{L(prom.total)} L ({Object.entries(prom.how || {}).map(([k, v]) => `${k} mix ${v.toFixed(1)} L`).join(', ')})
              {!prom.in_use && <b style={{ color: theme.warning }}> · not in use: the route is MRP</b>}
              {prom.stale && <b style={{ color: theme.warning }}> · the article plan changed since (file, Plan by or department plan) - promote again</b>}</>}
          {promErr && <span style={{ color: theme.danger }}> · {promErr}</span>}
        </span>
        <button style={{ ...BTN, background: theme.primary, color: '#fff', borderColor: theme.primary }} disabled={promBusy || !sum} onClick={promote}>
          {promBusy ? 'Promoting… (about 40 s)' : prom?.promoted ? 'Promote again' : 'Promote to MRP stage'}
        </button>
        {prom?.promoted && <button style={BTN} onClick={() => nav('/mrp-plan/output')}>MRP Plan Output →</button>}
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <div className="sp-sub" style={{ margin: 0, flex: 1, minWidth: 280 }}>
          The department plan split by Article Name, by <b>{grain}</b> (the header's Plan by). New departments, new article names and split
          departments take the imported Art Nm Cont % as it is.
        </div>
        <button style={BTN} onClick={() => nav('/art-plan/import')}>Buyer's Input →</button>
        <button style={BTN} disabled={!sum} onClick={() => window.open(`${API}/plan-export?grain=${grain}`, '_blank')}>Export Excel ↓</button>
      </div>

      {/* the plan engine, step by step */}
      <div role="list" aria-label="How the plan is made" style={{ display: 'flex', gap: 0, flexWrap: 'wrap', background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, overflow: 'hidden', marginBottom: 12 }}>
        {STEPS(grain).map(([n, h, t], i) => (
          <div key={n} role="listitem" style={{ flex: '1 1 170px', padding: '9px 12px', borderLeft: i ? `1px solid ${theme.border}` : 'none' }}>
            <div style={{ fontSize: 11.5, fontWeight: 700 }}><span style={{ color: theme.primary }}>{n}</span> · {h}</div>
            <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>{t}</div>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 8 }}>
        {sum?.cont ? <>Input file <b style={{ color: theme.textPrimary }}>{sum.cont.source_file}</b> · block {sum.cont.block || '?'} · imported {sum.cont.imported_at}
          {' · '}article plan ₹{L(sum.plan)} L = department AOP ₹{L(sum.aop)} L</>
          : sum ? "No Art Nm Cont % imported yet - every department is on its LY mix until it is (Article Name Plan → Buyer's Input)." : null}
      </div>
      {!sum && !err && <div style={{ color: theme.textMuted, fontSize: 13, padding: 12 }}>Reading LY article sales and the plan… (about 30 s the first time)</div>}
      {err && <div style={{ color: theme.danger, fontSize: 13, padding: 12 }}>{err}</div>}
      {sum && (
        <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 10, padding: '8px 14px', marginBottom: 14 }}>
          {sum.checks.map(c => (
            <div key={c.key} style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12, padding: '3px 0' }}>
              <span aria-label={c.status} style={{ width: 9, height: 9, borderRadius: '50%', background: ST[c.status], flexShrink: 0, transform: 'translateY(1px)' }} />
              <b style={{ minWidth: 330 }}>{c.label}</b>
              <span style={{ color: theme.textSecondary }}>{c.detail}{c.fix && <span style={{ color: ST[c.status] }}> - {c.fix}</span>}</span>
            </div>
          ))}
        </div>
      )}
      {sum && <PostCheck grain={grain} />}
      {sum && <HierarchyView key={grain} api={API} levels={levels} defaults={['department', 'article', 'month']} store={`sp.art.${grain}`} versions={false} query={{ grain }} />}
    </div>
  )
}
