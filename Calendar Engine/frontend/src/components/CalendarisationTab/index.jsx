import { useState, useEffect } from 'react'
import { getClusterProfiles, putClusterProfiles, getAppState, updateCalendarFestivals, listCalendarLibrary, getCalendar } from '../../lib/api'
import { generateMappings, validate, computeMonthly, buildFestMap } from '../../lib/engine'
import { parseDate, fmtISO, fmtDisp, calDiff, weekNum } from '../../lib/dateUtils'
import ClusterTabs from './ClusterTabs'
import FestivalTable from './FestivalTable'
import OutputSection from './OutputSection'
import CalendarLibrary from './CalendarLibrary'
import ChangeLogViewer from './ChangeLogViewer'
import { DEFAULT_FESTIVALS, applyYearToProfiles, yearSyncMessage, resolveFestivalDefaults } from '../../lib/festivalData'

let _nextFestivalId = 1000

// Ported from `Calendar Engine/calendar_engine.html` line ~1332 (defined alongside
// MONTHS, just above the Date Utilities section there) — not exported by lib/dateUtils.js
// or lib/engine.js, so redefined here for building display rows.
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

// Default date for a newly added festival row: today's day/month in the given year
// (the configured Reference/Future year), falling back to the current year when
// that isn't set yet. Unlike the old localStorage app, a blank date is not an
// option here - put_cluster_profiles parses refDate/futDate with
// date.fromisoformat() into NOT NULL columns, so persisting '' would 500. The
// day is clamped to the target month's length so e.g. Feb 29 -> Feb 28 in a
// non-leap year rather than silently rolling over into March.
function defaultFestivalDate(year) {
  const now = new Date()
  const y = Number(year) || now.getFullYear()
  const m = now.getMonth()
  const daysInMonth = new Date(y, m + 1, 0).getDate()
  return fmtISO(new Date(y, m, Math.min(now.getDate(), daysInMonth)))
}

// Converts one raw mapping object (as returned by generateMappings/reconstructed
// from a saved calendar) into the flat row shape OutputSection.jsx renders.
// Mirrors the cell derivations in the old app's renderDayTable() (calendar_engine.html
// lines 1819-1868).
function toRow(m, clusterName) {
  const futInfo = m.futFestInfo
  const futFestStr = futInfo ? `${futInfo.festival} ${futInfo.position >= 0 ? '+' : ''}${futInfo.position}` : ''
  return {
    cluster: clusterName,
    refDate: fmtDisp(m.refDate),
    refDay: DAYS[m.refDate.getDay()],
    refWeek: weekNum(m.refDate),
    festival: m.festival || '',
    category: m.festiveCategory,
    position: m.festivePosition != null ? (m.festivePosition >= 0 ? '+' : '') + m.festivePosition : '—',
    futDate: fmtDisp(m.futureDate),
    // Raw 0-11 future-month index, carried alongside the formatted futDate so
    // OutputSection's Month filter can match on it directly. The old app filtered
    // with `m.futureDate.getMonth()` (calendar_engine.html line 1830); here the
    // Date object doesn't survive into the row shape, and re-parsing the
    // "20-Oct-2026" display string back into a month would be needlessly fragile.
    futMonthIdx: m.futureDate.getMonth(),
    futDay: DAYS[m.futureDate.getDay()],
    futWeek: weekNum(m.futureDate),
    futFestival: futFestStr,
    mappingType: m.mappingType,
    score: Math.round(m.score || 0),
    monthDelta: m.monthMatch ? 'Yes' : 'No',
    weekdayDelta: m.weekdayMatch ? 'Yes' : 'No',
    dayDelta: m.dateDiff,
  }
}

