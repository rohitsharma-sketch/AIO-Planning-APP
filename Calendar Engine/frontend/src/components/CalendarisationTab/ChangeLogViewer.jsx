import { useState } from 'react'
import { getFestivalChangelog } from '../../lib/api'

// Read-only viewer. The old app auto-recorded a changelog entry (with pre/core/post
// day-count overrides, not just dates) on every festival edit via saveChangeLog();
// the new `calendar.festival_changelog` table only has ref_date/fut_date columns
// (see sub-project A's Open Risks), so extending it to capture day-count overrides
// is deferred until that schema gap is closed. This task therefore only reads
// existing entries - it does not write a new entry when a festival is edited here.
export default function ChangeLogViewer({ rangeKey }) {
  const [entries, setEntries] = useState([])
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(null)

  function load() {
    getFestivalChangelog(rangeKey).then(setEntries).catch(e => setError(e.message))
  }

  return (
    <div className="card">
      <h4 onClick={() => { setOpen(!open); if (!open) load() }} style={{ cursor: 'pointer' }}>Change Log</h4>
      {open && (
        <>
          <p style={{ color: 'var(--muted)', fontSize: '12px' }}>
            Shows recorded date overrides only - pre/core/post day-count overrides aren't
            captured by the current backend schema (known gap, tracked separately). Editing
            a festival in the table above does not add a new entry here yet - writes are
            not wired up in this task, only reads.
          </p>
          {error && <p style={{ color: 'var(--red)' }}>{error}</p>}
          <ul>
            {entries.length === 0 && !error && <li style={{ color: 'var(--muted)' }}>No entries for this range.</li>}
            {entries.map((e, i) => (
              <li key={i}>{e.clusterName} - {e.festivalName}: {e.refDate} -&gt; {e.futDate} ({e.savedAt})</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
