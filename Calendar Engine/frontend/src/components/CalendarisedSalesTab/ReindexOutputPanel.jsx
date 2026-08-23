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
          <p>Used frozen sync: {result.usedFrozenSync ? 'Yes' : 'No'}</p>
          <p>Unmapped stores: {result.unmappedStores?.length || 0}</p>
          <p>Unmapped dates: {result.unmappedDateCount || 0} (sample: {(result.unmappedDateSample || []).join(', ')})</p>
        </div>
      )}
    </div>
  )
}
