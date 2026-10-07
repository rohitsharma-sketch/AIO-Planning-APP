import { useState, useEffect, useMemo } from 'react'
import { listCalendarLibrary, getCalendar, getStoreClusterMap } from '../../lib/api'
import { buildFestMap } from '../../lib/engine'
import { parseDate, fmtDisp, calDiff } from '../../lib/dateUtils'
import { useStoredFlag } from '../ui'

// Ported from the old app's "Store-Cluster x Date Shift" panel
// (calendar_engine.html lines ~956-993 markup, ~3245-3423 behaviour): the ten
// real columns, the cascading Cluster / Ref Month / Festival / Category
// filters, click-to-sort headers, the DS_CAP render cap and the CSV export of
// the *filtered* (not the capped/visible) set.
//
// NOTE: the "Cluster x Day" level toggle below is intentionally not wired up yet.
// The table always shows store-level rows regardless of which radio is selected.
// Aggregating to one row per cluster (and CSV download) is a deliberate follow-up,
// out of scope for this task.

// calendar_engine.html line 3247. A real calendar is ~223 stores x 365 day
// pairs ≈ 81,000 rows; rendering that many <tr> synchronously locks the tab for
// ~30s, so only the first DS_CAP are ever put in the DOM. Filtering, sorting
// and the CSV export all still run over the full set.
const DS_CAP = 500

// Redefined here rather than imported: lib/dateUtils.js keeps MON3 private and
// exports no weekday/month-name arrays (CalendarisationTab/index.jsx redefines
// DAYS for the same reason). Ported from calendar_engine.html lines 1336-1338.
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

// Same lookup tables OutputSection.jsx uses, keying off engine.js's own
// `category` strings verbatim.
const CAT_BADGE = { 'Pre-Festive': 'b-pre', 'Core Festive': 'b-core', 'Post-Festive': 'b-post', 'Non-Festive': 'b-non' }
const CAT_ROW = { 'Pre-Festive': 'r-pre', 'Core Festive': 'r-core', 'Post-Festive': 'r-post', 'Non-Festive': '' }
const CAT_ORDER = ['Pre-Festive', 'Core Festive', 'Post-Festive', 'Non-Festive']

const COLUMNS = [
  { key: 'store', label: 'Store' },
  { key: 'cluster', label: 'Cluster' },
  { key: 'ref', label: 'Ref Date' },
  { key: 'refDay', label: 'Ref Day', ctx: true },
  { key: 'festival', label: 'Festival' },
  { key: 'category', label: 'Category' },
  { key: 'fut', label: 'Future Date' },
  { key: 'futDay', label: 'Fut Day', ctx: true },
  { key: 'shift', label: 'Days Moved', title: 'How many days the date moved: Future Date minus Ref Date (day-of-year basis). Not the window length.' },
  { key: 'monthMatch', label: 'Mo', title: 'Same month' },
]

