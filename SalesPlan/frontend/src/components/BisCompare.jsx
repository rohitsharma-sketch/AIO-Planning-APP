import { useEffect, useMemo, useState } from 'react'
import { theme, alpha } from '../theme'

// A saved BIS version (Original / iteration) beside the live plan, department by department (user, 2026-10-13: "yes add
// it on the department pages" - every iteration holds each division on AOP, so they differ only below it). View only:
// live = what BIS last saved; both priced on the same LY (Sales Plan's like-for-like stores), Mar-Jun'27.
const L = v => v == null || !Number.isFinite(v) ? '–' : v.toLocaleString('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
const P = v => v == null || !Number.isFinite(v) ? '–' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
const gr = (x, ly) => (ly > 0 ? (x / ly - 1) * 100 : null)
const KEY = 'sp.bisCompare'

export default function BisCompare({ division }) {
  const [versions, setVersions] = useState([])
  const [vid, setVid] = useState(() => { try { return localStorage.getItem(KEY) || '' } catch { return '' } })
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [changedOnly, setChangedOnly] = useState(true)
  const [open, setOpen] = useState(null)   // department with its months shown

  useEffect(() => {
    fetch('/api/planning/department-plan/bis-versions').then(r => (r.ok ? r.json() : [])).then(setVersions).catch(() => setVersions([]))
  }, [])

  const pick = id => { setVid(id); try { localStorage.setItem(KEY, id) } catch { /* storage blocked */ } }

  useEffect(() => {
    if (!vid || !division) { setData(null); return }
    let gone = false
    setLoading(true); setErr('')
    fetch(`/api/planning/department-plan/bis-compare/${encodeURIComponent(vid)}?division=${division}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { if (!gone) setData(j) })
      .catch(e => { if (!gone) { setErr(e.message); setData(null); if (/saved any more/.test(e.message)) pick('') } })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [vid, division])   // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => {
    const rs = (data?.rows || []).map(r => ({ ...r, diff: r.it - r.live }))
    return rs.filter(r => !changedOnly || Math.abs(r.diff) > 0.005).sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))
  }, [data, changedOnly])

  if (!versions.length) return null
  const th = { padding: '7px 10px', fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textAlign: 'right', whiteSpace: 'nowrap',
    background: theme.surfaceUp, borderBottom: `1px solid ${theme.border}`, position: 'sticky', top: 0, zIndex: 1 }
  const td = { padding: '6px 10px', fontSize: 12, textAlign: 'right', whiteSpace: 'nowrap', borderBottom: `1px solid ${theme.border}`, fontVariantNumeric: 'tabular-nums' }
  const foot = { ...td, fontWeight: 700, borderTop: `2px solid ${theme.border}` }
  const tone = v => (v > 0.005 ? theme.success : v < -0.005 ? theme.danger : theme.textMuted)
  const T = data?.total
  const nChanged = (data?.rows || []).filter(r => Math.abs(r.it - r.live) > 0.005).length

  return (
    <div style={{ marginTop: 22, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '12px 16px', background: theme.surfaceUp, borderBottom: vid ? `1px solid ${theme.border}` : 'none' }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: theme.navy }}>{division} · compare with a BIS iteration</span>
        <select value={vid} onChange={e => pick(e.target.value)} aria-label="BIS version to compare with"
          style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${vid ? theme.warning : theme.border}`, fontSize: 12, fontWeight: vid ? 700 : 400 }}>
          <option value="">— none —</option>
          {versions.map(v => <option key={v.id} value={v.id}>{v.label} · {v.saved_at ? new Date(v.saved_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' }) : ''}</option>)}
        </select>
        {vid && <label style={{ fontSize: 12, color: theme.textSecondary, display: 'inline-flex', gap: 5, alignItems: 'center' }}>
          <input type="checkbox" checked={changedOnly} onChange={e => setChangedOnly(e.target.checked)} /> Changed departments only</label>}
        {loading && <span style={{ fontSize: 12, color: theme.textMuted }}>Loading…</span>}
      </div>
      {vid && (
        <div style={{ padding: '10px 16px 14px' }}>
          {err && <div style={{ color: theme.danger, fontSize: 12.5, padding: '6px 0' }}>Could not load: {err}</div>}
          {data && (<>
            <div style={{ fontSize: 12, color: theme.textSecondary, background: alpha(theme.warning, '12'), border: `1px solid ${alpha(theme.warning, '40')}`, borderRadius: 8, padding: '8px 10px', marginBottom: 8, lineHeight: 1.5 }}>
              <b>View only.</b> Live plan = what BIS last saved; <b>{data.version.label}</b> = that saved BIS version. Both are priced on the same LY - Sales Plan's {data.lfl_stores} like-for-like stores, {data.months.join(', ')} - so the gap is the growth difference alone (BIS's own LY base differs a little, so its totals do too).
              {' '}{nChanged ? `${nChanged} of ${data.rows.length} departments differ.` : 'No department differs - this version is the live plan.'} Click a department for its months.
              {data.rows.some(r => r.missing_it) && <> <b>{data.rows.filter(r => r.missing_it).length} departments are not in {data.version.label}</b> (e.g. split after it was saved) - priced at LY there.</>}
            </div>
            <div style={{ overflow: 'auto', maxHeight: 460, border: `1px solid ${theme.border}`, borderRadius: 8 }}>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead><tr>
                  <th style={{ ...th, textAlign: 'left', left: 0, zIndex: 2 }}>Department</th>
                  <th style={th}>LY (₹ L)</th>
                  <th style={th}>Live plan</th><th style={th}>Live growth</th>
                  <th style={th}>{data.version.label}</th><th style={th}>Its growth</th>
                  <th style={th} title="the BIS version minus the live plan">Difference</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => [
                    <tr key={r.department} onClick={() => setOpen(o => (o === r.department ? null : r.department))} style={{ cursor: 'pointer', background: open === r.department ? alpha(theme.primary, '10') : undefined }}>
                      <td style={{ ...td, textAlign: 'left', fontWeight: 600, position: 'sticky', left: 0, background: theme.surface }}>
                        {open === r.department ? '▾' : '▸'} {r.department}{r.inactive_it && <span style={{ marginLeft: 6, fontSize: 9.5, fontWeight: 700, color: theme.danger }}>INACTIVE IN {data.version.label.toUpperCase()}</span>}
                        {r.missing_it && <span style={{ marginLeft: 6, fontSize: 9.5, fontWeight: 700, color: theme.warning }} title="This department has no growth in that version (e.g. it was split from another one after it was saved) - priced at LY there">NOT IN {data.version.label.toUpperCase()}</span>}</td>
                      <td style={{ ...td, color: theme.textSecondary }}>{L(r.ly)}</td>
                      <td style={td}>{L(r.live)}</td><td style={{ ...td, color: tone(gr(r.live, r.ly)) }}>{P(gr(r.live, r.ly))}</td>
                      <td style={td}>{L(r.it)}</td><td style={{ ...td, color: tone(gr(r.it, r.ly)) }}>{P(gr(r.it, r.ly))}</td>
                      <td style={{ ...td, fontWeight: 700, color: tone(r.diff) }}>{r.diff > 0 ? '+' : ''}{L(r.diff)}</td>
                    </tr>,
                    ...(open === r.department ? data.months.map(m => { const x = r.months[m]; return (
                      <tr key={r.department + m} style={{ background: alpha(theme.primary, '06') }}>
                        <td style={{ ...td, textAlign: 'left', paddingLeft: 30, color: theme.textSecondary, position: 'sticky', left: 0, background: theme.surface }}>{m}</td>
                        <td style={{ ...td, color: theme.textSecondary }}>{L(x.ly)}</td>
                        <td style={{ ...td, color: theme.textSecondary }}>{L(x.live)}</td><td style={{ ...td, color: theme.textSecondary }}>{P(x.live_g)}</td>
                        <td style={{ ...td, color: theme.textSecondary }}>{L(x.it)}</td><td style={{ ...td, color: theme.textSecondary }}>{P(x.it_g)}</td>
                        <td style={{ ...td, color: tone(x.it - x.live) }}>{L(x.it - x.live)}</td>
                      </tr>) }) : []),
                  ])}
                  {!rows.length && <tr><td colSpan={7} style={{ ...td, textAlign: 'center', color: theme.textMuted }}>No department differs.</td></tr>}
                </tbody>
                <tfoot><tr>
                  <td style={{ ...foot, textAlign: 'left' }}>{division} total ({data.rows.length} departments)</td>
                  <td style={foot}>{L(T.ly)}</td>
                  <td style={foot}>{L(T.live)}</td><td style={{ ...foot, color: tone(gr(T.live, T.ly)) }}>{P(gr(T.live, T.ly))}</td>
                  <td style={foot}>{L(T.it)}</td><td style={{ ...foot, color: tone(gr(T.it, T.ly)) }}>{P(gr(T.it, T.ly))}</td>
                  <td style={{ ...foot, color: tone(T.it - T.live) }}>{T.it - T.live > 0 ? '+' : ''}{L(T.it - T.live)}</td>
                </tr></tfoot>
              </table>
            </div>
          </>)}
        </div>
      )}
    </div>
  )
}
