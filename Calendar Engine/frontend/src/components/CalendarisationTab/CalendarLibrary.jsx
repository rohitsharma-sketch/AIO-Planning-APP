import { useState, useEffect } from 'react'
import { Menu } from '../ui'
import { listCalendarLibrary, getCalendar, saveCalendar, deleteCalendar, renameCalendar, getAppState } from '../../lib/api'
import { generateMappings } from '../../lib/engine'
import { coreFestivalNamesFor, laganDaysFor, loadFestivalReference } from '../../lib/festivalData'
import { fmtISO, yearDays } from '../../lib/dateUtils'

// Saved-date format used on every library card, matching the old app's
// renderCalendarLibrary() (calendar_engine.html line ~3849:
// toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric'})).
function fmtSavedAt(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d)) return '-'
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

// Data-integrity + staleness check for one locked calendar, run entirely
// client-side against its own stored snapshot (getCalendar's clusters+dayMap)
// - no server endpoint needed since the V2 algorithm only exists in engine.js.
//
// Two independent things get checked, per the standing business rule (see
// CALENDAR_ENGINE_LOGIC.md's "V1 vs V2 engines" section):
//   1. Coverage/duplicates on the STORED day-map itself - missing or
//      future-date-collision rows are always a hard bug (should be 0).
//      Duplicate REFERENCE dates are reported but NOT treated as an error:
//      the 2026-09-22 tier-reorder fix confirmed a genuine mathematical floor
//      of same-month reuse remains even under the current, correct algorithm
//      (e.g. 45/113/87/151 per calendar) - flagging every one as an "error"
//      would just be noise the user already decided to accept.
//   2. Staleness - only meaningful for a V2-tagged calendar: regenerate each
//      cluster's day-map right now, from the SAME stored festival config,
//      using today's engine.js + today's global maxShift/moPri (app-state).
//      A mismatch means the algorithm has changed since this was locked
//      (exactly what happened repeatedly this session) and the snapshot no
//      longer reflects the current rules - "Sync Now" regenerates it in place.
function checkIntegrity(full, appSettings) {
  const ry = Number(full.refYear), fy = Number(full.futYear)
  const ms = Number(appSettings.maxShift) || 45
  const moPri = appSettings.moPri || 'prev'
  const isV2 = (full.engine || '').includes('v2')
  const expectedFut = new Set(yearDays(fy).map(fmtISO))

  let dupRefDates = 0, missingDays = 0, futCollisions = 0, staleClusters = 0
  for (const cl of full.clusters || []) {
    const pairs = (full.dayMap && full.dayMap[cl.name]) || []
    const refCounts = new Map(), futSeen = new Set()
    for (const [r, f] of pairs) {
      refCounts.set(r, (refCounts.get(r) || 0) + 1)
      if (futSeen.has(f)) futCollisions++
      futSeen.add(f)
    }
    dupRefDates += [...refCounts.values()].filter(n => n > 1).length
    for (const d of expectedFut) if (!futSeen.has(d)) missingDays++

    if (isV2) {
      const fresh = generateMappings(cl.festivals, ry, fy, ms, moPri, coreFestivalNamesFor(cl.name), 2, laganDaysFor(ry, fy))
      const freshSet = new Set(fresh.map(m => `${fmtISO(m.refDate)}|${fmtISO(m.futureDate)}`))
      const storedSet = new Set(pairs.map(([r, f]) => `${r}|${f}`))
      const same = freshSet.size === storedSet.size && [...freshSet].every(k => storedSet.has(k))
      if (!same) staleClusters++
    }
  }
  return { isV2, dupRefDates, missingDays, futCollisions, isStale: staleClusters > 0 }
}

