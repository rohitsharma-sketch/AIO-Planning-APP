import { useState, useEffect, useMemo, Fragment } from 'react'
import { getStoreClusterMap } from '../../lib/api'

// Ported from the old app's reindex output tabs (calendar_engine.html
// rxWideRows() ~3973-3989, rxRenderTabs() ~3990-4051, rxDownload() ~4059-4083):
// the long-form -> wide pivot, the three real tables it feeds, the 500-row
// render cap and the CSV export of the full (uncapped) set.

// calendar_engine.html line 4014 passes 500 as renderCsoTable()'s `limit` for
// all three tables. A real run is far bigger than that: the live month-wise run
// this was verified against pivots 15,492 long-form rows into 2,633 store x
// division rows, and a day-wise run is ~223 stores x up to 365 date columns.
// Only the first RX_CAP rows are ever put in the DOM; the search filter and the
// CSV exports still run over the full set.
const RX_CAP = 500

// Same quoting the Store Mapping and Date Shift Preview exports use (itself the
// old app's _rxCsvDownload / _scmCsv), so a store / division / cluster name
// containing a comma or a quote cannot corrupt the file.
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

// calendar_engine.html renders a missing (store, column) cell as '' rather than
// 0 - a store with no sales that day genuinely has no row in the source, which
// is not the same claim as "sold zero".
const cell = (v) => (v == null ? '' : v)
// Deliberately `== null` rather than the old app's falsy test (`v ? ... : ''`):
// a month whose rows genuinely sum to 0 is a real, different fact from one with
// no rows at all, and the live data does contain such totals - 49 of them in
// the month-wise run (ANG/CDIT, BKR/CDIT and other CDIT divisions carry
// explicit 0.00 values), which the old app silently rendered as blank. Blank
// here means only "nothing contributed to this cell".
const round2 = (v) => (v == null ? '' : +v.toFixed(2))

// Composite grain key separator: a character that cannot occur in a store or
// division name, so ('AB','C') and ('A','BC') can never collide into one row.
const KEY_SEP = '\u0001'

const KEY_LABELS = { store: 'Store', division: 'Division' }