// Reconstructs mapping objects (same shape generateMappings produces, minus
// mappingPriority/score which aren't stored) from a saved calendar's flat
// [refISO, futISO] day pairs, so the same toRow()/validate()/computeMonthly()
// pipeline can render a loaded calendar. festival/category are looked up from
// the saved cluster's own festival definitions via buildFestMap so the display
// still shows festive context even though the day-pair storage itself doesn't
// carry it (backend `CalendarDayPair` only has ref_date/fut_date columns).
function mappingsFromSavedPairs(pairs, festivals, refYr, futYr) {
  const rMap = buildFestMap(refYr, festivals, refYr)
  const fMap = buildFestMap(futYr, festivals, refYr)
  return pairs.map(([refIso, futIso]) => {
    const rd = parseDate(refIso), fd = parseDate(futIso)
    const ri = rMap[refIso], fi = fMap[futIso]
    return {
      refDate: rd, futureDate: fd,
      festival: ri ? ri.festival : null,
      festivePosition: ri ? ri.position : null,
      festiveCategory: ri ? ri.category : (fi ? fi.category : 'Non-Festive'),
      futFestInfo: fi || null,
      mappingType: '(loaded from library)', mappingPriority: null, score: 0,
      monthMatch: rd.getMonth() === fd.getMonth(),
      weekdayMatch: rd.getDay() === fd.getDay(),
      dateDiff: calDiff(rd, fd),
    }
  })
}

