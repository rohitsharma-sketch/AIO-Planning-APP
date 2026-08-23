import { useState } from 'react'

export default function ReindexOutputPanel({ result }) {
  const [activeSub, setActiveSub] = useState('reindexed')
  // On failure run_reindex (scans.py) returns only {ok: false, error}, with none of
  // the columns/rows/source/etc fields this panel reads below - index.jsx already
  // surfaces `status.msg` for that case, so bail out here instead of crashing on
  // result.columns being undefined.
  if (!result || !result.ok) return null

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'reindexed' ? 'active' : ''} onClick={() => setActiveSub('reindexed')}>Reindexed Sales</button>
        <button className={activeSub === 'summary' ? 'active' : ''} onClick={() => setActiveSub('summary')}>Monthly Summary</button>
        <button className={activeSub === 'cluster' ? 'active' : ''} onClick={() => setActiveSub('cluster')}>By Cluster</button>
        <button className={activeSub === 'raw' ? 'active' : ''} onClick={() => setActiveSub('raw')}>Run Details</button>
      </div>

      {activeSub === 'reindexed' && (
        <table>
          <thead>
            <tr>
              <th>{result.grain === 'store_division' ? 'Store / Division' : 'Store'}</th>
              {result.columns.map(c => <th key={c}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {/* pivot result.rows (long-form: {store, division?, col, value}) wide by result.columns per store(+division) key */}
            {/* Wide-pivot rendering and CSV download (rxDownload) are a deliberate follow-up, out of scope for this task. */}
          </tbody>
        </table>
      )}

      {activeSub === 'summary' && <p>Monthly aggregation — sum {result.rows.length} rows by month across all stores.</p>}
      {activeSub === 'cluster' && <p>Cluster aggregation — sum rows by each store's calendar cluster.</p>}

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
