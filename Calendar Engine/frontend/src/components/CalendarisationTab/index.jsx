import { useState, useEffect, useRef } from 'react'
import { syncFestivalWindow, getClusterProfiles, putClusterProfiles, getAppState, updateCalendarFestivals, listCalendarLibrary, getCalendar, saveCalendar, deleteCalendar, syncFestivalReference } from '../../lib/api'
import { generateMappings, validate, computeMonthly, buildFestMap } from '../../lib/engine'
import { parseDate, fmtISO, fmtDisp, calDiff, weekNum } from '../../lib/dateUtils'
import ClusterTabs from './ClusterTabs'
import FestivalTable from './FestivalTable'
import FestivalImportPanel from './FestivalImportPanel'
import OutputSection from './OutputSection'
import CalendarLibrary from './CalendarLibrary'
import ChangeLogViewer from './ChangeLogViewer'
import { DEFAULT_FESTIVALS, applyYearToProfiles, yearSyncMessage, resolveFestivalDefaults, coreFestivalNamesFor, loadFestivalReference, laganDaysFor } from '../../lib/festivalData'

let _nextFestivalId = 1000

// Ported from `Calendar Engine/calendar_engine.html` line ~1332 (defined alongside
// MONTHS, just above the Date Utilities section there) - not exported by lib/dateUtils.js
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
    position: m.festivePosition != null ? (m.festivePosition >= 0 ? '+' : '') + m.festivePosition : '-',
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
      mappingType: '', mappingPriority: null, score: 0,
      monthMatch: rd.getMonth() === fd.getMonth(),
      weekdayMatch: rd.getDay() === fd.getDay(),
      dateDiff: calDiff(rd, fd),
    }
  })
}