export default function CalendarisationTab({ isPlanner }) {
  const [profiles, setProfiles] = useState([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [status, setStatus] = useState(null)
  // Festival Master collapse state (old app: toggleFestMaster(), which started
  // expanded — .fest-body had no inline display:none and #festToggle carried
  // the "open" class in the markup).
  const [festOpen, setFestOpen] = useState(true)

  // Engine run state. refYear/futYear/maxShift/moPri come from Task 4's
  // /app-state endpoint (owned/edited by VersionSettingTab) — read once on
  // mount, same as VersionSettingTab does. generateMappings/validate need
  // refYear/futYear/maxShift as actual numbers (they do `yr === refYear`
  // comparisons internally), so these are coerced with Number(...) wherever used.
  const [refYear, setRefYear] = useState(null)
  const [futYear, setFutYear] = useState(null)
  const [maxShift, setMaxShift] = useState(45)
  const [moPri, setMoPri] = useState('prev')

  // Raw per-cluster mappings from the last "Create Calendar" run — Date-object
  // based, keyed to profiles by index — used to build the save payload (needs
  // every cluster's day map, not just the one currently being viewed). Cleared
  // after loading a calendar from the library, since a loaded snapshot isn't a
  // fresh generation and shouldn't be re-saved as though it were.
  const [clusterMappingsRaw, setClusterMappingsRaw] = useState(null)
  // Which locked calendar is currently "on the preview board" - set on Load &
  // Preview, and again after Lock & Save. While set, every festival-list edit
  // (name/date/pre/core/post) autosaves into THAT calendar's own stored
  // festival list too, not just the live working set - see persist() below.
  // Only the festival list autosaves this way; the day-by-day mapping stays
  // exactly as last generated until Create Calendar + Lock & Save runs again.
  const [previewCalendarId, setPreviewCalendarId] = useState(null)
  const [dayMap, setDayMap] = useState(null)
  const [validationIssues, setValidationIssues] = useState([])
  const [monthlySummary, setMonthlySummary] = useState(null)
  const [engineStatus, setEngineStatus] = useState(null)
  // Every cluster's day-by-day rows combined, each tagged with its own cluster
  // name — feeds OutputSection's Day-by-Day preview, which defaults to showing
  // every cluster (not just whichever one ClusterTabs has "active" for editing
  // purposes). Rebuilt whenever a full set of per-cluster mappings becomes
  // available (a fresh "Create Calendar" run, or a calendar loaded from the
  // library) — NOT on every activeIdx switch, since it doesn't depend on which
  // cluster tab is being edited.
  const [allDayMap, setAllDayMap] = useState(null)

  useEffect(() => {
    getClusterProfiles().then(({ profiles }) => {
      setProfiles(profiles.length ? profiles : [{ name: 'Cluster 1', region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }])
    }).catch(e => setStatus({ ok: false, msg: e.message }))
    getAppState().then(s => {
      if (s.refYear != null) setRefYear(s.refYear)
      if (s.futYear != null) setFutYear(s.futYear)
      if (s.maxShift != null) setMaxShift(s.maxShift)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  // "Create Calendar" — ports the old app's createCalendar() (calendar_engine.html
  // lines 2922-2938), whose first real step was autoUpdateFestivalDates(): every
  // cluster's every festival date is re-synced to the configured Reference/Future
  // years BEFORE the engine runs. Without that step, changing the years on the
  // Version Setting tab did nothing to the festival dates and the generated
  // calendar was silently built from whatever years the festivals happened to be
  // seeded with.
  //
  // The rewrite is planner-only: it mutates real persisted data, and persist()
  // already no-ops the write for non-planners. A buyer clicking this still gets
  // a calendar generated from the stored dates, read-only, exactly as before.
  async function runEngine() {
    if (!refYear || !futYear) {
      setEngineStatus({ ok: false, msg: 'Set Reference Year and Future Year on the Version Setting tab first.' })
      return
    }
    const ry = Number(refYear), fy = Number(futYear), ms = Number(maxShift) || 45
    if (ry === fy) {
      setEngineStatus({ ok: false, msg: 'Reference and Future year must be different.' })
      return
    }
    if (ry < 1900 || ry > 2099 || fy < 1900 || fy > 2099) {
      setEngineStatus({ ok: false, msg: 'Years must be between 1900 and 2099.' })
      return
    }

    let workingProfiles = profiles
    let syncMsg = ''
    if (isPlanner) {
      const sync = applyYearToProfiles(profiles, ry, fy)
      workingProfiles = sync.profiles
      if (sync.updated) {
        // persist() also does setProfiles(), so the festival table on screen
        // re-renders with the new dates — the old app's renderFestivalTable().
        await persist(workingProfiles)
        syncMsg = yearSyncMessage(ry, fy, sync.updated, sync.estimated) + ' · '
      }
    }

    try {
      const perCluster = workingProfiles.map(cp => ({ name: cp.name, mappings: generateMappings(cp.festivals, ry, fy, ms, moPri) }))
      setClusterMappingsRaw(perCluster)
      setAllDayMap(perCluster.flatMap(cm => cm.mappings.map(m => toRow(m, cm.name))))
      const activeMappings = perCluster[activeIdx].mappings
      setDayMap(activeMappings.map(m => toRow(m, perCluster[activeIdx].name)))
      setValidationIssues(validate(activeMappings, ry, fy, ms, workingProfiles[activeIdx].festivals))
      setMonthlySummary(computeMonthly(activeMappings))
      setEngineStatus({ ok: true, msg: `${syncMsg}Calendar generated: ${activeMappings.length} days mapped for "${workingProfiles[activeIdx].name}".` })
    } catch (e) {
      setEngineStatus({ ok: false, msg: e.message })
    }
  }

  // Keep the output view in sync with whichever cluster tab is active, same as
  // the old app's viewCluster() (calendar_engine.html lines 1787-1799).
  useEffect(() => {
    if (!clusterMappingsRaw || !clusterMappingsRaw[activeIdx] || !profiles[activeIdx]) return
    const ry = Number(refYear), fy = Number(futYear), ms = Number(maxShift) || 45
    const activeMappings = clusterMappingsRaw[activeIdx].mappings
    setDayMap(activeMappings.map(m => toRow(m, clusterMappingsRaw[activeIdx].name)))
    setValidationIssues(validate(activeMappings, ry, fy, ms, profiles[activeIdx].festivals))
    setMonthlySummary(computeMonthly(activeMappings))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx])

  function buildSavePayload() {
    if (!clusterMappingsRaw) throw new Error('Click "Create Calendar" to generate mappings before saving.')
    const dayMapByCluster = {}
    clusterMappingsRaw.forEach(cm => {
      dayMapByCluster[cm.name] = cm.mappings.map(m => [fmtISO(m.refDate), fmtISO(m.futureDate)])
    })
    return {
      id: Date.now(),
      name: `${profiles[activeIdx].name} Calendar`,
      refYear: Number(refYear),
      futYear: Number(futYear),
      savedAt: new Date().toISOString(),
      engine: 'calendarisation-v1',
      clusters: profiles.map(cp => ({ name: cp.name, region: cp.region, festivals: cp.festivals })),
      dayMap: dayMapByCluster,
    }
  }

  // "Load" from the Calendar Library — ported from the old app's
  // loadSavedCalendar() (calendar_engine.html lines 3827-3842), which replaced
  // the whole working cluster-profiles state with the snapshot's clusters before
  // re-rendering. That is the important half: without setProfiles(...) this only
  // re-rendered a day table for whichever cluster happened to already be loaded
  // from /cluster-profiles, so "Load" previewed a calendar instead of loading it.
  //
  // The restored profiles are in-memory only: they are NOT pushed to
  // /cluster-profiles here, matching every other profiles-state change in this
  // file (handleReorder/handleAdd/handleFestivalsChange all write through
  // persist() only when the user actually edits something). The next real edit
  // persists the loaded set through that same path.
  function handleLoadFromLibrary(full) {
    const clusters = full.clusters || []
    const ry = Number(full.refYear), fy = Number(full.futYear)
    if (!clusters.length) {
      setEngineStatus({ ok: false, msg: `Loaded "${full.name}", but it has no saved cluster definitions.` })
      return
    }

    // Snapshot clusters carry {name, region, festivals} only — nextId isn't
    // stored, so derive it from the highest festival id in the snapshot (same
    // rule handleAddFestival uses) rather than from festivals.length, which
    // would hand out ids that already exist.
    const nextProfiles = clusters.map(c => {
      const festivals = (c.festivals || []).map(f => ({ ...f }))
      const maxId = festivals.reduce((m, f) => Math.max(m, Number(f.id) || 0), 0)
      return { name: c.name, region: c.region || 'all', nextId: maxId + 1, festivals }
    })

    // Stay on the same-named cluster if the loaded calendar has one; otherwise
    // fall back to the first, so activeIdx can never point past the new array.
    const prevName = profiles[activeIdx]?.name
    const foundIdx = nextProfiles.findIndex(p => p.name === prevName)
    const nextIdx = foundIdx >= 0 ? foundIdx : 0
    const cluster = nextProfiles[nextIdx]

    setProfiles(nextProfiles)
    setActiveIdx(nextIdx)
    setRefYear(full.refYear)
    setFutYear(full.futYear)
    setClusterMappingsRaw(null) // a loaded snapshot; regenerate via "Create Calendar" before saving again
    setPreviewCalendarId(full.id) // subsequent festival-list edits autosave into this calendar too

    // Every cluster's saved pairs, reconstructed the same way the active
    // cluster's are below — feeds the Day-by-Day preview's "all clusters"
    // default. A cluster with no saved pairs of its own just contributes
    // nothing here rather than blocking the others.
    setAllDayMap(
      nextProfiles.flatMap(p => {
        const pPairs = (full.dayMap && full.dayMap[p.name]) || []
        if (!pPairs.length) return []
        return mappingsFromSavedPairs(pPairs, p.festivals, ry, fy).map(m => toRow(m, p.name))
      })
    )

    const pairs = (full.dayMap && full.dayMap[cluster.name]) || []
    if (!pairs.length) {
      setDayMap([])
      setValidationIssues([])
      setMonthlySummary(null)
      setEngineStatus({ ok: false, msg: `Loaded "${full.name}" (${nextProfiles.length} clusters), but it has no saved day mapping for "${cluster.name}".` })
      return
    }
    const mappings = mappingsFromSavedPairs(pairs, cluster.festivals, ry, fy)
    setDayMap(mappings.map(m => toRow(m, cluster.name)))
    setValidationIssues(validate(mappings, ry, fy, Number(maxShift) || 45, cluster.festivals))
    setMonthlySummary(computeMonthly(mappings))
    setEngineStatus({ ok: true, msg: `Loaded "${full.name}" (${full.refYear} -> ${full.futYear}) — ${nextProfiles.length} cluster${nextProfiles.length === 1 ? '' : 's'} restored, showing "${cluster.name}".` })
  }

  async function persist(nextProfiles) {
    setProfiles(nextProfiles)
    if (!isPlanner) return
    try {
      await putClusterProfiles({
        profiles: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
      })
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
      return
    }
    // Autosave into whichever locked calendar is on the preview board (see
    // previewCalendarId above) - festival list only, day-map untouched. Best-
    // effort: a failure here doesn't roll back or re-throw, since the live
    // working set above already saved fine; it just shows alongside the normal
    // "Saved" status so a real problem (e.g. that calendar got deleted from
    // another tab) is still visible instead of silently swallowed.
    if (previewCalendarId != null) {
      try {
        await updateCalendarFestivals(previewCalendarId, {
          clusters: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, festivals: cp.festivals })),
        })
      } catch (e) {
        setStatus({ ok: false, msg: `Saved to working set, but autosave into the previewed template failed: ${e.message}` })
      }
    }
  }

  function handleReorder(from, to) {
    const next = [...profiles]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    let nextActive = activeIdx
    if (activeIdx === from) nextActive = to
    else if (from < activeIdx && to >= activeIdx) nextActive--
    else if (from > activeIdx && to <= activeIdx) nextActive++
    setActiveIdx(nextActive)
    persist(next)
  }

  function handleAdd() {
    const next = [...profiles, { name: `Cluster ${profiles.length + 1}`, region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }]
    persist(next)
  }

  function handleFestivalsChange(nextFestivals) {
    const next = profiles.map((cp, i) => i === activeIdx ? { ...cp, festivals: nextFestivals } : cp)
    persist(next)
  }

  // Rename the active cluster — old app: renameCluster() (calendar_engine.html
  // lines 2197-2206). The trim/"Cluster N" fallback and the uniqueness check
  // live in ClusterTabs (which owns the draft input); by the time this runs the
  // name is already validated.
  //
  // IMPORTANT: cluster name is a join key elsewhere in this system
  // (calendar.store_calendar_clusters.cluster_name and a saved calendar's
  // per-cluster dayMap are both keyed by it), so this has to go through the same
  // persist() -> putClusterProfiles write path as every other profile edit —
  // which it does. Renaming does NOT retro-rewrite those other tables, exactly
  // as in the old app; a renamed cluster loses its store mapping until the
  // Store-Cluster Mapping tab is re-pointed at the new name.
  function handleRename(name) {
    persist(profiles.map((cp, i) => i === activeIdx ? { ...cp, name } : cp))
  }

  // Region selector — old app: setClusterRegion() (calendar_engine.html lines
  // 2151-2154). Only cp.region is written here; the old app's
  // autoApplyRegionalFestivals() side effect is intentionally not ported (see
  // the note in ClusterTabs.jsx).
  function handleRegionChange(region) {
    persist(profiles.map((cp, i) => i === activeIdx ? { ...cp, region } : cp))
  }

  // "Copy from" — old app: copyFromCluster() (calendar_engine.html lines
  // 2107-2121), including its confirm() before the destructive replace. The
  // festival objects are deep-copied ({...f}) so the two clusters don't end up
  // sharing row objects, same as handleAdd does with DEFAULT_FESTIVALS; nextId
  // is carried over from the source so freshly added rows can't collide with
  // the copied ids.
  function handleCopyFrom(srcIdx) {
    const src = profiles[srcIdx]
    const dest = profiles[activeIdx]
    if (!src || !dest || srcIdx === activeIdx) return
    if (!window.confirm(`Copy all ${src.festivals.length} festivals from "${src.name}" into "${dest.name}"?\n\nThis replaces the current festival list for "${dest.name}", is saved immediately, and cannot be undone.`)) return
    persist(profiles.map((cp, i) => i === activeIdx
      ? { ...cp, festivals: src.festivals.map(f => ({ ...f })), nextId: src.nextId }
      : cp))
  }

  // "Reset to Defaults" — old app: resetFestivals() (calendar_engine.html lines
  // 2067-2074), which also reset the cluster's nextId to 20 (the DEFAULT_FESTIVALS
  // ids top out at 15). The old app did NOT confirm first; a confirm is added
  // here because this writes straight through to the shared database instead of
  // localStorage, with no undo — the same reasoning FestivalTable's row delete
  // already uses.
  function handleResetFestivals() {
    const dest = profiles[activeIdx]
    if (!dest) return
    if (!window.confirm(`Replace all ${dest.festivals.length} festivals in "${dest.name}" with the ${DEFAULT_FESTIVALS.length} built-in defaults?\n\nThis is saved immediately and cannot be undone.`)) return
    persist(profiles.map((cp, i) => i === activeIdx
      ? { ...cp, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })), nextId: 20 }
      : cp))
  }

  // Editing one row's Pre/Core/Post inline cascades to every OTHER cluster's
  // festival with the same name, so a shared festival's window (e.g. "Diwali")
  // stays consistent across clusters without a separate bulk-set step.
  // Matched by name (falling back to the exact row by index/cluster so the
  // edited cell itself always applies even if its name is blank or
  // duplicated) - clusters with no festival of that name are left untouched.
  // Unlike handleHeaderBulk, this is a normal-weight edit (one named
  // festival, not "every festival in every cluster"), so it does not confirm.
  function handleDayFieldChange(idx, field, value) {
    const name = profiles[activeIdx].festivals[idx].name
    persist(profiles.map((cp, ci) => ({
      ...cp,
      festivals: cp.festivals.map((f, fi) => ((ci === activeIdx && fi === idx) || f.name === name)
        ? { ...f, [field]: value }
        : f),
    })))
  }

  // Header Pre/Core/Post bulk set — old app: applyHeaderBulk()
  // (calendar_engine.html lines 1977-2000). Cross-cluster by design: the
  // original loops `clusterProfiles.forEach`, so it sets the column for every
  // festival of every cluster, not just the active one. FestivalTable clamps
  // the value (core >= 1, pre/post >= 0) and confirms before calling this.
  function handleHeaderBulk(field, value) {
    persist(profiles.map(cp => ({ ...cp, festivals: cp.festivals.map(f => ({ ...f, [field]: value })) })))
  }

  // "+ Add Festival" (old app: addFestival(), calendar_engine.html line ~2061).
  // Appends an editable placeholder row to the active cluster and persists it
  // through the same handleFestivalsChange/persist() path every other festival
  // edit uses.
  function handleAddFestival() {
    const existing = profiles[activeIdx]?.festivals || []
    // _nextFestivalId is module-scoped, so it resets to its initial value on every
    // page load. Lift it above the ids already in use before handing one out, so a
    // festival added today can't collide with one added in an earlier session -
    // these ids are both the React keys in FestivalTable and the backend's
    // source_festival_id.
    const maxId = existing.reduce((m, f) => Math.max(m, Number(f.id) || 0), 0)
    if (_nextFestivalId <= maxId) _nextFestivalId = maxId + 1
    handleFestivalsChange([...existing, {
      id: _nextFestivalId++,
      name: 'New Festival',
      refDate: defaultFestivalDate(refYear),
      futDate: defaultFestivalDate(futYear),
      pre: 1, core: 1, post: 1,
    }])
  }

  // A festival picked from the Festival Name autocomplete (FestivalTable's
  // pickSuggestion) auto-copies into every OTHER saved/locked calendar that
  // has a cluster with this same name - each template gets the date resolved
  // for ITS OWN refYear/futYear (resolveFestivalDefaults), not a copy of the
  // date just entered here. Purely additive: a template whose matching
  // cluster already has a festival of this name is left untouched (no
  // overwrite of anything the user already has), and the currently-previewed
  // template is skipped here since persist()'s own autosave already covers
  // it. Best-effort per template - one template failing to update (e.g.
  // deleted from another tab) doesn't block the others.
  async function handleFestivalPicked(name) {
    const clusterName = profiles[activeIdx]?.name
    if (!clusterName) return
    let items
    try {
      items = await listCalendarLibrary()
    } catch {
      return
    }
    let updated = 0
    let failed = 0
    for (const item of items) {
      if (item.id === previewCalendarId) continue
      try {
        const full = await getCalendar(item.id)
        const clusters = full.clusters || []
        const ci = clusters.findIndex(c => c.name === clusterName)
        if (ci < 0) continue
        const festivals = clusters[ci].festivals || []
        if (festivals.some(f => f.name === name)) continue
        const perYear = resolveFestivalDefaults(name, full.refYear, full.futYear)
        if (!perYear) continue
        const maxId = festivals.reduce((m, f) => Math.max(m, Number(f.id) || 0), 0)
        const nextClusters = clusters.map((c, i) => i === ci
          ? { ...c, festivals: [...festivals, { id: maxId + 1, name, ...perYear }] }
          : c)
        await updateCalendarFestivals(item.id, { clusters: nextClusters })
        updated++
      } catch {
        failed++
      }
    }
    if (updated || failed) {
      const parts = []
      if (updated) parts.push(`copied into ${updated} other saved template${updated === 1 ? '' : 's'}`)
      if (failed) parts.push(`${failed} failed`)
      setStatus({ ok: failed === 0, msg: `"${name}" added to "${clusterName}" — ${parts.join(', ')}.` })
    }
  }

  if (!profiles.length) return <div className="module-panel">Loading…</div>

  return (
    <div className="module-panel" style={{ display: 'flex', gap: '16px' }}>
      <main style={{ flex: 1 }}>
        {/* Festival Master card chrome — ported from calendar_engine.html lines
            760-826. The header (title + count pill + caret) collapses .fest-body,
            which spans the cluster tabs, the rename/region/copy rows, the
            festival table and the footer action bar — the same scope
            toggleFestMaster() had (calendar_engine.html lines 2075-2080). */}
        <div className="fest-wrap">
          <div className="fest-header" onClick={() => setFestOpen(o => !o)}
            title={festOpen ? 'Collapse Festival Master' : 'Expand Festival Master'}>
            <div className="fest-header-title">
              Festival Master
              <span className="fest-count">{profiles[activeIdx].festivals.length}</span>
            </div>
            <span className={`toggle${festOpen ? ' open' : ''}`} />
          </div>
          {festOpen && (
            <div className="fest-body">
              <ClusterTabs profiles={profiles} activeIdx={activeIdx} onSwitch={setActiveIdx}
                onReorder={handleReorder} onAdd={handleAdd} onRename={handleRename}
                onRegionChange={handleRegionChange} onCopyFrom={handleCopyFrom} isPlanner={isPlanner} />
              <FestivalTable festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange}
                onAdd={handleAddFestival} onReset={handleResetFestivals} onBulkSet={handleHeaderBulk}
                onDayFieldChange={handleDayFieldChange} onFestivalPicked={handleFestivalPicked} isPlanner={isPlanner}
                refYear={refYear} futYear={futYear} />
            </div>
          )}
        </div>

        <div className="card">
          <div style={{ fontSize: '11px', color: 'var(--muted)', margin: '0 0 12px' }}>
            Reference Year {refYear ?? '—'} → Future Year {futYear ?? '—'} (set on the Version Setting tab)
          </div>
          <button className="btn" onClick={runEngine}>Create Calendar</button>
          {engineStatus && <p style={{ color: engineStatus.ok ? 'var(--green)' : 'var(--red)' }}>{engineStatus.msg}</p>}
        </div>

        <OutputSection dayMap={dayMap} allDayMap={allDayMap} validationIssues={validationIssues} monthlySummary={monthlySummary} />

        {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
      </main>

      <aside style={{ width: '320px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <CalendarLibrary onLoad={handleLoadFromLibrary} onSaved={setPreviewCalendarId} isPlanner={isPlanner} buildSavePayload={buildSavePayload} />
        <ChangeLogViewer rangeKey={refYear && futYear ? `${refYear}-${futYear}` : null} />
      </aside>
    </div>
  )
}

// NOTE (Task 6 known simplifications, to be addressed by later tasks if needed):
// - Festival-name autocomplete (old calendar_engine.html lines 1222-1301, searchFestDB/FESTIVAL_DATES-driven
//   suggestions dropdown) is not ported. Typing a full festival name still works without suggestions.
// - autoFillDate (old calendar_engine.html lines 2036-2054): when a festival's Reference Date is edited and its
//   Future Date is still empty (or vice versa), the old app auto-filled the other date by re-using the day/month
//   against a separately-selected ref/fut year (inputs #refYear/#futYear, part of the bulk-adjust panel added in
//   Task 7). Since those year selectors don't exist yet in this partial file, that auto-fill is deferred to
//   Task 7/8 rather than approximated here.
