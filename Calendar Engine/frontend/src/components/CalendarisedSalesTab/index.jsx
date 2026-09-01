import { useState, useEffect, useRef, useMemo } from 'react'
import LinkStatusPanel from './LinkStatusPanel'
import ReindexOutputPanel from './ReindexOutputPanel'
import { startReindex, pollReindex, getReindexCacheStatus, listCalendarLibrary, getCalendar, getStoreClusterMap, getSourceSchema, putSalesdataLinkSelection } from '../../lib/api'

// Same compact "45s" / "2m 05s" style as LinkStatusPanel's fmtDuration.
function fmtDuration(totalSeconds) {
  if (totalSeconds == null) return null
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`
}

// A day-wise reindex over a full year can run 15-20+ minutes. Without this,
// reloading the page (or a browser reload URL, a tab losing focus and being
// discarded, etc.) mid-run wipes the in-memory jobId the poll loop closed
// over - the backend job keeps running and finishes fine, but nothing is
// listening anymore to call setResult(), so the download never appears even
// though the result sat in reindex_jobs/<id>/result.json the whole time.
// Persisting the (jobId, startedAt, source) here lets the mount-time effect
// below pick the poll loop back up instead of orphaning it.
const RX_JOB_KEY = 'calendarEngine.activeReindexJob'
function saveActiveJob(job) {
  try { localStorage.setItem(RX_JOB_KEY, JSON.stringify(job)) } catch { /* private mode etc - resume just won't work */ }
}
function loadActiveJob() {
  try { const raw = localStorage.getItem(RX_JOB_KEY); return raw ? JSON.parse(raw) : null } catch { return null }
}
function clearActiveJob() {
  try { localStorage.removeItem(RX_JOB_KEY) } catch { /* nothing to clean up if this throws */ }
}

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})
  const [calendars, setCalendars] = useState([])
  const [source, setSource] = useState('dw')
  const [calendarId, setCalendarId] = useState(null)
  const [result, setResult] = useState(null)
  // Set instead of `result` when a completed job's payload is too large to
  // safely parse/hold in the browser tab - see pollJob's 'too_large' branch.
  const [largeResult, setLargeResult] = useState(null)
  // {futureDate -> [festival names]} built from the selected calendar's own
  // festival records (getCalendar already returns clusters[].festivals[]) so
  // ReindexOutputPanel can label which output dates/months are festival-
  // driven - a planner scanning a demand spike can see WHY it's there
  // instead of guessing. Keyed by day-wise's exact YYYY-MM-DD futDate, and
  // also by its YYYY-MM prefix for month-wise columns. Not populated for a
  // job resumed from a previous page load (no fresh getCalendar call then) -
  // an acceptable gap since this is a labelling aid, not core output data.
  const [festivalByDate, setFestivalByDate] = useState({})
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

  // Which of the synced months to actually reindex - previously runRx() always
  // sent every synced month (sel?.months), forcing the worker to read and
  // aggregate the full year even when a planner only cares about one or two
  // months. null = "not yet initialised for this source's synced list"; reset
  // to "all" whenever that list changes (a fresh sync, or switching source)
  // via the effect below, same pattern as ReindexOutputPanel's month filter.
  const [runMonths, setRunMonths] = useState(null)

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

  // The full list of synced months for the current source, scoped to the
  // selected calendar's reference year - the calendar's day-map is locked to
  // one exact ref-year (see selectedCalendar comment above), so a month from
  // any OTHER year matches nothing and only clutters the picker. Falls back
  // to every synced month when no calendar is picked yet. This is the subset
  // the planner then chooses from to reindex this run.
  const syncedMonths = useMemo(() => {
    const all = selections[source]?.months || []
    if (!selectedCalendar) return all
    const refYear = String(selectedCalendar.refYear)
    return all.filter(m => m.slice(0, 4) === refYear)
  }, [selections, source, selectedCalendar])
  useEffect(() => { setRunMonths(new Set(syncedMonths)) }, [syncedMonths.join(',')])
  const activeRunMonths = runMonths || new Set(syncedMonths)
  function toggleRunMonth(m) {
    setRunMonths(prev => {
      const next = new Set(prev || syncedMonths)
      next.has(m) ? next.delete(m) : next.add(m)
      return next
    })
  }

  // Per-month Open/Cached/Pending status - lets a planner see, before ever
  // clicking Run Reindex, which of the synced months a run would actually
  // have to do fresh work for. A closed month reindexed once under this
  // exact calendar/fields/metric combination never needs recomputing again
  // (see ReindexMonthCache in scans.py) - this is what makes login-to-login
  // reindexing fast after the first real run of a given calendar.
  const [cacheStatus, setCacheStatus] = useState(null)
  useEffect(() => {
    if (!calendarId || !syncedMonths.length) { setCacheStatus(null); return }
    let alive = true
    getReindexCacheStatus({ source, calendarId, months: syncedMonths, extraDims, metric })
      .then(r => { if (alive) setCacheStatus(r.months) })
      .catch(() => { if (alive) setCacheStatus(null) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, calendarId, syncedMonths.join(','), extraDims.join(','), metric])
  const cacheStatusByMonth = useMemo(
    () => Object.fromEntries((cacheStatus || []).map(s => [s.month, s])), [cacheStatus])

  // Shared by a fresh runRx() and the resume-on-mount effect below - the
  // resumed case has no local `startedAt` to fall back on if the backend's
  // own elapsedSeconds is ever missing, so it always passes one recovered
  // from the persisted job record instead.
  function pollJob(jobId, startedAt) {
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
        if (misses >= MAX_MISSES) {
          setProgress(null)
          setStatus({ ok: false, msg: `Lost contact with the reindex job: ${e.message}` })
          clearActiveJob()
          return
        }
        pollTimer.current = setTimeout(poll, 1000)
        return
      }
      if (p.status === 'running') {
        // p.elapsedSeconds comes from the backend job's own started_at; the
        // Date.now() fallback only matters against an old backend deployed
        // before that field existed, so the timer still counts even then.
        const elapsedSeconds = p.elapsedSeconds != null ? p.elapsedSeconds : Math.round((Date.now() - startedAt) / 1000)
        setProgress({ pct: p.progressPct || 0, filesDone: p.filesDone || 0, filesTotal: p.filesTotal || 0, elapsedSeconds, etaSeconds: p.etaSeconds })
        pollTimer.current = setTimeout(poll, 1000)
        return
      }
      setProgress(null)
      clearActiveJob()
      // p.status === 'too_large': pollReindex (lib/api.js) already cancelled
      // the body instead of parsing it - a combined multi-month day-wise
      // result can be 400+MB, which crashes the browser tab trying to hold
      // that much JSON in memory (reproduced live). Offer a real file
      // download (native browser download manager, no JS parse) instead of
      // an in-page table, rather than crashing or silently doing nothing.
      if (p.status === 'too_large') { setResult(null); setLargeResult(p); return }
      setLargeResult(null)
      if (p.status === 'error' || !p.ok) { setStatus({ ok: false, msg: p.error }); return }
      setResult(p)
    }
    return poll()
  }

  // Resume a job left running by a previous page load - see the RX_JOB_KEY
  // comment above. Runs once on mount; if the job already finished while
  // this page was gone (common for a 15-20 minute day-wise run), the very
  // first poll below returns status 'done' immediately and the result
  // appears right away instead of being silently stranded server-side.
  useEffect(() => {
    if (!isPlanner) return
    const job = loadActiveJob()
    if (!job?.jobId) return
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0, elapsedSeconds: 0 })
    pollJob(job.jobId, job.startedAt)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlanner])

  async function runRx() {
    if (!isPlanner || !calendarId || progress) return
    setStatus(null)
    setLargeResult(null)
    const sel = selections[source]
    const monthsToRun = syncedMonths.filter(m => activeRunMonths.has(m))
    if (!monthsToRun.length) {
      setStatus({ ok: false, msg: 'Pick at least one synced month to reindex.' })
      return
    }
    // Checked against the months actually being SENT (monthsToRun), not every
    // synced month - a planner who unchecks the calendar's own reference year
    // below would otherwise pass this guard and still get a silently empty
    // result, exactly the failure mode this check exists to prevent.
    const runYears = new Set(monthsToRun.map(m => m.slice(0, 4)))
    if (selectedCalendar && !runYears.has(String(selectedCalendar.refYear))) {
      setStatus({
        ok: false,
        msg: `"${selectedCalendar.name}" reindexes ${selectedCalendar.refYear} sales onto ${selectedCalendar.futYear} dates, `
          + `but the months selected to reindex for ${source === 'dw' ? 'Day-wise' : 'Month-wise'} above `
          + `(${[...runYears].sort().join(', ') || 'none selected'}) don't include ${selectedCalendar.refYear}. `
          + `Select ${selectedCalendar.refYear} months to use this calendar, or pick a calendar whose reference year matches what you selected.`,
      })
      return
    }
    const startedAt = Date.now()
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0, elapsedSeconds: 0 })
    try {
      const [detail, storeMap] = await Promise.all([getCalendar(calendarId), getStoreClusterMap()])
      const storeCluster = Object.fromEntries((storeMap.stores || []).map(s => [s.store, s.cluster]))

      // Build {date -> [festival names]} from every cluster's festival list -
      // a festival can land on a different exact date per cluster (regional
      // calendars), so this deliberately isn't scoped to one cluster; a
      // future column showing multiple names just means more than one
      // cluster has a festival on that date.
      const festMap = {}
      for (const cl of detail.clusters || []) {
        for (const f of cl.festivals || []) {
          if (!f.futDate || !f.name) continue
          const add = (key) => { (festMap[key] = festMap[key] || new Set()).add(f.name) }
          add(f.futDate)
          add(f.futDate.slice(0, 7))
        }
      }
      setFestivalByDate(Object.fromEntries(Object.entries(festMap).map(([k, v]) => [k, [...v].sort()])))

      const { jobId } = await startReindex({
        source, months: monthsToRun,
        storeCluster,
        dayMap: detail.dayMap, syncedAt: sel?.syncedAt,
        extraDims, metric,
      })
      saveActiveJob({ jobId, startedAt, source })
      await pollJob(jobId, startedAt)
    } catch (e) {
      setProgress(null)
      setStatus({ ok: false, msg: e.message })
    }
  }

  // Files-based pct (progress.pct) sits at 100% for nearly the whole run once
  // the single file finishes reading - the read is a small fraction of a big
  // day-wise job, the post-read pandas aggregation is the rest, and that phase
  // has no file-completion signal of its own. That's what made the bar LOOK
  // finished for 15+ minutes while the job was still genuinely working.
  // Once a time estimate exists (etaSeconds), drive the bar from elapsed vs.
  // estimated-total instead, capped at 99% so it never claims "done" before
  // the job actually reports done=true. Without an estimate yet (cold start,
  // no history for this source), fall back to the file pct but still cap it
  // at 90 once the file read itself is done, so the bar keeps room to move
  // instead of parking at 100.
  const displayPct = progress && progress.etaSeconds != null
    ? Math.min(99, Math.round((progress.elapsedSeconds / Math.max(1, progress.elapsedSeconds + progress.etaSeconds)) * 100))
    : progress && progress.filesTotal > 0 && progress.filesDone >= progress.filesTotal
      ? Math.min(progress.pct, 90)
      : progress?.pct || 0

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
          {calendars.map(c => <option key={c.id} value={c.id}>{c.name} ({c.refYear} -&gt; {c.futYear})</option>)}
        </select>
        {selectedCalendar && (
          <p style={{ fontSize: '11px', color: 'var(--muted)', margin: '6px 0 0' }}>
            Reindexes <strong>{selectedCalendar.refYear}</strong> sales onto <strong>{selectedCalendar.futYear}</strong> dates —
            sync {selectedCalendar.refYear} months above (for {source === 'dw' ? 'Day-wise' : 'Month-wise'}) to use it.
          </p>
        )}

        {/* Which synced months to actually reindex - previously always the full
            365-day/12-month set. Narrowing this is the main lever for "shorten
            the delay": fewer months means less raw data for the worker to read
            and aggregate. */}
        {syncedMonths.length > 0 && (
          <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--muted)', marginBottom: '6px' }}>
              MONTHS TO REINDEX
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '6px' }}>
              A closed month reindexed once under this calendar and these output fields is cached —
              Run Reindex reuses it instead of re-reading its sales. Only Open (the current month, still
              accumulating sales) and Pending (closed, not cached yet) do real work.
            </div>
            <div className="scm-toolbar" style={{ flexWrap: 'wrap' }}>
              {syncedMonths.map(m => {
                const st = cacheStatusByMonth[m]
                return (
                  <label key={m} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', cursor: 'pointer' }}>
                    <input type="checkbox" checked={activeRunMonths.has(m)} onChange={() => toggleRunMonth(m)} />
                    {m}
                    {st?.status === 'cached' && (
                      <span className="scm-pill scm-pill-ok" title={`Cached ${st.computedAt}`}>Cached</span>
                    )}
                    {st?.status === 'open' && <span className="scm-pill scm-pill-warn">Open</span>}
                    {st?.status === 'pending' && <span className="scm-pill">Pending</span>}
                  </label>
                )
              })}
              <button onClick={() => setRunMonths(new Set(syncedMonths))}>All</button>
              <button onClick={() => setRunMonths(new Set())}>None</button>
            </div>
          </div>
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

        {isPlanner && (
          <button className="btn" onClick={runRx} disabled={!!progress || activeRunMonths.size === 0} style={{ marginTop: '12px' }}>
            {progress ? 'Reindexing…' : 'Run Reindex'}
          </button>
        )}
        {progress && (
          <div style={{ marginTop: '8px' }}>
            <div style={{ background: 'var(--border)', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
              <div style={{
                width: `${displayPct}%`, height: '100%', background: 'var(--navy2)',
                transition: 'width 0.3s ease',
              }} />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
              {displayPct}%{progress.filesTotal > 0 && ` — ${progress.filesDone} of ${progress.filesTotal} files`}
              {progress.elapsedSeconds != null && ` — elapsed ${fmtDuration(progress.elapsedSeconds)}`}
              {progress.etaSeconds != null
                ? ` — about ${fmtDuration(progress.etaSeconds)} remaining`
                : ' — estimating remaining time…'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
              The read/aggregate step has no sub-progress signal of its own, so the remaining-time
              estimate is projected from how long past runs of this size took — it firms up as more
              runs complete, and reads "estimating…" until the first one finishes.
            </div>
          </div>
        )}
        {status && <p style={{ color: 'var(--red)' }}>{status.msg}</p>}
      </div>

      {largeResult && (
        <div className="card">
          <h4>Reindex Complete — Result Too Large to Preview</h4>
          <p style={{ fontSize: '12px', color: 'var(--muted)' }}>
            This run finished successfully ({(largeResult.contentLength / (1024 * 1024)).toFixed(0)} MB combined
            across the selected months) — too large to load into this page without risking the browser tab
            crashing. Download the CSV below (same Wide/Stacked choice as the interactive table would offer),
            or narrow the month/field selection above and run again for an interactive preview.
          </p>
          <div className="scm-toolbar">
            <a className="btn" href={largeResult.csvUrl('wide')} download style={{ display: 'inline-block', textDecoration: 'none' }}>
              Download CSV (Wide)
            </a>
            <a className="btn" href={largeResult.csvUrl('stacked')} download style={{ display: 'inline-block', textDecoration: 'none' }}>
              Download CSV (Stacked)
            </a>
          </div>
        </div>
      )}

      <ReindexOutputPanel result={result} festivalByDate={festivalByDate} />
    </div>
  )
}