const MONTH_ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function ReindexOutputPanel({ result, festivalByCluster, refDateByCluster }) {
  const [activeSub, setActiveSub] = useState('reindexed')
  const [search, setSearch] = useState('')
  // Reindexed Sales has two layouts to choose from: Wide (the existing
  // pivot - one row per store[+extra fields], one column per date/month;
  // good for a full year at a glance but the column count explodes with
  // extra output fields) and Stacked - one row per (store, date/month) pair,
  // restricted to just Store + Date/Month + Value regardless of which extra
  // fields were picked for the run, summed across those fields. Fewer
  // columns, a much lighter table to compute and render, meant for a quick
  // preview rather than the full detailed breakdown - the user picks
  // whichever fits what they're looking at.
  const [viewMode, setViewMode] = useState('wide')
  // Which months to show/export - applies to both Day-wise (columns are
  // individual dates, filtered by their own month) and Month-wise (columns
  // are already months) results, since this one panel serves both sources.
  // '' entries in the Set mean "not yet initialised"; empty Set after init
  // means "none selected" (deliberately shows nothing rather than silently
  // falling back to "all"). Starts null so the "select everything by
  // default" effect below can tell "not initialised" apart from "user
  // unchecked everything".
  const [selectedMonths, setSelectedMonths] = useState(null)
  // The reindex response carries only {store, division?, col, value} - no
  // cluster - so the Cluster column and the whole By Cluster tab need the
  // store -> cluster map fetched separately (the same GET the Date Shift
  // Preview panel and CalendarisedSalesTab/index.jsx already use).
  const [storeCluster, setStoreCluster] = useState(null)
  // Day-wise comparison download: shows a month-picker popover before generating
  // the CSV, since a full year at day-level (365 cols x 223 stores x 2 rows) is
  // too large to produce without knowing which months the planner actually wants.
  const [showDayDlMenu, setShowDayDlMenu] = useState(false)
  const [dayDlSel, setDayDlSel] = useState(null)
  // 'stacked' = two rows per store (Actual / Reindexed); 'wide' = one row per
  // store with paired date-columns ({date} Actual, {date} Reindexed, {date} Diff)
  const [dayDlFmt, setDayDlFmt] = useState('stacked')

  useEffect(() => {
    let alive = true
    getStoreClusterMap()
      .then(m => { if (alive) setStoreCluster(Object.fromEntries((m.stores || []).map(s => [s.store, s.cluster]))) })
      .catch(() => { if (alive) setStoreCluster({}) })
    return () => { alive = false }
  }, [])

  const ok = !!(result && result.ok)
  // keyFields comes straight from the backend now - it always lists every field
  // that identifies one output row (store[, division][, any extra output fields
  // the user picked]), so the table adapts to however many were selected instead
  // of assuming at most store+division. Falls back to the old grain-string guess
  // only for a result cached before keyFields existed.
  const keyFields = result?.keyFields || (result?.grain === 'store_division' ? ['store', 'division'] : ['store'])

  // rxWideRows(): group the long-form rows by the grain key, then hang each
  // row's {col: value} off that key. Deliberately does NOT depend on
  // storeCluster - the cluster is looked up per-cell below so that the map
  // arriving late does not re-pivot 15k+ rows.
  const wide = useMemo(() => {
    if (!ok) return []
    const byKey = new Map()
    for (const row of result.rows) {
      const k = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      let e = byKey.get(k)
      if (!e) {
        e = { vals: {} }
        for (const f of keyFields) e[f] = row[f] ?? ''
        byKey.set(k, e)
      }
      e.vals[row.col] = row.value
    }
    const out = [...byKey.values()]
    out.sort((a, b) => {
      for (const f of keyFields) {
        const d = (a[f] > b[f]) - (a[f] < b[f])
        if (d) return d
      }
      return 0
    })
    return out
  }, [ok, result])

  // '(unmapped)' rather than blank (calendar_engine.html uses blank in the wide
  // table but '(unmapped)' in the cluster rollup): a store missing from the
  // cluster map still has real sales in this result, so it gets a visible row
  // instead of being silently folded into an empty-named group.
  const clusterOf = (store) => (storeCluster && storeCluster[store]) || '(unmapped)'

  const filteredWide = useMemo(() => {
    const q = search.toLowerCase().trim()
    if (!q) return wide
    return wide.filter(r =>
      String(r.store).toLowerCase().includes(q) ||
      String(r.division ?? '').toLowerCase().includes(q) ||
      clusterOf(r.store).toLowerCase().includes(q))
  }, [wide, search, storeCluster])

  // Wide rows grouped by cluster, sorted within each - lets both the table
  // and downloadReindexed give every cluster its own Reference Date/Festival
  // header block, instead of one global header row that can only ever be
  // true for one cluster's mapping at a time. An earlier fix hid that header
  // entirely for a mixed-cluster export rather than show it wrong - found
  // live 2026-09-02 that trading wrong data for MISSING data isn't right
  // either; a planner needs this info just as much as a single-cluster view
  // does. Grouping keeps it both present and correct for every cluster.
  const wideByCluster = useMemo(() => {
    const byCluster = new Map()
    for (const r of filteredWide) {
      const cl = clusterOf(r.store)
      if (!byCluster.has(cl)) byCluster.set(cl, [])
      byCluster.get(cl).push(r)
    }
    return [...byCluster.entries()].sort((a, b) => (a[0] > b[0]) - (a[0] < b[0]))
  }, [filteredWide, storeCluster])

  // Stacked view: one row per (store, column) pair, summed across whatever
  // OTHER key fields (division, department, attribute1...) the run was
  // broken out by - restricted to Store + Date/Month + Value only, on
  // purpose, so this stays a light long-form list no matter how many extra
  // output fields were picked. Built straight off result.rows (not `wide`),
  // same source `_by_cluster`/`_summary` already use.
  const stacked = useMemo(() => {
    if (!ok) return []
    const byKey = new Map()  // `${store}${col}` -> {store, col, value}
    for (const row of result.rows) {
      const k = `${row.store}${KEY_SEP}${row.col}`
      const e = byKey.get(k)
      if (e) e.value += row.value
      else byKey.set(k, { store: row.store, col: row.col, value: row.value })
    }
    return [...byKey.values()].sort((a, b) =>
      (a.store > b.store) - (a.store < b.store) || (a.col > b.col) - (a.col < b.col))
  }, [ok, result])


  // Day-wise columns are YYYY-MM-DD and collapse to months here; month-wise
  // columns are already YYYY-MM, so slice(0,7) leaves them untouched and the
  // summary is the same grain as the reindexed table (matching the old app).
  const monthCols = useMemo(
    () => (ok ? [...new Set(result.columns.map(c => c.slice(0, 7)))].sort() : []),
    [ok, result])

  // Reset the month filter to "everything" on a new result (a fresh reindex
  // run or a switch between Day-wise/Month-wise) - a stale selection from a
  // previous run's month list would otherwise silently hide months that are
  // actually present in this one.
  useEffect(() => { setSelectedMonths(new Set(monthCols)) }, [monthCols])

  const activeMonths = selectedMonths || new Set(monthCols)
  function toggleMonth(m) {
    setSelectedMonths(prev => {
      const next = new Set(prev || monthCols)
      next.has(m) ? next.delete(m) : next.add(m)
      return next
    })
  }

  // What "Reindexed Sales" (day-level or month-level raw columns) shows and
  // downloads - Day-wise columns are individual dates, so a month is excluded
  // by matching its own YYYY-MM prefix; Month-wise columns already are that
  // prefix, so this filters them directly.
  const visibleColumns = useMemo(
    () => result?.columns?.filter(c => activeMonths.has(c.slice(0, 7))) || [],
    [result, activeMonths])
  // What "Monthly Summary" and "By Cluster" show/download.
  const visibleMonthCols = useMemo(() => monthCols.filter(m => activeMonths.has(m)), [monthCols, activeMonths])

  // Stacked view's filtered rows - both the month filter (via visibleColumns,
  // same as every other tab) and the search box, which for this restricted
  // Store+Date/Month-only layout only makes sense against store/cluster (no
  // division/extra-field columns exist here to search against).
  const filteredStacked = useMemo(() => {
    const cols = new Set(visibleColumns)
    const q = search.toLowerCase().trim()
    return stacked.filter(r => cols.has(r.col) &&
      (!q || String(r.store).toLowerCase().includes(q) || clusterOf(r.store).toLowerCase().includes(q)))
  }, [stacked, visibleColumns, search, storeCluster])

  // Per-row (store[/division]) actual sums, keyed by reference month-number so
  // they can be matched to the reindexed side's future-dated columns - same
  // "actual is a different year, match by MM not by column string" rule as
  // p1p2Rows below, but kept PER key here (not collapsed to one global total)
  // so the Monthly Summary table can show a differential per store, not just
  // per month. mw results carry actualRows too (see reindex_monthwise), so
  // this works for both sources - a result cached before actualRows existed
  // just yields an empty map and the Actual/Diff columns are hidden below.
  const actualByKeyMM = useMemo(() => {
    if (!ok || !result.actualRows) return null
    const m = new Map()
    for (const row of result.actualRows) {
      const key = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      const mm = row.col.slice(5, 7)
      let e = m.get(key)
      if (!e) { e = {}; m.set(key, e) }
      e[mm] = (e[mm] || 0) + row.value
    }
    return m
  }, [ok, result])

  const summaryRows = useMemo(() => {
    if (!ok) return []
    return filteredWide.map(r => {
      const sums = {}
      for (const c of visibleColumns) {
        const v = r.vals[c]
        if (v != null) sums[c.slice(0, 7)] = (sums[c.slice(0, 7)] || 0) + v
      }
      const key = keyFields.map(f => r[f] ?? '').join(KEY_SEP)
      const actualForKey = actualByKeyMM?.get(key) || {}
      const actualSums = {}
      for (const m of visibleMonthCols) actualSums[m] = actualForKey[m.slice(5, 7)] || 0
      return { row: r, sums, actualSums }
    })
  }, [ok, visibleColumns, visibleMonthCols, filteredWide, actualByKeyMM])

  // By Cluster sums straight off the long-form rows (not off `wide`), exactly
  // as calendar_engine.html does: one row per cluster, one cell per column.
  const clusterRows = useMemo(() => {
    if (!ok) return []
    const cols = new Set(visibleColumns)
    const byCluster = new Map()
    for (const row of result.rows) {
      if (!cols.has(row.col)) continue
      const cl = clusterOf(row.store)
      let e = byCluster.get(cl)
      if (!e) { e = {}; byCluster.set(cl, e) }
      e[row.col] = (e[row.col] || 0) + row.value
    }
    return [...byCluster.entries()].sort((a, b) => (a[0] > b[0]) - (a[0] < b[0]))
      .map(([cluster, vals]) => ({ cluster, vals }))
  }, [ok, result, storeCluster, visibleColumns])

  // Store-level month-wise comparison: actual vs reindexed per store (+ division).
  // Actual rows use reference-year month strings (e.g. 2026-04); reindexed use
  // future-year strings (e.g. 2027-04). Match by MM only, same rule as p1p2.
  const storeMonthComp = useMemo(() => {
    if (!ok || !result.actualRows) return null
    // Actual: keyed by grain-key -> {mm -> total}
    const actualByKey = new Map()
    for (const row of result.actualRows) {
      const k = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      const mm = row.col.slice(5, 7)
      let e = actualByKey.get(k)
      if (!e) { e = { meta: {}, byMM: {} }; for (const f of keyFields) e.meta[f] = row[f] ?? ''; actualByKey.set(k, e) }
      e.byMM[mm] = (e.byMM[mm] || 0) + row.value
    }
    // Reindexed: keyed by grain-key -> {ym -> total}
    const cols = new Set(visibleColumns)
    const rxByKey = new Map()
    for (const row of result.rows) {
      if (!cols.has(row.col)) continue
      const k = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      const ym = row.col.slice(0, 7)
      let e = rxByKey.get(k)
      if (!e) { e = { meta: {}, byYM: {} }; for (const f of keyFields) e.meta[f] = row[f] ?? ''; rxByKey.set(k, e) }
      e.byYM[ym] = (e.byYM[ym] || 0) + row.value
    }
    // Merge keys from both sides
    const allKeys = [...new Set([...actualByKey.keys(), ...rxByKey.keys()])]
    allKeys.sort((a, b) => a.localeCompare(b))
    const rows = allKeys.map(k => ({
      meta: (actualByKey.get(k) || rxByKey.get(k)).meta,
      actualByMM: actualByKey.get(k)?.byMM || {},
      rxByYM: rxByKey.get(k)?.byYM || {},
    }))
    // Grand total
    const grandActualMM = {}, grandRxYM = {}
    for (const { actualByMM, rxByYM } of rows) {
      for (const [mm, v] of Object.entries(actualByMM)) grandActualMM[mm] = (grandActualMM[mm] || 0) + v
      for (const [ym, v] of Object.entries(rxByYM)) grandRxYM[ym] = (grandRxYM[ym] || 0) + v
    }
    return { rows, grandActualMM, grandRxYM }
  }, [ok, result, visibleColumns, keyFields])

  const filteredStoreMonthComp = useMemo(() => {
    if (!storeMonthComp) return null
    const q = search.toLowerCase().trim()
    if (!q) return storeMonthComp.rows
    return storeMonthComp.rows.filter(r =>
      keyFields.some(f => String(r.meta[f] ?? '').toLowerCase().includes(q)) ||
      clusterOf(r.meta.store).toLowerCase().includes(q))
  }, [storeMonthComp, search, storeCluster])

  // Day-wise Comparison: stacked two rows per store (Actual + Reindexed).
  // DW only - MW has no day-of-month field, so date columns don't exist there.
  // Actual side: reference-year dates (e.g. 2026-04-15) → keyed by MM-DD so
  //   they can be matched against future-year column headers (e.g. 2027-04-15).
  // Reindexed side: future-year dates - exact column match, no year adjustment.
  const storeDayComp = useMemo(() => {
    // Snapshots collapse DW columns to YYYY-MM - no day-level data available.
    if (!ok || !result.actualRows || result.source !== 'dw' || result.isSnapshot) return null
    // Also bail if columns are already month-strings (7 chars) not day-strings (10 chars)
    if (!result.columns?.[0] || result.columns[0].length < 10) return null
    // Actual: grain-key -> {MMDD ('04-15') -> value}
    const actualByKey = new Map()
    for (const row of result.actualRows) {
      const k = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      const mmdd = row.col.slice(5)  // '2026-04-15' → '04-15'
      let e = actualByKey.get(k)
      if (!e) { e = { meta: {}, byMMDD: {} }; for (const f of keyFields) e.meta[f] = row[f] ?? ''; actualByKey.set(k, e) }
      e.byMMDD[mmdd] = (e.byMMDD[mmdd] || 0) + row.value
    }
    // Reindexed: grain-key -> {futureDate ('2027-04-15') -> value}; only visible cols
    const cols = new Set(visibleColumns)
    const rxByKey = new Map()
    for (const row of result.rows) {
      if (!cols.has(row.col)) continue
      const k = keyFields.map(f => row[f] ?? '').join(KEY_SEP)
      let e = rxByKey.get(k)
      if (!e) { e = { meta: {}, byDate: {} }; for (const f of keyFields) e.meta[f] = row[f] ?? ''; rxByKey.set(k, e) }
      e.byDate[row.col] = (e.byDate[row.col] || 0) + row.value
    }
    const allKeys = [...new Set([...actualByKey.keys(), ...rxByKey.keys()])].sort((a, b) => a.localeCompare(b))
    const rows = allKeys.map(k => ({
      meta: (actualByKey.get(k) || rxByKey.get(k)).meta,
      actualByMMDD: actualByKey.get(k)?.byMMDD || {},
      rxByDate: rxByKey.get(k)?.byDate || {},
    }))
    const grandActualMMDD = {}, grandRxDate = {}
    for (const { actualByMMDD, rxByDate } of rows) {
      for (const [mmdd, v] of Object.entries(actualByMMDD)) grandActualMMDD[mmdd] = (grandActualMMDD[mmdd] || 0) + v
      for (const [d, v] of Object.entries(rxByDate)) grandRxDate[d] = (grandRxDate[d] || 0) + v
    }
    return { rows, grandActualMMDD, grandRxDate }
  }, [ok, result, visibleColumns, keyFields])

  const filteredStoreDayComp = useMemo(() => {
    if (!storeDayComp) return null
    const q = search.toLowerCase().trim()
    if (!q) return storeDayComp.rows
    return storeDayComp.rows.filter(r =>
      keyFields.some(f => String(r.meta[f] ?? '').toLowerCase().includes(q)) ||
      clusterOf(r.meta.store).toLowerCase().includes(q))
  }, [storeDayComp, search, storeCluster])

  function downloadStoreMonth() {
    if (!storeMonthComp) return
    const hdr = visibleMonthCols.flatMap(ym => [`${ym} Actual`, `${ym} Reindexed`, `${ym} Diff`, `${ym} Diff %`])
    const makeDataCells = (aByMM, rByYM) => visibleMonthCols.flatMap(ym => {
      const a = aByMM[ym.slice(5, 7)] || 0, r = rByYM[ym] || 0
      return [round2(a), round2(r), round2(r - a), fmtPct(pctDiff(a, r))]
    })
    const { rows, grandActualMM, grandRxYM } = storeMonthComp
    downloadCsv([
      ['Cluster', ...kfHeaders, ...hdr],
      ...rows.map(({ meta, actualByMM, rxByYM }) =>
        [clusterOf(meta.store), ...keyFields.map(f => meta[f]), ...makeDataCells(actualByMM, rxByYM)]),
      ['', ...keyFields.map((_, i) => i === 0 ? 'Grand Total' : ''), ...makeDataCells(grandActualMM, grandRxYM)],
    ], `${fileStem}_store_month_comparison.csv`)
  }

  function downloadStoreDayComp(dlMonths, fmt) {
    if (!storeDayComp) return
    const dlCols = visibleColumns.filter(c => dlMonths.has(c.slice(0, 7)))
    const { rows, grandActualMMDD, grandRxDate } = storeDayComp
    let csvRows
    if (fmt === 'wide') {
      // One row per store; each date = three columns: Actual, Reindexed, Diff
      const hdr = ['Cluster', ...kfHeaders, ...dlCols.flatMap(c => [`${c} Actual`, `${c} Reindexed`, `${c} Diff`])]
      csvRows = [hdr]
      for (const { meta, actualByMMDD, rxByDate } of rows) {
        const cluster = clusterOf(meta.store)
        csvRows.push([cluster, ...keyFields.map(f => meta[f]), ...dlCols.flatMap(c => {
          const a = actualByMMDD[c.slice(5)] ?? null, r = rxByDate[c] ?? null
          return [round2(a), round2(r), (a != null && r != null) ? round2(r - a) : '']
        })])
      }
      const ga = dlCols.flatMap(c => {
        const a = grandActualMMDD[c.slice(5)] || 0, r = grandRxDate[c] || 0
        return [round2(a), round2(r), round2(r - a)]
      })
      csvRows.push(['', ...keyFields.map((_, i) => i === 0 ? 'Grand Total' : ''), ...ga])
    } else {
      // Stacked (transposed): one row per (store, date) - dates in rows,
      // Actual and Reindexed as column headers. Long/tall format.
      const actualYear = result.actualRows?.[0]?.col?.slice(0, 4) ?? ''
      const hdr = ['Cluster', ...kfHeaders, 'Date', 'Actual Ref Date', 'Actual', 'Reindexed Ref Date', 'Reindexed', 'Diff']
      csvRows = [hdr]
      for (const { meta, actualByMMDD, rxByDate } of rows) {
        const cluster = clusterOf(meta.store)
        for (const c of dlCols) {
          const a = actualByMMDD[c.slice(5)] ?? null
          const r = rxByDate[c] ?? null
          const actualRefDate = actualYear ? `${actualYear}-${c.slice(5)}` : ''
          const rxRefDate = refDateOf(cluster, c)
          csvRows.push([cluster, ...keyFields.map(f => meta[f]), c, actualRefDate, round2(a), rxRefDate, round2(r),
            (a != null && r != null) ? round2(r - a) : ''])
        }
      }
      // Grand total row per date
      for (const c of dlCols) {
        const a = grandActualMMDD[c.slice(5)] || 0, r = grandRxDate[c] || 0
        csvRows.push(['', ...keyFields.map((_, i) => i === 0 ? 'Grand Total' : ''), c, '', round2(a), '', round2(r), round2(r - a)])
      }
    }
    downloadCsv(csvRows, `${fileStem}_day_comparison_${fmt}.csv`)
    setShowDayDlMenu(false)
  }

  // P1/P2: day 1-15 vs day 16-end of month, actual vs reindexed. The two
  // sides use DIFFERENT date columns by design - `result.rows` (reindexed)
  // are keyed by FUTURE dates (e.g. 2027), `result.actualRows` are keyed by
  // each sale's own REFERENCE date (e.g. 2026, see reindex_daywise's own
  // comment: "real sales on their own reference date"). That's not a bug to
  // work around, it IS the comparison being asked for: "what did this month
  // actually do last cycle" vs "what will the calendar-shifted version look
  // like" - so actual is matched to reindexed by MONTH NUMBER (04 to 04),
  // not by absolute year, since the two sides are never the same year.
  //
  // Month-wise has no day-of-month field anywhere in its source (see
  // _fetch_raw_monthwise in scans.py - it reads BILLMONTH, never a day), so
  // there is no real day 1-15/16-end split to compute there. Rather than hide
  // the tab for that source, p1MwEven splits each month's real total evenly
  // in half - clearly not a claim about actual intra-month pattern, just a
  // consistent P1/P2 shape across both sources. isEven flags this so the
  // render/download below can label it honestly instead of implying it's
  // measured data.
  // Snapshot results carry monthly columns (YYYY-MM) regardless of source -
  // the day-level detail was collapsed server-side. Treat them like mw so the
  // P1/P2 code never tries col.slice(8,10) on a 7-char string.
  const isEven = ok && (result.source === 'mw' || !!result.isSnapshot)
  const p1p2Rows = useMemo(() => {
    if (!ok || !result.actualRows) return []
    if (isEven) {
      const actualByMM = {}  // {'04': total}
      for (const row of result.actualRows) {
        const mm = row.col.slice(5, 7)
        actualByMM[mm] = (actualByMM[mm] || 0) + row.value
      }
      const cols = new Set(visibleColumns)
      const reindexedByYM = {}  // {'2027-04': total}
      for (const row of result.rows) {
        if (!cols.has(row.col)) continue
        reindexedByYM[row.col] = (reindexedByYM[row.col] || 0) + row.value
      }
      return visibleMonthCols.map(ym => {
        const a = (actualByMM[ym.slice(5, 7)] || 0) / 2
        const r = (reindexedByYM[ym] || 0) / 2
        return { month: ym, a1: a, r1: r, a2: a, r2: r }
      })
    }
    const actualByMM = {}  // {'04': {p1, p2}}
    for (const row of result.actualRows) {
      const mm = row.col.slice(5, 7)
      const half = +row.col.slice(8, 10) <= 15 ? 'p1' : 'p2'
      const e = (actualByMM[mm] = actualByMM[mm] || { p1: 0, p2: 0 })
      e[half] += row.value
    }
    const cols = new Set(visibleColumns)
    const reindexedByYM = {}  // {'2027-04': {p1, p2}}
    for (const row of result.rows) {
      if (!cols.has(row.col)) continue
      const half = +row.col.slice(8, 10) <= 15 ? 'p1' : 'p2'
      const e = (reindexedByYM[row.col.slice(0, 7)] = reindexedByYM[row.col.slice(0, 7)] || { p1: 0, p2: 0 })
      e[half] += row.value
    }
    return visibleMonthCols.map(ym => {
      const a = actualByMM[ym.slice(5, 7)] || { p1: 0, p2: 0 }
      const r = reindexedByYM[ym] || { p1: 0, p2: 0 }
      return { month: ym, a1: a.p1, r1: r.p1, a2: a.p2, r2: r.p2 }
    })
  }, [ok, result, visibleColumns, visibleMonthCols, isEven])

  // Shared by Monthly Summary and P1/P2: null (rendered as "-") when actual is
  // zero/missing rather than a misleading 0% or a divide-by-zero Infinity.
  const pctDiff = (actual, reindexed) => (actual ? ((reindexed - actual) / actual) * 100 : null)
  const fmtPct = (v) => (v == null ? '-' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)
  const hasActual = ok && !!result.actualRows

  if (!result || !result.ok) return null

  const kfHeaders = keyFields.map(f => KEY_LABELS[f] || f)
  const fileStem = `calendarised_sales_${result.source}`
  // Reference (LY) date a given CLUSTER's future-date column was shifted
  // from - built per-cluster in CalendarisedSalesTab from the calendar's own
  // day-map, so it's always that cluster's real mapping, never some other
  // cluster's (see refDateByCluster's state comment there for the bug this
  // replaced: a global plurality vote across every cluster mixed together
  // could show a reference date that isn't even the row's own cluster's
  // mapping). Falls back to the backend's global plurality only when no
  // per-cluster map is available at all (a job resumed from a previous page
  // load, with no fresh getCalendar call to build one from).
  const globalRefDateByColumn = result.refDateByColumn || {}
  const refDateOf = (cluster, c) => refDateByCluster?.[cluster]?.[c] ?? (globalRefDateByColumn[c] || '')
  // Which festival(s), if any, land on this output column FOR THIS CLUSTER -
  // built from that cluster's own festival records only (see
  // festivalByCluster's state comment in CalendarisedSalesTab for the same
  // cross-cluster leakage this replaced). '' when none, so a planner
  // scanning the table can spot a demand spike's cause instead of guessing.
  // Keyed by exact YYYY-MM-DD for day-wise columns and by the YYYY-MM prefix
  // for month-wise ones - a plain lookup by the column string works for both.
  const festivalOf = (cluster, c) => (festivalByCluster?.[cluster]?.[c] || []).join(', ')
  const hasFestivalRow = !!festivalByCluster && Object.keys(festivalByCluster).length > 0
  const hasFestivalRowFor = (cluster) => Object.keys(festivalByCluster?.[cluster] || {}).length > 0

  function countText(n) {
    if (!n) return 'No rows to show.'
    return n > RX_CAP
      ? `Showing first ${RX_CAP} of ${n.toLocaleString()} rows - refine your search to see more (Download CSV exports all ${n.toLocaleString()})`
      : `${n.toLocaleString()} rows`
  }

  function downloadReindexed() {
    downloadCsv([
      ['Cluster', ...kfHeaders, ...visibleColumns],
      // One Reference Date / Festival header block per cluster, directly
      // above that cluster's own rows - each block is that cluster's real
      // mapping, never mixed with any other's. See wideByCluster above.
      ...wideByCluster.flatMap(([cluster, rows]) => [
        // Plain ASCII hyphen, not an em-dash: this Blob has no BOM, so Excel
        // opened directly (double-click, not an explicit UTF-8 import) can
        // misread a non-ASCII character as the system codepage and mangle it.
        [`${cluster} - Reference Date`, ...kfHeaders.map(() => ''), ...visibleColumns.map(c => refDateOf(cluster, c))],
        ...(hasFestivalRowFor(cluster)
          ? [[`${cluster} - Festival`, ...kfHeaders.map(() => ''), ...visibleColumns.map(c => festivalOf(cluster, c))]]
          : []),
        ...rows.map(r => [cluster, ...keyFields.map(f => r[f]), ...visibleColumns.map(c => cell(r.vals[c]))]),
      ]),
    ], `${fileStem}_reindexed.csv`)
  }

  function downloadStacked() {
    downloadCsv([
      ['Cluster', 'Store', result.source === 'dw' ? 'Date' : 'Month', 'Reference Date', 'Festival', 'Value'],
      ...filteredStacked.map(r => {
        const cluster = clusterOf(r.store)
        return [cluster, r.store, r.col, refDateOf(cluster, r.col), festivalOf(cluster, r.col), round2(r.value)]
      }),
    ], `${fileStem}_stacked.csv`)
  }

  function downloadSummary() {
    const monthHeaders = hasActual
      ? visibleMonthCols.flatMap(m => [`${m} Actual`, `${m} Reindexed`, `${m} Diff`, `${m} Diff %`])
      : visibleMonthCols
    function monthCells(sums, actualSums) {
      if (!hasActual) return visibleMonthCols.map(m => round2(sums[m]))
      return visibleMonthCols.flatMap(m => {
        const a = actualSums[m] || 0, r = sums[m] || 0
        return [round2(a), round2(r), round2(r - a), fmtPct(pctDiff(a, r))]
      })
    }
    downloadCsv([
      ['Cluster', ...kfHeaders, ...monthHeaders],
      ...summaryRows.map(({ row, sums, actualSums }) =>
        [clusterOf(row.store), ...keyFields.map(f => row[f]), ...monthCells(sums, actualSums)]),
    ], `${fileStem}_summary.csv`)
  }

  function downloadP1P2() {
    downloadCsv([
      ...(isEven ? [['Note: Month-wise has no day-of-month field - P1/P2 below is an even half-and-half of each month\'s total, not measured data.']] : []),
      ['Month', 'P1 Actual', 'P1 Reindexed', 'P1 Diff', 'P1 Diff %', 'P2 Actual', 'P2 Reindexed', 'P2 Diff', 'P2 Diff %'],
      ...p1p2Rows.map(r => [
        r.month,
        round2(r.a1), round2(r.r1), round2(r.r1 - r.a1), fmtPct(pctDiff(r.a1, r.r1)),
        round2(r.a2), round2(r.r2), round2(r.r2 - r.a2), fmtPct(pctDiff(r.a2, r.r2)),
      ]),
    ], `${fileStem}_p1_p2.csv`)
  }

  function downloadCluster() {
    downloadCsv([
      ['Cluster', ...visibleColumns],
      ...clusterRows.map(r => [r.cluster, ...visibleColumns.map(c => round2(r.vals[c]))]),
    ], `${fileStem}_by_cluster.csv`)
  }

  const num = { textAlign: 'right' }

  return (
    <div className="card">
      {result.isSnapshot && (
        <div style={{ background: 'var(--navy2)', color: '#fff', borderRadius: '4px', padding: '6px 10px', marginBottom: '10px', fontSize: '11px' }}>
          Showing last run's monthly summary - computed {new Date(result.computedAt).toLocaleString()}.
          Run Reindex above to refresh. Festival labels are not available in cached snapshots.
        </div>
      )}
      <div className="tabs">
        <button className={activeSub === 'reindexed' ? 'active' : ''} onClick={() => setActiveSub('reindexed')}>Reindexed Sales</button>
        <button className={activeSub === 'summary' ? 'active' : ''} onClick={() => setActiveSub('summary')}>Monthly Summary</button>
        <button className={activeSub === 'cluster' ? 'active' : ''} onClick={() => setActiveSub('cluster')}>By Cluster</button>
        {/* P1/P2 (first/second half of a month) is a real day 1-15/16-end split
            for day-wise; month-wise has no day-of-month field in its source at
            all, so its P1/P2 here is an even half-and-half of the month total
            (isEven, see p1p2Rows) - shown either way for a consistent shape
            across sources, but clearly labeled below when it's the even case. */}
        {ok && result.actualRows && <button className={activeSub === 'divmonth' ? 'active' : ''} onClick={() => setActiveSub('divmonth')}>MW Comparison</button>}
        {ok && result.actualRows && result.source === 'dw' && !result.isSnapshot && result.columns?.[0]?.length >= 10 && <button className={activeSub === 'daycomp' ? 'active' : ''} onClick={() => setActiveSub('daycomp')}>DW Comparison</button>}
        {ok && result.actualRows && <button className={activeSub === 'p1p2' ? 'active' : ''} onClick={() => setActiveSub('p1p2')}>P1 / P2 Comparison</button>}
        <button className={activeSub === 'raw' ? 'active' : ''} onClick={() => setActiveSub('raw')}>Run Details</button>
      </div>

      {/* Month filter - shared across every tab below (Reindexed/Summary/
          Cluster/P1-P2), so picking "just April" once narrows the table AND
          the CSV export on whichever tab is open, instead of each tab having
          its own separate month picker. */}
      {activeSub !== 'raw' && monthCols.length > 0 && (
        <div className="scm-toolbar" style={{ marginBottom: '10px', flexWrap: 'wrap' }}>
          <span className="sdt-tb-label">Months</span>
          {monthCols.map(m => (
            <label key={m} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', cursor: 'pointer' }}>
              <input type="checkbox" checked={activeMonths.has(m)} onChange={() => toggleMonth(m)} />
              {m}
            </label>
          ))}
          <button onClick={() => setSelectedMonths(new Set(monthCols))}>All</button>
          <button onClick={() => setSelectedMonths(new Set())}>None</button>
        </div>
      )}

      {/* calendar_engine.html rxRenderTabs() lines ~3995-4011: a run whose synced
          months fall outside the chosen calendar's reference year maps nothing,
          and three silently-empty tables look like a rendering bug rather than a
          mismatched calendar. */}
      {result.rows.length === 0 && activeSub !== 'raw' && (
        <p style={{ color: 'var(--warn)', fontWeight: 600, fontSize: '12px' }}>
          No rows mapped for this run - the synced period likely falls outside the chosen
          calendar's reference year, so the tables below are empty. See Run Details.
        </p>
      )}

      {activeSub === 'reindexed' && (
        <>
          {/* Wide = existing pivot (one row per store[+fields], one column per
              date/month). Stacked = one row per store+date/month pair, Store +
              Date/Month + Value only regardless of which extra fields were
              picked - a lighter, restricted preview for a quicker look instead
              of the full detailed breakdown. User's choice, not automatic. */}
          <div className="scm-toolbar" style={{ marginBottom: '8px' }}>
            <span className="sdt-tb-label">View</span>
            <button className={viewMode === 'wide' ? 'active' : ''} onClick={() => setViewMode('wide')}>Wide</button>
            <button className={viewMode === 'stacked' ? 'active' : ''} onClick={() => setViewMode('stacked')}>Stacked</button>
            {viewMode === 'stacked' && (
              <span style={{ fontSize: '11px', color: 'var(--muted)' }}>
                Store + {result.source === 'dw' ? 'Date' : 'Month'} + Value only, summed across any other output fields.
              </span>
            )}
          </div>
          <div className="scm-toolbar">
            <div className="field">
              <label htmlFor="rx-search">Search</label>
              <input id="rx-search" type="text" style={{ width: '240px' }}
                placeholder={viewMode === 'wide' ? 'store, division, cluster' : 'store, cluster'}
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            {viewMode === 'wide' ? (
              <button className="btn" onClick={downloadReindexed} disabled={!filteredWide.length}>
                Download CSV
              </button>
            ) : (
              <button className="btn" onClick={downloadStacked} disabled={!filteredStacked.length}>
                Download CSV
              </button>
            )}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
            {countText(viewMode === 'wide' ? filteredWide.length : filteredStacked.length)}
          </div>
          {viewMode === 'wide' ? (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Cluster</th>
                    {kfHeaders.map(h => <th key={h}>{h}</th>)}
                    {visibleColumns.map(c => <th key={c} style={num}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {/* One Reference Date / Festival block per cluster, directly
                      above that cluster's own rows - see wideByCluster above.
                      RX_CAP limits DATA rows shown (matches the pre-grouping
                      cap), not the header rows leading each cluster's block. */}
                  {(() => {
                    let shown = 0
                    const out = []
                    for (const [cluster, rows] of wideByCluster) {
                      if (shown >= RX_CAP) break
                      out.push(
                        <tr className="rx-ref-date-row" key={`ref-${cluster}`}>
                          <th style={{ textAlign: 'left' }}>{cluster} - Reference Date</th>
                          {kfHeaders.map(h => <th key={`ref-${cluster}-${h}`} />)}
                          {visibleColumns.map(c => <th key={`ref-${cluster}-${c}`} style={num}>{refDateOf(cluster, c)}</th>)}
                        </tr>
                      )
                      if (hasFestivalRowFor(cluster)) {
                        out.push(
                          <tr className="rx-ref-date-row" key={`fest-${cluster}`}>
                            <th style={{ textAlign: 'left' }}>{cluster} - Festival</th>
                            {kfHeaders.map(h => <th key={`fest-${cluster}-${h}`} />)}
                            {visibleColumns.map(c => <th key={`fest-${cluster}-${c}`} style={{ ...num, color: 'var(--warn)' }}>{festivalOf(cluster, c)}</th>)}
                          </tr>
                        )
                      }
                      for (const r of rows) {
                        if (shown >= RX_CAP) break
                        out.push(
                          <tr key={keyFields.map(f => r[f]).join(KEY_SEP)}>
                            <td>{cluster}</td>
                            {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{r[f]}</td>)}
                            {visibleColumns.map(c => <td key={c} style={num}>{cell(r.vals[c])}</td>)}
                          </tr>
                        )
                        shown++
                      }
                    }
                    return out
                  })()}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Cluster</th>
                    <th>Store</th>
                    <th>{result.source === 'dw' ? 'Date' : 'Month'}</th>
                    <th>Reference Date</th>
                    {hasFestivalRow && <th>Festival</th>}
                    <th style={num}>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStacked.slice(0, RX_CAP).map(r => {
                    const cluster = clusterOf(r.store)
                    return (
                      <tr key={`${r.store}${KEY_SEP}${r.col}`}>
                        <td>{cluster}</td>
                        <td style={{ fontWeight: 600 }}>{r.store}</td>
                        <td>{r.col}</td>
                        <td>{refDateOf(cluster, r.col)}</td>
                        {hasFestivalRow && <td style={{ color: 'var(--warn)' }}>{festivalOf(cluster, r.col)}</td>}
                        <td style={num}>{round2(r.value)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {activeSub === 'summary' && (
        <>
          <div className="scm-toolbar">
            <div className="field">
              <label htmlFor="rx-summary-search">Search</label>
              <input id="rx-summary-search" type="text" style={{ width: '240px' }}
                placeholder="store, division, cluster"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <button className="btn" onClick={downloadSummary} disabled={!summaryRows.length}>
              Download CSV
            </button>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
            {countText(summaryRows.length)} · {visibleMonthCols.length} month column(s)
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th>
                  {kfHeaders.map(h => <th key={h}>{h}</th>)}
                  {visibleMonthCols.map(m => hasActual ? (
                    <th key={m} colSpan={4} style={num}>{m}</th>
                  ) : (
                    <th key={m} style={num}>{m}</th>
                  ))}
                </tr>
                {hasActual && (
                  <tr>
                    <th />
                    {kfHeaders.map(h => <th key={`sub-${h}`} />)}
                    {visibleMonthCols.map(m => (
                      <Fragment key={m}>
                        <th style={num}>Actual</th>
                        <th style={num}>Reindexed</th>
                        <th style={num}>Diff</th>
                        <th style={num}>Diff %</th>
                      </Fragment>
                    ))}
                  </tr>
                )}
              </thead>
              <tbody>
                {summaryRows.slice(0, RX_CAP).map(({ row, sums, actualSums }) => (
                  <tr key={keyFields.map(f => row[f]).join(KEY_SEP)}>
                    <td>{clusterOf(row.store)}</td>
                    {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{row[f]}</td>)}
                    {visibleMonthCols.map(m => hasActual ? (
                      <Fragment key={m}>
                        <td style={num}>{round2(actualSums[m])}</td>
                        <td style={num}>{round2(sums[m])}</td>
                        <td style={num}>{round2((sums[m] || 0) - (actualSums[m] || 0))}</td>
                        <td style={num}>{fmtPct(pctDiff(actualSums[m], sums[m]))}</td>
                      </Fragment>
                    ) : (
                      <td key={m} style={num}>{round2(sums[m])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeSub === 'cluster' && (
        <>
          <div className="scm-toolbar">
            <button className="btn" onClick={downloadCluster} disabled={!clusterRows.length}>
              Download CSV
            </button>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
            {clusterRows.length} cluster(s) x {visibleColumns.length} column(s)
            {storeCluster === null && ' - loading store-cluster map...'}
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th>
                  {visibleColumns.map(c => <th key={c} style={num}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {clusterRows.map(r => (
                  <tr key={r.cluster}>
                    <td style={{ fontWeight: 600 }}>{r.cluster}</td>
                    {visibleColumns.map(c => <td key={c} style={num}>{round2(r.vals[c])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeSub === 'divmonth' && storeMonthComp && (() => {
        // Actual reference-year label - first actual row's col gives the year (e.g. "2026")
        const actualYear = result.actualRows?.[0]?.col?.slice(0, 4) ?? 'Actual'
        const rxYear = visibleMonthCols[0]?.slice(0, 4) ?? 'Reindexed'
        const { rows: smRows, grandActualMM, grandRxYM } = storeMonthComp
        const displayRows = filteredStoreMonthComp || smRows
        // For each TY month column, collect the distinct LY months that clusters map into it.
        // refDateByCluster[cluster][ym] gives the dominant LY month ("2026-02") for each TY month ym.
        const lyMonthLabelByYM = {}
        for (const ym of visibleMonthCols) {
          const tyMonthIdx = parseInt(ym.slice(5, 7), 10) - 1
          const lyMonths = new Set()
          for (const cl of Object.keys(refDateByCluster || {})) {
            const ly = refDateByCluster[cl]?.[ym]
            if (ly) lyMonths.add(ly.slice(0, 7))
          }
          const parts = [...lyMonths].sort().map(m => MONTH_ABBR[parseInt(m.slice(5, 7), 10) - 1])
          lyMonthLabelByYM[ym] = { label: parts.join('/'), isCross: parts.length > 0 && parts.some(p => p !== MONTH_ABBR[tyMonthIdx]) }
        }
        return (
          <>
            <div className="scm-toolbar">
              <div className="field">
                <label htmlFor="rx-mwcomp-search">Search</label>
                <input id="rx-mwcomp-search" type="text" style={{ width: '240px' }}
                  placeholder="store, division, cluster"
                  value={search} onChange={e => setSearch(e.target.value)} />
              </div>
              <button className="btn" onClick={downloadStoreMonth} disabled={!smRows.length}>Download CSV</button>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
              {countText(displayRows.length)} · Each month: <strong>{actualYear} Actual</strong> vs <strong>{rxYear} Reindexed</strong> (matched by month number - difference reflects festival/calendar shifts)
            </div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  {/* Row 0: LY reference month labels – shows which LY month feeds each TY month column.
                      Amber highlight when the LY month differs from the TY month (cross-month pull). */}
                  <tr>
                    <th rowSpan={3}>Cluster</th>
                    {kfHeaders.map(h => <th key={h} rowSpan={3}>{h}</th>)}
                    {visibleMonthCols.map(ym => {
                      const { label, isCross } = lyMonthLabelByYM[ym] || { label: '', isCross: false }
                      return (
                        <th key={ym} colSpan={2} style={{
                          ...num,
                          borderLeft: '2px solid var(--border)',
                          fontSize: '10px',
                          background: isCross ? 'rgba(245,158,11,0.15)' : undefined,
                          color: isCross ? '#d97706' : 'var(--muted)',
                          fontWeight: isCross ? 600 : 400,
                        }}>
                          {label || ''}
                        </th>
                      )
                    })}
                  </tr>
                  {/* Row 1: TY month group headers */}
                  <tr>
                    {visibleMonthCols.map(ym => (
                      <th key={ym} colSpan={2} style={{ ...num, borderLeft: '2px solid var(--border)' }}>{ym}</th>
                    ))}
                  </tr>
                  {/* Row 2: Actual / Reindexed sub-headers */}
                  <tr>
                    {visibleMonthCols.map(ym => (
                      <Fragment key={ym}>
                        <th style={{ ...num, borderLeft: '2px solid var(--border)', fontSize: '10px', color: 'var(--muted)' }}>{actualYear}</th>
                        <th style={{ ...num, fontSize: '10px', color: 'var(--navy2)' }}>{rxYear}</th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayRows.slice(0, RX_CAP).map(({ meta, actualByMM, rxByYM }) => (
                    <tr key={keyFields.map(f => meta[f]).join(KEY_SEP)}>
                      <td>{clusterOf(meta.store)}</td>
                      {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{meta[f]}</td>)}
                      {visibleMonthCols.map(ym => {
                        const mm = ym.slice(5, 7)
                        const a = actualByMM[mm] ?? null
                        const r = rxByYM[ym] ?? null
                        const diff = (a != null && r != null) ? r - a : null
                        return (
                          <Fragment key={ym}>
                            <td style={{ ...num, borderLeft: '2px solid var(--border)' }}>{round2(a)}</td>
                            <td style={{ ...num, color: diff == null ? undefined : diff > 0.005 ? 'var(--navy2)' : diff < -0.005 ? 'var(--red)' : undefined }}>{round2(r)}</td>
                          </Fragment>
                        )
                      })}
                    </tr>
                  ))}
                  <tr style={{ borderTop: '2px solid var(--border)', fontWeight: 700 }}>
                    <td />
                    {keyFields.map((f, i) => <td key={f}>{i === 0 ? 'Grand Total' : ''}</td>)}
                    {visibleMonthCols.map(ym => {
                      const mm = ym.slice(5, 7)
                      const a = grandActualMM[mm] || 0, r = grandRxYM[ym] || 0
                      return (
                        <Fragment key={ym}>
                          <td style={{ ...num, borderLeft: '2px solid var(--border)' }}>{round2(a)}</td>
                          <td style={{ ...num, color: r > a + 0.005 ? 'var(--navy2)' : r < a - 0.005 ? 'var(--red)' : undefined }}>{round2(r)}</td>
                        </Fragment>
                      )
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )
      })()}

      {activeSub === 'daycomp' && storeDayComp && (() => {
        // Each store = 2 DOM rows; cap at half RX_CAP stores to keep the DOM lean.
        const DW_STORE_CAP = Math.ceil(RX_CAP / 2)
        const sdcRows = filteredStoreDayComp || storeDayComp.rows
        const { grandActualMMDD, grandRxDate } = storeDayComp
        const effectiveSel = dayDlSel || activeMonths
        return (
          <>
            <div className="scm-toolbar">
              <div className="field">
                <label htmlFor="rx-daycomp-search">Search</label>
                <input id="rx-daycomp-search" type="text" style={{ width: '240px' }}
                  placeholder="store, division, cluster"
                  value={search} onChange={e => setSearch(e.target.value)} />
              </div>
              {/* Download button with month-picker popover - DW date columns can
                  run to 365 per year; the popover lets the planner pick which
                  months to export before the (potentially very wide) CSV is built. */}
              <div style={{ position: 'relative' }}>
                <button className="btn" disabled={!sdcRows.length}
                  onClick={() => { setDayDlSel(new Set(activeMonths)); setShowDayDlMenu(v => !v) }}>
                  Download CSV ▾
                </button>
                {showDayDlMenu && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 300,
                    background: 'var(--white, #fff)', border: '1.5px solid var(--border)',
                    borderRadius: '10px', padding: '14px 16px', minWidth: '230px',
                    boxShadow: '0 12px 36px rgba(0,0,0,0.28), 0 2px 6px rgba(0,0,0,0.12)',
                    backdropFilter: 'none',
                  }}>
                    {/* Format toggle */}
                    <div style={{ fontSize: '10px', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>Format</div>
                    <div style={{ display: 'flex', borderRadius: '6px', overflow: 'hidden', border: '1px solid var(--border)', marginBottom: '6px' }}>
                      {[['stacked', 'Stacked'], ['wide', 'Wide']].map(([val, label]) => {
                        const isActive = dayDlFmt === val
                        return (
                          <button key={val} onClick={() => setDayDlFmt(val)} style={{
                            flex: 1, border: 'none', outline: 'none', cursor: 'pointer',
                            padding: '5px 0', fontSize: '12px', fontWeight: isActive ? 700 : 400,
                            background: isActive ? 'var(--navy2)' : 'transparent',
                            color: isActive ? '#fff' : 'var(--text)',
                            transition: 'background 0.15s, color 0.15s',
                          }}>
                            {label}
                          </button>
                        )
                      })}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--muted)', marginBottom: '12px', lineHeight: 1.4 }}>
                      {dayDlFmt === 'stacked'
                        ? 'One row per (store, date) - Date | Actual Ref Date | Actual | Reindexed Ref Date | Reindexed | Diff'
                        : 'One row per store - each date expands to Actual, Reindexed, Diff'}
                    </div>
                    {/* Month picker */}
                    <div style={{ fontSize: '10px', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>Months to export</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 8px', marginBottom: '10px' }}>
                      {monthCols.map(m => (
                        <label key={m} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', cursor: 'pointer', padding: '2px 0' }}>
                          <input type="checkbox"
                            checked={effectiveSel.has(m)}
                            onChange={() => setDayDlSel(prev => {
                              const s = new Set(prev || activeMonths)
                              s.has(m) ? s.delete(m) : s.add(m)
                              return s
                            })} />
                          {m}
                        </label>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button className="btn" style={{ flex: 1 }}
                        onClick={() => downloadStoreDayComp(effectiveSel, dayDlFmt)}
                        disabled={!effectiveSel.size}>
                        Download
                      </button>
                      <button style={{ padding: '4px 10px' }} onClick={() => setShowDayDlMenu(false)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
              {countText(sdcRows.length)} stores · 2 rows each (Actual / Reindexed) ·
              Actual = reference-year day keyed by MM-DD · Reindexed = calendar-shifted future-year day
            </div>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Cluster</th>
                    {kfHeaders.map(h => <th key={h}>{h}</th>)}
                    <th>Type</th>
                    {visibleColumns.map(c => <th key={c} style={num}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {sdcRows.slice(0, DW_STORE_CAP).map(({ meta, actualByMMDD, rxByDate }) => {
                    const cluster = clusterOf(meta.store)
                    const rowKey = keyFields.map(f => meta[f]).join(KEY_SEP)
                    return (
                      <Fragment key={rowKey}>
                        {/* Actual row - muted background so the pair is visually grouped */}
                        <tr style={{ background: 'var(--light)' }}>
                          <td>{cluster}</td>
                          {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{meta[f]}</td>)}
                          <td style={{ fontSize: '10px', color: 'var(--muted)', fontStyle: 'italic' }}>Actual</td>
                          {visibleColumns.map(c => <td key={`a-${c}`} style={num}>{round2(actualByMMDD[c.slice(5)])}</td>)}
                        </tr>
                        {/* Reindexed row - colour-coded vs actual */}
                        <tr>
                          <td />
                          {keyFields.map(f => <td key={f} />)}
                          <td style={{ fontSize: '10px', color: 'var(--navy2)', fontStyle: 'italic' }}>Reindexed</td>
                          {visibleColumns.map(c => {
                            const a = actualByMMDD[c.slice(5)] ?? null
                            const r = rxByDate[c] ?? null
                            const diff = (a != null && r != null) ? r - a : null
                            return (
                              <td key={`r-${c}`} style={{ ...num, color: diff == null ? undefined : diff > 0.005 ? 'var(--navy2)' : diff < -0.005 ? 'var(--red)' : undefined }}>
                                {round2(r)}
                              </td>
                            )
                          })}
                        </tr>
                      </Fragment>
                    )
                  })}
                  <tr style={{ borderTop: '2px solid var(--border)', fontWeight: 700, background: 'var(--light)' }}>
                    <td />{keyFields.map((f, i) => <td key={f}>{i === 0 ? 'Grand Total' : ''}</td>)}
                    <td style={{ fontSize: '10px', fontStyle: 'italic' }}>Actual</td>
                    {visibleColumns.map(c => <td key={`ga-${c}`} style={num}>{round2(grandActualMMDD[c.slice(5)])}</td>)}
                  </tr>
                  <tr style={{ fontWeight: 700 }}>
                    <td />{keyFields.map(f => <td key={f} />)}
                    <td style={{ fontSize: '10px', color: 'var(--navy2)', fontStyle: 'italic' }}>Reindexed</td>
                    {visibleColumns.map(c => <td key={`gr-${c}`} style={num}>{round2(grandRxDate[c])}</td>)}
                  </tr>
                </tbody>
              </table>
            </div>
          </>
        )
      })()}

      {activeSub === 'p1p2' && (
        <>
          <div className="scm-toolbar">
            <button className="btn" onClick={downloadP1P2} disabled={!p1p2Rows.length}>
              Download CSV
            </button>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
            P1 = day 1-15, P2 = day 16-end of month. Actual is that month's own reference-year
            sales; Reindexed is the calendar-shifted future-year sales for the same month.
            {isEven && (
              <>
                {' '}<strong style={{ color: 'var(--warn)' }}>Month-wise source has no day-of-month field -
                P1/P2 here is an even half-and-half of each month's total, not a measured
                intra-month pattern.</strong>
              </>
            )}
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th rowSpan={2}>Month</th>
                  <th colSpan={4} style={num}>P1 (1-15)</th>
                  <th colSpan={4} style={num}>P2 (16-end)</th>
                </tr>
                <tr>
                  <th style={num}>Actual</th>
                  <th style={num}>Reindexed</th>
                  <th style={num}>Diff</th>
                  <th style={num}>Diff %</th>
                  <th style={num}>Actual</th>
                  <th style={num}>Reindexed</th>
                  <th style={num}>Diff</th>
                  <th style={num}>Diff %</th>
                </tr>
              </thead>
              <tbody>
                {p1p2Rows.map(r => (
                  <tr key={r.month}>
                    <td style={{ fontWeight: 600 }}>{r.month}</td>
                    <td style={num}>{round2(r.a1)}</td>
                    <td style={num}>{round2(r.r1)}</td>
                    <td style={num}>{round2(r.r1 - r.a1)}</td>
                    <td style={num}>{fmtPct(pctDiff(r.a1, r.r1))}</td>
                    <td style={num}>{round2(r.a2)}</td>
                    <td style={num}>{round2(r.r2)}</td>
                    <td style={num}>{round2(r.r2 - r.a2)}</td>
                    <td style={num}>{fmtPct(pctDiff(r.a2, r.r2))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeSub === 'raw' && (
        <div>
          <p>Source: {result.source} ({result.grain}, metric {result.metric})</p>
          <p>Rows read: {result.rowsRead}, rows mapped: {result.rowsMapped}</p>
          {(result.cachedMonths?.length > 0 || result.computedMonths?.length > 0) && (
            <p>
              {result.cachedMonths?.length > 0 && (
                <><span className="scm-pill scm-pill-ok">{result.cachedMonths.length} month(s) reused from cache</span>{' '}
                ({result.cachedMonths.join(', ')}){' '}</>
              )}
              {result.computedMonths?.length > 0 && (
                <><span className="scm-pill scm-pill-warn">{result.computedMonths.length} month(s) freshly computed</span>{' '}
                ({result.computedMonths.join(', ')})</>
              )}
            </p>
          )}
          <p>Used frozen sync: <span className={`scm-pill ${result.usedFrozenSync ? 'scm-pill-ok' : 'scm-pill-warn'}`}>{result.usedFrozenSync ? 'Yes' : 'No'}</span></p>
          <p>
            Unmapped stores: <span className={`scm-pill ${result.unmappedStores?.length ? 'scm-pill-warn' : 'scm-pill-ok'}`}>{result.unmappedStores?.length || 0}</span>
            {result.unmappedStores?.length > 0 && <> (stores: {result.unmappedStores.join(', ')})</>}
          </p>
          <p>
            Unmapped dates: <span className={`scm-pill ${result.unmappedDateCount ? 'scm-pill-warn' : 'scm-pill-ok'}`}>{result.unmappedDateCount || 0}</span>
            {' '}(sample: {(result.unmappedDateSample || []).join(', ')})
          </p>
          {/* Distinct from "unmapped dates": these stores' calendar cluster has no entry
              at all in the selected calendar's day map (usually a cluster-name mismatch
              between the store/cluster map and the calendar), so EVERY one of their rows
              is dropped - not just a few dates. */}
          {result.unmappedClusters?.length > 0 && (
            <p style={{ color: 'var(--red)' }}>
              Clusters missing from this calendar: {result.unmappedClusters.join(', ')}
              {' '}({result.unmappedClusterStores?.length || 0} store(s) fully excluded)
            </p>
          )}
        </div>
      )}
    </div>
  )
}
