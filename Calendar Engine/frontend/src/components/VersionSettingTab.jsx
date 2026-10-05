import { useState, useEffect } from 'react'
import { getAppState, putAppState, getClusterProfiles, putClusterProfiles } from '../lib/api'
import { applyYearToProfiles, yearSyncMessage, loadFestivalReference } from '../lib/festivalData'
import FestivalDatesCard from './FestivalDatesCard'

// The seven mapping-type strings `lib/engine.js`'s scoreMapping() actually
// assigns to `mappingType` (see its `mtype = ...` branches) - these are the
// exact values the Day-by-Day table's "Mapping Type" column renders, so the
// legend has to list them verbatim to be useful.
//
// This replaces an earlier invented list ('Exact Match', 'Nearest Weekday',
// 'Cross-Month Shift', 'Regional Override', 'Fallback Assignment', 'Manual
// Override', 'Repaired (Excessive Shift)') - none of which the engine has ever
// emitted, making the legend actively misleading. Descriptions are ported from
// the old app's Mapping Type Reference card (calendar_engine.html lines
// 581-591).
// 2026-09-24: shown as each engine version's actual priority order (engine.js
// _v1Core / _v2Remap), not a flat list - [mapping-type badge, what it means].
const FESTIVE_STEPS = [
  ['Festival-to-Festival', 'festival day -> the same festival day'],
  ['Festive Relative Day', 'same position in the festival window (pre/core/post)'],
]
const SAME_MONTH_STEPS = [
  ['Same Month + Same Weekday', 'unused day, same weekday'],
  ['Same Month + Same Day Type', 'unused day, weekend<->weekend / weekday<->weekday'],
  ['Same Month + Nearest Weekday', 'unused day, nearest date'],
]
const PRIORITY = {
  1: [...FESTIVE_STEPS, ...SAME_MONTH_STEPS,
      ['Nearest Available Date (Same-Month Reuse)', "month's days used up - reuse the nearest same-month day"]],
  2: [...FESTIVE_STEPS, ...SAME_MONTH_STEPS,
      [null, "month's days used up - unused day from the adjacent month (Month Priority direction first), non-festive days only"]],
}
const PRIORITY_NOTE = {
  1: 'Non-festive days never leave their month, so a short month reuses a last-year day.',
  2: 'No last-year day is ever used twice.',
}
// V1 = same month only, reuses a day when a month runs short; V2 = never
// reuses, borrows the adjacent month instead (user decision 2026-09-25 - both
// kept as distinct options; see engine.js _v1Core / _v2Remap).

// Ported from calendar_engine.html lines 573-577. The swatch colours are the
// same --pre-*/--core-*/--post-* tokens the Day-by-Day badges use, so the
// legend and the table agree; a previous version used --navy3/--navy/--muted/
// --border, which matched nothing on screen.
const CATEGORY_LEGEND = [
  ['var(--pre-bg)', 'var(--pre-border)', 'Pre-Festive', 'build-up window before festival'],
  ['var(--core-bg)', 'var(--core-border)', 'Core Festive', 'primary festival days'],
  ['var(--post-bg)', 'var(--post-border)', 'Post-Festive', 'tail window after festival'],
  ['var(--light)', 'var(--border)', 'Non-Festive', 'same weekday, else weekend↔weekend / weekday↔weekday, same month first'],
]

