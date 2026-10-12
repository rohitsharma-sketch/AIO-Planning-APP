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
  const [showAll, setShowAll] = useState(false)

  useEffect(() => { if (division && division !== div) { setDiv(division); setDept('') } }, [division])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return
    let gone = false
    setLoading(true); setErr('')
    const qs = new URLSearchParams({ grain, division: div, ...(dept ? { dept } : {}) })
    fetch(`/api/planning/grain/${stage}?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { if (!gone) { setData(j); if (j.dept && j.dept !== dept) setDept(j.dept) } })
      .catch(e => { if (!gone) setErr(e.message) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [open, stage, grain, div, dept])   // eslint-disable-line react-hooks/exhaustive-deps

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
      get: r => { const x = r.months?.[m] || {}; return measure === 'gr' ? gr(x.ty, x.ly) : x[measure] ?? 0 },
      pct: measure === 'gr',
    }))
  }, [data, stage, measure])

  const tot = r => (stage === 'display' ? r?.total?.plan : r?.total?.ty) ?? 0
  const ctot = r => (stage === 'display' ? r?.cluster_total?.plan : r?.cluster_total?.ty) ?? 0
  const ql = q.trim().toLowerCase()
  const hit = s => s.toLowerCase().includes(ql)
  const match = r => !ql || hit(`${r.label} ${r.cluster || ''}`) || (r.stores || []).some(s => hit(s.label))
  const rows = (data?.rows || []).filter(match)
  const shown = grain === 'store' && !showAll ? rows.slice(0, STORE_CAP) : rows
  const ly = stage === 'division' || stage === 'department'

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
        {open && (stage === 'department' || stage === 'mrp') && data?.departments?.length > 0 && (
          <select value={dept} onChange={e => setDept(e.target.value)} aria-label="Department"
            style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 12, maxWidth: 260 }}>
            {data.departments.map(d => <option key={d.dept} value={d.dept}>{d.dept}</option>)}
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
            <div style={{ overflow: 'auto', maxHeight: 520, border: `1px solid ${theme.border}`, borderRadius: 8 }}>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead><tr>
                  <th style={{ ...th, textAlign: 'left', left: 0, zIndex: 2 }}>{grain === 'cluster' ? 'Cluster' : 'Store'}</th>
                  {grain === 'store' && <th style={{ ...th, textAlign: 'left' }}>Cluster</th>}
                  {cols.map(c => <th key={c.key} style={th}>{c.label}</th>)}
                  <th style={th}>Plan (total)</th>
                  {ly && <th style={th}>LY (total)</th>}
                  {ly && <th style={th}>Growth</th>}
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
                    if (c.pct) { const x = data.rows.reduce((a, r) => { const m = r.months?.[c.key] || {}; return { ty: a.ty + (m.ty || 0), ly: a.ly + (m.ly || 0) } }, { ty: 0, ly: 0 })
                      return <td key={c.key} style={{ ...foot, color: tone(gr(x.ty, x.ly)) }}>{P(gr(x.ty, x.ly))}</td> }
                    return <td key={c.key} style={foot}>{L(data.rows.reduce((a, r) => a + (c.get(r) || 0), 0))}</td>
                  })}
                  <td style={foot}>{L(tot(data))}</td>
                  {ly && <td style={foot}>{L(data.total?.ly)}</td>}
                  {ly && <td style={{ ...foot, color: tone(gr(data.total?.ty, data.total?.ly)) }}>{P(gr(data.total?.ty, data.total?.ly))}</td>}
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
