import { useState, useMemo, useEffect } from 'react'

// NOTE: `validationIssues` are the actual objects returned by `lib/engine.js`'s
// `validate()` - `{ type: 'error'|'warn'|'info', icon, title, desc }` - not
// plain strings as the task-8 brief's illustrative snippet assumed. Rendered
// accordingly below (title + desc, colour keyed off `type`).
//
// `dayMap` rows are built by index.jsx's toRow(): `category` carries
// engine.js's own `festiveCategory` string verbatim ('Pre-Festive' /
// 'Core Festive' / 'Post-Festive' / 'Non-Festive'), and monthDelta/weekdayDelta
// are the strings 'Yes'/'No'. The two lookup tables below are ported from the
// old app's renderDayTable() (calendar_engine.html lines 1841-1842) and key off
// exactly those values.
const CAT_BADGE = { 'Pre-Festive': 'b-pre', 'Core Festive': 'b-core', 'Post-Festive': 'b-post', 'Non-Festive': 'b-non' }
const CAT_ROW = { 'Pre-Festive': 'r-pre', 'Core Festive': 'r-core', 'Post-Festive': 'r-post', 'Non-Festive': '' }

// Ported from calendar_engine.html's renderValidation() (line ~1958).
const VAL_CLASS = { error: 'val-error', warn: 'val-warn', info: 'val-info' }

// Full month names, matching the old app's own MONTHS const (calendar_engine.html
// line 1336) that renderMonthly() indexes by month number - and the same local
// convention DateShiftPreviewPanel.jsx already uses. The By-Future-Month
// contribution pills slice these to 3 chars exactly as the old app does.
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

// Day-by-Day filter option lists, ported from the old app's left filter rail
// (calendar_engine.html lines 632-660). Category and Mapping Type are fixed sets
// there and here; Festival and Month are derived from the live mapping set by
// populateFilters() (line ~1811), so they're built with useMemo below instead.
//
// CATEGORY_OPTIONS deliberately reuses the exact strings CAT_BADGE/CAT_ROW key
// off - i.e. engine.js's own festiveCategory values, which toRow() copies into
// row.category verbatim. MAP_TYPE_OPTIONS is the same 7-value list now shown in
// VersionSettingTab.jsx's Mapping Type Reference card and is what row.mappingType
// actually contains. Note the old app's <option> *labels* were abbreviated
// ("Same Month + Weekday") while its values were the full strings; the full
// strings are used for both here so the dropdown reads the same as the table's
// own Mapping Type column.
const CATEGORY_OPTIONS = ['Pre-Festive', 'Core Festive', 'Post-Festive', 'Non-Festive']
const MAP_TYPE_OPTIONS = [
  'Festival-to-Festival',
  'Festive Relative Day',
  'Same Month + Same Weekday',
  'Same Month + Nearest Weekday',
  'Previous Month + Same Weekday',
  'Next Month + Same Weekday',
  'Nearest Available Date',
]

// Same four swatches as the old rail's Legend section (calendar_engine.html lines
// 668-675), expressed with the .leg-item/.leg-dot classes already in index.css
// and already used by VersionSettingTab.jsx's Festive Category Legend.
const CATEGORY_LEGEND = [
  ['var(--pre-bg)', 'var(--pre-border)', 'Pre-Festive'],
  ['var(--core-bg)', 'var(--core-border)', 'Core Festive'],
  ['var(--post-bg)', 'var(--post-border)', 'Post-Festive'],
  ['var(--light)', 'var(--border)', 'Non-Festive'],
]

