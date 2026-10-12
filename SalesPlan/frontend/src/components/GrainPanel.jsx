import { useEffect, useMemo, useState } from 'react'
import { theme, alpha } from '../theme'
import { useGrain } from '../grain'

// The plan of one stage by cluster or by store (user, 2026-10-12: "give a vice versa preview on all stages - Division,
// Department, MRP or Display Type"). View only - the same numbers as the stage, from /api/planning/grain/<stage>.
// Cluster view: each cluster opens to its stores (the plan flowing down). Store view: each store shows its cluster and
// its share of it (what it rolls up to). Values are Rs lakh, as in the plan files.
const DIVS = ['ALL', 'KIDS', 'LADIES', 'MENS', 'GM', 'RETAIL']
const L = v => v == null || Number.isNaN(v) ? '–' : v.toLocaleString('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
const P = v => v == null || !Number.isFinite(v) ? '–' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
const gr = (ty, ly) => (ly > 0 ? (ty / ly - 1) * 100 : null)
const STORE_CAP = 150

export default function GrainPanel({ stage, division, title }) {
  const [grain, setGrain] = useGrain()
  const [div, setDiv] = useState(division || (stage === 'division' || stage === 'display' ? 'ALL' : 'MENS'))
  const [dept, setDept] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('sp.grain.open.' + stage) !== '0' } catch { return true } })
  const [expanded, setExpanded] = useState(() => new Set())
  const [q, setQ] = useState('')
  const [measure, setMeasure] = useState('ty')   // ty | ly | gr (division / department)
  // step 2 (2026-10-12): how the plan is built - today's plan, or a preview of store-built / cluster-built AOP x BIS
  const [method, setMethod] = useState('ty')      // ty (today) | store_built | cluster_built
  const [deptList, setDeptList] = useState([])
  const [showAll, setShowAll] = useState(false)

  useEffect(() => { if (division && division !== div) { setDiv(division); setDept('') } }, [division])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return
    let gone = false
    setLoading(true); setErr('')
    const viaMethods = method !== 'ty' && (stage === 'division' || (stage === 'department' && dept))
    const qs = new URLSearchParams({ grain, division: div, ...(dept ? { dept } : {}) })
    fetch(`/api/planning/grain/${viaMethods ? 'methods' : stage}?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { if (!gone) { setData(j); if (j.departments) setDeptList(j.departments); if (j.dept && j.dept !== dept) setDept(j.dept) } })
      .catch(e => { if (!gone) setErr(e.message) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [open, stage, grain, div, dept, method])   // eslint-disable-line react-hooks/exhaustive-deps

  const toggleOpen = () => setOpen(o => { try { localStorage.setItem('sp.grain.open.' + stage, o ? '0' : '1') } catch { /* ignore */ } return !o })

  // columns: months (division / department), MRP bands (mrp), plan / table / non-table (display)
  const cols = useMemo(() => {
    if (!data) return []
    if (stage === 'mrp') return (data.bands || []).map(b => ({ key: b, label: `₹${b}`, get: r => r.total?.bands?.[b] ?? 0 }))
    if (stage === 'display') return [
      { key: 'table', label: 'Table', get: r => r.total?.table ?? 0 },
      { key: 'nontable', label: 'Non-Table', get: r => r.total?.nontable ?? 0 },
    ]
    return (data.months || []).map(m => ({
      key: m, label: m,
      get: r => { const x = r.months?.[m] || {}; const f = method !== 'ty' && 'store_built' in (data.total || {}) ? method : 'ty'
        return measure === 'gr' ? gr(x[f], x.ly) : x[measure === 'ty' ? f : measure] ?? 0 },
      pct: measure === 'gr',
    }))
  }, [data, stage, measure, method])

  const ly = stage === 'division' || stage === 'department'
  const alt = method !== 'ty' && ly && !!data && 'store_built' in (data.total || {})
  const F = alt ? method : 'ty'           // the plan field shown: today's plan or the previewed method
  const tot = r => (stage === 'display' ? r?.total?.plan : r?.total?.[F]) ?? 0
  const ctot = r => (stage === 'display' ? r?.cluster_total?.plan : r?.cluster_total?.[F]) ?? 0
  const ql = q.trim().toLowerCase()
  const hit = s => s.toLowerCase().includes(ql)
  const match = r => !ql || hit(`${r.label} ${r.cluster || ''}`) || (r.stores || []).some(s => hit(s.label))
  const rows = (data?.rows || []).filter(match)
  const shown = grain === 'store' && !showAll ? rows.slice(0, STORE_CAP) : rows

  const th = { padding: '7px 10px', fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textAlign: 'right', whiteSpace: 'nowrap',
    background: theme.surfaceUp, borderBottom: `1px solid ${theme.border}`, position: 'sticky', top: 0, zIndex: 1 }
  const td = { padding: '6px 10px', fontSize: 12, textAlign: 'right', whiteSpace: 'nowrap', borderBottom: `1px solid ${theme.border}`,
    fontVariantNumeric: 'tabular-nums' }
  const foot = { ...td, fontWeight: 700, borderTop: `2px solid ${theme.border}` }
  const seg = (on) => ({ padding: '5px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', border: `1px solid ${on ? theme.primary : theme.border}`,
    background: on ? theme.primary : theme.surface, color: on ? '#fff' : theme.textSecondary })
  const tone = v => (v > 0 ? theme.success : v < 0 ? theme.danger : theme.textMuted)

  const cells = (r, sub) => (<>
    {cols.map(c => { const v = c.get(r); return <td key={c.key} style={{ ...td, color: c.pct ? tone(v) : sub ? theme.textSecondary : theme.textPrimary }}>{c.pct ? P(v) : L(v)}</td> })}
    <td style={{ ...td, fontWeight: 700 }}>{L(tot(r))}</td>
    {ly && <td style={{ ...td, color: theme.textSecondary }}>{L(r.total?.ly)}</td>}
    {ly && <td style={{ ...td, color: tone(gr(tot(r), r.total?.ly)) }}>{P(gr(tot(r), r.total?.ly))}</td>}
    {alt && <td style={{ ...td, color: theme.textSecondary }}>{L(r.total?.ty)}</td>}
    {alt && <td style={{ ...td, color: tone(tot(r) - (r.total?.ty || 0)) }}>{L(tot(r) - (r.total?.ty || 0))}</td>}
    {alt && stage === 'division' && <td style={{ ...td, color: theme.textSecondary }}>{L(r.total?.aop)}</td>}
  </>)
  const lfl = r => (r.ssg ? <span style={{ marginLeft: 6, fontSize: 9.5, fontWeight: 700, color: theme.primary }}>LFL</span> : null)

  return (
    <div style={{ marginTop: 22, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '12px 16px', borderBottom: open ? `1px solid ${theme.border}` : 'none', background: theme.surfaceUp }}>
        <button type="button" onClick={toggleOpen} aria-expanded={open}
          style={{ all: 'unset', cursor: 'pointer', fontWeight: 700, fontSize: 14, color: theme.navy }}>
          {open ? '▾' : '▸'} {title} · by {grain}
        </button>
        <div role="group" aria-label="Show by" style={{ display: 'flex' }}>
          <button type="button" style={{ ...seg(grain === 'store'), borderRadius: '8px 0 0 8px' }} aria-pressed={grain === 'store'} onClick={() => setGrain('store')}>Store</button>
          <button type="button" style={{ ...seg(grain === 'cluster'), borderRadius: '0 8px 8px 0', marginLeft: -1 }} aria-pressed={grain === 'cluster'} onClick={() => setGrain('cluster')}>Cluster</button>
        </div>
        {open && !division && (
          <select value={div} onChange={e => { setDiv(e.target.value); setDept('') }} aria-label="Division"
            style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 12 }}>
            {DIVS.filter(d => stage === 'division' || stage === 'display' || d !== 'ALL').map(d => <option key={d} value={d}>{d === 'ALL' ? 'All divisions' : d}</option>)}
          </select>
        )}
        {open && (stage === 'department' || stage === 'mrp') && deptList.length > 0 && (
          <select value={dept} onChange={e => setDept(e.target.value)} aria-label="Department"
            style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 12, maxWidth: 260 }}>
            {deptList.map(d => <option key={d.dept} value={d.dept}>{d.dept}</option>)}
          </select>
        )}
        {open && ly && (
          <select value={method} onChange={e => setMethod(e.target.value)} aria-label="How the plan is built"
            title="Today's plan, or a preview of a plan built from the AOP Forecaster's store forecast x BIS growth - nothing is saved"
            style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${method === 'ty' ? theme.border : theme.warning}`, fontSize: 12, fontWeight: method === 'ty' ? 400 : 700 }}>
            <option value="ty">Today's plan</option>
            <option value="store_built">Preview: store-built (AOP × BIS)</option>
            <option value="cluster_built">Preview: cluster-built (AOP × BIS)</option>
          </select>
        )}
        {open && ly && (
          <div role="group" aria-label="Value" style={{ display: 'flex' }}>
            {[['ty', 'Plan'], ['ly', 'LY'], ['gr', 'Growth %']].map(([k, t], i) => (
              <button key={k} type="button" aria-pressed={measure === k} onClick={() => setMeasure(k)}
                style={{ ...seg(measure === k), borderRadius: i === 0 ? '8px 0 0 8px' : i === 2 ? '0 8px 8px 0' : 0, marginLeft: i ? -1 : 0 }}>{t}</button>
            ))}
          </div>
        )}
        {open && <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder={grain === 'cluster' ? 'Find a cluster or store' : 'Find a store or cluster'} aria-label="Find"
          style={{ marginLeft: 'auto', padding: '5px 9px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 12, minWidth: 170 }} />}
      </div>
      {open && (
        <div style={{ padding: '10px 16px 14px' }}>
          {err && <div style={{ color: theme.danger, fontSize: 12.5, padding: '6px 0' }}>Could not load: {err}</div>}
          {loading && !data && <div style={{ color: theme.textMuted, fontSize: 12.5, padding: '6px 0' }}>Loading - the first open after a change runs the plan (about 15 s)…</div>}
          {data?.note && <div style={{ color: theme.textMuted, fontSize: 12.5, padding: '6px 0' }}>{data.note}</div>}
          {data && !data.note && (<>
            <div style={{ fontSize: 11.5, color: theme.textMuted, marginBottom: 8 }}>
              From {data.source?.note} · ₹ lakh · {data.n_clusters} clusters, {data.n_stores} stores{data.n_empty ? ` (${data.n_empty} with no sales not listed)` : ''}
              {stage === 'mrp' && ` · ${data.dept}, ${(data.months || []).join(', ')}: each store's plan × the department's MRP split`}
              {grain === 'cluster' ? ' · click a cluster to see its stores' : ' · each store with its cluster and its share of it'}
              {loading && ' · updating…'}
            </div>
            {alt && (
              <div style={{ fontSize: 12, color: theme.textSecondary, background: alpha(theme.warning, '12'), border: `1px solid ${alpha(theme.warning, '40')}`, borderRadius: 8, padding: '8px 10px', marginBottom: 8, lineHeight: 1.5 }}>
                <b>Preview only - nothing is saved or adopted.</b>{' '}
                {method === 'store_built'
                  ? <>Each store's division total = its AOP Forecaster store forecast ({data.aop?.label}, publish {data.aop?.publish}), split over departments by the store's own LY department mix × BIS growth; a store with no LY of its own (a new store) takes its cluster's mix. Clusters are the sum of their stores.</>
                  : <>Each cluster's division total = the sum of its stores' AOP store forecasts ({data.aop?.label}, publish {data.aop?.publish}), split over departments by the cluster's LY mix × BIS growth, then given to its stores by each store's LY share. <b>Stores with no LY (new stores) get nothing here - their AOP is spread over the cluster's other stores.</b></>}
                {' '}Months: {(data.months || []).join(', ')} - the months this AOP version has LY for, so both sides cover the same months.
                {' '}The AOP store forecast includes new / ramp stores, which today's plan gives nothing (no LY) - most of the gap to today's plan is them.
              </div>
            )}
            <div style={{ overflow: 'auto', maxHeight: 520, border: `1px solid ${theme.border}`, borderRadius: 8 }}>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead><tr>
                  <th style={{ ...th, textAlign: 'left', left: 0, zIndex: 2 }}>{grain === 'cluster' ? 'Cluster' : 'Store'}</th>
                  {grain === 'store' && <th style={{ ...th, textAlign: 'left' }}>Cluster</th>}
                  {cols.map(c => <th key={c.key} style={th}>{c.label}</th>)}
                  <th style={th}>Plan (total)</th>
                  {ly && <th style={th}>LY (total)</th>}
                  {ly && <th style={th}>Growth</th>}
                  {alt && <th style={th} title="today's plan (the base plan)">Today's plan</th>}
                  {alt && <th style={th} title="this method minus today's plan">vs today</th>}
                  {alt && stage === 'division' && <th style={th} title="the AOP Forecaster's store forecast">AOP</th>}
                  <th style={th} title={grain === 'cluster' ? 'share of the whole plan' : "share of its cluster's plan"}>{grain === 'cluster' ? 'Share' : 'Share of cluster'}</th>
                </tr></thead>
                <tbody>
                  {shown.map(r => {
                    const isOpen = expanded.has(r.key)
                    const share = grain === 'cluster' ? (tot(data) ? tot(r) / tot(data) * 100 : null) : (ctot(r) ? tot(r) / ctot(r) * 100 : null)
                    return [
                      <tr key={r.key} style={{ background: isOpen ? alpha(theme.primary, '10') : undefined }}>
                        <td style={{ ...td, textAlign: 'left', fontWeight: grain === 'cluster' ? 700 : 500, position: 'sticky', left: 0, background: theme.surface }}>
                          {grain === 'cluster'
                            ? <button type="button" aria-expanded={isOpen} onClick={() => setExpanded(s => { const n = new Set(s); if (n.has(r.key)) n.delete(r.key); else n.add(r.key); return n })}
                                style={{ all: 'unset', cursor: 'pointer' }} title={`${isOpen ? 'Hide' : 'Show'} its ${r.n_stores} stores`}>
                                {isOpen ? '▾' : '▸'} {r.label} <span style={{ fontWeight: 400, color: theme.textMuted, fontSize: 11 }}>· {r.n_stores} stores</span></button>
                            : <>{r.label}{lfl(r)}</>}
                        </td>
                        {grain === 'store' && <td style={{ ...td, textAlign: 'left', color: theme.textSecondary }}>{r.cluster}</td>}
                        {cells(r)}
                        <td style={{ ...td, color: theme.textSecondary }}>{share == null ? '–' : `${share.toFixed(1)}%`}</td>
                      </tr>,
                      ...(grain === 'cluster' && isOpen ? r.stores.filter(s => !ql || hit(r.label) || hit(s.label)).map(s => (
                        <tr key={r.key + '/' + s.key} style={{ background: alpha(theme.primary, '06') }}>
                          <td style={{ ...td, textAlign: 'left', paddingLeft: 30, color: theme.textSecondary, position: 'sticky', left: 0, background: theme.surface }}>{s.label}{lfl(s)}</td>
                          {cells(s, true)}
                          <td style={{ ...td, color: theme.textMuted }} title="share of its cluster">{tot(r) ? `${(tot(s) / tot(r) * 100).toFixed(1)}%` : '–'}</td>
                        </tr>)) : []),
                    ]
                  })}
                </tbody>
                <tfoot><tr>
                  <td style={{ ...foot, textAlign: 'left' }}>Total</td>
                  {grain === 'store' && <td style={foot} />}
                  {cols.map(c => {
                    if (c.pct) { const x = data.rows.reduce((a, r) => { const m = r.months?.[c.key] || {}; return { ty: a.ty + (m[F] || 0), ly: a.ly + (m.ly || 0) } }, { ty: 0, ly: 0 })
                      return <td key={c.key} style={{ ...foot, color: tone(gr(x.ty, x.ly)) }}>{P(gr(x.ty, x.ly))}</td> }
                    return <td key={c.key} style={foot}>{L(data.rows.reduce((a, r) => a + (c.get(r) || 0), 0))}</td>
                  })}
                  <td style={foot}>{L(tot(data))}</td>
                  {ly && <td style={foot}>{L(data.total?.ly)}</td>}
                  {ly && <td style={{ ...foot, color: tone(gr(data.total?.[F], data.total?.ly)) }}>{P(gr(data.total?.[F], data.total?.ly))}</td>}
                  {alt && <td style={foot}>{L(data.total?.ty)}</td>}
                  {alt && <td style={{ ...foot, color: tone(tot(data) - (data.total?.ty || 0)) }}>{L(tot(data) - (data.total?.ty || 0))}</td>}
                  {alt && stage === 'division' && <td style={foot}>{L(data.total?.aop)}</td>}
                  <td style={foot}>100%</td>
                </tr></tfoot>
              </table>
            </div>
            {grain === 'store' && rows.length > STORE_CAP && (
              <button type="button" onClick={() => setShowAll(v => !v)} style={{ marginTop: 8, fontSize: 12, color: theme.primary, background: 'none', border: 'none', cursor: 'pointer' }}>
                {showAll ? `Show the top ${STORE_CAP}` : `Show all ${rows.length} stores`}</button>
            )}
          </>)}
        </div>
      )}
    </div>
  )
}