export default function CalendarLibrary({ onLoad, onSaved, isPlanner, buildSavePayload }) {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  // {calendar id -> checkIntegrity() result}, filled in as each card's own
  // getCalendar(id) resolves - never blocks the initial list render.
  const [integrity, setIntegrity] = useState({})
  const [syncingId, setSyncingId] = useState(null)
  const [appSettings, setAppSettings] = useState(null)  // null until app-state + lagan dates are in

  function refresh() {
    listCalendarLibrary().then(setItems).catch(e => setStatus({ ok: false, msg: e.message }))
  }

  useEffect(refresh, [])
  useEffect(() => {
    // lagan dates load with the festival reference; the staleness check must see them like Create Calendar does
    Promise.all([getAppState(), loadFestivalReference()])
      .then(([s]) => setAppSettings({ maxShift: s.maxShift ?? 45, moPri: s.moPri || 'prev' }))
      .catch(() => setAppSettings({ maxShift: 45, moPri: 'prev' }))
  }, [])

  // Re-checks every card whenever the library list changes (including after
  // a Sync Now, which issues the calendar a brand-new id) - an id already
  // present in `integrity` is skipped, so this never re-fetches a card that
  // hasn't changed just because some OTHER card in the list changed.
  useEffect(() => {
    if (!appSettings) return
    items.forEach(c => {
      if (integrity[c.id] !== undefined) return
      getCalendar(c.id)
        .then(full => setIntegrity(prev => ({ ...prev, [c.id]: checkIntegrity(full, appSettings) })))
        .catch(() => setIntegrity(prev => ({ ...prev, [c.id]: null })))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, appSettings])

  // "Sync Now" - regenerates this ONE locked calendar's day-map from its own
  // stored festival config, using today's V2 engine + today's global
  // maxShift/moPri, and overwrites it in place (same delete-then-create
  // pattern every other library write uses, per handleSave's comment above -
  // there is no partial-update endpoint). Deliberately scoped to just this
  // calendar's own stored clusters, independent of whatever's currently
  // loaded in the live editor.
  async function handleSyncNow(item) {
    if (!isPlanner || syncingId || !appSettings) return
    setSyncingId(item.id)
    try {
      const full = await getCalendar(item.id)
      const ry = Number(full.refYear), fy = Number(full.futYear)
      const ms = Number(appSettings.maxShift) || 45
      const moPri = appSettings.moPri || 'prev'
      const dayMap = {}
      let changed = 0, total = 0
      full.clusters.forEach(cl => {
        const fresh = generateMappings(cl.festivals, ry, fy, ms, moPri, coreFestivalNamesFor(cl.name), 2, laganDaysFor(ry, fy))
        dayMap[cl.name] = fresh.map(m => [fmtISO(m.refDate), fmtISO(m.futureDate)])
        const freshSet = new Set(dayMap[cl.name].map(([r, f]) => `${r}|${f}`))
        const stored = (full.dayMap && full.dayMap[cl.name]) || []
        total += stored.length
        changed += stored.filter(([r, f]) => !freshSet.has(`${r}|${f}`)).length
      })
      // Its stored festival list may have been edited since lock, so say how
      // much of the locked day map this actually rewrites before doing it.
      if (!window.confirm(
        `Sync Now will rewrite ${changed} of ${total} stored day pairs for "${item.name}" from its current festival list (today's V2 rules).\nThis overwrites the locked snapshot and cannot be undone.`
      )) return
      const payload = {
        id: Date.now(), name: full.name, refYear: ry, futYear: fy,
        savedAt: new Date().toISOString(), engine: 'calendarisation-v2',
        clusters: full.clusters.map(cl => ({ name: cl.name, region: cl.region, festivals: cl.festivals })),
        dayMap,
      }
      // save first, delete the old one only once the new one is in (audit 2026-10-06: a failed save after the
      // delete lost the locked calendar for good)
      await saveCalendar(payload)
      await deleteCalendar(item.id)
      setStatus({ ok: true, msg: `"${item.name}" synced to today's V2 rules.` })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setSyncingId(null)
    }
  }

  // "Lock & Save Calendar" - ported from the old app's saveCalendarToLibrary()
  // (calendar_engine.html lines 3756-3817). Two behaviours are restored here:
  //   1. It prompts for a template name (defaulting to the auto-generated one,
  //      so a plain click-through behaves exactly as it did before), and
  //      cancelling the prompt saves nothing.
  //   2. Re-using an existing entry's name overwrites that entry rather than
  //      piling up duplicates. The backend has no update endpoint (POST
  //      /calendar-library 409s on a duplicate id and there is no PUT), so
  //      "overwrite" is done as delete-then-create, which reaches the same end
  //      state with only the endpoints that already exist.
  // The old app's third behaviour - refusing to save a snapshot whose content is
  // identical to an existing one - is NOT ported: with this backend it would mean
  // GET /calendar-library/{id} for every entry in the library (the list endpoint
  // returns no dayMap/clusters to compare against) on every save, which is not
  // the cheap local check it was against localStorage.
  async function handleSave() {
    if (!isPlanner || busy) return
    let payload
    try {
      payload = buildSavePayload()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
      return
    }
    const entered = window.prompt(
      'Name this calendar template:\n(Using an existing name overwrites that template with your changes.)',
      payload.name,
    )
    if (entered === null) return           // cancelled - save nothing
    const name = entered.trim()
    if (!name) { setStatus({ ok: false, msg: 'Enter a name to save this calendar.' }); return }

    setBusy(true)
    try {
      // save first, then drop every older calendar of that name (same name overwrites); a failed save keeps them
      const existing = items.filter(c => (c.name || '') === name && c.id !== payload.id)
      await saveCalendar({ ...payload, name })
      for (const c of existing) await deleteCalendar(c.id)
      setStatus({ ok: true, msg: existing.length ? `Template "${name}" updated with your changes` : `Template "${name}" locked & saved` })
      onSaved?.(payload.id, name)
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleLoad(id) {
    try {
      const full = await getCalendar(id)
      onLoad(full)
      setStatus(null)
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleRename(c) {
    if (!isPlanner) return
    const entered = window.prompt('Rename this calendar:', c.name)
    if (entered === null) return   // cancelled
    const name = entered.trim()
    if (!name || name === c.name) return
    try {
      await renameCalendar(c.id, name)
      setStatus({ ok: true, msg: `Renamed to "${name}"` })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleDelete(id) {
    if (!isPlanner) return
    // Same confirm-before-destroy pattern as deleteSavedCalendar()
    // (calendar_engine.html line ~3821) and FestivalTable.jsx's row delete.
    if (!window.confirm('Delete this saved calendar? This cannot be undone.')) return
    try {
      await deleteCalendar(id)
      setStatus({ ok: true, msg: 'Calendar deleted' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="card" id="calLibrary">
      <div className="lib-header">
        <span className="lib-title">
          Calendar Library<span className="lib-count">({items.length})</span>
        </span>
        {isPlanner && (
          <button className="btn lib-save-btn" onClick={handleSave} disabled={busy}>Lock &amp; Save</button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="lib-empty">
          <div className="lib-empty-icon">LK</div>
          <div className="lib-empty-title">No saved calendars yet</div>
          <div className="lib-empty-desc">
            Generate a comparative calendar, then click "Lock &amp; Save" to create a locked snapshot here.
          </div>
        </div>
      ) : (
        <div className="lib-grid">
          {items.map(c => {
            const chips = c.mappingSummary || []
            const chk = integrity[c.id]
            const engineLabel = (c.engine || '').includes('v2') ? 'V2' : (c.engine || '').includes('v1') ? 'V1' : null
            const hasIntegrityIssue = chk && (chk.missingDays > 0 || chk.futCollisions > 0)
            // 2026-10-07 declutter: the integrity badges collapse into one dot + tooltip.
            const dotTitle = chk && [
              hasIntegrityIssue
                ? (chk.missingDays > 0 ? `${chk.missingDays} day(s) unmapped` : `${chk.futCollisions} future-date collision(s)`)
                : '365 coverage OK',
              chk.dupRefDates > 0 && `${chk.dupRefDates} reused ref-date${chk.dupRefDates === 1 ? '' : 's'} (expected when a month's future days outnumber its spare reference days - not necessarily a bug)`,
              chk.isV2 && (chk.isStale
                ? 'Out of sync with current V2 (regenerating its stored festival config with today\'s engine gives a different day-map)'
                : 'In sync with current V2'),
            ].filter(Boolean).join('\n')
            const dotClass = hasIntegrityIssue ? 'bad' : chk?.isV2 && chk.isStale ? 'stale' : 'ok'
            return (
              <div
                key={c.id}
                className="lib-card"
                role="button"
                tabIndex={0}
                title={`Load "${c.name}" into the editor`}
                onClick={() => handleLoad(c.id)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleLoad(c.id) } }}
              >
                <div className="lib-card-head">
                  <div className="lib-lock-icon">LK</div>
                  <div style={{ minWidth: 0 }}>
                    <div className="lib-name">
                      {c.name}
                      {/* Every entry in this library is a finalised snapshot: the API exposes
                          only create + delete for a saved calendar (no PUT/edit), so there is
                          no "unlocked/draft" state a badge could distinguish it from. The badge
                          is therefore shown on all of them, as a statement that saved calendars
                          are immutable, rather than driven by a (non-existent) `locked` field. */}
                      <span className="lib-locked-badge">Locked</span>
                      {engineLabel && <span className="lib-locked-badge lib-engine-badge">{engineLabel}</span>}
                      {/* Integrity + V1/V2 staleness check (checkIntegrity, top of this file);
                          no dot while its own getCalendar(id) is still in flight. */}
                      {chk && <span className={`ce-dot ${dotClass}`} title={dotTitle} role="img" aria-label={dotTitle} />}
                    </div>
                    <div className="lib-pair">{c.refYear} -&gt; {c.futYear}</div>
                  </div>
                  {isPlanner && (
                    // Enter/Space/clicks here must not also trigger the card's own load.
                    <span style={{ marginLeft: 'auto' }} onClick={e => e.stopPropagation()}
                      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation() }}>
                      <Menu label="⋯" className="ce-menu-right" title={`Actions for "${c.name}"`}>
                        <button onClick={e => { e.stopPropagation(); handleRename(c) }}>Rename</button>
                        <button className="danger" onClick={e => { e.stopPropagation(); handleDelete(c.id) }}>Delete</button>
                      </Menu>
                    </span>
                  )}
                </div>

                {/* Chip count is days mapped for that cluster (mappingSummary.totalDays,
                    the only per-cluster number the list endpoint returns). The old app's
                    chip showed the cluster's festival count instead - that would cost one
                    full GET per calendar here, so the day count stands in for it. */}
                <div className="lib-clusters">
                  {chips.map(m => (
                    <span key={m.cluster} className="lib-cluster-chip" title={`${m.totalDays} days mapped`}>
                      {m.cluster} ({m.totalDays})
                    </span>
                  ))}
                </div>

                <div className="lib-meta">
                  Saved {fmtSavedAt(c.savedAt)} • {chips.length} cluster{chips.length === 1 ? '' : 's'}
                </div>

                {/* Card click / Enter loads it ("Load & Preview" button removed as a duplicate). */}
                {isPlanner && chk?.isStale && (
                <div className="lib-actions">
                  {isPlanner && chk?.isStale && (
                    <button
                      className="btn lib-sync-btn"
                      disabled={syncingId === c.id}
                      onClick={e => { e.stopPropagation(); handleSyncNow(c) }}
                    >
                      {syncingId === c.id ? 'Syncing…' : 'Sync Now'}
                    </button>
                  )}
                </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)', fontSize: '12px', margin: '10px 0 0' }}>{status.msg}</p>}
    </div>
  )
}
