import { useState, useEffect, useRef } from 'react'
import { startLinkScan, pollLinkScan, getSalesdataLinkSelection, putSalesdataLinkSelection } from '../../lib/api'

const LABELS = { mw: 'Month-wise', dw: 'Day-wise' }

// "45s" / "2m 05s" - matches the compact style everywhere else in this app,
// not a full duration-formatting library for what's just an estimate.
function fmtDuration(totalSeconds) {
  if (totalSeconds == null) return null
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`
}

// One source's row in the combined "Link Sales Data Source" table (2026-09-25:
// the two cards were squeezed into one table; the From/To year pickers and
// per-card buttons were removed). The parent's single "Sync all months" /
// "Refresh" buttons bump syncSignal / refreshSignal; each row reacts to them.
// Sync = every month this source currently has (what the full-range default
// of the old year pickers already did).
export default function LinkStatusPanel({ sourceType, isPlanner, onSelectionChange, syncSignal, refreshSignal }) {
  const [link, setLink] = useState(null)
  // null = idle; otherwise {pct, filesDone, filesTotal, etaSeconds} while a
  // background scan job is running (day-wise reads 86M+ rows).
  const [progress, setProgress] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const pollTimer = useRef(null)
  const [selection, setSelection] = useState(null)
  const [syncing, setSyncing] = useState(false)

  async function refresh(force) {
    clearTimeout(pollTimer.current)
    setFetchError(null)
    setLink(null)
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0, etaSeconds: null })
    try {
      const { jobId } = await startLinkScan(sourceType, force)
      // Same transient-failure tolerance as Run Reindex's poll loop.
      let misses = 0
      const MAX_MISSES = 5
      const poll = async () => {
        let p
        try {
          p = await pollLinkScan(jobId)
          misses = 0
        } catch (e) {
          misses += 1
          if (misses >= MAX_MISSES) { setProgress(null); setFetchError(`Lost contact with the scan job: ${e.message}`); return }
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        if (p.status === 'running') {
          setProgress({ pct: p.progressPct || 0, filesDone: p.filesDone || 0, filesTotal: p.filesTotal || 0, etaSeconds: p.etaSeconds })
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        setProgress(null)
        if (p.status === 'error' || !p.ok) { setFetchError(p.error || 'Scan failed'); return }
        setLink(p)
      }
      await poll()
    } catch (e) {
      setProgress(null)
      setFetchError(e.message)
    }
  }
  useEffect(() => {
    refresh(false)
    return () => clearTimeout(pollTimer.current) // stop polling if the tab/panel unmounts mid-scan
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { if (refreshSignal) refresh(true) }, [refreshSignal]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    getSalesdataLinkSelection(sourceType).then(s => {
      setSelection(s)
      // Push the PERSISTED selection up too - "Run Reindex" on a fresh page
      // load otherwise posts months: [] and the backend rejects it.
      onSelectionChange?.(sourceType, s)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceType])

  async function syncAll() {
    if (!isPlanner || !link?.ok) return
    const months = (link.months || []).map(m => m.month).sort()
    // dw scan results carry `dirs`, not `path`; the backend column is NOT NULL.
    const path = link.path || (Array.isArray(link.dirs) ? link.dirs.join('; ') : '')
    const payload = { months, path, syncedAt: new Date().toISOString() }
    setSyncing(true)
    try {
      await putSalesdataLinkSelection(sourceType, payload)
      setSelection(payload)
      onSelectionChange?.(sourceType, payload)
    } finally {
      setSyncing(false)
    }
  }
  useEffect(() => { if (syncSignal) syncAll() }, [syncSignal]) // eslint-disable-line react-hooks/exhaustive-deps

  const synced = selection?.syncedAt ? new Date(selection.syncedAt).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-'
  let status
  if (progress) {
    status = <td colSpan={4}>
      Scanning {progress.pct}%{progress.filesTotal > 0 && ` - ${progress.filesDone}/${progress.filesTotal} files`}
      {progress.etaSeconds != null && ` - ~${fmtDuration(progress.etaSeconds)} left`}
    </td>
  } else if (fetchError || (link && !link.ok)) {
    status = <td colSpan={4}>
      <span className="scm-pill scm-pill-bad">Not linked</span>{' '}
      <span style={{ color: 'var(--red)' }}>{fetchError || link.error}</span>{' '}
      <button className="btn" onClick={() => refresh(false)}>Retry</button>
    </td>
  } else if (link) {
    const unmatched = link.stores?.unmatchedInSource?.length || 0
    status = <>
      <td><span className={`scm-pill ${link.offline ? 'scm-pill-warn' : 'scm-pill-ok'}`} title={link.offline ? `Source unreachable - last known data as of ${link.scannedAt}` : ''}>{link.offline ? 'Offline' : 'Linked'}</span></td>
      <td className="date-mono">{link.dateRange?.min} - {link.dateRange?.max}</td>
      <td>{link.rowCount?.toLocaleString()} rows / {link.months?.length} months</td>
      <td>{link.stores?.matched?.length} matched{unmatched ? <span style={{ color: 'var(--warn)' }}> / {unmatched} unmatched</span> : ''}</td>
    </>
  } else {
    status = <td colSpan={4} />
  }
  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{LABELS[sourceType]}</td>
      {status}
      <td style={{ color: 'var(--muted)' }}>{syncing ? 'Syncing...' : synced}</td>
    </tr>
  )
}