// Same quoting convention as CalendarisedSalesTab/ReindexOutputPanel.jsx's
// csvField/downloadCsv - a cluster/festival name containing a comma or quote
// can't corrupt the file.
const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`

function downloadCsv(rows, filename) {
  const text = rows.map(r => r.map(csvField).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function OutputSection({ dayMap, allDayMap, validationIssues, monthlySummary }) {
  const [activeSub, setActiveSub] = useState('day')

  // ── Day-by-Day filters (old app's #filterMonth/#filterCat/#filterMap/
  // #filterFest/#filterMonthMatch). All are '' = no filter, and all combine with
  // AND, exactly as renderDayTable() chains its .filter() calls (line 1829-1836).
  // fCluster is new here (not in the old app, which had no cross-cluster preview
  // at all) - '' means every cluster, matching the "don't default to one cluster"
  // ask directly: the Day-by-Day preview shows the FULL combined set out of the
  // box, filterable down to one cluster same as any other dimension below.
  const [fCluster, setFCluster] = useState('')  // '' = all clusters
  const [fMonth, setFMonth] = useState('')       // '' | '0'..'11' (FUTURE month)
  const [fCat, setFCat] = useState('')
  const [fMapType, setFMapType] = useState('')
  const [fFest, setFFest] = useState('')
  const [fMoMatch, setFMoMatch] = useState('')   // '' | 'yes' | 'no'

  // A new allDayMap means a different data set - a regenerated calendar or a
  // snapshot loaded from the library (NOT a ClusterTabs switch - allDayMap is
  // cluster-independent, see index.jsx). Cluster/Festival/Month options are
  // derived from that set, so a stale selection (a cluster/festival the new set
  // doesn't have) would silently render an empty table. Clearing on identity
  // change keeps the rail honest; the old app got this for free by rebuilding
  // the <select>s in populateFilters() on every run.
  useEffect(() => {
    setFCluster(''); setFMonth(''); setFCat(''); setFMapType(''); setFFest(''); setFMoMatch('')
  }, [allDayMap])

  // The base row set for the Day-by-Day tab: every cluster's rows, narrowed to
  // one if fCluster is set. This is deliberately its own step (not folded into
  // the filter chain below) because `stats` also needs it - the stat tiles
  // reflect the cluster filter (selecting one cluster shows that cluster's own
  // totals) but, matching the existing "stat tiles always cover all N days"
  // convention, never reflect the OTHER filters (Month/Category/etc).
  const clusterScopedDayMap = useMemo(() => {
    if (!allDayMap) return []
    return fCluster ? allDayMap.filter(r => r.cluster === fCluster) : allDayMap
  }, [allDayMap, fCluster])

  // Stats row (old app's renderStats(), calendar_engine.html lines 1762-1775).
  // Every figure is a count over data this component is already handed - no
  // extra fetching. `festival` is '' for non-festive rows (see toRow()).
  const stats = useMemo(() => {
    if (!allDayMap) return null
    const total = clusterScopedDayMap.length
    const festive = clusterScopedDayMap.filter(r => r.festival).length
    return {
      total,
      festive,
      nonFestive: total - festive,
      sameMonth: clusterScopedDayMap.filter(r => r.monthDelta === 'Yes').length,
      sameWeekday: clusterScopedDayMap.filter(r => r.weekdayDelta === 'Yes').length,
      errors: (validationIssues || []).filter(i => i.type === 'error').length,
    }
  }, [allDayMap, clusterScopedDayMap, validationIssues])

  // Cluster/Festival/Month dropdown options, built from whatever is actually in
  // the current combined mapping set - the old app's populateFilters()
  // (calendar_engine.html lines 1811-1817), extended with clusters since the old
  // app never had more than one cluster in view at once. Festivals/months are
  // deliberately drawn from the FULL set (not clusterScopedDayMap) so switching
  // the cluster filter doesn't also reshuffle the other dropdowns out from under
  // a selection the user just made.
  const { clusterOptions, festivalOptions, monthOptions } = useMemo(() => {
    if (!allDayMap) return { clusterOptions: [], festivalOptions: [], monthOptions: [] }
    const clusters = new Set()
    const fests = new Set()
    const months = new Set()
    for (const r of allDayMap) {
      if (r.cluster) clusters.add(r.cluster)
      if (r.festival) fests.add(r.festival)
      if (r.futMonthIdx != null) months.add(r.futMonthIdx)
    }
    return {
      clusterOptions: [...clusters].sort(),
      festivalOptions: [...fests].sort(),
      monthOptions: [...months].sort((a, b) => a - b),
    }
  }, [allDayMap])

  // The filter chain itself - a direct port of renderDayTable()'s (line 1829-1836),
  // with the new app's row shape substituted for the raw mapping objects:
  //   m.futureDate.getMonth() -> row.futMonthIdx   (added by index.jsx's toRow)
  //   m.festiveCategory       -> row.category
  //   m.monthMatch (boolean)  -> row.monthDelta === 'Yes'  (toRow stringifies it)
  // Only the multi-select month picker is dropped; a single <select> covers the
  // same filtering job (see the note at the foot of this file). Cluster is
  // already applied via clusterScopedDayMap above, so it isn't repeated here.
  const filteredDayMap = useMemo(() => {
    let rows = clusterScopedDayMap
    if (fMonth !== '') rows = rows.filter(r => r.futMonthIdx === +fMonth)
    if (fCat) rows = rows.filter(r => r.category === fCat)
    if (fMapType) rows = rows.filter(r => r.mappingType === fMapType)
    if (fFest) rows = rows.filter(r => r.festival === fFest)
    if (fMoMatch === 'yes') rows = rows.filter(r => r.monthDelta === 'Yes')
    if (fMoMatch === 'no') rows = rows.filter(r => r.monthDelta !== 'Yes')
    return rows
  }, [clusterScopedDayMap, fMonth, fCat, fMapType, fFest, fMoMatch])

  const anyFilterActive = !!fCluster || fMonth !== '' || !!fCat || !!fMapType || !!fFest || !!fMoMatch

  // Exports exactly what's currently on screen (every active filter, cluster
  // included) - "download the calendar to understand the gist" reads as "give
  // me what I'm looking at", not a separate full-set export. Column order
  // matches the visible table (see the <thead> below), with Cluster prepended.
  function downloadCalendar() {
    const header = ['Cluster', 'Ref Date', 'Ref Day', 'Ref Wk', 'Festival', 'Category', 'Position',
      'Future Date', 'Future Day', 'Future Wk', 'Fut Festival', 'Mapping Type', 'Score', 'Mo', 'Wd', 'Day Delta']
    const rows = filteredDayMap.map(r => [
      r.cluster, r.refDate, r.refDay, r.refWeek, r.festival, r.category, r.position,
      r.futDate, r.futDay, r.futWeek, r.futFestival, r.mappingType, r.score, r.monthDelta, r.weekdayDelta, r.dayDelta,
    ])
    const stamp = fCluster ? fCluster.replace(/[^a-z0-9]+/gi, '_') : 'all_clusters'
    downloadCsv([header, ...rows], `calendar_day_by_day_${stamp}.csv`)
  }

  // Monthly Summary derivations - ported 1:1 from the old app's renderMonthly()
  // (calendar_engine.html lines 1870-1941). Both loops walk months 0-11 and
  // `continue` past any month whose total is 0, so empty months are skipped
  // rather than rendered as blank rows; the TOTAL row therefore sums only the
  // months actually shown (which, since skipped months contribute 0, equals the
  // grand total either way).
  const { refRows, refTotals, futRows } = useMemo(() => {
    if (!monthlySummary) return { refRows: [], refTotals: null, futRows: [] }
    const { byRef, byFut } = monthlySummary
    const totals = { total: 0, same: 0, prev: 0, next: 0, other: 0, pre: 0, core: 0, post: 0, non: 0 }
    const rRows = []
    for (let m = 0; m < 12; m++) {
      const r = byRef[m]
      if (!r || r.total === 0) continue
      totals.total += r.total; totals.same += r.sameMonth; totals.prev += r.prevMonth
      totals.next += r.nextMonth; totals.other += r.other
      totals.pre += r.pre; totals.core += r.core; totals.post += r.post; totals.non += r.non
      // "Shifted out" = every day of this ref month that did NOT land in the
      // same-numbered future month (old app: prevMonth + nextMonth + other).
      rRows.push({ m, r, lost: r.prevMonth + r.nextMonth + r.other })
    }
    const fRows = []
    for (let m = 0; m < 12; m++) {
      const f = byFut[m]
      if (!f || f.total === 0) continue
      const contribs = Object.entries(f.daysFromRef)
        .sort((a, b) => +a[0] - +b[0])
        .map(([rm, cnt]) => ({ rm: +rm, cnt, isSameMonth: +rm === m }))
      const externalDays = contribs.filter(c => !c.isSameMonth).reduce((a, c) => a + c.cnt, 0)
      fRows.push({ m, f, contribs, externalDays })
    }
    return { refRows: rRows, refTotals: totals, futRows: fRows }
  }, [monthlySummary])

  if (!allDayMap) return null

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'day' ? 'active' : ''} onClick={() => setActiveSub('day')}>Day-by-Day Mapping</button>
        <button className={activeSub === 'monthly' ? 'active' : ''} onClick={() => setActiveSub('monthly')}>Monthly Summary</button>
        <button className={activeSub === 'validation' ? 'active' : ''} onClick={() => setActiveSub('validation')}>Validation</button>
      </div>

      {activeSub === 'day' && (
        <>
          {stats && (
            <div className="stats">
              <div className="stat"><div className="stat-val" style={{ color: 'var(--navy)' }}>{stats.total}</div><div className="stat-lbl">Total Days Mapped</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--warn)' }}>{stats.festive}</div><div className="stat-lbl">Festive Days</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--char)' }}>{stats.nonFestive}</div><div className="stat-lbl">Non-Festive Days</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--green)' }}>{stats.sameMonth}</div><div className="stat-lbl">Same Month Mapped</div></div>
              <div className="stat"><div className="stat-val" style={{ color: 'var(--green)' }}>{stats.sameWeekday}</div><div className="stat-lbl">Same Weekday Matched</div></div>
              <div className="stat"><div className="stat-val" style={{ color: stats.errors ? 'var(--red)' : 'var(--green)' }}>{stats.errors}</div><div className="stat-lbl">Validation Errors</div></div>
            </div>
          )}

          {/* ── Filter rail ──────────────────────────────────────────────────
              The old app's equivalent is a fixed-width left <aside class="cal-left">
              beside the table (calendar_engine.html lines 610-677). Rendered here as
              a horizontal bar above the table instead: OutputSection is a single
              `card` inside a <main> that already sits next to the 320px Calendar
              Library aside, so a second left rail would mean restructuring both this
              component and its parent's flex layout for no functional gain. The bar
              uses .field-row/.field, the same grouping DateShiftPreviewPanel.jsx's
              filter toolbar uses, so the two read as one pattern. */}
          <div className="field-row" style={{ marginBottom: '10px' }}>
            <div className="field">
              <label htmlFor="dm-cluster">Cluster</label>
              <select id="dm-cluster" value={fCluster} onChange={e => setFCluster(e.target.value)}>
                <option value="">All Clusters</option>
                {clusterOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dm-month">Month (future)</label>
              <select id="dm-month" value={fMonth} onChange={e => setFMonth(e.target.value)}>
                <option value="">All Months</option>
                {monthOptions.map(m => <option key={m} value={m}>{MONTHS[m]}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dm-cat">Category</label>
              <select id="dm-cat" value={fCat} onChange={e => setFCat(e.target.value)}>
                <option value="">All</option>
                {CATEGORY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dm-map">Mapping Type</label>
              <select id="dm-map" style={{ maxWidth: '220px' }} value={fMapType} onChange={e => setFMapType(e.target.value)}>
                <option value="">All Types</option>
                {MAP_TYPE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dm-fest">Festival</label>
              <select id="dm-fest" style={{ maxWidth: '200px' }} value={fFest} onChange={e => setFFest(e.target.value)}>
                <option value="">All Festivals</option>
                {festivalOptions.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="dm-momatch">Month Match</label>
              <select id="dm-momatch" value={fMoMatch} onChange={e => setFMoMatch(e.target.value)}>
                <option value="">All</option>
                <option value="yes">Same month</option>
                <option value="no">Cross-month</option>
              </select>
            </div>
            {/* Clear-filters is intentionally unclassed: index.css's bare `button`
                rule is the ported ghost/secondary look, while .btn is the loud navy
                primary reserved for "Create Calendar". */}
            {anyFilterActive && (
              <button onClick={() => {
                setFCluster(''); setFMonth(''); setFCat(''); setFMapType(''); setFFest(''); setFMoMatch('')
              }}>Clear filters</button>
            )}
            {/* "if the preview pane is open" - this whole block only renders once
                allDayMap exists (the `if (!allDayMap) return null` guard above),
                so the button is inherently gated on that already. Exports exactly
                what's currently filtered/visible, not a separate full-set dump. */}
            <button className="btn" onClick={downloadCalendar} disabled={!filteredDayMap.length} style={{ marginLeft: anyFilterActive ? '0' : 'auto' }}>
              Download Calendar
            </button>
          </div>

          {/* Filtered row count (old app's #dayCount, set in renderDayTable at line
              1838). Worded to stay distinct from the stat tiles above, which always
              summarise the whole generated calendar and never react to these filters. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
              Showing <strong style={{ color: 'var(--char)' }}>{filteredDayMap.length}</strong> of {clusterScopedDayMap.length} mappings
              {anyFilterActive && <> · stat tiles above always cover all {clusterScopedDayMap.length} days</>}
            </span>
            <div className="legend" style={{ flexDirection: 'row', gap: '12px', marginBottom: 0, marginLeft: 'auto' }}>
              {CATEGORY_LEGEND.map(([bg, border, name]) => (
                <div className="leg-item" key={name} style={{ gap: '6px', fontSize: '11px' }}>
                  <div className="leg-dot" style={{ width: '11px', height: '11px', background: bg, border: `1px solid ${border}` }} />
                  <span>{name}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th><th>Ref Date</th><th>Ref Day</th><th>Ref Wk</th><th>Festival</th><th>Category</th>
                  <th>Position</th><th>-&gt;</th><th>Future Date</th><th>Future Day</th><th>Future Wk</th>
                  <th>Fut Festival</th><th>Mapping Type</th><th>Score</th><th>Mo</th><th>Wd</th><th>Day Delta</th>
                </tr>
              </thead>
              <tbody>
                {filteredDayMap.length === 0 && (
                  <tr><td colSpan={17} style={{ textAlign: 'center', color: 'var(--muted)', padding: '24px 12px' }}>
                    {clusterScopedDayMap.length === 0
                      ? 'No mappings to show.'
                      : 'No mappings match the current filters.'}
                  </td></tr>
                )}
                {filteredDayMap.map((row, i) => (
                  <tr key={i} className={CAT_ROW[row.category] || ''}>
                    <td style={{ fontWeight: 600 }}>{row.cluster}</td>
                    <td className="date-mono">{row.refDate}</td>
                    <td>{row.refDay}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.refWeek}</td>
                    <td>{row.festival || <span style={{ color: 'var(--muted)' }}>-</span>}</td>
                    <td><span className={`badge ${CAT_BADGE[row.category] || 'b-non'}`}>{row.category}</span></td>
                    <td style={{ color: 'var(--muted)' }}>{row.position}</td>
                    <td className="arrow-sep">-&gt;</td>
                    <td className="date-mono">{row.futDate}</td>
                    <td>{row.futDay}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.futWeek}</td>
                    <td style={{ color: 'var(--muted)' }}>{row.futFestival || '-'}</td>
                    <td><span className="b-map">{row.mappingType}</span></td>
                    <td style={{ textAlign: 'right', color: 'var(--muted)' }}>{row.score}</td>
                    <td><span className={row.monthDelta === 'Yes' ? 'check' : 'cross'}>{row.monthDelta}</span></td>
                    <td><span className={row.weekdayDelta === 'Yes' ? 'check' : 'cross'}>{row.weekdayDelta}</span></td>
                    <td style={{ textAlign: 'right', color: Math.abs(row.dayDelta) > 30 ? 'var(--warn)' : 'var(--muted)' }}>
                      {row.dayDelta >= 0 ? '+' : ''}{row.dayDelta}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeSub === 'monthly' && monthlySummary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(520px, 1fr))', gap: '20px' }}>
          {/* ── By Reference Month ─────────────────────────────────────── */}
          <div>
            <div className="section-heading"><h4>By Reference Month - Where did each month map to?</h4></div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ref Month</th>
                    <th className="num">Total</th>
                    <th className="num" title="Mapped to same future month">Same Mo</th>
                    <th className="num" title="Mapped to previous month">Prev</th>
                    <th className="num" title="Mapped to next month">Next</th>
                    <th className="num">Pre-Fest</th>
                    <th className="num">Core</th>
                    <th className="num">Post-Fest</th>
                    <th className="num">Non-Fest</th>
                    <th>Net Month Shift</th>
                  </tr>
                </thead>
                <tbody>
                  {refRows.map(({ m, r, lost }) => (
                    <tr key={m}>
                      <td className="month-nm">{MONTHS[m]}</td>
                      <td className="num">{r.total}</td>
                      <td className="num">{r.sameMonth}</td>
                      <td className="num" style={{ color: r.prevMonth > 0 ? 'var(--warn)' : 'var(--muted)' }}>{r.prevMonth || '-'}</td>
                      <td className="num" style={{ color: r.nextMonth > 0 ? 'var(--warn)' : 'var(--muted)' }}>{r.nextMonth || '-'}</td>
                      <td className="num" style={{ color: 'var(--pre-text)' }}>{r.pre || '-'}</td>
                      <td className="num" style={{ color: 'var(--core-text)', fontWeight: 700 }}>{r.core || '-'}</td>
                      <td className="num" style={{ color: 'var(--post-text)' }}>{r.post || '-'}</td>
                      <td className="num" style={{ color: 'var(--muted)' }}>{r.non}</td>
                      <td>
                        {lost === 0
                          ? <span className="shift-pill shift-neutral">Neutral</span>
                          : <span className="shift-pill shift-loss">-{lost} day{lost > 1 ? 's' : ''} shifted out</span>}
                      </td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td>TOTAL</td>
                    <td className="num">{refTotals.total}</td>
                    <td className="num">{refTotals.same}</td>
                    <td className="num">{refTotals.prev}</td>
                    <td className="num">{refTotals.next}</td>
                    <td className="num">{refTotals.pre}</td>
                    <td className="num">{refTotals.core}</td>
                    <td className="num">{refTotals.post}</td>
                    <td className="num">{refTotals.non}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ── By Future Month ────────────────────────────────────────── */}
          <div>
            <div className="section-heading"><h4>By Future Month - Which reference months feed each future month?</h4></div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Future Month</th>
                    <th className="num">Total Days</th>
                    <th>Contributions from Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {futRows.map(({ m, f, contribs, externalDays }) => (
                    <tr key={m}>
                      <td className="month-nm">{MONTHS[m]}</td>
                      <td className="num">{f.total}</td>
                      <td>
                        {contribs.map(({ rm, cnt, isSameMonth }) => (
                          <span
                            key={rm}
                            style={{
                              fontSize: '11px',
                              background: isSameMonth ? 'var(--light)' : 'var(--pre-bg)',
                              color: isSameMonth ? 'var(--navy)' : 'var(--pre-text)',
                              padding: '1px 7px',
                              borderRadius: '10px',
                              fontWeight: 600,
                              marginRight: '4px',
                              display: 'inline-block',
                            }}
                          >
                            {MONTHS[rm].slice(0, 3)}: {cnt}
                          </span>
                        ))}
                        {externalDays > 0 && (
                          <span className="shift-pill shift-gain" style={{ marginLeft: '4px' }}>+{externalDays} shifted in</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeSub === 'validation' && (
        validationIssues.length === 0 ? (
          <div className="empty-state">
            <p style={{ fontWeight: 600, marginBottom: '4px' }}>No validation issues found</p>
            <p>All mappings passed the validation checks.</p>
          </div>
        ) : (
          <>
            <div className="section-heading">
              <h4>Validation Results</h4>
              <span className="count">{validationIssues.length} issue{validationIssues.length > 1 ? 's' : ''}</span>
            </div>
            <div className="val-list">
              {validationIssues.map((issue, i) => (
                <div key={i} className={`val-item ${VAL_CLASS[issue.type] || 'val-info'}`}>
                  <div className="val-icon">{issue.icon}</div>
                  <div className="val-txt">
                    <div className="val-title">{issue.title}</div>
                    <div className="val-desc">{issue.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )
      )}
    </div>
  )
}

// KNOWN SIMPLIFICATION vs. the old app's filter rail:
// The Month filter is a single <select>. calendar_engine.html additionally carried a
// checkbox multi-select with a search box (.mo-ms-* markup at lines 615-631, backed by
// window._calMonths), whose Set took priority over the plain #filterMonth <select> when
// non-empty - the two coexisted, filtering the same futureDate month. Only the plain
// select is ported: the multi-select is a UX affordance, not extra filtering power, and
// the single control covers the same behaviour with none of the dropdown/outside-click/
// search plumbing. If multi-month selection is wanted later, `fMonth` becomes a Set and
// the one `r.futMonthIdx === +fMonth` line becomes `fMonthSet.has(r.futMonthIdx)`.
