import { useState, useEffect, useRef } from 'react'
import LinkStatusPanel from './LinkStatusPanel'
import ReindexOutputPanel from './ReindexOutputPanel'
import { startReindex, pollReindex, listCalendarLibrary, getCalendar, getStoreClusterMap, getSourceSchema, putSalesdataLinkSelection } from '../../lib/api'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})
  const [calendars, setCalendars] = useState([])
  const [source, setSource] = useState('dw')
  const [calendarId, setCalendarId] = useState(null)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState(null)
  // null = idle; otherwise {pct, filesDone, filesTotal} while a background
  // reindex job is running (day-wise can read tens of millions of rows - the
  // old runReindex() call just blocked with no feedback for however long that took).
  const [progress, setProgress] = useState(null)
  const pollTimer = useRef(null)

  // Customisable output fields - real columns for the CURRENT source, fetched
  // fresh whenever `source` changes so the picker is always true to what that
  // source actually has (day-wise has far fewer columns than month-wise).
  const [schema, setSchema] = useState(null)
  const [extraDims, setExtraDims] = useState([])
  const [metric, setMetric] = useState(null)

  useEffect(() => { listCalendarLibrary().then(cs => setCalendars(cs.filter(c => c.mappingSummary?.length))) }, [])
  useEffect(() => () => clearTimeout(pollTimer.current), []) // stop polling if the tab unmounts mid-run

  useEffect(() => {
    setSchema(null)
    getSourceSchema(source).then(s => setSchema(s)).catch(() => setSchema({ ok: false }))
  }, [source])

  // Hydrate extraDims/metric from the persisted selection once it's available
  // (LinkStatusPanel loads it independently via GET and reports it up through
  // onSelectionChange) instead of always resetting to "no extras" - this is
  // what makes a planner's field choice stick across visits: pick it once via
  // toggleDim/changeMetric below (which saves immediately), and every later
  // page load - and every later Run Reindex - starts from the same fields
  // without asking again.
  useEffect(() => {
    if (!schema?.ok) return
    const saved = selections[source]
    setExtraDims(saved?.extraDims || [])
    setMetric(saved?.metric || schema.defaultMetric)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, schema, selections[source]?.extraDims, selections[source]?.metric])

  function toggleDim(name) {
    const next = extraDims.includes(name) ? extraDims.filter(d => d !== name) : [...extraDims, name]
    setExtraDims(next)
    putSalesdataLinkSelection(source, { extraDims: next }).catch(() => {})
  }

  function changeMetric(value) {
    setMetric(value)
    putSalesdataLinkSelection(source, { metric: value }).catch(() => {})
  }

  function handleSelectionChange(sourceType, payload) {
    // Merge, not replace: LinkStatusPanel's own GET/PUT calls only ever carry
    // months/path/syncedAt, never extraDims/metric (those are this
    // component's concern, saved via changeMetric/toggleDim below) - a
    // replace would wipe the persisted extraDims/metric out of `selections`
    // the moment a planner re-syncs a year range, even though they're still
    // safely persisted server-side (the PUT there is a partial update too).
    setSelections(prev => ({ ...prev, [sourceType]: { ...prev[sourceType], ...payload } }))
  }

  // The selected calendar's day-map is locked to one exact ref-year -> fut-year
  // pair (e.g. a "2025 -> 2026" calendar's keys are all 2025 dates). Reindexing
  // synced months from any other year matches zero keys and silently returns
  // an empty result - there is no partial/fuzzy match. Surfacing refYear here
  // lets both the guidance note below and the pre-flight check in runRx() warn
  // BEFORE a wasted run instead of after an empty one.
  const selectedCalendar = calendars.find(c => String(c.id) === String(calendarId))

  async function runRx() {
    if (!isPlanner || !calendarId || progress) return
    setStatus(null)
    const sel = selections[source]
    const syncedYears = new Set((sel?.months || []).map(m => m.slice(0, 4)))
    if (selectedCalendar && !syncedYears.has(String(selectedCalendar.refYear))) {
      setStatus({
        ok: false,
        msg: `"${selectedCalendar.name}" reindexes ${selectedCalendar.refYear} sales onto ${selectedCalendar.futYear} dates, `
          + `but the months synced for ${source === 'dw' ? 'Day-wise' : 'Month-wise'} above `
          + `(${[...syncedYears].sort().join(', ') || 'none selected'}) don't include ${selectedCalendar.refYear}. `
          + `Sync ${selectedCalendar.refYear} months to use this calendar, or pick a calendar whose reference year matches what you synced.`,
      })
      return
    }
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0 })
    try {
      const [detail, storeMap] = await Promise.all([getCalendar(calendarId), getStoreClusterMap()])
      const storeCluster = Object.fromEntries((storeMap.stores || []).map(s => [s.store, s.cluster]))
      const { jobId } = await startReindex({
        source, months: sel?.months || [],
        storeCluster,
        dayMap: detail.dayMap, syncedAt: sel?.syncedAt,
        extraDims, metric,
      })

      // A single poll can transiently fail - the backend does its own CPU-bound
      // pandas/pyarrow work on a background thread, which can occasionally
      // starve the request briefly enough for the connection to reset even
      // though the job itself is still running fine. Retry through a handful
      // of those before actually giving up, rather than treating one dropped
      // poll as the whole reindex having failed.
      let misses = 0
      const MAX_MISSES = 5
      const poll = async () => {
        let p
        try {
          p = await pollReindex(jobId)
          misses = 0
        } catch (e) {
          misses += 1
          if (misses >= MAX_MISSES) { setProgress(null); setStatus({ ok: false, msg: `Lost contact with the reindex job: ${e.message}` }); return }
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        if (p.status === 'running') {
          setProgress({ pct: p.progressPct || 0, filesDone: p.filesDone || 0, filesTotal: p.filesTotal || 0 })
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        setProgress(null)
        if (p.status === 'error' || !p.ok) { setStatus({ ok: false, msg: p.error }); return }
        setResult(p)
      }
      await poll()
    } catch (e) {
      setProgress(null)
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="module-panel">
      <LinkStatusPanel sourceType="mw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange}
        hintYear={source === 'mw' ? selectedCalendar?.refYear : null} hintCalendarName={selectedCalendar?.name} />
      <LinkStatusPanel sourceType="dw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange}
        hintYear={source === 'dw' ? selectedCalendar?.refYear : null} hintCalendarName={selectedCalendar?.name} />

      <div className="card">
        <h4>Run Reindex</h4>
        <select value={source} onChange={e => setSource(e.target.value)}>
          <option value="dw">Day-wise NETAMT</option>
          <option value="mw">Month-wise Sales Value</option>
        </select>
        <select value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
          <option value="">Select a locked calendar…</option>
          {calendars.map(c => <option key={c.id} value={c.id}>{c.name} ({c.refYear} → {c.futYear})</option>)}
        </select>
        {selectedCalendar && (
          <p style={{ fontSize: '11px', color: 'var(--muted)', margin: '6px 0 0' }}>
            Reindexes <strong>{selectedCalendar.refYear}</strong> sales onto <strong>{selectedCalendar.futYear}</strong> dates —
            sync {selectedCalendar.refYear} months above (for {source === 'dw' ? 'Day-wise' : 'Month-wise'}) to use it.
          </p>
        )}

        {/* Customise output fields - real columns for the current source, so what's
            offered here is always true to what that source actually has (day-wise
            has far fewer than month-wise). Store (and Division, for month-wise) are
            always included and not shown as options - only the extras are picked here. */}
        {schema?.ok && (
          <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--muted)', marginBottom: '2px' }}>
              CUSTOMISE OUTPUT FIELDS
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '6px' }}>
              Saved automatically — picked once here, every later Run Reindex for this source reuses it.
            </div>
            {schema.metrics.length > 1 && (
              <div className="field" style={{ marginBottom: '8px' }}>
                <label htmlFor="rx-metric">Metric</label>
                <select id="rx-metric" value={metric || schema.defaultMetric} onChange={e => changeMetric(e.target.value)}>
                  {schema.metrics.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            )}
            {schema.dimensions.length > 0 ? (
              <>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '6px' }}>
                  Break the output out by additional fields (beyond Store{source === 'mw' ? ' + Division' : ''}):
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px' }}>
                  {schema.dimensions.map(d => (
                    <label key={d} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={extraDims.includes(d)} onChange={() => toggleDim(d)} />
                      {d}
                    </label>
                  ))}
                </div>
                {extraDims.length > 0 && (
                  <p style={{ fontSize: '11px', color: 'var(--warn)', marginTop: '6px' }}>
                    High-cardinality fields (e.g. Article Name) can multiply the row count a lot.
                  </p>
                )}
              </>
            ) : (
              <div style={{ fontSize: '11px', color: 'var(--muted)' }}>No extra fields available for this source.</div>
            )}
          </div>
        )}

        {isPlanner && <button className="btn" onClick={runRx} disabled={!!progress} style={{ marginTop: '12px' }}>{progress ? 'Reindexing…' : 'Run Reindex'}</button>}
        {progress && (
          <div style={{ marginTop: '8px' }}>
            <div style={{ background: 'var(--border)', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
              <div style={{
                width: `${progress.pct}%`, height: '100%', background: 'var(--navy2)',
                transition: 'width 0.3s ease',
              }} />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
              {progress.pct}%{progress.filesTotal > 0 && ` — ${progress.filesDone} of ${progress.filesTotal} files`}
            </div>
          </div>
        )}
        {status && <p style={{ color: 'var(--red)' }}>{status.msg}</p>}
      </div>

      <ReindexOutputPanel result={result} />
    </div>
  )
}
