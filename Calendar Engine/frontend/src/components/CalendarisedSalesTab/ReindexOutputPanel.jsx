import { useState, useEffect, useMemo } from 'react'
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
// 0 — a store with no sales that day genuinely has no row in the source, which
// is not the same claim as "sold zero".
const cell = (v) => (v == null ? '' : v)
// Deliberately `== null` rather than the old app's falsy test (`v ? ... : ''`):
// a month whose rows genuinely sum to 0 is a real, different fact from one with
// no rows at all, and the live data does contain such totals — 49 of them in
// the month-wise run (ANG/CDIT, BKR/CDIT and other CDIT divisions carry
// explicit 0.00 values), which the old app silently rendered as blank. Blank
// here means only "nothing contributed to this cell".
const round2 = (v) => (v == null ? '' : +v.toFixed(2))

// Composite grain key separator: a character that cannot occur in a store or
// division name, so ('AB','C') and ('A','BC') can never collide into one row.
const KEY_SEP = '\u0001'

const KEY_LABELS = { store: 'Store', division: 'Division' }

export default function ReindexOutputPanel({ result }) {
  const [activeSub, setActiveSub] = useState('reindexed')
  const [search, setSearch] = useState('')
  // The reindex response carries only {store, division?, col, value} — no
  // cluster — so the Cluster column and the whole By Cluster tab need the
  // store -> cluster map fetched separately (the same GET the Date Shift
  // Preview panel and CalendarisedSalesTab/index.jsx already use).
  const [storeCluster, setStoreCluster] = useState(null)

  useEffect(() => {
    let alive = true
    getStoreClusterMap()
      .then(m => { if (alive) setStoreCluster(Object.fromEntries((m.stores || []).map(s => [s.store, s.cluster]))) })
      .catch(() => { if (alive) setStoreCluster({}) })
    return () => { alive = false }
  }, [])

  const ok = !!(result && result.ok)
  const keyFields = result?.grain === 'store_division' ? ['store', 'division'] : ['store']

  // rxWideRows(): group the long-form rows by the grain key, then hang each
  // row's {col: value} off that key. Deliberately does NOT depend on
  // storeCluster — the cluster is looked up per-cell below so that the map
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
    const k2 = keyFields[1]
    out.sort((a, b) =>
      ((a.store > b.store) - (a.store < b.store)) ||
      (k2 ? ((a[k2] > b[k2]) - (a[k2] < b[k2])) : 0))
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

  // Day-wise columns are YYYY-MM-DD and collapse to months here; month-wise
  // columns are already YYYY-MM, so slice(0,7) leaves them untouched and the
  // summary is the same grain as the reindexed table (matching the old app).
  const monthCols = useMemo(
    () => (ok ? [...new Set(result.columns.map(c => c.slice(0, 7)))].sort() : []),
    [ok, result])

  const summaryRows = useMemo(() => {
    if (!ok) return []
    return filteredWide.map(r => {
      const sums = {}
      for (const c of result.columns) {
        const v = r.vals[c]
        if (v != null) sums[c.slice(0, 7)] = (sums[c.slice(0, 7)] || 0) + v
      }
      return { row: r, sums }
    })
  }, [ok, result, filteredWide])

  // By Cluster sums straight off the long-form rows (not off `wide`), exactly
  // as calendar_engine.html does: one row per cluster, one cell per column.
  const clusterRows = useMemo(() => {
    if (!ok) return []
    const byCluster = new Map()
    for (const row of result.rows) {
      const cl = clusterOf(row.store)
      let e = byCluster.get(cl)
      if (!e) { e = {}; byCluster.set(cl, e) }
      e[row.col] = (e[row.col] || 0) + row.value
    }
    return [...byCluster.entries()].sort((a, b) => (a[0] > b[0]) - (a[0] < b[0]))
      .map(([cluster, vals]) => ({ cluster, vals }))
  }, [ok, result, storeCluster])

  if (!result || !result.ok) return null

  const kfHeaders = keyFields.map(f => KEY_LABELS[f] || f)
  const fileStem = `calendarised_sales_${result.source}`

  function countText(n) {
    if (!n) return 'No rows to show.'
    return n > RX_CAP
      ? `Showing first ${RX_CAP} of ${n.toLocaleString()} rows — refine your search to see more (Download CSV exports all ${n.toLocaleString()})`
      : `${n.toLocaleString()} rows`
  }

  function downloadReindexed() {
    downloadCsv([
      ['Cluster', ...kfHeaders, ...result.columns],
      ...filteredWide.map(r => [clusterOf(r.store), ...keyFields.map(f => r[f]),
        ...result.columns.map(c => cell(r.vals[c]))]),
    ], `${fileStem}_reindexed.csv`)
  }

  function downloadSummary() {
    downloadCsv([
      ['Cluster', ...kfHeaders, ...monthCols],
      ...summaryRows.map(({ row, sums }) => [clusterOf(row.store), ...keyFields.map(f => row[f]),
        ...monthCols.map(m => round2(sums[m]))]),
    ], `${fileStem}_summary.csv`)
  }

  function downloadCluster() {
    downloadCsv([
      ['Cluster', ...result.columns],
      ...clusterRows.map(r => [r.cluster, ...result.columns.map(c => round2(r.vals[c]))]),
    ], `${fileStem}_by_cluster.csv`)
  }

  const num = { textAlign: 'right' }

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'reindexed' ? 'active' : ''} onClick={() => setActiveSub('reindexed')}>Reindexed Sales</button>
        <button className={activeSub === 'summary' ? 'active' : ''} onClick={() => setActiveSub('summary')}>Monthly Summary</button>
        <button className={activeSub === 'cluster' ? 'active' : ''} onClick={() => setActiveSub('cluster')}>By Cluster</button>
        <button className={activeSub === 'raw' ? 'active' : ''} onClick={() => setActiveSub('raw')}>Run Details</button>
      </div>

      {/* calendar_engine.html rxRenderTabs() lines ~3995-4011: a run whose synced
          months fall outside the chosen calendar's reference year maps nothing,
          and three silently-empty tables look like a rendering bug rather than a
          mismatched calendar. */}
      {result.rows.length === 0 && activeSub !== 'raw' && (
        <p style={{ color: 'var(--warn)', fontWeight: 600, fontSize: '12px' }}>
          No rows mapped for this run — the synced period likely falls outside the chosen
          calendar's reference year, so the tables below are empty. See Run Details.
        </p>
      )}

      {activeSub === 'reindexed' && (
        <>
          <div className="scm-toolbar">
            <div className="field">
              <label htmlFor="rx-search">Search</label>
              <input id="rx-search" type="text" style={{ width: '240px' }}
                placeholder="store, division, cluster"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <button className="btn" onClick={downloadReindexed} disabled={!filteredWide.length}>
              Download CSV
            </button>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '8px' }}>
            {countText(filteredWide.length)}
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th>
                  {kfHeaders.map(h => <th key={h}>{h}</th>)}
                  {result.columns.map(c => <th key={c} style={num}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {filteredWide.slice(0, RX_CAP).map(r => (
                  <tr key={keyFields.map(f => r[f]).join(KEY_SEP)}>
                    <td>{clusterOf(r.store)}</td>
                    {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{r[f]}</td>)}
                    {result.columns.map(c => <td key={c} style={num}>{cell(r.vals[c])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
            {countText(summaryRows.length)} · {monthCols.length} month column(s)
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th>
                  {kfHeaders.map(h => <th key={h}>{h}</th>)}
                  {monthCols.map(m => <th key={m} style={num}>{m}</th>)}
                </tr>
              </thead>
              <tbody>
                {summaryRows.slice(0, RX_CAP).map(({ row, sums }) => (
                  <tr key={keyFields.map(f => row[f]).join(KEY_SEP)}>
                    <td>{clusterOf(row.store)}</td>
                    {keyFields.map(f => <td key={f} style={{ fontWeight: f === 'store' ? 600 : 400 }}>{row[f]}</td>)}
                    {monthCols.map(m => <td key={m} style={num}>{round2(sums[m])}</td>)}
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
            {clusterRows.length} cluster(s) × {result.columns.length} column(s)
            {storeCluster === null && ' — loading store-cluster map…'}
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cluster</th>
                  {result.columns.map(c => <th key={c} style={num}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {clusterRows.map(r => (
                  <tr key={r.cluster}>
                    <td style={{ fontWeight: 600 }}>{r.cluster}</td>
                    {result.columns.map(c => <td key={c} style={num}>{round2(r.vals[c])}</td>)}
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
          <p>Used frozen sync: <span className={`scm-pill ${result.usedFrozenSync ? 'scm-pill-ok' : 'scm-pill-warn'}`}>{result.usedFrozenSync ? 'Yes' : 'No'}</span></p>
          <p>Unmapped stores: <span className={`scm-pill ${result.unmappedStores?.length ? 'scm-pill-warn' : 'scm-pill-ok'}`}>{result.unmappedStores?.length || 0}</span></p>
          <p>
            Unmapped dates: <span className={`scm-pill ${result.unmappedDateCount ? 'scm-pill-warn' : 'scm-pill-ok'}`}>{result.unmappedDateCount || 0}</span>
            {' '}(sample: {(result.unmappedDateSample || []).join(', ')})
          </p>
          {/* Distinct from "unmapped dates": these stores' calendar cluster has no entry
              at all in the selected calendar's day map (usually a cluster-name mismatch
              between the store/cluster map and the calendar), so EVERY one of their rows
              is dropped — not just a few dates. */}
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