// Max Date Shift and Month Priority are no longer user-editable (user decision
// 2026-09-25): the version setting's month rules already bound every shift,
// and a maxShift above getWeights().dayType (50) would let nearest-date beat
// the weekend/weekday rule. Both stay as stored app_state values (45 / 'prev')
// that the engine keeps reading; moPri is loaded only to label the V2 step.
export default function VersionSettingTab({ isPlanner, onNavigate }) {
  const [refYear, setRefYear] = useState('')
  const [futYear, setFutYear] = useState('')
  const [moPri, setMoPri] = useState('prev')
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getAppState().then(s => {
      if (s.refYear) setRefYear(s.refYear)
      if (s.futYear) setFutYear(s.futYear)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  async function save(partial) {
    if (!isPlanner) return
    try {
      await putAppState(partial)
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  // "Create Calendar" - the old app had this button on this tab
  // (calendar_engine.html lines 2922-2938, createCalendar()); the React port
  // dropped it, leaving this tab with no way to act on a year change at all.
  //
  // VersionSettingTab does not own the cluster profiles (CalendarisationTab
  // does), so this fetches them, re-syncs every cluster's every festival to the
  // configured years via applyYearToProfiles(), writes them back, and then hands
  // over to the Calendarisation tab - which remounts and re-fetches, so it opens
  // showing the freshly re-synced dates.
  //
  // Deviation from the old app: it does NOT auto-run the engine on arrival. The
  // engine lives in CalendarisationTab's own state and isn't reachable from here
  // without lifting that whole state up. The user lands on Calendarisation with
  // correct dates already applied and clicks its "Create Calendar" - one extra
  // click, no correctness difference.
  async function createCalendar() {
    if (!isPlanner || busy) return
    const ry = Number(refYear), fy = Number(futYear)
    if (!ry || !fy || ry < 1900 || ry > 2099 || fy < 1900 || fy > 2099) {
      setStatus({ ok: false, msg: 'Years must be between 1900 and 2099.' })
      return
    }
    if (ry === fy) {
      setStatus({ ok: false, msg: 'Reference and Future year must be different.' })
      return
    }
    setBusy(true)
    try {
      // Save the years first: the inputs persist on blur, and clicking this
      // button fires blur and click as two independent async saves. Writing them
      // here explicitly means the years are stored before the profiles are
      // rewritten, whatever order those land in.
      await putAppState({ refYear: ry, futYear: fy })
      const { profiles } = await getClusterProfiles()
      await loadFestivalReference()
      const sync = applyYearToProfiles(profiles || [], ry, fy)
      await putClusterProfiles({
        profiles: sync.profiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
      })
      setStatus({ ok: true, msg: yearSyncMessage(ry, fy, sync.updated, sync.estimated, sync.fallback) })
      if (onNavigate) onNavigate('calendarisation')
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="module-panel">
      <div className="card">
        <div className="card-label">Calendar Years</div>
        <div className="field-row">
          <div className="field">
            <label>Reference Year</label>
            <input type="number" className="year-input" value={refYear} disabled={!isPlanner}
              onChange={e => setRefYear(e.target.value)}
              onBlur={() => save({ refYear })} />
          </div>
          <div style={{ fontSize: '18px', color: 'var(--muted)', alignSelf: 'flex-end', paddingBottom: '4px' }}>-&gt;</div>
          <div className="field">
            <label>Future Year</label>
            <input type="number" className="year-input" value={futYear} disabled={!isPlanner}
              onChange={e => setFutYear(e.target.value)}
              onBlur={() => save({ futYear })} />
          </div>
        </div>
        <div style={{ marginTop: '12px' }}>
          <button className="btn" onClick={createCalendar} disabled={!isPlanner || busy}>
            {busy ? 'Updating dates...' : 'Create Calendar'}
          </button>
          <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '6px' }}>
            Re-syncs every cluster's festival dates to the years above using the multi-year
            festival date table, then opens the Calendarisation tab.
          </div>
        </div>
      </div>

      <FestivalDatesCard refYear={refYear} futYear={futYear} />

      <div className="card">
        <div className="card-label">Festive Category Legend</div>
        <div className="legend">
          {CATEGORY_LEGEND.map(([bg, border, name, desc]) => (
            <div className="leg-item" key={name}>
              <div className="leg-dot" style={{ background: bg, border: `1px solid ${border}` }} />
              <span>{name} - {desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-label">Mapping Priority Order</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', fontSize: '11px', color: 'var(--muted)' }}>
          {[1, 2].map(v => (
            <div key={v} style={{ flex: '1 1 320px' }}>
              <div style={{ fontWeight: 700, color: 'var(--navy)', marginBottom: '6px' }}>
                V{v} - {v === 1 ? 'same month only' : 'same month, then adjacent month'}
              </div>
              <ol style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                {PRIORITY[v].map(([type, desc], i) => (
                  <li key={i}>{type
                    ? <span className="b-map">{type}</span>
                    : <><span className="b-map">{moPri === 'next' ? 'Next' : 'Previous'} Month + Same Weekday</span> / <span className="b-map">{moPri === 'next' ? 'Previous' : 'Next'} Month + Same Weekday</span></>} {desc}</li>
                ))}
              </ol>
              <div style={{ marginTop: '6px', fontStyle: 'italic' }}>{PRIORITY_NOTE[v]}</div>
            </div>
          ))}
        </div>
      </div>

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