// Same quoting the Store Mapping panel's CSV export uses (itself the old app's
// _scmCsv), so a store / cluster / festival name containing a comma or a quote
// cannot corrupt the file.
const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`

function downloadCsv(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function DateShiftPreviewPanel() {
  const [calendars, setCalendars] = useState([])
  const [calendarId, setCalendarId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [storeMap, setStoreMap] = useState(null)
  const [level, setLevel] = useState('store')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('store')
  const [sortDir, setSortDir] = useState(1)

  const [fCluster, setFCluster] = useState('')
  const [fMonth, setFMonth] = useState('')
  const [fFestival, setFFestival] = useState('')
  const [fCategory, setFCategory] = useState('')
  // 2026-10-07 declutter: Cluster / Ref Month / Festival / Category behind
  // "Filters"; Ref Day / Fut Day behind "+ Context columns".
  const [moreFilters, setMoreFilters] = useState(false)
  const [ctxCols, setCtxCols] = useStoredFlag('cal.dateShift.contextCols')
  const hiddenActive = [fCluster, fMonth, fFestival, fCategory].filter(v => v !== '').length

  useEffect(() => {
    listCalendarLibrary().then(setCalendars)
    getStoreClusterMap().then(setStoreMap)
  }, [])

  useEffect(() => {
    if (calendarId) getCalendar(calendarId).then(setDetail)
  }, [calendarId])

  // A different calendar has a different set of clusters / festivals, so no
  // filter selection from the previous one is guaranteed to still exist.
  useEffect(() => { setFCluster(''); setFMonth(''); setFFestival(''); setFCategory('') }, [calendarId])

  // Festival / category / days-moved / month-match are not stored on the saved
  // calendar - the backend's CalendarDayPair rows are bare (ref_date, fut_date)
  // pairs (router.py get_calendar, lines 127-134). They are reconstructed here
  // the same way CalendarisationTab/index.jsx's mappingsFromSavedPairs() does
  // it: buildFestMap() over the *cluster's own* saved festival list, which the
  // same response carries as detail.clusters[].festivals.
  //
  // Every store in a cluster shares that cluster's day pairs, so the per-day
  // derivation (date parsing, weekday, festive lookup, shift) is done once per
  // cluster (10 x 365 rows) and then fanned out across the cluster's stores,
  // instead of ~81,000 times.
  const rows = useMemo(() => {
    if (!detail || !storeMap) return []
    const refYr = Number(detail.refYear), futYr = Number(detail.futYear)
    const perCluster = {}
    // Driven off dayMap, not detail.clusters: dayMap is what a store row
    // actually needs, and a cluster with day pairs but no saved festival list
    // must still produce rows (all Non-Festive) rather than silently vanish.
    for (const [name, pairs] of Object.entries(detail.dayMap || {})) {
      const cl = (detail.clusters || []).find(c => c.name === name)
      const fests = (cl && cl.festivals) || []
      const rMap = buildFestMap(refYr, fests, refYr)
      const fMap = buildFestMap(futYr, fests, refYr)
      perCluster[name] = pairs.map(([ref, fut]) => {
        const rd = parseDate(ref), fd = parseDate(fut)
        const ri = rMap[ref], fi = fMap[fut]
        return {
          cluster: name,
          ref, fut,
          refDisp: fmtDisp(rd), futDisp: fmtDisp(fd),
          refDay: DAYS[rd.getDay()], futDay: DAYS[fd.getDay()],
          refMonth: rd.getMonth(),
          festival: ri ? ri.festival : '',
          category: ri ? ri.category : (fi ? fi.category : 'Non-Festive'),
          shift: calDiff(rd, fd),
          monthMatch: rd.getMonth() === fd.getMonth() ? 1 : 0,
        }
      })
    }
    const out = []
    for (const st of storeMap.stores) {
      const tpls = perCluster[st.cluster]
      if (!tpls) continue
      for (const t of tpls) out.push({ ...t, store: st.store })
    }
    return out
  }, [detail, storeMap])

  // Clusters this calendar actually carries a day mapping for that at least one
  // store is assigned to - i.e. exactly the clusters present in `rows`.
  const clusterOptions = useMemo(
    () => [...new Set(rows.map(r => r.cluster))].sort(),
    [rows])

  // Cascading options, ported from dsSyncFilters() (calendar_engine.html
  // ~3324-3362): each dropdown only offers values that actually occur once the
  // filters above it are applied, because every cluster has its own Festival
  // Master. Ref Month is derived from the loaded calendar for the same reason -
  // never a hardcoded Jan-Dec list.
  const ctxCluster = useMemo(
    () => (fCluster ? rows.filter(r => r.cluster === fCluster) : rows),
    [rows, fCluster])
  const festivalOptions = useMemo(
    () => [...new Set(ctxCluster.map(r => r.festival).filter(Boolean))].sort(),
    [ctxCluster])
  const ctxFestival = useMemo(() => {
    if (!fFestival) return ctxCluster
    if (fFestival === '__festive__') return ctxCluster.filter(r => !!r.festival)
    return ctxCluster.filter(r => r.festival === fFestival)
  }, [ctxCluster, fFestival])
  const monthOptions = useMemo(
    () => [...new Set(ctxFestival.map(r => r.refMonth))].sort((a, b) => a - b),
    [ctxFestival])
  const categoryOptions = useMemo(() => {
    const ctx = fMonth === '' ? ctxFestival : ctxFestival.filter(r => r.refMonth === +fMonth)
    return CAT_ORDER.filter(c => ctx.some(r => r.category === c))
  }, [ctxFestival, fMonth])

  // Drop a selection that the cascade above no longer offers (e.g. picking a
  // cluster whose schema has no "Diwali"), matching dsSyncFilters()'s keepIf().
  useEffect(() => {
    if (fFestival && fFestival !== '__festive__' && !festivalOptions.includes(fFestival)) setFFestival('')
  }, [festivalOptions, fFestival])
  useEffect(() => {
    if (fMonth !== '' && !monthOptions.includes(+fMonth)) setFMonth('')
  }, [monthOptions, fMonth])
  useEffect(() => {
    if (fCategory && !categoryOptions.includes(fCategory)) setFCategory('')
  }, [categoryOptions, fCategory])

  // The full filtered + sorted set. The CSV export uses this array, not the
  // capped slice rendered below.
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    const out = rows.filter(r =>
      (!fFestival || (fFestival === '__festive__' ? !!r.festival : r.festival === fFestival)) &&
      (!fCluster || r.cluster === fCluster) &&
      (fMonth === '' || r.refMonth === +fMonth) &&
      (!fCategory || r.category === fCategory) &&
      (!q || r.store.toLowerCase().includes(q) || r.cluster.toLowerCase().includes(q) ||
        r.festival.toLowerCase().includes(q) || r.ref.includes(q) || r.fut.includes(q)))
    // Ported from dsFiltered() (line ~3370): sort on the active key, then fall
    // back to store then ref date so the order is stable and readable.
    out.sort((a, b) =>
      ((a[sortKey] > b[sortKey]) - (a[sortKey] < b[sortKey])) * sortDir ||
      ((a.store > b.store) - (a.store < b.store)) ||
      ((a.ref > b.ref) - (a.ref < b.ref)))
    return out
  }, [rows, search, fCluster, fMonth, fFestival, fCategory, sortKey, sortDir])

  const visible = useMemo(() => filtered.slice(0, DS_CAP), [filtered])

  function sortBy(key) {
    if (key === sortKey) setSortDir(d => -d)
    else { setSortKey(key); setSortDir(1) }
  }

  function download() {
    if (!filtered.length) return
    const out = ['Store,Cluster,Ref Date,Ref Day,Festival,Category,Future Date,Future Day,Days Moved,Month Match']
    for (const r of filtered) {
      out.push([r.store, r.cluster, r.ref, r.refDay, r.festival, r.category,
        r.fut, r.futDay, r.shift, r.monthMatch ? 'Yes' : 'No'].map(csvField).join(','))
    }
    const name = (calendars.find(c => String(c.id) === String(calendarId)) || {}).name || 'calendar'
    downloadCsv(out.join('\n'), 'store_date_shift_' + name.replace(/[^a-z0-9]+/gi, '_').slice(0, 40) + '.csv')
  }

  const countText = !calendarId
    ? 'Pick a calendar to preview its store-level date shift.'
    : filtered.length > DS_CAP
      ? `Showing first ${DS_CAP} of ${filtered.length.toLocaleString()} rows - refine your search/filters to see more (Download CSV exports all ${filtered.length.toLocaleString()})`
      : `${filtered.length.toLocaleString()} rows`

  return (
    <>
      <div className="card" style={{ marginBottom: '12px' }}>
        <div className="card-label">
          Store-Cluster x Date Shift
          <span className="ce-info" tabIndex={0} aria-label="About this preview"
            title="Every store inherits the day-by-day date mapping of its calendar cluster. Pick a calendar and a level, then search, sort (click a column) and filter to preview the shift at any depth.">ⓘ</span>
        </div>
        <div className="scm-toolbar" style={{ alignItems: 'flex-end' }}>
          <div className="field">
            <label htmlFor="ds-calendar">Calendar</label>
            <select id="ds-calendar" style={{ maxWidth: '380px' }}
              value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
              <option value="">Select a calendar...</option>
              {calendars.map(c => (
                <option key={c.id} value={c.id}>{c.name} ({c.refYear} -&gt; {c.futYear}, locked)</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Level</label>
            <div className="ds-level">
              <label><input type="radio" checked={level === 'store'} onChange={() => setLevel('store')} /> Store x Day</label>
              <label><input type="radio" checked={level === 'cluster'} onChange={() => setLevel('cluster')} /> Cluster x Day</label>
            </div>
          </div>
          <div className="field">
            <label htmlFor="ds-search">Search</label>
            <input id="ds-search" type="text" style={{ width: '210px' }}
              placeholder="store, cluster, festival, date"
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          <button className="ce-link-btn" onClick={() => setMoreFilters(o => !o)} aria-expanded={moreFilters}>
            Filters{hiddenActive ? ` (${hiddenActive})` : ''} {moreFilters ? '▴' : '▾'}
          </button>
          <button className="ce-link-btn" onClick={() => {
            // hiding the context columns while sorted by one of them falls back to Store (audit 2026-10-07)
            if (ctxCols && COLUMNS.find(c => c.key === sortKey)?.ctx) { setSortKey('store'); setSortDir(1) }
            setCtxCols(!ctxCols)
          }} aria-pressed={ctxCols}
            title="Ref Day, Fut Day">
            {ctxCols ? '- Context columns' : '+ Context columns'}
          </button>
          {/* Kept in the DOM while hidden - display only. */}
          <div className="scm-toolbar" style={{ display: moreFilters ? 'flex' : 'none', flexBasis: '100%', order: 1, alignItems: 'flex-end', marginBottom: 0 }}>
          <div className="field">
            <label htmlFor="ds-cluster">Cluster</label>
            <select id="ds-cluster" value={fCluster} onChange={e => setFCluster(e.target.value)}>
              <option value="">All clusters</option>
              {clusterOptions.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ds-month">Ref Month</label>
            <select id="ds-month" value={fMonth} onChange={e => setFMonth(e.target.value)}>
              <option value="">All</option>
              {monthOptions.map(m => <option key={m} value={m}>{MONTHS[m]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ds-festival">Festival</label>
            <select id="ds-festival" style={{ maxWidth: '200px' }}
              value={fFestival} onChange={e => setFFestival(e.target.value)}>
              <option value="">All days</option>
              <option value="__festive__">All festive days</option>
              {festivalOptions.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ds-category">Category</label>
            <select id="ds-category" value={fCategory} onChange={e => setFCategory(e.target.value)}>
              <option value="">All</option>
              {categoryOptions.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          </div>
          <button className="btn" onClick={download} disabled={!filtered.length}>
            Download CSV (filtered)
          </button>
        </div>
      </div>

      <div className="card">
        <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>{countText}</div>
        <div className="tbl-wrap" style={{ maxHeight: '560px' }}>
          <table>
            <thead>
              <tr>
                {COLUMNS.filter(col => ctxCols || !col.ctx).map(col => (
                  <th key={col.key} title={col.title}
                    className={'ds-th' + (sortKey === col.key ? (sortDir === 1 ? ' sorted-asc' : ' sorted-desc') : '')}
                    onClick={() => sortBy(col.key)}>{col.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={r.store + '|' + r.ref + '|' + i} className={CAT_ROW[r.category] || ''}>
                  <td style={{ fontWeight: 600 }}>{r.store}</td>
                  <td>{r.cluster}</td>
                  <td className="date-mono">{r.refDisp}</td>
                  {ctxCols && <td>{r.refDay}</td>}
                  <td>{r.festival || <span className="cross">-</span>}</td>
                  <td><span className={`badge ${CAT_BADGE[r.category] || 'b-non'}`}>{r.category}</span></td>
                  <td className="date-mono">{r.futDisp}</td>
                  {ctxCols && <td>{r.futDay}</td>}
                  <td style={{ textAlign: 'right', color: Math.abs(r.shift) > 30 ? 'var(--warn)' : 'var(--muted)' }}>
                    {r.shift > 0 ? '+' : ''}{r.shift}
                  </td>
                  <td>{r.monthMatch ? <span className="check">Y</span> : <span className="cross">N</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