export default function CalendarisationTab({ isPlanner, engineVersion = 1 }) {
  const [profiles, setProfiles] = useState([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [status, setStatus] = useState(null)
  // Festival Master collapse state (old app: toggleFestMaster(), which started
  // expanded - .fest-body had no inline display:none and #festToggle carried
  // the "open" class in the markup).
  const [festOpen, setFestOpen] = useState(true)
  // "Redact festival from all clusters" input - the draft name typed before
  // handleRedactFestival() runs. Deliberately free text, not a dropdown of
  // existing names: whatever cluster you're currently viewing shows you the
  // exact spelling to copy, and the confirm step in the handler names every
  // cluster it actually found a match in before anything is removed, so a
  // typo just reports "not found" rather than silently doing nothing useful.
  const [redactName, setRedactName] = useState('')

  // Engine run state. refYear/futYear/maxShift/moPri come from Task 4's
  // /app-state endpoint (owned/edited by VersionSettingTab) - read once on
  // mount, same as VersionSettingTab does. generateMappings/validate need
  // refYear/futYear/maxShift as actual numbers (they do `yr === refYear`
  // comparisons internally), so these are coerced with Number(...) wherever used.
  const [refYear, setRefYear] = useState(null)
  const [futYear, setFutYear] = useState(null)
  const [maxShift, setMaxShift] = useState(45)
  const [moPri, setMoPri] = useState('prev')

  // Raw per-cluster mappings from the last "Create Calendar" run - Date-object
  // based, keyed to profiles by index - used to build the save payload (needs
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
  // True once Load & Preview has swapped a library template's clusters into
  // the editor - from then on the editor does NOT hold the live working set,
  // so persist() must never PUT it to /cluster-profiles. (previewCalendarId
  // alone can't tell this: Lock & Save of the live set also sets it.)
  const [editingTemplate, setEditingTemplate] = useState(false)
  // The loaded template's own name, kept alongside previewCalendarId - lets
  // handleSaveToLoadedTemplate overwrite that EXACT template without
  // prompting (Lock & Save's own prompt defaults to an auto-generated name
  // derived from the active cluster, not the loaded template's real name, so
  // it can't be reused here without asking the user to retype it).
  const [previewCalendarName, setPreviewCalendarName] = useState(null)
  const [savingToTemplate, setSavingToTemplate] = useState(false)
  const [syncingStructure, setSyncingStructure] = useState(false)
  const [syncingDates, setSyncingDates] = useState(false)
  const [dateSyncChanges, setDateSyncChanges] = useState(null)
  const [dayMap, setDayMap] = useState(null)
  const [validationIssues, setValidationIssues] = useState([])
  const [monthlySummary, setMonthlySummary] = useState(null)
  const [engineStatus, setEngineStatus] = useState(null)
  // Every cluster's day-by-day rows combined, each tagged with its own cluster
  // name - feeds OutputSection's Day-by-Day preview, which defaults to showing
  // every cluster (not just whichever one ClusterTabs has "active" for editing
  // purposes). Rebuilt whenever a full set of per-cluster mappings becomes
  // available (a fresh "Create Calendar" run, or a calendar loaded from the
  // library) - NOT on every activeIdx switch, since it doesn't depend on which
  // cluster tab is being edited.
  const [allDayMap, setAllDayMap] = useState(null)

  useEffect(() => {
    getClusterProfiles().then(({ profiles }) => {
      setProfiles(profiles.length ? profiles : [{ name: 'Cluster 1', region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }])
    }).catch(e => setStatus({ ok: false, msg: e.message }))
    loadFestivalReference()  // so resolveFestivalDefaults (festival-name picks) sees the Google dates
    getAppState().then(s => {
      if (s.refYear != null) setRefYear(s.refYear)
      if (s.futYear != null) setFutYear(s.futYear)
      if (s.maxShift != null) setMaxShift(s.maxShift)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  // "Create Calendar" - ports the old app's createCalendar() (calendar_engine.html
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
  // Returns the freshly generated per-cluster mappings (or null on an early
  // validation bail-out) - NOT just a success boolean, because a caller that
  // needs the fresh data right away (e.g. handleSaveToLoadedTemplate, which
  // must save what was JUST generated, not whatever the calendar looked like
  // before) can't safely read it back off clusterMappingsRaw state: the
  // setClusterMappingsRaw call below only takes effect on the next render,
  // so a synchronous read immediately after awaiting this function would
  // still see the STALE value from before this call ran (or null on a
  // component's first-ever generate), not what was just computed.
  async function runEngine() {
    if (!refYear || !futYear) {
      setEngineStatus({ ok: false, msg: 'Set Reference Year and Future Year on the Version Setting tab first.' })
      return null
    }
    const ry = Number(refYear), fy = Number(futYear), ms = Number(maxShift) || 45
    if (ry === fy) {
      setEngineStatus({ ok: false, msg: 'Reference and Future year must be different.' })
      return null
    }
    if (ry < 1900 || ry > 2099 || fy < 1900 || fy > 2099) {
      setEngineStatus({ ok: false, msg: 'Years must be between 1900 and 2099.' })
      return null
    }

    let workingProfiles = profiles
    let syncMsg = ''
    await loadFestivalReference()  // everyone: it also loads the Drik lagan dates the engine matches on
    if (isPlanner) {
      const sync = applyYearToProfiles(profiles, ry, fy)
      workingProfiles = sync.profiles
      if (sync.updated) {
        // persist() also does setProfiles(), so the festival table on screen
        // re-renders with the new dates - the old app's renderFestivalTable().
        await persist(workingProfiles)
        syncMsg = yearSyncMessage(ry, fy, sync.updated, sync.estimated, sync.fallback) + ' · '
      } else if (sync.fallback.length) {
        syncMsg = `WARNING: not in Google reference, used built-in table: ${sync.fallback.join(', ')} · `
      }
    } else {
      // Non-planners can't re-date (persist() no-ops for them), and
      // buildFestMap drops every festival date outside ry/fy - so stale
      // Festival Master dates would silently give a festival-less calendar.
      const stale = profiles.flatMap(cp => cp.festivals || []).find(f =>
        (f.refDate && String(f.refDate).slice(0, 4) !== String(ry)) ||
        (f.futDate && String(f.futDate).slice(0, 4) !== String(fy)))
      if (stale) {
        setEngineStatus({ ok: false, msg: `Festival Master dates are for ${String(stale.refDate || '?').slice(0, 4)} -> ${String(stale.futDate || '?').slice(0, 4)}, but this calendar is ${ry} -> ${fy}. Ask a planner to update the Festival Master.` })
        return null
      }
    }

    try {
      const perCluster = workingProfiles.map(cp => ({
        name: cp.name,
        mappings: generateMappings(cp.festivals, ry, fy, ms, moPri, coreFestivalNamesFor(cp.name), engineVersion, laganDaysFor(ry, fy)),
      }))
      setClusterMappingsRaw(perCluster)
      setAllDayMap(perCluster.flatMap(cm => cm.mappings.map(m => toRow(m, cm.name))))
      const activeMappings = perCluster[activeIdx].mappings
      setDayMap(activeMappings.map(m => toRow(m, perCluster[activeIdx].name)))
      setValidationIssues(validate(activeMappings, ry, fy, ms, workingProfiles[activeIdx].festivals, coreFestivalNamesFor(workingProfiles[activeIdx].name), engineVersion))
      setMonthlySummary(computeMonthly(activeMappings))
      setEngineStatus({ ok: true, msg: `${syncMsg}Calendar generated: ${activeMappings.length} days mapped for "${workingProfiles[activeIdx].name}".` })
      // workingProfiles alongside perCluster for the same reason: a year-sync
      // just above (applyYearToProfiles) may have changed festival dates and
      // called persist(workingProfiles), but that setProfiles() is equally
      // subject to the stale-render problem in this function's own opening
      // comment - the `profiles` variable in scope right now, and any closure
      // that captured it, is still the pre-sync array until the next render.
      return { mappings: perCluster, profiles: workingProfiles }
    } catch (e) {
      setEngineStatus({ ok: false, msg: e.message })
      return null
    }
  }

  // Keep the output view in sync with whichever cluster tab is active, same as
  // the old app's viewCluster() (calendar_engine.html lines 1787-1799).
  useEffect(() => {
    if (!clusterMappingsRaw || !clusterMappingsRaw[activeIdx] || !profiles[activeIdx]) return
    const ry = Number(refYear), fy = Number(futYear), ms = Number(maxShift) || 45
    const activeMappings = clusterMappingsRaw[activeIdx].mappings
    setDayMap(activeMappings.map(m => toRow(m, clusterMappingsRaw[activeIdx].name)))
    setValidationIssues(validate(activeMappings, ry, fy, ms, profiles[activeIdx].festivals, coreFestivalNamesFor(clusterMappingsRaw[activeIdx].name), engineVersion))
    setMonthlySummary(computeMonthly(activeMappings))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx])

  // fresh, when given, overrides both the mappings and the profiles read
  // from React state - needed by handleSaveToLoadedTemplate, which calls
  // this immediately after runEngine() and can't rely on clusterMappingsRaw/
  // profiles state having caught up yet (see runEngine's own comment on the
  // same stale-render problem). Every other caller (CalendarLibrary's own
  // Lock & Save) omits it and gets the normal state-backed behavior.
  function buildSavePayload(fresh) {
    const mappings = fresh?.mappings ?? clusterMappingsRaw
    const sourceProfiles = fresh?.profiles ?? profiles
    if (!mappings) throw new Error('Click "Create Calendar" to generate mappings before saving.')
    const dayMapByCluster = {}
    mappings.forEach(cm => {
      dayMapByCluster[cm.name] = cm.mappings.map(m => [fmtISO(m.refDate), fmtISO(m.futureDate)])
    })
    return {
      id: Date.now(),
      // default Lock & Save name = "LY -> TY Calendar - All" from the Version Setting years the calendar was
      // generated with (user, 2026-10-05; was "<cluster> Calendar")
      name: `${Number(refYear)} -> ${Number(futYear)} Calendar - All`,
      refYear: Number(refYear),
      futYear: Number(futYear),
      savedAt: new Date().toISOString(),
      engine: `calendarisation-v${engineVersion}`,
      clusters: sourceProfiles.map(cp => ({ name: cp.name, region: cp.region, festivals: cp.festivals })),
      dayMap: dayMapByCluster,
    }
  }

  // Overwrites the CURRENTLY LOADED locked template (previewCalendarId/Name,
  // set by "Load & Preview") with the calendar regenerated from whatever the
  // Festival Master edits currently look like - the one-click alternative to
  // manually running "Create Calendar" and then "Lock & Save" with the exact
  // existing name retyped into its prompt. Only meaningful when a template
  // is actually loaded; the button that calls this is hidden otherwise.
  async function handleSaveToLoadedTemplate() {
    if (!isPlanner || !previewCalendarId || !previewCalendarName || savingToTemplate) return
    if (!window.confirm(
      `Overwrite locked template "${previewCalendarName}" with the current festival changes?\n`
      + 'This regenerates it from your current Festival Master settings and cannot be undone.'
    )) return

    setSavingToTemplate(true)
    try {
      const fresh = await runEngine()
      if (!fresh) return // runEngine already surfaced why via engineStatus

      let payload
      try {
        payload = buildSavePayload(fresh)
      } catch (e) {
        setEngineStatus({ ok: false, msg: e.message })
        return
      }

      const items = await listCalendarLibrary()
      // the template that is loaded, by id - names can repeat, and deleting by name hit the other one (audit 2026-10-06)
      const existing = items.find(c => c.id === previewCalendarId)
      // Same delete-then-create overwrite CalendarLibrary's own Lock & Save
      // uses (see its handleSave comment - the backend has no update
      // endpoint for a saved calendar). existing should always be found
      // here (previewCalendarName only ever comes from an already-loaded
      // template), but if it was deleted from another tab in the meantime,
      // this still succeeds - just as a fresh save under the same name.
      await saveCalendar({ ...payload, name: previewCalendarName })   // save first: a failed save keeps the old one
      if (existing) await deleteCalendar(existing.id)
      setPreviewCalendarId(payload.id)
      setEngineStatus({ ok: true, msg: `Template "${previewCalendarName}" overwritten with your current festival changes.` })
    } catch (e) {
      setEngineStatus({ ok: false, msg: e.message })
    } finally {
      setSavingToTemplate(false)
    }
  }

  // "Load" from the Calendar Library - ported from the old app's
  // loadSavedCalendar() (calendar_engine.html lines 3827-3842), which replaced
  // the whole working cluster-profiles state with the snapshot's clusters before
  // re-rendering. That is the important half: without setProfiles(...) this only
  // re-rendered a day table for whichever cluster happened to already be loaded
  // from /cluster-profiles, so "Load" previewed a calendar instead of loading it.
  //
  // The restored profiles are in-memory only and are NEVER pushed to
  // /cluster-profiles: editingTemplate makes persist() write edits into that
  // template's own festival list only, so previewing a template can't
  // overwrite the shared live Festival Master. Reload the page to get back to
  // the live working set.
  function handleLoadFromLibrary(full) {
    const clusters = full.clusters || []
    const ry = Number(full.refYear), fy = Number(full.futYear)
    if (!clusters.length) {
      setEngineStatus({ ok: false, msg: `Loaded "${full.name}", but it has no saved cluster definitions.` })
      return
    }

    // Snapshot clusters carry {name, region, festivals} only - nextId isn't
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
    setPreviewCalendarName(full.name)
    setEditingTemplate(true)

    // Every cluster's saved pairs, reconstructed the same way the active
    // cluster's are below - feeds the Day-by-Day preview's "all clusters"
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
    setValidationIssues(validate(mappings, ry, fy, Number(maxShift) || 45, cluster.festivals, coreFestivalNamesFor(cluster.name), engineVersion))
    setMonthlySummary(computeMonthly(mappings))
    setEngineStatus({ ok: true, msg: `Loaded "${full.name}" (${full.refYear} -> ${full.futYear}) - ${nextProfiles.length} cluster${nextProfiles.length === 1 ? '' : 's'} restored, showing "${cluster.name}".` })
  }

  // Returns whether the working-set save itself succeeded, so a caller with
  // its own more specific success message (e.g. handleRedactFestival) knows
  // whether it's safe to show it - overwriting a genuine failure's status
  // with a false "success" message would be worse than not having one.
  async function persist(nextProfiles) {
    setProfiles(nextProfiles)
    if (!isPlanner) return false
    // A Load & Preview'd template (editingTemplate) holds THAT calendar's
    // clusters (possibly another year's dates), not the live working set - so
    // it is never PUT to /cluster-profiles.
    if (!editingTemplate) {
      try {
        await putClusterProfiles({
          profiles: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
        })
        setStatus({ ok: true, msg: 'Saved' })
      } catch (e) {
        setStatus({ ok: false, msg: e.message })
        return false
      }
    }
    // Autosave into whichever locked calendar is on the preview board -
    // festival list only, day-map untouched.
    if (previewCalendarId != null) {
      try {
        await updateCalendarFestivals(previewCalendarId, {
          clusters: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, festivals: cp.festivals })),
        })
        if (editingTemplate) setStatus({ ok: true, msg: 'Saved to previewed template (live Festival Master unchanged)' })
      } catch (e) {
        setStatus({ ok: false, msg: `Autosave into the previewed template failed: ${e.message}` })
        return false
      }
    }
    return true
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

  // Remove a festival BY NAME from every cluster that has it, in one action -
  // the manual alternative is switching to each of up to 10 cluster tabs and
  // clicking that row's x individually. Exact match after trim + lowercase
  // (a festival name is free text per cluster, so this is the only reliable
  // way to find "the same festival" across clusters - there's no shared id).
  // Goes through the same persist() every other Festival Master edit does,
  // so it inherits the same working-set save + locked-preview autosave.
  async function handleRedactFestival() {
    const name = redactName.trim()
    if (!name) return
    const needle = name.toLowerCase()
    const matches = profiles.filter(cp => cp.festivals.some(f => f.name.trim().toLowerCase() === needle))
    if (!matches.length) {
      setStatus({ ok: false, msg: `"${name}" was not found in any cluster's festival list.` })
      return
    }
    const clusterNames = matches.map(cp => cp.name).join(', ')

    // Also reach every OTHER saved template, not just the one currently
    // loaded - removing a festival here is a "this shouldn't exist
    // anywhere" decision, so it propagates the same way
    // handleSyncStructureToAllTemplates does, just narrower: only strips
    // the named festival from whichever clusters already have it, never
    // replaces or adds anything else in a target's list. Checked BEFORE
    // confirming so the prompt's scope is accurate, not a guess.
    let otherTargets = []
    try {
      const items = await listCalendarLibrary()
      const candidates = items.filter(it => it.id !== previewCalendarId)
      for (const item of candidates) {
        const full = await getCalendar(item.id)
        const hit = (full.clusters || []).some(c => (c.festivals || []).some(f => f.name.trim().toLowerCase() === needle))
        if (hit) otherTargets.push({ id: item.id, name: item.name, clusters: full.clusters || [] })
      }
    } catch {
      // best-effort - a failure here still leaves the live-editor removal available below
    }

    const otherMsg = otherTargets.length
      ? `\n\nAlso found in ${otherTargets.length} other saved template(s): ${otherTargets.map(t => t.name).join(', ')} - removing there too.`
      : ''
    if (!window.confirm(`Remove "${name}" from ${matches.length} cluster(s): ${clusterNames}?${otherMsg}\nThis cannot be undone automatically.`)) {
      return
    }
    const next = profiles.map(cp => ({ ...cp, festivals: cp.festivals.filter(f => f.name.trim().toLowerCase() !== needle) }))
    // Awaited so this handler's own, more specific message can land AFTER
    // persist()'s own "Saved" status - but only on success; a genuine save
    // failure keeps persist()'s own error message on screen instead of being
    // clobbered by a false "Removed" claim.
    const saved = await persist(next)
    if (!saved) return
    setRedactName('')

    let otherUpdated = 0, otherFailed = 0
    for (const t of otherTargets) {
      try {
        const nextClusters = t.clusters.map(c => ({ ...c, festivals: (c.festivals || []).filter(f => f.name.trim().toLowerCase() !== needle) }))
        await updateCalendarFestivals(t.id, { clusters: nextClusters })
        otherUpdated++
      } catch {
        otherFailed++
      }
    }
    const otherPart = otherTargets.length
      ? ` Also removed from ${otherUpdated} other template${otherUpdated === 1 ? '' : 's'}${otherFailed ? `, ${otherFailed} failed` : ''}.`
      : ''
    setStatus({ ok: true, msg: `Removed "${name}" from ${matches.length} cluster(s): ${clusterNames}.${otherPart}` })
  }

  // Applying a bulk festival import (FestivalImportPanel's confirmImport) -
  // same awaited-persist-then-more-specific-message pattern as
  // handleRedactFestival above.
  async function handleImportFestivals(mergedProfiles, message) {
    const saved = await persist(mergedProfiles)
    if (saved) setStatus({ ok: true, msg: message })
  }

  // Rename the active cluster - old app: renameCluster() (calendar_engine.html
  // lines 2197-2206). The trim/"Cluster N" fallback and the uniqueness check
  // live in ClusterTabs (which owns the draft input); by the time this runs the
  // name is already validated.
  //
  // IMPORTANT: cluster name is a join key elsewhere in this system
  // (calendar.store_calendar_clusters.cluster_name and a saved calendar's
  // per-cluster dayMap are both keyed by it), so this has to go through the same
  // persist() -> putClusterProfiles write path as every other profile edit -
  // which it does. Renaming does NOT retro-rewrite those other tables, exactly
  // as in the old app; a renamed cluster loses its store mapping until the
  // Store-Cluster Mapping tab is re-pointed at the new name.
  function handleRename(name) {
    persist(profiles.map((cp, i) => i === activeIdx ? { ...cp, name } : cp))
  }

  // Region selector - old app: setClusterRegion() (calendar_engine.html lines
  // 2151-2154). Only cp.region is written here; the old app's
  // autoApplyRegionalFestivals() side effect is intentionally not ported (see
  // the note in ClusterTabs.jsx).
  function handleRegionChange(region) {
    persist(profiles.map((cp, i) => i === activeIdx ? { ...cp, region } : cp))
  }

  // "Copy from" - old app: copyFromCluster() (calendar_engine.html lines
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

  // "Reset to Defaults" - old app: resetFestivals() (calendar_engine.html lines
  // 2067-2074), which also reset the cluster's nextId to 20 (the DEFAULT_FESTIVALS
  // ids top out at 15). The old app did NOT confirm first; a confirm is added
  // here because this writes straight through to the shared database instead of
  // localStorage, with no undo - the same reasoning FestivalTable's row delete
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
  //
  // `independent` (per row) is the manual-intervention exemption: an island
  // neither pushes its own edits out to other clusters' same-named festival,
  // nor gets overwritten by an edit made on one of them - it stays in the
  // shared cascade for every OTHER festival, this flag only takes ONE row out.
  //
  // It then reaches every saved template too (PUT /festival-window, 2026-09-25:
  // "it should auto sync to every template and every cluster wherever that
  // festival is available") - debounced so typing / repeated +/- clicks send
  // one write, and only after persist() has finished its own writes.
  function handleDayFieldChange(idx, field, value) {
    const editedFest = profiles[activeIdx].festivals[idx]
    const name = editedFest.name
    const editedIsIndependent = !!editedFest.independent
    const saving = persist(profiles.map((cp, ci) => ({
      ...cp,
      festivals: cp.festivals.map((f, fi) => {
        const isEditedRow = ci === activeIdx && fi === idx
        if (isEditedRow) return { ...f, [field]: value }
        if (editedIsIndependent || f.independent) return f
        return f.name === name ? { ...f, [field]: value } : f
      }),
    })))
    if (!isPlanner || editedIsIndependent || !name?.trim() || value === '' || value == null) return
    const pend = windowSync.current
    pend.fields = pend.name === name ? { ...pend.fields, [field]: Number(value) } : { [field]: Number(value) }
    pend.name = name
    pend.saving = saving
    clearTimeout(pend.timer)
    pend.timer = setTimeout(async () => {
      const { name: n, fields, saving: s } = pend
      pend.name = null
      if (!(await s)) return
      try {
        const r = await syncFestivalWindow({ name: n, ...fields })
        setStatus({ ok: true, msg: `"${n}" window synced - ${r.liveRows} live cluster row(s) and ${r.templateRows} row(s) in ${r.templates.length} template(s)${r.templates.length ? `: ${r.templates.join(', ')}` : ''}. A template's day map updates when it is regenerated (Create Calendar + Lock & Save).` })
      } catch (err) {
        setStatus({ ok: false, msg: `"${n}" changed here, but syncing it to the other templates failed: ${err.message}` })
      }
    }, 700)
  }

  // Toggling the "Independent" exemption itself must never cascade the way
  // handleDayFieldChange does for every other field - it is inherently a
  // per-row property (whether THIS cluster's THIS festival opts out), so
  // this only ever changes the one row clicked.
  const windowSync = useRef({ name: null, fields: {}, timer: null, saving: null })

  function handleIndependentToggle(idx, value) {
    persist(profiles.map((cp, ci) => ci === activeIdx
      ? { ...cp, festivals: cp.festivals.map((f, fi) => fi === idx ? { ...f, independent: value } : f) }
      : cp))
  }

  // Header Pre/Core/Post bulk set - old app: applyHeaderBulk()
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
      pre: 1, core: 1, post: 1, independent: false,
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
      setStatus({ ok: failed === 0, msg: `"${name}" added to "${clusterName}" - ${parts.join(', ')}.` })
    }
  }

  // Sync the CURRENT festival structure (every cluster's full list, as it
  // stands right now in the editor) into every OTHER saved template - the
  // broader sibling of handleFestivalPicked above, which only ever copies
  // ONE newly-added festival. Only a cluster name common to both the live
  // editor and a given target template gets its festival list REPLACED
  // (not merged) - a cluster unique to either side is left untouched, never
  // added or deleted.
  //
  // Re-dates via applyYearToProfiles rather than resolveFestivalDefaults
  // (used above): that function resolves against FESTIVAL_DB's generic
  // default date whenever no exact per-year table entry exists, which would
  // silently discard a deliberately customized date in favour of the
  // generic one. applyYearToProfiles instead falls back to shifting the
  // FESTIVAL'S OWN current day/month onto the target year - and never
  // touches pre/core/post at all - so a customization survives the sync
  // unless a real per-year table entry (the actual festival date for that
  // specific year) overrides it, exactly as intended.
  //
  // Deliberately does NOT touch any target template's locked day-map -
  // matching handleFestivalPicked's own precedent, this only updates the
  // festival list metadata saved alongside each template. Regenerating a
  // template's actual calendar is handleSaveToLoadedTemplate's job, one
  // template at a time (Load & Preview it, then Save Changes).
  async function handleSyncStructureToAllTemplates() {
    if (!isPlanner || syncingStructure) return
    let items
    try {
      items = await listCalendarLibrary()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
      return
    }
    const targets = items.filter(it => it.id !== previewCalendarId)
    if (!targets.length) {
      setStatus({ ok: false, msg: 'No other saved templates to sync to.' })
      return
    }
    const targetNames = targets.map(t => t.name).join(', ')
    if (!window.confirm(
      `Sync current festival structure to ${targets.length} other template(s): ${targetNames}?\n`
      + "This replaces each one's festival list per cluster to match what you have now (dates resolved for their own year) - "
      + 'any customizations unique to those templates will be lost.\nThis cannot be undone automatically.'
    )) return

    setSyncingStructure(true)
    let updated = 0, failed = 0
    const fallback = new Set()
    try {
      await loadFestivalReference()
      for (const item of targets) {
        try {
          const full = await getCalendar(item.id)
          const sync = applyYearToProfiles(profiles, full.refYear, full.futYear)
          sync.fallback.forEach(n => fallback.add(n))
          const resolved = sync.profiles
          const sourceByName = new Map(resolved.map(cp => [cp.name, cp]))
          const nextClusters = (full.clusters || []).map(tc => {
            const source = sourceByName.get(tc.name)
            return source ? { ...tc, festivals: source.festivals } : tc
          })
          await updateCalendarFestivals(item.id, { clusters: nextClusters })
          updated++
        } catch {
          failed++
        }
      }
      setStatus({
        ok: failed === 0,
        msg: `Synced festival structure to ${updated} template${updated === 1 ? '' : 's'}${failed ? `, ${failed} failed` : ''}: ${targetNames}.`
          + (fallback.size ? ` WARNING: not in Google reference, used built-in table: ${[...fallback].join(', ')}.` : ''),
      })
    } finally {
      setSyncingStructure(false)
    }
  }

  // Server-side festival_dates sync (same job as the 05:00 run_all): refreshes
  // the Google reference cache, then re-dates the live Festival Master (for
  // app_state's years) and every locked calendar's festival list (its own
  // years) - dates only, never pre/core/post or any day-map. Reloads profiles
  // afterwards so the table on screen shows what the server wrote.
  async function handleSyncFestivalDates() {
    if (!isPlanner || syncingDates) return
    setSyncingDates(true)
    try {
      const { changes, reference_rows } = await syncFestivalReference()
      await loadFestivalReference()
      // A Load & Preview'd template on screen is that calendar's clusters, not
      // the live set - swapping the live set in would autosave it INTO the template.
      if (!editingTemplate) {
        const { profiles: fresh } = await getClusterProfiles()
        if (fresh.length) setProfiles(fresh)
      }
      const lines = changes.map(c => `${c.scope} / ${c.cluster}: ${c.festival} ${c.field === 'ref_date' ? 'ref' : 'fut'} ${c.old} -> ${c.new}`)
      setStatus({ ok: true, msg: `Festival dates synced from Google (${reference_rows} reference dates) · ${changes.length} date${changes.length === 1 ? '' : 's'} changed`
        + (editingTemplate ? ' - Load & Preview the template again to see its new dates' : '') })
      setDateSyncChanges(lines)
    } catch (e) {
      setStatus({ ok: false, msg: `Festival date sync failed: ${e.message}` })
    } finally {
      setSyncingDates(false)
    }
  }

  if (!profiles.length) return <div className="module-panel">Loading...</div>

  return (
    <div className="module-panel" style={{ display: 'flex', gap: '16px' }}>
      <main style={{ flex: 1 }}>
        {/* Festival Master card chrome - ported from calendar_engine.html lines
            760-826. The header (title + count pill + caret) collapses .fest-body,
            which spans the cluster tabs, the rename/region/copy rows, the
            festival table and the footer action bar - the same scope
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
              {/* Redact a festival by name from EVERY cluster in one action -
                  the manual alternative is switching to each of up to 10
                  cluster tabs and deleting that row individually. Cross-cluster
                  (not scoped to activeIdx), so it lives here rather than inside
                  FestivalTable, which only ever edits the active cluster. */}
              {/* Both cross-cluster actions (redact-by-name and push-to-all-templates)
                  in one toolbar row so every button here sits in one place instead of
                  wrapping onto its own line. */}
              {isPlanner && (
                <div className="scm-toolbar" style={{ margin: '10px 0', flexWrap: 'wrap' }}>
                  <div className="field">
                    <label htmlFor="fest-redact-name">Remove festival from all clusters</label>
                    <input id="fest-redact-name" type="text" style={{ width: '220px' }}
                      placeholder="Exact festival name" value={redactName}
                      onChange={e => setRedactName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRedactFestival() }} />
                  </div>
                  <button className="btn" onClick={handleRedactFestival} disabled={!redactName.trim()}>
                    Remove from All Clusters
                  </button>
                  {/* Push the CURRENT full festival structure out to every other
                      saved template, each re-dated for its own reference/future
                      year - see handleSyncStructureToAllTemplates for exactly
                      what this does and doesn't touch (festival lists only,
                      never a target's locked day-map). */}
                  <button className="btn" onClick={handleSyncStructureToAllTemplates} disabled={syncingStructure}
                    title="Replace every other saved template's festival list per cluster with the current structure, dates resolved for each template's own year">
                    {syncingStructure ? 'Syncing...' : 'Sync Festival Structure to All Templates'}
                  </button>
                  <button className="btn" onClick={handleSyncFestivalDates} disabled={syncingDates}
                    title="Refresh festival dates from Google's Holidays in India calendar, then re-date the Festival Master and every locked calendar's festival list for its own years (dates only)">
                    {syncingDates ? 'Syncing...' : 'Sync festival dates (Google)'}
                  </button>
                  {/* Bulk festival-to-cluster import, modeled on Store-Cluster
                      Mapping's own upload+diff-preview flow - see
                      FestivalImportPanel for why this is an upsert per
                      (festival, cluster) row, never a full replace. */}
                  <FestivalImportPanel profiles={profiles} onApply={handleImportFestivals} isPlanner={isPlanner} />
                </div>
              )}
              {dateSyncChanges && (
                <details open style={{ margin: '0 0 10px', fontSize: '12px' }}>
                  <summary>
                    Google date sync: {dateSyncChanges.length} change{dateSyncChanges.length === 1 ? '' : 's'}{' '}
                    <button className="btn" onClick={() => setDateSyncChanges(null)}>Dismiss</button>
                  </summary>
                  {dateSyncChanges.length
                    ? <ul style={{ maxHeight: '200px', overflowY: 'auto', margin: '6px 0' }}>{dateSyncChanges.map((l, i) => <li key={i}>{l}</li>)}</ul>
                    : <p style={{ margin: '6px 0' }}>All festival dates already matched the reference.</p>}
                </details>
              )}
              <FestivalTable festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange}
                onAdd={handleAddFestival} onReset={handleResetFestivals} onBulkSet={handleHeaderBulk}
                onDayFieldChange={handleDayFieldChange} onIndependentToggle={handleIndependentToggle} onFestivalPicked={handleFestivalPicked} isPlanner={isPlanner}
                refYear={refYear} futYear={futYear} />
            </div>
          )}
        </div>

        <div className="card">
          <div style={{ fontSize: '11px', color: 'var(--muted)', margin: '0 0 12px' }}>
            Reference Year {refYear ?? '-'} -&gt; Future Year {futYear ?? '-'} (set on the Version Setting tab)
          </div>
          <button className="btn" onClick={runEngine}>Create Calendar</button>
          {/* One-click overwrite of whichever locked template is currently
              loaded (see previewCalendarId/Name) - only shown when one
              actually is, since there's nothing to overwrite otherwise. */}
          {isPlanner && previewCalendarId != null && (
            <button className="btn" onClick={handleSaveToLoadedTemplate} disabled={savingToTemplate}
              style={{ marginLeft: '8px' }} title={`Regenerate and overwrite "${previewCalendarName}" with your current festival changes`}>
              {savingToTemplate ? 'Saving...' : `Save Changes to "${previewCalendarName}"`}
            </button>
          )}
          {engineStatus && <p style={{ color: engineStatus.ok ? 'var(--green)' : 'var(--red)' }}>{engineStatus.msg}</p>}
        </div>

        <OutputSection dayMap={dayMap} allDayMap={allDayMap} validationIssues={validationIssues} monthlySummary={monthlySummary} />

        {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
      </main>

      <aside style={{ width: '320px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <CalendarLibrary onLoad={handleLoadFromLibrary}
          onSaved={(id, name) => { setPreviewCalendarId(id); setPreviewCalendarName(name) }}
          isPlanner={isPlanner} buildSavePayload={buildSavePayload} />
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
